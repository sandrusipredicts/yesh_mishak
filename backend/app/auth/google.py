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
    except Exception as exc:
        return {
            "decode_error": str(exc),
            "token_length": len(token),
        }

    return {
        "aud": claims.get("aud"),
        "iss": claims.get("iss"),
        "email": claims.get("email"),
        "email_verified": claims.get("email_verified"),
        "has_sub": bool(claims.get("sub")),
        "has_name": bool(claims.get("name")),
        "iat": claims.get("iat"),
        "exp": claims.get("exp"),
        "token_length": len(token),
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
            "google_login[%s] optional user debug lookup failed for email=%s error=%r",
            attempt_id,
            email,
            exc,
        )
        return

    if not debug_response.data:
        logger.info("google_login[%s] optional user debug lookup found no row for email=%s", attempt_id, email)
        return

    user = debug_response.data[0]
    logger.info(
        "google_login[%s] optional user debug row id=%s email=%s has_google_sub=%s username_is_null=%s phone_is_null=%s has_password_hash=%s last_login_is_null=%s",
        attempt_id,
        user.get("id"),
        user.get("email"),
        bool(user.get("google_sub")),
        user.get("username") is None,
        user.get("phone_number") is None,
        bool(user.get("password_hash")),
        user.get("last_login") is None,
    )


def verify_google_token(token: str, attempt_id: str = "unknown") -> dict[str, Any]:
    settings = get_settings()
    logger.info("google_login[%s] token received claims=%s", attempt_id, _token_debug_claims(token))

    try:
        token_info = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        logger.warning(
            "google_login[%s] returning 401 during Google token verification error=%r claims=%s",
            attempt_id,
            exc,
            _token_debug_claims(token),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc

    email = token_info.get("email")
    google_sub = token_info.get("sub")

    if not email or not google_sub:
        logger.warning(
            "google_login[%s] returning 401 because required claims are missing email=%s has_sub=%s verified_claims=%s",
            attempt_id,
            email,
            bool(google_sub),
            {
                "aud": token_info.get("aud"),
                "iss": token_info.get("iss"),
                "email": token_info.get("email"),
                "email_verified": token_info.get("email_verified"),
                "has_sub": bool(token_info.get("sub")),
                "has_name": bool(token_info.get("name")),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    name = token_info.get("name") or email.split("@", maxsplit=1)[0]
    logger.info(
        "google_login[%s] token verified email=%s has_sub=%s has_name=%s using_name=%s",
        attempt_id,
        email,
        bool(google_sub),
        bool(token_info.get("name")),
        name,
    )

    return {
        "google_sub": google_sub,
        "email": email,
        "name": name,
        "picture": token_info.get("picture"),
    }


def find_or_create_google_user(google_user: dict[str, Any], attempt_id: str = "unknown") -> dict[str, Any]:
    supabase = get_supabase_client()
    email = google_user["email"]
    logger.info(
        "google_login[%s] looking up existing user by email=%s google_sub_present=%s",
        attempt_id,
        email,
        bool(google_user.get("google_sub")),
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
        logger.exception("google_login[%s] Supabase users select failed: %s", attempt_id, error)
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
            "google_login[%s] existing user found id=%s email=%s name_present=%s",
            attempt_id,
            user.get("id"),
            user.get("email"),
            bool(user.get("name")),
        )
        _log_google_user_lookup_debug(email, attempt_id)
        return existing_user.data[0]

    logger.info("google_login[%s] no existing user found; creating Google user email=%s", attempt_id, email)
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
        logger.exception("google_login[%s] Supabase users insert failed: %s", attempt_id, error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "DB insert failure",
                "supabase_error": error,
                "hint": "Check SUPABASE_KEY permissions, users table RLS policies, required columns, and unique constraints for email/google_sub.",
            },
        ) from exc

    if not created_user.data:
        logger.error("google_login[%s] user insert returned no rows email=%s", attempt_id, email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "DB insert failure",
                "supabase_error": "Insert returned no user rows",
                "hint": "If insert succeeded but returns no data, check Supabase/PostgREST return settings and table policies.",
            },
        )

    logger.info(
        "google_login[%s] created Google user id=%s email=%s",
        attempt_id,
        created_user.data[0].get("id"),
        created_user.data[0].get("email"),
    )
    _log_google_user_lookup_debug(email, attempt_id)
    return created_user.data[0]
