from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import logging
import re
from typing import Any, Protocol

from fastapi import HTTPException, status
from postgrest.exceptions import APIError

from app.core.config import get_settings
from app.db.supabase import get_supabase_service_role_client
from app.errors import raise_api_error
from app.rate_limit import get_limiter

logger = logging.getLogger(__name__)

E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
ISRAEL_LOCAL_RE = re.compile(r"^0[2-9]\d{7,8}$")
OTP_RE = re.compile(r"^\d{4,10}$")
PHONE_PROVIDER = "phone"


class PhoneProviderError(Exception):
    def __init__(self, code: str = "PROVIDER_UNAVAILABLE") -> None:
        self.code = code
        super().__init__(code)


class InvalidPhoneOtp(PhoneProviderError):
    def __init__(self) -> None:
        super().__init__("PHONE_OTP_INVALID")


class PhoneVerificationProvider(Protocol):
    def start_otp(self, phone_e164: str) -> None:
        ...

    def verify_otp(self, phone_e164: str, otp: str) -> str:
        ...


class SupabasePhoneVerificationProvider:
    def __init__(self, client: Any | None = None) -> None:
        self.client = client

    def _client(self) -> Any:
        return self.client or get_supabase_service_role_client()

    def start_otp(self, phone_e164: str) -> None:
        try:
            self._client().auth.sign_in_with_otp({"phone": phone_e164})
        except Exception as exc:
            logger.warning(
                "phone OTP provider start failed",
                extra={
                    "event": "auth.phone.provider.start.failure",
                    "error_code": "PROVIDER_UNAVAILABLE",
                    "exception_type": exc.__class__.__name__,
                },
            )
            raise PhoneProviderError() from exc

    def verify_otp(self, phone_e164: str, otp: str) -> str:
        try:
            response = self._client().auth.verify_otp(
                {"phone": phone_e164, "token": otp, "type": "sms"}
            )
        except Exception as exc:
            logger.warning(
                "phone OTP provider verify failed",
                extra={
                    "event": "auth.phone.provider.verify.failure",
                    "error_code": "PHONE_OTP_INVALID",
                    "exception_type": exc.__class__.__name__,
                },
            )
            raise InvalidPhoneOtp() from exc

        provider_user = getattr(response, "user", None)
        verified_phone = getattr(provider_user, "phone", None)
        if not verified_phone and isinstance(response, dict):
            verified_phone = (
                response.get("user", {}).get("phone")
                if isinstance(response.get("user"), dict)
                else None
            )
        if verified_phone != phone_e164:
            raise InvalidPhoneOtp()
        return verified_phone


@dataclass
class PhoneVerificationStartResult:
    message: str
    cooldown_seconds: int


@dataclass
class PhoneVerificationVerifyResult:
    message: str
    phone_number: str


def normalize_phone_number(value: str) -> str:
    compact = re.sub(r"[\s().-]+", "", value.strip())
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if compact.startswith("+"):
        if not E164_RE.match(compact):
            raise ValueError("Phone number must be a valid E.164 number")
        return compact
    if ISRAEL_LOCAL_RE.match(compact):
        return f"+972{compact[1:]}"
    raise ValueError("Phone number must be E.164 or a valid Israeli local number")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_phone(phone_e164: str) -> str:
    settings = get_settings()
    return hmac.new(
        settings.jwt_secret.encode("utf-8"),
        phone_e164.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _masked_phone(phone_e164: str) -> str:
    return f"***{phone_e164[-2:]}"


def _rate_limit_or_raise(key: str, max_requests: int, window_seconds: int) -> None:
    allowed, retry_after = get_limiter().check(key, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": True,
                "code": "RATE_LIMITED",
                "message": "Too many requests. Please try again later.",
            },
            headers={"Retry-After": str(retry_after)},
        )


class PhoneVerificationService:
    def __init__(
        self,
        *,
        provider: PhoneVerificationProvider | None = None,
        supabase_client: Any | None = None,
        resend_cooldown_seconds: int = 60,
    ) -> None:
        self.provider = provider or SupabasePhoneVerificationProvider()
        self.supabase = supabase_client or get_supabase_service_role_client()
        self.resend_cooldown_seconds = resend_cooldown_seconds

    def start(self, *, user: dict[str, Any], phone_number: str) -> PhoneVerificationStartResult:
        user_id = str(user["id"])
        phone_e164 = self._normalize_or_400(phone_number)
        phone_key = _hash_phone(phone_e164)

        _rate_limit_or_raise(f"user:auth_phone_start:{user_id}", 5, 3600)
        _rate_limit_or_raise(f"phone:auth_phone_start:{phone_key}", 3, 3600)
        _rate_limit_or_raise(
            f"user-phone:auth_phone_resend:{user_id}:{phone_key}",
            1,
            self.resend_cooldown_seconds,
        )
        self._ensure_user_can_verify_phone(user_id, phone_e164)

        logger.info(
            "phone verification start requested",
            extra={
                "event": "auth.phone.start",
                "user_id": user_id,
                "phone_hint": _masked_phone(phone_e164),
            },
        )
        try:
            self.provider.start_otp(phone_e164)
        except PhoneProviderError:
            raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="PHONE_PROVIDER_UNAVAILABLE",
                message="Phone verification is temporarily unavailable. Please try again later.",
            )

        return PhoneVerificationStartResult(
            message="If this phone number can be verified, a code will be sent.",
            cooldown_seconds=self.resend_cooldown_seconds,
        )

    def verify(self, *, user: dict[str, Any], phone_number: str, otp: str) -> PhoneVerificationVerifyResult:
        user_id = str(user["id"])
        phone_e164 = self._normalize_or_400(phone_number)
        phone_key = _hash_phone(phone_e164)
        if not OTP_RE.match(otp.strip()):
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="PHONE_OTP_INVALID",
                message="The verification code is invalid or expired.",
            )

        _rate_limit_or_raise(f"user:auth_phone_verify:{user_id}", 10, 3600)
        _rate_limit_or_raise(f"phone:auth_phone_verify:{phone_key}", 10, 3600)
        self._ensure_user_can_verify_phone(user_id, phone_e164)

        try:
            verified_phone = self.provider.verify_otp(phone_e164, otp.strip())
        except InvalidPhoneOtp:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="PHONE_OTP_INVALID",
                message="The verification code is invalid or expired.",
            )
        except PhoneProviderError:
            raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="PHONE_PROVIDER_UNAVAILABLE",
                message="Phone verification is temporarily unavailable. Please try again later.",
            )

        if verified_phone != phone_e164:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="PHONE_OTP_INVALID",
                message="The verification code is invalid or expired.",
            )

        self._record_verified_phone(user_id, phone_e164)
        logger.info(
            "phone verification succeeded",
            extra={
                "event": "auth.phone.verify.success",
                "user_id": user_id,
                "phone_hint": _masked_phone(phone_e164),
            },
        )
        return PhoneVerificationVerifyResult(
            message="Phone number verified.",
            phone_number=phone_e164,
        )

    def _normalize_or_400(self, phone_number: str) -> str:
        try:
            return normalize_phone_number(phone_number)
        except ValueError:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="PHONE_INVALID",
                message="Enter a valid international phone number.",
            )

    def _select_phone_identities(self, phone_e164: str) -> list[dict[str, Any]]:
        response = (
            self.supabase.table("user_identities")
            .select("id,user_id,provider,provider_subject")
            .eq("provider", PHONE_PROVIDER)
            .eq("provider_subject", phone_e164)
            .limit(1)
            .execute()
        )
        return response.data or []

    def _select_user_phone_identities(self, user_id: str) -> list[dict[str, Any]]:
        response = (
            self.supabase.table("user_identities")
            .select("id,user_id,provider,provider_subject")
            .eq("provider", PHONE_PROVIDER)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        return response.data or []

    def _select_user(self, user_id: str) -> dict[str, Any] | None:
        response = (
            self.supabase.table("users")
            .select("id,phone_number,status")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None

    def _ensure_user_can_verify_phone(self, user_id: str, phone_e164: str) -> None:
        user_row = self._select_user(user_id)
        if not user_row or user_row.get("status") in {"banned", "suspended"}:
            raise_api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="ACCOUNT_RESTRICTED",
                message="Account cannot verify a phone number.",
            )

        existing_user_phone = user_row.get("phone_number")
        if existing_user_phone:
            try:
                normalized_existing = normalize_phone_number(existing_user_phone)
            except ValueError:
                normalized_existing = existing_user_phone
            if normalized_existing != phone_e164:
                raise_api_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code="PHONE_CHANGE_NOT_SUPPORTED",
                    message="Phone verification is unavailable for this phone number.",
                )

        identity_for_user = self._select_user_phone_identities(user_id)
        if identity_for_user and identity_for_user[0].get("provider_subject") != phone_e164:
            raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="PHONE_CHANGE_NOT_SUPPORTED",
                message="Phone verification is unavailable for this phone number.",
            )
        if identity_for_user and identity_for_user[0].get("provider_subject") == phone_e164:
            raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="PHONE_ALREADY_VERIFIED",
                message="This phone number is already verified.",
            )

        identity_for_phone = self._select_phone_identities(phone_e164)
        if identity_for_phone and str(identity_for_phone[0].get("user_id")) != user_id:
            raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="PHONE_VERIFICATION_UNAVAILABLE",
                message="Phone verification is unavailable for this phone number.",
            )

    def _record_verified_phone(self, user_id: str, phone_e164: str) -> None:
        now = _now_iso()
        try:
            self.supabase.table("user_identities").insert(
                {
                    "user_id": user_id,
                    "provider": PHONE_PROVIDER,
                    "provider_subject": phone_e164,
                    "phone_verified_at": now,
                }
            ).execute()
            self.supabase.table("users").update({"phone_number": phone_e164}).eq("id", user_id).execute()
        except APIError as exc:
            message = str(exc)
            if "duplicate" in message.lower() or "23505" in message:
                raise_api_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code="PHONE_VERIFICATION_UNAVAILABLE",
                    message="Phone verification is unavailable for this phone number.",
                )
            raise
