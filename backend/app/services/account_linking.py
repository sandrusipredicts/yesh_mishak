from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from fastapi import HTTPException, Request, status

from app.auth.dependencies import invalidate_cached_user
from app.auth.google import verify_google_token as _verify_google_token_raw
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, validate_password, verify_password
from app.brute_force import get_brute_force_protector, get_client_ip
from app.db.supabase import get_supabase_service_role_client
from app.errors import error_response, raise_api_error
from app.services.authentication_audit_events import (
    AuthMethod,
    RevocationReason,
    record_token_revocation_event,
)
from app.services.authentication_observability import safe_auth_log, safe_auth_monitor
from app.services.postgrest_mutation_outcomes import (
    execute_postgrest_mutation,
    observe_ambiguous_mutation,
)

REAUTH_WINDOW_KEY_PREFIX = "account_linking_reauth"
logger = logging.getLogger(__name__)


def _raise_sanitized_google_verification_failure(status_code: int) -> None:
    if status_code == status.HTTP_401_UNAUTHORIZED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                code="INVALID_GOOGLE_TOKEN",
                message="Invalid Google token",
            ),
        ) from None
    if status_code == status.HTTP_403_FORBIDDEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response(
                code="EMAIL_NOT_VERIFIED",
                message="Google email address is not verified",
            ),
        ) from None
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=error_response(
            code="INTERNAL_SERVER_ERROR",
            message="Google verification could not be completed",
        ),
    ) from None


def _verify_google_token_with(
    token: str,
    verifier: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    verified: dict[str, Any] | None = None
    failure_status: int | None = None
    try:
        verified = verifier(token)
    except HTTPException as exc:
        failure_status = exc.status_code

    if failure_status is not None:
        _raise_sanitized_google_verification_failure(failure_status)
    if verified is None:
        _raise_sanitized_google_verification_failure(status.HTTP_401_UNAUTHORIZED)
    return verified


def _verify_google_token(token: str) -> dict[str, Any]:
    # The shared verifier raises plain 401s for the /auth/google *login*
    # flow, where there is no session yet to protect. Here the caller
    # already holds a valid session: letting a 401 through this endpoint
    # would trip the frontend's global axios interceptor (any 401 while a
    # token is set clears the session), silently logging the user out just
    # for presenting a bad/expired Google credential. Re-raise as 403 so a
    # a failed re-auth surfaces as an in-page error instead of a forced logout.
    return _verify_google_token_with(token, _verify_google_token_raw)


def mask_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _fetch_full_user(user_id: str) -> dict[str, Any]:
    response = None
    lookup_failed = False
    try:
        response = (
            get_supabase_service_role_client()
            .table("users")
            .select("id,email,email_verified,google_sub,password_hash")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001 - sanitize the authentication boundary
        lookup_failed = True
    if lookup_failed or response is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Failed to load account methods",
            ),
        )
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="User not found",
        )
    return response.data[0]


def _fetch_google_identity(user_id: str) -> dict[str, Any] | None:
    response = None
    lookup_failed = False
    try:
        response = (
            get_supabase_service_role_client()
            .table("user_identities")
            .select("id,user_id,provider,provider_subject,email_at_link")
            .eq("user_id", user_id)
            .eq("provider", "google")
            .limit(1)
            .execute()
        )
    except Exception:  # noqa: BLE001 - sanitize the authentication boundary
        lookup_failed = True
    if lookup_failed or response is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Failed to load account methods",
            ),
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


def _validated_revoking_rpc_result(
    response: Any,
    *,
    expected_results: frozenset[str],
) -> str | None:
    try:
        data = response.data
    except Exception:  # noqa: BLE001 - malformed success response is ambiguous
        return None
    if isinstance(data, list):
        if len(data) != 1:
            return None
        row = data[0]
    else:
        row = data
    if not isinstance(row, dict) or set(row) != {"result"}:
        return None
    result = row.get("result")
    if not isinstance(result, str) or result not in expected_results:
        return None
    return result


def _reissue_token(user_id: str) -> str:
    user = _fetch_full_user(user_id)
    invalidate_cached_user(user_id)
    return create_access_token(subject=user_id, email=user.get("email", ""))


def _execute_revoking_rpc(
    *,
    rpc_name: str,
    params: dict[str, Any],
    user_id: str,
    auth_method: AuthMethod,
    revocation_reason: RevocationReason,
    failure_message: str,
) -> str:
    expected_results: frozenset[str]
    if rpc_name == "unlink_google_identity":
        expected_results = frozenset(
            {"unlinked", "not_linked", "last_method", "user_not_found"}
        )
    elif rpc_name == "set_account_password":
        expected_results = frozenset({"set", "already_set", "user_not_found"})
    else:
        expected_results = frozenset(
            {"removed", "not_set", "last_method", "user_not_found"}
        )

    attempt = execute_postgrest_mutation(
        lambda: (
            get_supabase_service_role_client()
            .rpc(rpc_name, params)
            .execute()
        ),
        validate_response=lambda response: _validated_revoking_rpc_result(
            response,
            expected_results=expected_results,
        ),
    )
    if attempt.state == "confirmed_failed":
        record_token_revocation_event(
            outcome="failed",
            auth_method=auth_method,
            revocation_reason=revocation_reason,
            user_id=user_id,
            failure_category=attempt.failure_category,
        )
    elif attempt.state == "outcome_ambiguous":
        observe_ambiguous_mutation(
            logger,
            auth_method=auth_method,
            revocation_reason=revocation_reason,
            user_id_present=True,
            ambiguity_reason=attempt.ambiguity_reason,
        )

    if attempt.state != "confirmed_succeeded":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message=failure_message,
            ),
        )

    result = cast(str, attempt.response)
    return result


def _post_revocation_response(
    *,
    user_id: str,
    auth_method: AuthMethod,
    revocation_reason: RevocationReason,
) -> dict[str, Any]:
    result: dict[str, Any] | None = None
    post_revocation_failed = False
    try:
        access_token = _reissue_token(user_id)
        result = {
            "account_methods": get_account_methods(user_id),
            "access_token": access_token,
        }
    except Exception:  # noqa: BLE001 - revocation already committed
        post_revocation_failed = True

    if post_revocation_failed or result is None:
        safe_auth_log(
            logger,
            "warning",
            "authentication response construction failed after token revocation",
            extra={
                "event": "auth.token_revocation.post_commit_response_failure",
                "auth_method": auth_method,
                "revocation_reason": revocation_reason,
                "user_id_present": True,
            },
        )
        safe_auth_monitor(
            "Authentication response construction failed after token revocation",
            level="warning",
            event="auth.token_revocation.post_commit_response_failure",
            auth_method=auth_method,
            revocation_reason=revocation_reason,
            user_id_present=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response(
                code="INTERNAL_SERVER_ERROR",
                message="Account security was updated but the response could not be completed",
            ),
        )
    return result


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
    if result in {"conflict_other_user", "email_conflict_other_user"}:
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="ACCOUNT_METHOD_IN_USE_BY_ANOTHER_ACCOUNT",
            message="This Google account is already linked to a different account.",
        )
    if result == "identity_data_conflict":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="IDENTITY_DATA_CONFLICT",
            message="Google identity data requires administrator review",
        )
    if result not in {"linked", "already_linked_same"}:
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

    result = _execute_revoking_rpc(
        rpc_name="unlink_google_identity",
        params={"p_user_id": user_id},
        user_id=user_id,
        auth_method="password",
        revocation_reason="google_unlinked",
        failure_message="Failed to unlink Google account",
    )

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
    if result == "user_not_found":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to unlink Google account",
        )
    if result != "unlinked":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to unlink Google account",
        )

    record_token_revocation_event(
        outcome="succeeded",
        auth_method="password",
        revocation_reason="google_unlinked",
        user_id=user_id,
    )
    return _post_revocation_response(
        user_id=user_id,
        auth_method="password",
        revocation_reason="google_unlinked",
    )


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

    result = _execute_revoking_rpc(
        rpc_name="set_account_password",
        params={"p_user_id": user_id, "p_password_hash": hash_password(password)},
        user_id=user_id,
        auth_method="google",
        revocation_reason="password_set",
        failure_message="Failed to set password",
    )

    if result == "already_set":
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="PASSWORD_ALREADY_SET",
            message="A password is already set for this account. Use password reset to change it.",
        )
    if result == "user_not_found":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to set password",
        )
    if result != "set":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to set password",
        )

    record_token_revocation_event(
        outcome="succeeded",
        auth_method="google",
        revocation_reason="password_set",
        user_id=user_id,
    )
    return _post_revocation_response(
        user_id=user_id,
        auth_method="google",
        revocation_reason="password_set",
    )


def remove_password_for_user(user_id: str, google_token: str) -> dict[str, Any]:
    _verify_reauth_google_token(user_id, google_token)

    result = _execute_revoking_rpc(
        rpc_name="remove_account_password",
        params={"p_user_id": user_id},
        user_id=user_id,
        auth_method="google",
        revocation_reason="password_removed",
        failure_message="Failed to remove password",
    )

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
    if result == "user_not_found":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to remove password",
        )
    if result != "removed":
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to remove password",
        )

    record_token_revocation_event(
        outcome="succeeded",
        auth_method="google",
        revocation_reason="password_removed",
        user_id=user_id,
    )
    return _post_revocation_response(
        user_id=user_id,
        auth_method="google",
        revocation_reason="password_removed",
    )
