"""Account deletion service.

Hard deletion is chosen over soft deletion because:
1. Google Play requires that account deletion actually removes user data,
   not merely hides it. A soft-deleted row still holds PII in the database.
2. The schema already uses ON DELETE CASCADE / SET NULL on every FK that
   references users(id), so Postgres handles referential cleanup atomically.
3. De-identification of shared records (fields, games) is handled by the
   existing SET NULL constraints — those records survive with added_by and
   created_by set to NULL, matching the privacy policy's de-identification
   clause.
4. No business requirement exists for restoring deleted accounts. Users can
   re-register with the same email or Google account after deletion.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import status

from app.auth.dependencies import invalidate_cached_user
from app.auth.google import verify_google_token as _verify_google_token_raw
from app.auth.passwords import verify_password
from app.db.supabase import get_supabase_service_role_client
from app.errors import raise_api_error

logger = logging.getLogger(__name__)


def _verify_google_token_for_reauth(token: str) -> dict[str, Any]:
    from fastapi import HTTPException

    try:
        return _verify_google_token_raw(token)
    except HTTPException as exc:
        if exc.status_code == 401:
            raise_api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="INVALID_GOOGLE_TOKEN",
                message="Invalid Google token",
            )
        raise


def _verify_reauth(
    user: dict[str, Any],
    password: str | None,
    google_token: str | None,
) -> None:
    has_password = bool(user.get("password_hash"))

    if password and has_password:
        if verify_password(password, user["password_hash"]):
            return
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="REAUTHENTICATION_REQUIRED",
            message="Current password is incorrect.",
        )

    if google_token:
        google_user = _verify_google_token_for_reauth(google_token)
        if google_user["google_sub"] == user.get("google_sub"):
            return
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="INVALID_GOOGLE_TOKEN",
            message="Google account does not match the account being deleted.",
        )

    raise_api_error(
        status_code=status.HTTP_403_FORBIDDEN,
        code="REAUTHENTICATION_REQUIRED",
        message="Valid credentials are required to delete this account.",
    )


def delete_account(
    user_id: str,
    password: str | None,
    google_token: str | None,
) -> None:
    client = get_supabase_service_role_client()

    user = (
        client.table("users")
        .select("id,email,google_sub,password_hash,role,status")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not user.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found",
        )
    user = user.data[0]

    _verify_reauth(user, password, google_token)

    if user.get("role") == "admin":
        admin_count = (
            client.table("users")
            .select("id", count="exact")
            .eq("role", "admin")
            .eq("status", "active")
            .execute()
        )
        if (admin_count.count or 0) <= 1:
            raise_api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="LAST_ADMIN",
                message="Cannot delete the last admin account.",
            )

    # Token revocation, game-counter reconciliation, and user deletion
    # run inside a single Postgres transaction via the RPC function.
    result = client.rpc(
        "delete_user_account", {"p_user_id": user_id}
    ).execute()

    rpc_data = result.data
    if isinstance(rpc_data, list):
        rpc_data = rpc_data[0] if rpc_data else {}
    if isinstance(rpc_data, str):
        import json
        rpc_data = json.loads(rpc_data)

    if rpc_data.get("error"):
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found",
        )

    invalidate_cached_user(user_id)

    logger.info(
        "account deleted",
        extra={
            "event": "auth.account_deletion.success",
            "user_id": user_id,
            "games_reconciled": rpc_data.get("games_reconciled", 0),
        },
    )
