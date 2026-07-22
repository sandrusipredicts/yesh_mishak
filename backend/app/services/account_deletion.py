from __future__ import annotations

from fastapi import Request, status

from app.auth.dependencies import invalidate_cached_user
from app.auth.passwords import verify_password
from app.errors import raise_api_error
from app.services import account_linking


def delete_account(
    user_id: str,
    *,
    current_password: str | None,
    google_token: str | None,
    request: Request,
) -> None:
    """Re-authenticate and permanently delete an app account.

    The database RPC performs the user-row deletion atomically. Foreign-key
    actions remove account-scoped data (identities, sessions/tokens,
    participation, reports, notification data and preferences) and
    de-identify public field/game records by setting their creator reference
    to NULL.
    """

    if bool(current_password) == bool(google_token):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Provide exactly one re-authentication method.",
        )

    user = account_linking._fetch_full_user(user_id)

    if current_password:
        if not user.get("password_hash") or not verify_password(
            current_password, user.get("password_hash")
        ):
            account_linking._check_reauth_rate_limit(request, user_id)
            raise_api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="REAUTHENTICATION_REQUIRED",
                message="Current password is incorrect.",
            )
    else:
        account_linking._verify_reauth_google_token(user_id, google_token or "")

    account_linking._reset_reauth_rate_limit(request, user_id)

    response = (
        account_linking.get_supabase_service_role_client()
        .rpc("delete_user_account", {"p_user_id": user_id})
        .execute()
    )
    result = account_linking._rpc_result(response)

    if result == "user_not_found":
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="User not found",
        )
    if result != "deleted":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Account deletion failed",
        )

    invalidate_cached_user(user_id)
