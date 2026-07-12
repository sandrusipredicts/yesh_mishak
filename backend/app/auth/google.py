import logging
from datetime import datetime, timezone
from typing import Any

import jwt
from fastapi import HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token

from app.core.config import get_settings
from app.db.supabase import get_supabase_client
from app.errors import raise_api_error

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


def find_or_create_google_user(google_user: dict[str, Any], attempt_id: str = "unknown") -> dict[str, Any]:
    supabase = get_supabase_client()
    email = google_user["email"]
    google_sub = google_user["google_sub"]

    logger.info(
        "looking up existing Google user by subject",
        extra={
            "event": "auth.google_user.lookup.start",
            "auth_method": "google",
            "attempt_id": attempt_id,
            "google_sub_present": bool(google_sub),
        },
    )

    # 1. Lookup in user_identities table
    try:
        identity_response = (
            supabase.table("user_identities")
            .select("id,user_id")
            .eq("provider", "google")
            .eq("provider_subject", google_sub)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        error = _format_supabase_error(exc)
        logger.exception(
            "Google user identity lookup failed",
            extra={
                "event": "auth.google_identity.lookup.failure",
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
                "message": "Failed to query user identities",
                "supabase_error": error,
            },
        ) from exc

    if identity_response.data:
        # Subject match (L1 resolution)
        user_id = identity_response.data[0]["user_id"]
        try:
            user_response = (
                supabase.table("users")
                .select("id,email,name,google_sub,username,phone_number,password_hash")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            error = _format_supabase_error(exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": "Failed to query user", "supabase_error": error},
            ) from exc

        if not user_response.data:
            logger.error(
                "linked user not found in users table",
                extra={
                    "event": "auth.google_user.lookup.failure",
                    "user_id": user_id,
                    "attempt_id": attempt_id,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        user = user_response.data[0]
        # Update last_used_at on identity safely
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            supabase.table("user_identities").update({"last_used_at": now_iso}).eq("id", identity_response.data[0]["id"]).execute()
        except Exception as exc:
            logger.warning(
                "failed to update identity last_used_at",
                extra={"exception": str(exc)},
            )

        logger.info(
            "existing Google user found by subject",
            extra={
                "event": "auth.google_user.lookup.success",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "user_id": user.get("id"),
                "result": "success",
            },
        )
        _log_google_user_lookup_debug(email, attempt_id)
        return user

    # 2. If not found in user_identities, check by email
    logger.info(
        "looking up existing Google user by email",
        extra={
            "event": "auth.google_user_email_lookup.start",
            "auth_method": "google",
            "attempt_id": attempt_id,
        },
    )
    try:
        existing_user_response = (
            supabase.table("users")
            .select("id,email,name,google_sub,username,phone_number,password_hash")
            .eq("email", email)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        error = _format_supabase_error(exc)
        logger.exception(
            "Google user email lookup failed",
            extra={
                "event": "auth.google_user_email_lookup.failure",
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
                "message": "Failed to query user by email",
                "supabase_error": error,
            },
        ) from exc

    if existing_user_response.data:
        existing_user = existing_user_response.data[0]
        # Check if existing user has a password (manual account)
        if existing_user.get("password_hash") is not None:
            # Reject with 409 Conflict (L2 Conflict resolution)
            logger.warning(
                "silent link blocked: account exists with manual password",
                extra={
                    "event": "auth.login.failure",
                    "auth_method": "google",
                    "attempt_id": attempt_id,
                    "status_code": status.HTTP_409_CONFLICT,
                    "error_code": "ACCOUNT_LINKING_REQUIRED",
                    "result": "failure",
                },
            )
            raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="ACCOUNT_LINKING_REQUIRED",
                message="An account with this email already exists. Please sign in with your password to link Google.",
            )

        # Existing user has no password (L2 auto-link resolution)
        logger.info(
            "auto-linking Google subject to existing provider-only account",
            extra={
                "event": "auth.google_user.autolink.start",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "user_id": existing_user["id"],
            },
        )
        try:
            # Create user_identity mapping
            supabase.table("user_identities").insert({
                "user_id": existing_user["id"],
                "provider": "google",
                "provider_subject": google_sub,
                "email_at_link": email,
                "email_verified_at_link": True,
            }).execute()

            # Keep users.google_sub updated for backward compatibility
            if not existing_user.get("google_sub"):
                supabase.table("users").update({"google_sub": google_sub}).eq("id", existing_user["id"]).execute()
                existing_user["google_sub"] = google_sub

        except Exception as exc:
            error = _format_supabase_error(exc)
            logger.exception(
                "failed to auto-link identity",
                extra={
                    "event": "auth.google_user.autolink.failure",
                    "auth_method": "google",
                    "attempt_id": attempt_id,
                    "user_id": existing_user["id"],
                },
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": "Failed to create user identity", "supabase_error": error},
            ) from exc

        logger.info(
            "auto-linking Google subject succeeded",
            extra={
                "event": "auth.google_user.autolink.success",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "user_id": existing_user["id"],
            },
        )
        _log_google_user_lookup_debug(email, attempt_id)
        return existing_user

    # 3. If no email exists (L3 resolution - create new user + user_identity)
    logger.info(
        "creating Google user",
        extra={
            "event": "auth.google_user.create.start",
            "auth_method": "google",
            "attempt_id": attempt_id,
        },
    )
    try:
        created_user_response = (
            supabase.table("users")
            .insert(
                {
                    "google_sub": google_sub,
                    "email": email,
                    "name": google_user["name"],
                    "email_verified": True,
                    "email_verified_at": datetime.now(timezone.utc).isoformat(),
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
                "result": "failure",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "DB insert failure",
                "supabase_error": error,
            },
        ) from exc

    if not created_user_response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "DB insert failure, returned no user rows"},
        )

    new_user = created_user_response.data[0]

    # Create user_identity mapping
    try:
        supabase.table("user_identities").insert({
            "user_id": new_user["id"],
            "provider": "google",
            "provider_subject": google_sub,
            "email_at_link": email,
            "email_verified_at_link": True,
        }).execute()
    except Exception as exc:
        error = _format_supabase_error(exc)
        logger.exception(
            "Google identity insert failed for new user",
            extra={
                "event": "auth.google_user.create.failure",
                "auth_method": "google",
                "attempt_id": attempt_id,
                "user_id": new_user["id"],
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"message": "Failed to create user identity", "supabase_error": error},
        ) from exc

    logger.info(
        "Google user created successfully with identity mapping",
        extra={
            "event": "auth.google_user.create.success",
            "auth_method": "google",
            "attempt_id": attempt_id,
            "user_id": new_user["id"],
            "result": "success",
        },
    )
    _log_google_user_lookup_debug(email, attempt_id)
    return new_user
