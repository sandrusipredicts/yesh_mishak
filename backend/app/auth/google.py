from typing import Any

from fastapi import HTTPException, status
from google.auth.transport import requests
from google.oauth2 import id_token

from app.core.config import get_settings
from app.db.supabase import get_supabase_client


def _format_supabase_error(exc: Exception) -> dict[str, str]:
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "repr": repr(exc),
    }


def verify_google_token(token: str) -> dict[str, Any]:
    settings = get_settings()

    try:
        token_info = id_token.verify_oauth2_token(
            token,
            requests.Request(),
            settings.google_client_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        ) from exc

    email = token_info.get("email")
    google_sub = token_info.get("sub")
    name = token_info.get("name")

    if not email or not google_sub or not name:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    return {
        "google_sub": google_sub,
        "email": email,
        "name": name,
        "picture": token_info.get("picture"),
    }


def find_or_create_google_user(google_user: dict[str, Any]) -> dict[str, Any]:
    supabase = get_supabase_client()
    email = google_user["email"]

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
        print(f"Supabase users select failed: {error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to query user",
                "supabase_error": error,
                "hint": "Check SUPABASE_KEY permissions, users table RLS policies, and that users has id/email/name columns.",
            },
        ) from exc

    if existing_user.data:
        return existing_user.data[0]

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
        print(f"Supabase users insert failed: {error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "DB insert failure",
                "supabase_error": error,
                "hint": "Check SUPABASE_KEY permissions, users table RLS policies, required columns, and unique constraints for email/google_sub.",
            },
        ) from exc

    if not created_user.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "DB insert failure",
                "supabase_error": "Insert returned no user rows",
                "hint": "If insert succeeded but returns no data, check Supabase/PostgREST return settings and table policies.",
            },
        )

    return created_user.data[0]
