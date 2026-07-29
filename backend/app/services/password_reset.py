from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import logging
import secrets
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException, status

from app.auth.dependencies import invalidate_cached_user
from app.auth.passwords import hash_password, validate_password
from app.core.config import get_settings
from app.db.supabase import get_supabase_service_role_client
from app.errors import error_response, raise_api_error
from app.services.authentication_audit_events import record_token_revocation_event
from app.services.authentication_observability import safe_auth_log, safe_auth_monitor
from app.services.email_delivery import ResendEmailDelivery
from app.services.password_reset_email import build_password_reset_email
from app.services.postgrest_mutation_outcomes import (
    execute_postgrest_mutation,
    observe_ambiguous_mutation,
)

logger = logging.getLogger(__name__)

GENERIC_PASSWORD_RESET_MESSAGE = "If an eligible account exists, password reset instructions will be sent."


class PasswordResetRateLimited(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class PasswordResetRequestResult:
    message: str = GENERIC_PASSWORD_RESET_MESSAGE
    delivery_job: PasswordResetDeliveryJob | None = None


@dataclass(frozen=True)
class PasswordResetDeliveryJob:
    token_hash: str
    raw_token: str
    recipient_email: str


class PasswordResetService:
    def __init__(
        self,
        *,
        email_delivery: ResendEmailDelivery | None = None,
        supabase_client: Any | None = None,
    ) -> None:
        self.email_delivery = email_delivery or ResendEmailDelivery()
        if supabase_client is not None:
            self.supabase = supabase_client
            return

        service_client = None
        client_initialization_failed = False
        try:
            service_client = get_supabase_service_role_client()
        except Exception:  # noqa: BLE001 - sanitize client/configuration diagnostics
            client_initialization_failed = True
        if client_initialization_failed or service_client is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_response(
                    code="INTERNAL_SERVER_ERROR",
                    message="Password reset could not be completed",
                ),
            )
        self.supabase = service_client

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
        self._create_reset_token(
            user_id=str(user["id"]),
            token_hash=token_hash,
        )

        logger.info(
            "password reset request completed for eligible account",
            extra={
                "event": "auth.password_reset.request.eligible",
                "user_id": str(user["id"]),
            },
        )
        return PasswordResetRequestResult(
            delivery_job=PasswordResetDeliveryJob(
                token_hash=token_hash,
                raw_token=raw_token,
                recipient_email=user["email"],
            )
        )

    def deliver_password_reset(self, job: PasswordResetDeliveryJob) -> None:
        reset_url = self._build_reset_url(job.raw_token)
        email_message = build_password_reset_email(
            reset_url, get_settings().password_reset_token_ttl_minutes
        )
        try:
            delivery_result = self.email_delivery.send_email(
                to_email=job.recipient_email,
                subject=email_message.subject,
                html_body=email_message.html_body,
                text_body=email_message.text_body,
                idempotency_key=f"password-reset-{job.token_hash}",
            )
            accepted = delivery_result.accepted
        except Exception as exc:
            accepted = False
            logger.warning(
                "password reset email delivery failed unexpectedly",
                extra={
                    "event": "auth.password_reset.delivery.unexpected_failure",
                    "exception_type": exc.__class__.__name__,
                },
            )
        response = self.supabase.rpc(
            "finalize_password_reset_delivery",
            {"p_token_hash": job.token_hash, "p_accepted": accepted},
        ).execute()
        result = self._first_rpc_row(response.data)
        logger.info(
            "password reset delivery finalized",
            extra={
                "event": "auth.password_reset.delivery.finalized",
                "delivery_accepted": accepted,
                "activation_result": result.get("result", "unknown"),
            },
        )

    def confirm_password_reset(
        self,
        *,
        token: str,
        password: str,
        password_confirm: str,
        client_ip: str,
    ) -> dict[str, str]:
        token_hash = self.hash_reset_token(token)
        self._check_confirm_rate_limit(token_hash=token_hash, client_ip=client_ip)

        if password != password_confirm:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="Passwords do not match",
            )

        precheck_result: str | None = None
        precheck_failed = False
        try:
            precheck_result = self._precheck_token(token_hash)
        except Exception:  # noqa: BLE001 - sanitize token/database diagnostics
            precheck_failed = True
        if precheck_failed or precheck_result is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_response(
                    code="INTERNAL_SERVER_ERROR",
                    message="Password reset could not be completed",
                ),
            )
        self._raise_for_token_result(precheck_result)

        password_errors = validate_password(password)
        if password_errors:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message=password_errors[0],
            )

        new_password_hash = hash_password(password)

        attempt = execute_postgrest_mutation(
            lambda: self.supabase.rpc(
                "consume_password_reset_token",
                {
                    "p_token_hash": token_hash,
                    "p_password_hash": new_password_hash,
                },
            ).execute(),
            validate_response=self._validated_consume_result,
        )

        if attempt.state == "confirmed_failed":
            record_token_revocation_event(
                outcome="failed",
                auth_method="recovery",
                revocation_reason="password_reset",
                user_id=None,
                failure_category=attempt.failure_category,
            )
        elif attempt.state == "outcome_ambiguous":
            observe_ambiguous_mutation(
                logger,
                auth_method="recovery",
                revocation_reason="password_reset",
                user_id_present=False,
                ambiguity_reason=attempt.ambiguity_reason,
            )

        if attempt.state != "confirmed_succeeded":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_response(
                    code="INTERNAL_SERVER_ERROR",
                    message="Password reset could not be completed",
                ),
            )

        result = cast(dict[str, Any], attempt.response)
        status_result = result["result"]
        user_id = result.get("user_id")

        if status_result == "success":
            record_token_revocation_event(
                outcome="succeeded",
                auth_method="recovery",
                revocation_reason="password_reset",
                user_id=str(user_id) if user_id else None,
            )
            if user_id:
                cache_invalidation_failed = False
                try:
                    invalidate_cached_user(str(user_id))
                except Exception:  # noqa: BLE001 - revocation already committed
                    cache_invalidation_failed = True
                if cache_invalidation_failed:
                    safe_auth_log(
                        logger,
                        "warning",
                        "password reset cache invalidation failed after revocation",
                        extra={
                            "event": "auth.password_reset.cache_invalidation.failure",
                            "auth_method": "recovery",
                            "revocation_reason": "password_reset",
                            "user_id_present": True,
                        },
                    )
                    safe_auth_monitor(
                        "Password reset cache invalidation failed after revocation",
                        level="warning",
                        event="auth.password_reset.cache_invalidation.failure",
                        auth_method="recovery",
                        revocation_reason="password_reset",
                        user_id_present=True,
                    )
            safe_auth_log(
                logger,
                "info",
                "password reset confirmed",
                extra={
                    "event": "auth.password_reset.confirm.success",
                    "auth_method": "recovery",
                    "revocation_reason": "password_reset",
                    "user_id_present": user_id is not None,
                },
            )
            return {"message": "Password reset successfully"}

        self._raise_for_token_result(status_result)

        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="RESET_TOKEN_INVALID",
            message="Password reset link is invalid",
        )
        return {"message": "Password reset failed"}

    @staticmethod
    def _raise_for_token_result(status_result: str) -> None:
        if status_result in {"success", "usable"}:
            return
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

    @staticmethod
    def _validated_consume_result(response: Any) -> dict[str, Any] | None:
        try:
            data = response.data
        except Exception:  # noqa: BLE001 - malformed success is ambiguous
            return None
        if isinstance(data, list):
            if len(data) != 1:
                return None
            row = data[0]
        else:
            row = data
        if not isinstance(row, dict) or set(row) != {"result", "user_id"}:
            return None
        result = row.get("result")
        if result not in {"success", "invalid", "expired", "consumed"}:
            return None
        user_id = row.get("user_id")
        if result == "success" and (not isinstance(user_id, str) or not user_id):
            return None
        if user_id is not None and not isinstance(user_id, str):
            return None
        if user_id is not None:
            try:
                user_id = str(UUID(user_id))
            except (ValueError, AttributeError):
                return None
        return {"result": result, "user_id": user_id}

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
            "check_password_reset_request_rate_limit",
            {
                "p_email_key": email_key,
                "p_ip_key": ip_key,
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

    def _check_confirm_rate_limit(self, *, token_hash: str, client_ip: str) -> None:
        check_failed = False
        try:
            ip_key = self.hash_rate_limit_value("ip-rate-limit", client_ip)
            token_key = self.hash_rate_limit_value(
                "confirm-token-rate-limit",
                token_hash,
            )
            response = self.supabase.rpc(
                "check_password_reset_confirm_rate_limit",
                {"p_token_key": token_key, "p_ip_key": ip_key},
            ).execute()
            result = self._validated_confirm_rate_limit_result(response)
            if result is None:
                check_failed = True
            elif result["allowed"] is False:
                raise PasswordResetRateLimited(result["retry_after_seconds"])
        except PasswordResetRateLimited:
            raise
        except Exception:  # noqa: BLE001 - sanitize rate-limit diagnostics
            check_failed = True

        if not check_failed:
            return

        context = {
            "event": "auth.password_reset.confirm_rate_limit.failure",
            "auth_method": "recovery",
            "revocation_reason": "password_reset",
            "user_id_present": False,
        }
        safe_auth_log(
            logger,
            "warning",
            "password reset confirmation rate-limit check failed",
            extra=context,
        )
        safe_auth_monitor(
            "Password reset confirmation rate-limit check failed",
            level="warning",
            **context,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Password reset could not be completed",
            ),
        ) from None

    @staticmethod
    def _validated_confirm_rate_limit_result(
        response: Any,
    ) -> dict[str, bool | int] | None:
        try:
            data = response.data
        except Exception:  # noqa: BLE001 - malformed response is sanitized
            return None
        if isinstance(data, list):
            if len(data) != 1:
                return None
            row = data[0]
        else:
            row = data
        if not isinstance(row, dict) or not isinstance(row.get("allowed"), bool):
            return None
        retry_after = row.get("retry_after_seconds")
        if row["allowed"] is False:
            if retry_after is None:
                retry_seconds = 60
            elif (
                isinstance(retry_after, int)
                and not isinstance(retry_after, bool)
                and retry_after > 0
            ):
                retry_seconds = retry_after
            else:
                return None
        else:
            retry_seconds = 0
        return {
            "allowed": row["allowed"],
            "retry_after_seconds": retry_seconds,
        }

    def _precheck_token(self, token_hash: str) -> str:
        response = self.supabase.rpc(
            "precheck_password_reset_token", {"p_token_hash": token_hash}
        ).execute()
        result = self._first_rpc_row(response.data)
        return str(result.get("result") or "invalid")

    def _create_reset_token(self, *, user_id: str, token_hash: str) -> None:
        self.supabase.rpc(
            "create_password_reset_token",
            {
                "p_user_id": user_id,
                "p_token_hash": token_hash,
                "p_ttl_minutes": get_settings().password_reset_token_ttl_minutes,
            },
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
