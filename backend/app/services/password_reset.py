from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import secrets
from typing import Any

from fastapi import status

from app.auth.dependencies import invalidate_cached_user
from app.auth.passwords import hash_password, validate_password
from app.core.config import get_settings
from app.db.supabase import get_supabase_service_role_client
from app.errors import raise_api_error
from app.services.email_delivery import EmailDeliveryResult, ResendEmailDelivery
from app.services.password_reset_email import build_password_reset_email

logger = logging.getLogger(__name__)

GENERIC_PASSWORD_RESET_MESSAGE = "If an eligible account exists, password reset instructions will be sent."


class PasswordResetRateLimited(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class PasswordResetRequestResult:
    message: str = GENERIC_PASSWORD_RESET_MESSAGE


class PasswordResetService:
    def __init__(
        self,
        *,
        email_delivery: ResendEmailDelivery | None = None,
        supabase_client: Any | None = None,
    ) -> None:
        self.email_delivery = email_delivery or ResendEmailDelivery()
        self.supabase = supabase_client or get_supabase_service_role_client()

    def request_password_reset(self, *, email: str, client_ip: str) -> PasswordResetRequestResult:
        self._check_rate_limit(email=email, client_ip=client_ip)

        user = self._find_eligible_password_user(email)
        if user is None:
            logger.info(
                "password reset request completed generically",
                extra={"event": "auth.password_reset.request.generic"},
            )
            return PasswordResetRequestResult()

        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_reset_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=get_settings().password_reset_token_ttl_minutes
        )

        self._create_reset_token(
            user_id=str(user["id"]),
            token_hash=token_hash,
            expires_at=expires_at,
        )

        reset_url = self._build_reset_url(raw_token)
        email_message = build_password_reset_email(
            reset_url,
            get_settings().password_reset_token_ttl_minutes,
        )
        delivery_result = self.email_delivery.send_email(
            to_email=user["email"],
            subject=email_message.subject,
            html_body=email_message.html_body,
            text_body=email_message.text_body,
        )
        self._record_delivery_result(token_hash, delivery_result)

        logger.info(
            "password reset request completed for eligible account",
            extra={
                "event": "auth.password_reset.request.eligible",
                "user_id": str(user["id"]),
                "delivery_accepted": delivery_result.accepted,
            },
        )
        return PasswordResetRequestResult()

    def confirm_password_reset(
        self,
        *,
        token: str,
        password: str,
        password_confirm: str,
    ) -> dict[str, str]:
        if password != password_confirm:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Passwords do not match",
            )

        password_errors = validate_password(password)
        if password_errors:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message=password_errors[0],
            )

        token_hash = self.hash_reset_token(token)
        new_password_hash = hash_password(password)
        tokens_valid_after = datetime.now(timezone.utc)

        response = self.supabase.rpc(
            "consume_password_reset_token",
            {
                "p_token_hash": token_hash,
                "p_password_hash": new_password_hash,
                "p_tokens_valid_after": tokens_valid_after.isoformat(),
            },
        ).execute()
        result = self._first_rpc_row(response.data)
        status_result = result.get("result") if result else "invalid"
        user_id = result.get("user_id") if result else None

        if status_result == "success":
            if user_id:
                invalidate_cached_user(str(user_id))
            logger.info(
                "password reset confirmed",
                extra={
                    "event": "auth.password_reset.confirm.success",
                    "user_id": str(user_id) if user_id else None,
                },
            )
            return {"message": "Password reset successfully"}

        if status_result == "expired":
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="RESET_TOKEN_EXPIRED",
                message="Password reset link has expired",
            )
        if status_result == "consumed":
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="RESET_TOKEN_CONSUMED",
                message="Password reset link has already been used",
            )

        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="RESET_TOKEN_INVALID",
            message="Password reset link is invalid",
        )
        return {"message": "Password reset failed"}

    @classmethod
    def hash_reset_token(cls, raw_token: str) -> str:
        secret = get_settings().password_reset_token_secret
        if not secret:
            raise_api_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="INTERNAL_SERVER_ERROR",
                message="Password reset is not configured",
            )
        return hmac.new(
            secret.encode("utf-8"),
            raw_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @classmethod
    def hash_rate_limit_value(cls, purpose: str, value: str) -> str:
        secret = get_settings().password_reset_token_secret
        if not secret:
            raise_api_error(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="INTERNAL_SERVER_ERROR",
                message="Password reset is not configured",
            )
        return hmac.new(
            secret.encode("utf-8"),
            f"{purpose}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _check_rate_limit(self, *, email: str, client_ip: str) -> None:
        email_key = self.hash_rate_limit_value("email-rate-limit", email)
        ip_key = self.hash_rate_limit_value("ip-rate-limit", client_ip)
        response = self.supabase.rpc(
            "check_password_reset_rate_limit",
            {
                "p_email_key": email_key,
                "p_ip_key": ip_key,
                "p_now": datetime.now(timezone.utc).isoformat(),
            },
        ).execute()
        result = self._first_rpc_row(response.data)
        if not result:
            return
        if result.get("allowed") is False:
            raise PasswordResetRateLimited(int(result.get("retry_after_seconds") or 60))

    def _find_eligible_password_user(self, email: str) -> dict[str, Any] | None:
        response = (
            self.supabase.table("users")
            .select("id,email,password_hash,status")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        user = response.data[0]
        if not user.get("password_hash"):
            return None
        if user.get("status", "active") != "active":
            return None
        return user

    def _create_reset_token(self, *, user_id: str, token_hash: str, expires_at: datetime) -> None:
        self.supabase.rpc(
            "create_password_reset_token",
            {
                "p_user_id": user_id,
                "p_token_hash": token_hash,
                "p_expires_at": expires_at.isoformat(),
            },
        ).execute()

    def _record_delivery_result(
        self,
        token_hash: str,
        delivery_result: EmailDeliveryResult,
    ) -> None:
        if delivery_result.accepted:
            payload = {
                "status": "active",
                "delivery_status": "sent",
            }
        else:
            payload = {
                "status": "delivery_failed",
                "delivery_status": "failed",
                "invalidated_at": datetime.now(timezone.utc).isoformat(),
            }
        self.supabase.table("password_reset_tokens").update(payload).eq(
            "token_hash",
            token_hash,
        ).execute()

    def _build_reset_url(self, raw_token: str) -> str:
        base_url = get_settings().public_web_base_url.rstrip("/")
        return f"{base_url}/reset-password?token={raw_token}"

    @staticmethod
    def _first_rpc_row(data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                return first
        return {}
