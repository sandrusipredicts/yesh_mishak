import logging
from typing import Any

import jwt
from fastapi import HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token

from app.core.config import get_settings
from app.db.supabase import get_supabase_service_role_client
from app.errors import raise_api_error

logger = logging.getLogger(__name__)


def _token_debug_claims(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        return {
            "decode_failed": True,
        }

    return {
        "has_sub": bool(claims.get("sub")),
        "has_name": bool(claims.get("name")),
        "email_present": bool(claims.get("email")),
        "email_verified_present": claims.get("email_verified") is not None,
    }

from datetime import datetime, timezone

def verify_google_token(token: str, attempt_id: str = "unknown") -> dict[str, Any]:
    settings = get_settings()
    logger.info(
        "google token verification started",
        extra={
            "event": "auth.google_token.verify.start",
            "auth_method": "google",
            "attempt_id": attempt_id,
        },
    )

    try:
        token_info = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.allowed_google_client_ids,
        )
    except Exception as exc:
        logger.exception(
            "google token verification failed "
            "exception_type=%s "
            "exception_message=%r "
            "allowed_audiences=%r "
            "server_utc=%s",
            type(exc).__name__,
            str(exc),
            settings.allowed_google_client_ids,
            datetime.now(timezone.utc).isoformat(),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc

    email_claim = token_info.get("email")
    subject_claim = token_info.get("sub")
    email_verified = token_info.get("email_verified")
    email = email_claim.strip().lower() if isinstance(email_claim, str) else ""
    google_sub = subject_claim.strip() if isinstance(subject_claim, str) else ""

    if not email or not google_sub:
        logger.warning(
            "google token required claims missing",
            extra={
                "event": "auth.login.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "status_code": status.HTTP_401_UNAUTHORIZED,
                "error_code": "AUTH_INVALID",
                "email_present": bool(email),
                "has_sub": bool(google_sub),
                "has_name": bool(token_info.get("name")),
                "result": "failure",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    if email_verified is not True:
        logger.warning(
            "google token email not verified",
            extra={
                "event": "auth.login.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "status_code": status.HTTP_403_FORBIDDEN,
                "error_code": "EMAIL_NOT_VERIFIED",
                "email_verified_value": email_verified,
                "result": "failure",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Google email address is not verified",
        )

    name = token_info.get("name") or email.split("@", maxsplit=1)[0]
    logger.info(
        "google token verified",
        extra={
            "event": "auth.google_token.verify.success",
            "auth_method": "google",
            "attempt_id": attempt_id,
            "has_sub": bool(google_sub),
            "has_name": bool(token_info.get("name")),
            "result": "success",
        },
    )

    return {
        "google_sub": google_sub,
        "email": email,
        "name": name,
        "picture": token_info.get("picture"),
    }


def find_or_create_google_user(google_user: dict[str, Any], attempt_id: str = "unknown") -> dict[str, Any]:
    service_client = get_supabase_service_role_client()
    logger.info(
        "resolving Google identity",
        extra={
            "event": "auth.google_identity.resolve.start",
            "auth_method": "google",
            "attempt_id": attempt_id,
        },
    )

    try:
        response = service_client.rpc(
            "resolve_google_login",
            {
                "p_provider_subject": google_user["google_sub"],
                "p_email": google_user["email"],
                "p_name": google_user["name"],
                "p_picture": google_user.get("picture"),
            },
        ).execute()
    except Exception as exc:
        logger.exception(
            "Google identity resolution failed",
            extra={
                "event": "auth.google_identity.resolve.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "error_code": "DATABASE_ERROR",
                "exception_type": exc.__class__.__name__,
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to resolve Google identity",
        )

    row = response.data[0] if isinstance(response.data, list) and response.data else None
    result = row.get("result") if isinstance(row, dict) else None
    user_id = row.get("user_id") if isinstance(row, dict) else None

    if result == "account_link_required":
        logger.warning(
            "Google login requires explicit account linking",
            extra={
                "event": "auth.login.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "status_code": status.HTTP_409_CONFLICT,
                "error_code": "ACCOUNT_LINK_REQUIRED",
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="ACCOUNT_LINK_REQUIRED",
            message=(
                "An account with this email already exists. Sign in with the existing "
                "method, then connect Google from Settings."
            ),
        )

    if result not in {"existing", "created"} or not user_id:
        logger.error(
            "Google identity resolver returned an invalid result",
            extra={
                "event": "auth.google_identity.resolve.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "resolver_result": result,
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="IDENTITY_DATA_CONFLICT",
            message="Google identity data requires administrator review",
        )

    try:
        user_response = (
            service_client.table("users")
            .select("id,email,name,google_sub,username,phone_number,password_hash,email_verified,terms_accepted_at")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.exception(
            "Resolved Google user lookup failed",
            extra={
                "event": "auth.google_user.lookup.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "user_id": user_id,
                "exception_type": exc.__class__.__name__,
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to load the linked user",
        )

    if not user_response.data:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="IDENTITY_DATA_CONFLICT",
            message="The linked application user does not exist",
        )

    user = user_response.data[0]
    logger.info(
        "Google identity resolved",
        extra={
            "event": "auth.google_identity.resolve.success",
            "auth_method": "google",
            "attempt_id": attempt_id,
            "user_id": user_id,
            "resolution": result,
            "result": "success",
        },
    )
    return user
