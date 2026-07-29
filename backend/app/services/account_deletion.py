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

import json
import logging
from typing import Any, Literal, cast

from fastapi import HTTPException, Request, status

from app.auth.dependencies import invalidate_cached_user
from app.auth.google import verify_google_token as _verify_google_token_raw
from app.auth.passwords import verify_password
from app.db.supabase import get_supabase_service_role_client
from app.errors import error_response, raise_api_error
from app.services import account_linking
from app.services.authentication_audit_events import record_token_revocation_event
from app.services.authentication_observability import safe_auth_log, safe_auth_monitor
from app.services.postgrest_mutation_outcomes import (
    execute_postgrest_mutation,
    observe_ambiguous_mutation,
)

logger = logging.getLogger(__name__)


def _validated_delete_account_response(response: Any) -> dict[str, Any] | None:
    try:
        data = response.data
    except Exception:  # noqa: BLE001 - malformed success is outcome-ambiguous
        return None
    if isinstance(data, list):
        if len(data) != 1:
            return None
        data = data[0]
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:  # noqa: BLE001 - never expose response diagnostics
            return None
    if not isinstance(data, dict):
        return None
    if set(data) == {"error"} and data["error"] == "user_not_found":
        return {"error": "user_not_found"}
    if set(data) != {"deleted", "games_reconciled"}:
        return None
    games_reconciled = data.get("games_reconciled")
    if (
        data.get("deleted") is True
        and isinstance(games_reconciled, int)
        and not isinstance(games_reconciled, bool)
        and games_reconciled >= 0
    ):
        return {
            "deleted": True,
            "games_reconciled": games_reconciled,
        }
    return None


def _verify_google_token_for_reauth(token: str) -> dict[str, Any]:
    return account_linking._verify_google_token_with(
        token,
        _verify_google_token_raw,
    )


def _verify_reauth(
    user: dict[str, Any],
    password: str | None,
    current_password: str | None,
    google_token: str | None,
    request: Request | None = None,
) -> Literal["password", "google"]:
    effective_password = password or current_password
    google_token = google_token or None

    if bool(effective_password) == bool(google_token):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Provide exactly one re-authentication method.",
        )

    has_password = bool(user.get("password_hash"))

    if effective_password:
        if not has_password or not verify_password(effective_password, user["password_hash"]):
            if request:
                account_linking._check_reauth_rate_limit(request, str(user["id"]))
            raise_api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="REAUTHENTICATION_REQUIRED",
                message="Current password is incorrect.",
            )
        # Reset reauth rate limit on success
        if request:
            account_linking._reset_reauth_rate_limit(request, str(user["id"]))
        return "password"

    if google_token:
        # Check Google token verification
        if request:
            try:
                account_linking._verify_reauth_google_token(str(user["id"]), google_token)
            except Exception:
                raise
        else:
            google_user = _verify_google_token_for_reauth(google_token)
            if google_user["google_sub"] != user.get("google_sub"):
                raise_api_error(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="INVALID_GOOGLE_TOKEN",
                    message="Google account does not match the account being deleted.",
                )
        return "google"

    raise_api_error(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="VALIDATION_ERROR",
        message="Provide exactly one re-authentication method.",
    )


def delete_account(
    user_id: str,
    password: str | None = None,
    google_token: str | None = None,
    *,
    current_password: str | None = None,
    request: Request | None = None,
) -> None:
    client = None
    client_initialization_failed = False
    try:
        client = get_supabase_service_role_client()
    except Exception:  # noqa: BLE001 - sanitize client/configuration diagnostics
        client_initialization_failed = True
    if client_initialization_failed or client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Account deletion could not be completed",
            ),
        )

    user = None
    user_lookup_failed = False
    try:
        user = (
            client.table("users")
            .select("id,email,google_sub,password_hash,role,status")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001 - sanitize database diagnostics
        user_lookup_failed = True
    if user_lookup_failed or user is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Account deletion could not be completed",
            ),
        )
    if not user.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found",
        )
    user_data = user.data[0]

    auth_method = _verify_reauth(
        user_data,
        password,
        current_password,
        google_token,
        request,
    )

    if user_data.get("role") == "admin":
        admin_count = None
        admin_lookup_failed = False
        try:
            admin_count = (
                client.table("users")
                .select("id", count="exact")
                .eq("role", "admin")
                .eq("status", "active")
                .execute()
            )
        except Exception:  # noqa: BLE001 - sanitize database diagnostics
            admin_lookup_failed = True
        if admin_lookup_failed or admin_count is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_response(
                    code="INTERNAL_SERVER_ERROR",
                    message="Account deletion could not be completed",
                ),
            )
        if (admin_count.count or 0) <= 1:
            raise_api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="LAST_ADMIN",
                message="Cannot delete the last admin account.",
            )

    # Token revocation, game-counter reconciliation, and user deletion
    # run inside a single Postgres transaction via the RPC function.
    attempt = execute_postgrest_mutation(
        lambda: client.rpc(
            "delete_user_account",
            {"p_user_id": user_id},
        ).execute(),
        validate_response=_validated_delete_account_response,
    )

    if attempt.state == "confirmed_failed":
        record_token_revocation_event(
            outcome="failed",
            auth_method=auth_method,
            revocation_reason="account_deleted",
            user_id=user_id,
            failure_category=attempt.failure_category,
        )
    elif attempt.state == "outcome_ambiguous":
        observe_ambiguous_mutation(
            logger,
            auth_method=auth_method,
            revocation_reason="account_deleted",
            user_id_present=True,
            ambiguity_reason=attempt.ambiguity_reason,
        )

    if attempt.state != "confirmed_succeeded":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Account deletion could not be completed",
            ),
        )

    rpc_data = cast(dict[str, Any], attempt.response)

    if rpc_data.get("error") == "user_not_found":
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found",
        )

    # The user row no longer exists, so the post-commit audit write must use a
    # NULL FK. This ordering guarantees that an audit row can never claim a
    # deletion that did not happen, at the accepted cost of a post-delete crash
    # window in which deletion succeeds without its audit row.
    record_token_revocation_event(
        outcome="succeeded",
        auth_method=auth_method,
        revocation_reason="account_deleted",
        user_id=None,
    )

    cache_invalidation_failed = False
    try:
        invalidate_cached_user(user_id)
    except Exception:  # noqa: BLE001 - deletion and revocation already committed
        cache_invalidation_failed = True
    if cache_invalidation_failed:
        safe_auth_log(
            logger,
            "warning",
            "account deletion cache invalidation failed after deletion",
            extra={
                "event": "auth.account_deletion.cache_invalidation.failure",
                "auth_method": auth_method,
                "revocation_reason": "account_deleted",
                "user_id_present": True,
            },
        )
        safe_auth_monitor(
            "Account deletion cache invalidation failed after deletion",
            level="warning",
            event="auth.account_deletion.cache_invalidation.failure",
            auth_method=auth_method,
            revocation_reason="account_deleted",
            user_id_present=True,
        )

    safe_auth_log(
        logger,
        "info",
        "account deleted",
        extra={
            "event": "auth.account_deletion.success",
            "auth_method": auth_method,
            "revocation_reason": "account_deleted",
            "user_id_present": True,
        },
    )
