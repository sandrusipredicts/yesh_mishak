from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status

from app.auth.dependencies import invalidate_cached_user
from app.auth.google import verify_google_token as _verify_google_token_raw
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, validate_password, verify_password
from app.brute_force import get_brute_force_protector, get_client_ip
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import raise_api_error

REAUTH_WINDOW_KEY_PREFIX = "account_linking_reauth"


def _verify_google_token(token: str) -> dict[str, Any]:
    # The shared verifier raises plain 401s for the /auth/google *login*
    # flow, where there is no session yet to protect. Here the caller
    # already holds a valid session: letting a 401 through this endpoint
    # would trip the frontend's global axios interceptor (any 401 while a
    # token is set clears the session), silently logging the user out just
    # for presenting a bad/expired Google credential. Re-raise as 403 so a
    # a failed re-auth surfaces as an in-page error instead of a forced logout.
    try:
        return _verify_google_token_raw(token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            raise_api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="INVALID_GOOGLE_TOKEN",
                message="Invalid Google token",
            )
        raise


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _fetch_full_user(user_id: str) -> dict[str, Any]:
    response = (
        get_supabase_client()
        .table("users")
        .select("id,email,email_verified,google_sub,password_hash")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="User not found",
        )
    return response.data[0]


def _fetch_google_identity(user_id: str) -> dict[str, Any] | None:
    response = (
        get_supabase_client()
        .table("user_identities")
        .select("id,user_id,provider,provider_subject,email_at_link")
        .eq("user_id", user_id)
        .eq("provider", "google")
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def _build_account_methods(user: dict[str, Any], google_identity: dict[str, Any] | None) -> dict[str, Any]:
    has_password = bool(user.get("password_hash"))
    is_email_verified = user.get("email_verified") is True
    google_linked = google_identity is not None or bool(user.get("google_sub"))

    return {
        "email": {
            "address": mask_email(user.get("email")),
            "linked": has_password,
            "verified": is_email_verified,
            "can_unlink": has_password and google_linked,
        },
        "google": {
            "linked": google_linked,
            "email": mask_email(google_identity.get("email_at_link")) if google_identity else None,
            "can_unlink": google_linked and has_password and is_email_verified,
        },
        "available_login_methods": (1 if has_password else 0) + (1 if google_linked else 0),
    }


def get_account_methods(user_id: str) -> dict[str, Any]:
    user = _fetch_full_user(user_id)
    identity = _fetch_google_identity(user_id)
    return _build_account_methods(user, identity)


def _rpc_result(response: Any) -> str:
    data = response.data
    if isinstance(data, list) and data:
        row = data[0]
        if isinstance(row, dict):
            return str(row.get("result", "unknown"))
    if isinstance(data, dict):
        return str(data.get("result", "unknown"))
    return "unknown"


def _reissue_token(user_id: str) -> str:
    user = _fetch_full_user(user_id)
    invalidate_cached_user(user_id)
    return create_access_token(subject=user_id, email=user.get("email", ""))


def _check_reauth_rate_limit(request: Request, user_id: str) -> None:
    protector = get_brute_force_protector()
    keys = [
        f"ip:{get_client_ip(request)}",
        f"{REAUTH_WINDOW_KEY_PREFIX}:{user_id}",
    ]
    delay_seconds = protector.record_failure(keys)
    protector.apply_delay(delay_seconds)


def _reset_reauth_rate_limit(request: Request, user_id: str) -> None:
    get_brute_force_protector().reset_keys(
        [
            f"ip:{get_client_ip(request)}",
            f"{REAUTH_WINDOW_KEY_PREFIX}:{user_id}",
        ]
    )


def link_google(user_id: str, google_token: str) -> dict[str, Any]:
    google_user = _verify_google_token(google_token)

    service_client = get_supabase_service_role_client()
    response = service_client.rpc(
        "link_google_identity",
        {
            "p_user_id": user_id,
            "p_provider_subject": google_user["google_sub"],
            "p_email_at_link": google_user["email"],
        },
    ).execute()
    result = _rpc_result(response)

    if result == "already_linked":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="ACCOUNT_METHOD_ALREADY_LINKED",
            message="A Google account is already linked. Unlink it before linking a different one.",
        )
    if result == "conflict_other_user":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="ACCOUNT_METHOD_IN_USE_BY_ANOTHER_ACCOUNT",
            message="This Google account is already linked to a different account.",
        )
    if result != "linked":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to link Google account",
        )

    access_token = _reissue_token(user_id)
    return {"account_methods": get_account_methods(user_id), "access_token": access_token}


def unlink_google(user_id: str, current_password: str, request: Request) -> dict[str, Any]:
    user = _fetch_full_user(user_id)

    if not verify_password(current_password, user.get("password_hash")):
        _check_reauth_rate_limit(request, user_id)
        # 403, not 401: a 401 here (a valid session presenting a wrong
        # re-auth password) would trip the frontend's global "401 clears the
        # session" axios interceptor and force-log the user out.
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="REAUTHENTICATION_REQUIRED",
            message="Current password is incorrect.",
        )
    _reset_reauth_rate_limit(request, user_id)

    service_client = get_supabase_service_role_client()
    response = service_client.rpc("unlink_google_identity", {"p_user_id": user_id}).execute()
    result = _rpc_result(response)

    if result == "not_linked":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="ACCOUNT_METHOD_NOT_LINKED",
            message="Google is not linked to this account.",
        )
    if result == "last_method":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="LAST_LOGIN_METHOD",
            message="Google cannot be unlinked because it is the only usable way to sign in.",
        )
    if result != "unlinked":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to unlink Google account",
        )

    access_token = _reissue_token(user_id)
    return {"account_methods": get_account_methods(user_id), "access_token": access_token}


def _verify_reauth_google_token(user_id: str, google_token: str) -> None:
    identity = _fetch_google_identity(user_id)
    if identity is None:
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="INVALID_GOOGLE_TOKEN",
            message="No Google account is linked to re-authenticate with.",
        )

    google_user = _verify_google_token(google_token)
    if google_user["google_sub"] != identity["provider_subject"]:
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="INVALID_GOOGLE_TOKEN",
            message="The Google account does not match the one linked to this account.",
        )


def set_password_for_user(
    user_id: str,
    google_token: str,
    password: str,
    password_confirm: str,
) -> dict[str, Any]:
    if password != password_confirm:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Passwords do not match",
        )

    password_errors = validate_password(password)
    if password_errors:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message=password_errors[0],
        )

    _verify_reauth_google_token(user_id, google_token)

    service_client = get_supabase_service_role_client()
    response = service_client.rpc(
        "set_account_password",
        {"p_user_id": user_id, "p_password_hash": hash_password(password)},
    ).execute()
    result = _rpc_result(response)

    if result == "already_set":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="PASSWORD_ALREADY_SET",
            message="A password is already set for this account. Use password reset to change it.",
        )
    if result != "set":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to set password",
        )

    access_token = _reissue_token(user_id)
    return {"account_methods": get_account_methods(user_id), "access_token": access_token}


def remove_password_for_user(user_id: str, google_token: str) -> dict[str, Any]:
    _verify_reauth_google_token(user_id, google_token)

    service_client = get_supabase_service_role_client()
    response = service_client.rpc("remove_account_password", {"p_user_id": user_id}).execute()
    result = _rpc_result(response)

    if result == "not_set":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="PASSWORD_NOT_SET",
            message="No password is set for this account.",
        )
    if result == "last_method":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="LAST_LOGIN_METHOD",
            message="The password cannot be removed because it is the only usable way to sign in.",
        )
    if result != "removed":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to remove password",
        )

    access_token = _reissue_token(user_id)
    return {"account_methods": get_account_methods(user_id), "access_token": access_token}
