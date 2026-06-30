import logging
from typing import Any

import jwt
from fastapi import HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token

from app.core.config import get_settings
from app.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)


def _format_supabase_error(exc: Exception) -> dict[str, str]:
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "repr": repr(exc),
    }


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


def _log_google_user_lookup_debug(email: str, attempt_id: str) -> None:
    try:
        debug_response = (
            get_supabase_client()
            .table("users")
            .select("id,email,name,google_sub,username,phone_number,password_hash,last_login")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning(
            "google user debug lookup failed",
            extra={
                "event": "auth.google_user_lookup.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "error_code": "DATABASE_ERROR",
                "exception_type": exc.__class__.__name__,
                "result": "failure",
            },
        )
        return

    if not debug_response.data:
        logger.info(
            "google user debug lookup found no row",
            extra={
                "event": "auth.google_user_lookup.not_found",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "result": "not_found",
            },
        )
        return

    user = debug_response.data[0]
    logger.info(
        "google user debug lookup found row",
        extra={
            "event": "auth.google_user_lookup.found",
            "auth_method": "google",
            "attempt_id": attempt_id,
            "user_id": user.get("id"),
            "has_google_sub": bool(user.get("google_sub")),
            "username_is_null": user.get("username") is None,
            "phone_is_null": user.get("phone_number") is None,
            "has_password_hash": bool(user.get("password_hash")),
            "last_login_is_null": user.get("last_login") is None,
            "result": "success",
        },
    )


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
            settings.google_client_id,
        )
    except ValueError as exc:
        logger.warning(
            "google token verification failed",
            extra={
                "event": "auth.login.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "status_code": status.HTTP_401_UNAUTHORIZED,
                "error_code": "AUTH_INVALID",
                "exception_type": exc.__class__.__name__,
                "claim_presence": _token_debug_claims(token),
                "result": "failure",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc

    email = token_info.get("email")
    google_sub = token_info.get("sub")
    email_verified = token_info.get("email_verified")

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


def verify_supabase_google_session(token: str) -> dict[str, Any]:
    try:
        response = get_supabase_client().auth.get_user(token)
        user = response.user
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase session",
        ) from exc

    if not user or not user.email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Supabase session",
        )

    identities = user.identities or []
    google_identity = next(
        (identity for identity in identities if identity.provider == "google"),
        None,
    )
    if google_identity is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Supabase session is not authenticated with Google",
        )

    identity_data = google_identity.identity_data or {}
    google_sub = identity_data.get("sub") or identity_data.get("provider_id") or google_identity.id
    name = (
        identity_data.get("full_name")
        or identity_data.get("name")
        or user.user_metadata.get("full_name")
        or user.user_metadata.get("name")
        or user.email.split("@", maxsplit=1)[0]
    )

    return {
        "google_sub": str(google_sub),
        "email": user.email,
        "name": name,
        "picture": identity_data.get("avatar_url") or identity_data.get("picture"),
    }


def find_or_create_google_user(google_user: dict[str, Any], attempt_id: str = "unknown") -> dict[str, Any]:
    supabase = get_supabase_client()
    email = google_user["email"]
    logger.info(
        "looking up existing Google user",
        extra={
            "event": "auth.google_user.lookup.start",
            "auth_method": "google",
            "attempt_id": attempt_id,
            "google_sub_present": bool(google_user.get("google_sub")),
        },
    )

    try:
        existing_user = (
            supabase.table("users")
            .select("id,email,name")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        error = _format_supabase_error(exc)
        logger.exception(
            "Google user lookup failed",
            extra={
                "event": "auth.google_user.lookup.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "error_code": "DATABASE_ERROR",
                "exception_type": exc.__class__.__name__,
                "result": "failure",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to query user",
                "supabase_error": error,
                "hint": "Check SUPABASE_KEY permissions, users table RLS policies, and that users has id/email/name columns.",
            },
        ) from exc

    if existing_user.data:
        user = existing_user.data[0]
        logger.info(
            "existing Google user found",
            extra={
                "event": "auth.google_user.lookup.success",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "user_id": user.get("id"),
                "name_present": bool(user.get("name")),
                "result": "success",
            },
        )
        _log_google_user_lookup_debug(email, attempt_id)
        return existing_user.data[0]

    logger.info(
        "creating Google user",
        extra={
            "event": "auth.google_user.create.start",
            "auth_method": "google",
            "attempt_id": attempt_id,
        },
    )
    try:
        created_user = (
            supabase.table("users")
            .insert(
                {
                    "google_sub": google_user["google_sub"],
                    "email": google_user["email"],
                    "name": google_user["name"],
                }
            )
            .execute()
        )
    except Exception as exc:
        error = _format_supabase_error(exc)
        logger.exception(
            "Google user insert failed",
            extra={
                "event": "auth.google_user.create.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "error_code": "DATABASE_ERROR",
                "exception_type": exc.__class__.__name__,
                "result": "failure",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "DB insert failure",
                "supabase_error": error,
                "hint": "Check SUPABASE_KEY permissions, users table RLS policies, required columns, and unique constraints for email/google_sub.",
            },
        ) from exc

    if not created_user.data:
        logger.error(
            "Google user insert returned no rows",
            extra={
                "event": "auth.google_user.create.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "error_code": "DATABASE_ERROR",
                "result": "failure",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "DB insert failure",
                "supabase_error": "Insert returned no user rows",
                "hint": "If insert succeeded but returns no data, check Supabase/PostgREST return settings and table policies.",
            },
        )

    logger.info(
        "Google user created",
        extra={
            "event": "auth.google_user.create.success",
            "auth_method": "google",
            "attempt_id": attempt_id,
            "user_id": created_user.data[0].get("id"),
            "result": "success",
        },
    )
    _log_google_user_lookup_debug(email, attempt_id)
    return created_user.data[0]
