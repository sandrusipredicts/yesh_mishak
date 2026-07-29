from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import logging
from typing import Any
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth.passwords import hash_password
from app.core.config import get_settings
from app.main import app
from app.services import account_deletion, account_linking
from app.services.account_deletion import delete_account
from app.services.password_reset import PasswordResetService
from tests.test_account_deletion import (
    FakeSupabaseClient as DeletionClient,
    _delete,
    configure_test_settings as configure_deletion_settings,
    google_only_user,
    make_token as deletion_token,
    password_user as deletion_password_user,
    patch_google_verifier as patch_deletion_google,
    patch_supabase as patch_deletion_supabase,
)
from tests.test_account_linking import (
    FakeRpc as LinkingRpc,
    FakeSupabaseClient as LinkingClient,
    configure_test_settings as configure_linking_settings,
    google_identity_for,
    google_user,
    make_token as linking_token,
    manual_user,
    patch_all_supabase,
    patch_google_verifier,
)
from tests.test_password_reset import (
    FakeEmailDelivery,
    FakeResetSupabaseClient,
    configure_settings as configure_reset_settings,
    extract_token,
    password_user as reset_password_user,
    patch_password_reset,
)


EVENT_ID = "00000000-0000-4000-8000-000000002002"
CORRELATION_ID = "phase2-correlation"
PASSWORD_SENTINEL = "Phase2-Password-Secret-123"
GOOGLE_SENTINEL = "phase2-google-credential-sentinel"
RESET_SENTINEL = "phase2-reset-token-sentinel-value"
EMAIL_SENTINEL = "phase2-private-email@example.invalid"
PROVIDER_SENTINEL = "phase2-private-provider-subject"
DATABASE_SENTINEL = "phase2-private-database-diagnostics"
AUDIT_SENTINEL = "phase2-private-audit-diagnostics"
MALFORMED_ID_SENTINEL = "phase2-private-malformed-user-id"
NULL_RPC_RESPONSE = object()


@dataclass
class AuditResponse:
    data: Any


class AuditCaptureRpc:
    def __init__(
        self,
        capture: "AuditCaptureClient",
        name: str,
        params: dict[str, Any],
    ) -> None:
        self.capture = capture
        self.name = name
        self.params = params

    def execute(self) -> AuditResponse:
        self.capture.calls.append((self.name, dict(self.params)))
        if self.capture.fail:
            raise RuntimeError(AUDIT_SENTINEL)
        return AuditResponse(data=True)


class AuditCaptureClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> AuditCaptureRpc:
        return AuditCaptureRpc(self, name, params)


class FailingLinkingRpc(LinkingRpc):
    def __init__(
        self,
        *args: Any,
        error_code: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.error_code = error_code

    def execute(self) -> Any:
        raise APIError(
            {
                "code": self.error_code,
                "message": DATABASE_SENTINEL,
                "hint": DATABASE_SENTINEL,
                "details": DATABASE_SENTINEL,
            }
        )


class FailingLinkingClient(LinkingClient):
    def __init__(
        self,
        *args: Any,
        failing_rpc: str,
        error_code: str = "XX000",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.failing_rpc = failing_rpc
        self.error_code = error_code

    def rpc(self, name: str, params: dict[str, Any]) -> LinkingRpc:
        if name == self.failing_rpc:
            return FailingLinkingRpc(
                self,
                name,
                params,
                error_code=self.error_code,
            )
        return super().rpc(name, params)


class AmbiguousLinkingRpc(LinkingRpc):
    def execute(self) -> Any:
        raise RuntimeError(DATABASE_SENTINEL)


class AmbiguousLinkingClient(LinkingClient):
    def __init__(
        self,
        *args: Any,
        failing_rpc: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.failing_rpc = failing_rpc

    def rpc(self, name: str, params: dict[str, Any]) -> LinkingRpc:
        if name == self.failing_rpc:
            return AmbiguousLinkingRpc(self, name, params)
        return super().rpc(name, params)


class CommitThenValidationLinkingClient(LinkingClient):
    def rpc_unlink_google_identity(self, params: dict[str, Any]) -> str:
        super().rpc_unlink_google_identity(params)
        try:
            raise ValueError(DATABASE_SENTINEL)
        except ValueError as exc:
            raise APIError(
                {
                    "code": "XX000",
                    "message": DATABASE_SENTINEL,
                    "hint": DATABASE_SENTINEL,
                    "details": DATABASE_SENTINEL,
                }
            ) from exc


class CommitThenMalformedLinkingClient(LinkingClient):
    def rpc_unlink_google_identity(self, params: dict[str, Any]) -> dict[str, Any]:
        super().rpc_unlink_google_identity(params)
        return {"unexpected": DATABASE_SENTINEL}


class ForcedResultLinkingClient(LinkingClient):
    def __init__(
        self,
        *args: Any,
        forced_rpc: str,
        forced_result: str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.forced_rpc = forced_rpc
        self.forced_result = forced_result

    def rpc_unlink_google_identity(self, params: dict[str, Any]) -> str:
        if self.forced_rpc == "unlink_google_identity":
            return self.forced_result
        return super().rpc_unlink_google_identity(params)

    def rpc_set_account_password(self, params: dict[str, Any]) -> str:
        if self.forced_rpc == "set_account_password":
            return self.forced_result
        return super().rpc_set_account_password(params)

    def rpc_remove_account_password(self, params: dict[str, Any]) -> str:
        if self.forced_rpc == "remove_account_password":
            return self.forced_result
        return super().rpc_remove_account_password(params)


class FailingResetClient(FakeResetSupabaseClient):
    error_code = "XX000"

    def consume_reset_token(self, params: dict[str, Any]) -> dict[str, Any]:
        raise APIError(
            {
                "code": self.error_code,
                "message": DATABASE_SENTINEL,
                "hint": DATABASE_SENTINEL,
                "details": DATABASE_SENTINEL,
            }
        )


class AmbiguousResetClient(FakeResetSupabaseClient):
    def consume_reset_token(self, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(DATABASE_SENTINEL)


class MissingRpcResetClient(FailingResetClient):
    error_code = "PGRST202"


class CommitThenValidationResetClient(FakeResetSupabaseClient):
    def consume_reset_token(self, params: dict[str, Any]) -> dict[str, Any]:
        super().consume_reset_token(params)
        try:
            raise ValueError(DATABASE_SENTINEL)
        except ValueError as exc:
            raise APIError(
                {
                    "code": "XX000",
                    "message": DATABASE_SENTINEL,
                    "hint": DATABASE_SENTINEL,
                    "details": DATABASE_SENTINEL,
                }
            ) from exc


class CommitThenMalformedResetClient(FakeResetSupabaseClient):
    def consume_reset_token(self, params: dict[str, Any]) -> dict[str, Any]:
        super().consume_reset_token(params)
        return {"unexpected": DATABASE_SENTINEL}


class ConfirmRateLimitFailureClient(FakeResetSupabaseClient):
    def check_rate_limit(self, params: dict[str, Any]) -> dict[str, Any]:
        if "p_token_key" in params:
            raise APIError(
                {
                    "code": "XX000",
                    "message": DATABASE_SENTINEL,
                    "hint": DATABASE_SENTINEL,
                    "details": DATABASE_SENTINEL,
                }
            )
        return super().check_rate_limit(params)


class ConfirmRateLimitMalformedClient(FakeResetSupabaseClient):
    def check_rate_limit(self, params: dict[str, Any]) -> dict[str, Any]:
        if "p_token_key" in params:
            return {"allowed": DATABASE_SENTINEL}
        return super().check_rate_limit(params)


class FailingDeletionClient(DeletionClient):
    error_code = "XX000"

    def rpc_delete_user_account(self, params: dict[str, Any]) -> dict[str, Any]:
        raise APIError(
            {
                "code": self.error_code,
                "message": DATABASE_SENTINEL,
                "hint": DATABASE_SENTINEL,
                "details": DATABASE_SENTINEL,
            }
        )


class AmbiguousDeletionClient(DeletionClient):
    def rpc_delete_user_account(self, params: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(DATABASE_SENTINEL)


class MissingRpcDeletionClient(FailingDeletionClient):
    error_code = "PGRST202"


class CommitThenValidationDeletionClient(DeletionClient):
    def rpc_delete_user_account(self, params: dict[str, Any]) -> dict[str, Any]:
        super().rpc_delete_user_account(params)
        try:
            raise ValueError(DATABASE_SENTINEL)
        except ValueError as exc:
            raise APIError(
                {
                    "code": "XX000",
                    "message": DATABASE_SENTINEL,
                    "hint": DATABASE_SENTINEL,
                    "details": DATABASE_SENTINEL,
                }
            ) from exc


class CommitThenMalformedDeletionClient(DeletionClient):
    def rpc_delete_user_account(self, params: dict[str, Any]) -> dict[str, Any]:
        super().rpc_delete_user_account(params)
        return {"unexpected": DATABASE_SENTINEL}


class PostCommitResponseOverride:
    def __init__(self, delegate: Any, response_data: Any) -> None:
        self.delegate = delegate
        self.response_data = response_data

    def execute(self) -> AuditResponse | None:
        self.delegate.execute()
        if self.response_data is NULL_RPC_RESPONSE:
            return None
        return AuditResponse(data=self.response_data)


def _override_rpc_response(
    monkeypatch,
    client: Any,
    *,
    rpc_name: str,
    response_data: Any,
) -> None:
    original_rpc = client.rpc

    def overridden_rpc(name: str, params: dict[str, Any]) -> Any:
        delegate = original_rpc(name, params)
        if name == rpc_name:
            return PostCommitResponseOverride(delegate, response_data)
        return delegate

    monkeypatch.setattr(client, "rpc", overridden_rpc)


def _patch_audit(
    monkeypatch,
    capture: AuditCaptureClient,
) -> None:
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "phase-2-test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.authentication_audit_events.get_supabase_service_role_client",
        lambda: capture,
    )
    monkeypatch.setattr(
        "app.services.authentication_audit_events.new_audit_event_id",
        lambda: EVENT_ID,
    )
    monkeypatch.setattr(
        "app.services.authentication_audit_events.new_auth_correlation_id",
        lambda: CORRELATION_ID,
    )


def _expected_payload(
    *,
    outcome: str,
    auth_method: str,
    reason: str,
    user_id: str | None,
    failure_category: str | None = None,
) -> dict[str, Any]:
    return {
        "p_event_id": EVENT_ID,
        "p_event_type": "token_revocation",
        "p_outcome": outcome,
        "p_auth_method": auth_method,
        "p_user_id": user_id,
        "p_failure_category": failure_category,
        "p_revocation_reason": reason,
        "p_correlation_id": CORRELATION_ID,
        "p_source_environment": "phase-2-test",
    }


def _assert_one_event(
    capture: AuditCaptureClient,
    expected: dict[str, Any],
) -> None:
    assert capture.calls == [
        ("record_authentication_audit_event", expected)
    ]


def _assert_private(*values: Any) -> None:
    serialized = json.dumps(values, default=str)
    for sentinel in (
        PASSWORD_SENTINEL,
        GOOGLE_SENTINEL,
        RESET_SENTINEL,
        EMAIL_SENTINEL,
        PROVIDER_SENTINEL,
        DATABASE_SENTINEL,
        AUDIT_SENTINEL,
        MALFORMED_ID_SENTINEL,
    ):
        assert sentinel not in serialized


def _capture_monitoring(monkeypatch) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    return calls


def _assert_bounded_monitoring(
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]],
    *,
    user_id: str | None,
) -> None:
    serialized = json.dumps(calls, default=str)
    assert EVENT_ID not in serialized
    assert CORRELATION_ID not in serialized
    if user_id is not None:
        assert user_id not in serialized
    _assert_private(calls)


def _assert_one_ambiguous_warning(
    caplog,
    monitoring: list[tuple[tuple[Any, ...], dict[str, Any]]],
) -> None:
    assert sum(
        record.getMessage() == "authentication mutation outcome is ambiguous"
        for record in caplog.records
    ) == 1
    assert len(monitoring) == 1


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/unlink/google",
            "headers": [],
            "client": ("127.0.0.1", 12345),
        }
    )


def _linking_case(
    monkeypatch,
    case: str,
    *,
    failing_rpc: str | None = None,
    ambiguous_rpc: str | None = None,
    failure_code: str = "XX000",
) -> tuple[LinkingClient, dict[str, Any], str, dict[str, Any], str, str]:
    configure_linking_settings(monkeypatch)
    if case == "unlink":
        user = manual_user(
            email=EMAIL_SENTINEL,
            google_sub=PROVIDER_SENTINEL,
            password_hash=hash_password(PASSWORD_SENTINEL),
        )
        identity = google_identity_for(
            user,
            provider_subject=PROVIDER_SENTINEL,
        )
        endpoint = "/auth/unlink/google"
        body = {"current_password": PASSWORD_SENTINEL}
        auth_method = "password"
        reason = "google_unlinked"
        rpc_name = "unlink_google_identity"
    elif case == "set":
        user = google_user(
            email=EMAIL_SENTINEL,
            google_sub=PROVIDER_SENTINEL,
        )
        identity = google_identity_for(
            user,
            provider_subject=PROVIDER_SENTINEL,
        )
        endpoint = "/auth/set-password"
        body = {
            "google_token": GOOGLE_SENTINEL,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        }
        auth_method = "google"
        reason = "password_set"
        rpc_name = "set_account_password"
    else:
        user = manual_user(
            email=EMAIL_SENTINEL,
            google_sub=PROVIDER_SENTINEL,
            password_hash=hash_password(PASSWORD_SENTINEL),
        )
        identity = google_identity_for(
            user,
            provider_subject=PROVIDER_SENTINEL,
        )
        endpoint = "/auth/remove-password"
        body = {"google_token": GOOGLE_SENTINEL}
        auth_method = "google"
        reason = "password_removed"
        rpc_name = "remove_account_password"

    if failing_rpc:
        client_type = FailingLinkingClient
        client_kwargs = {
            "failing_rpc": failing_rpc,
            "error_code": failure_code,
        }
    elif ambiguous_rpc:
        client_type = AmbiguousLinkingClient
        client_kwargs = {"failing_rpc": ambiguous_rpc}
    else:
        client_type = LinkingClient
        client_kwargs = {}
    fake = client_type([user], [identity], **client_kwargs)
    patch_all_supabase(monkeypatch, fake)
    patch_google_verifier(
        monkeypatch,
        {
            GOOGLE_SENTINEL: {
                "sub": PROVIDER_SENTINEL,
                "email": EMAIL_SENTINEL,
                "email_verified": True,
            }
        },
    )
    return fake, user, endpoint, body, auth_method, reason


@pytest.mark.parametrize("case", ["unlink", "set", "remove"])
def test_account_linking_success_emits_exact_private_event(
    monkeypatch,
    caplog,
    case: str,
) -> None:
    capture = AuditCaptureClient()
    fake, user, endpoint, body, auth_method, reason = _linking_case(
        monkeypatch,
        case,
    )
    _patch_audit(monkeypatch, capture)
    headers = {"Authorization": f"Bearer {linking_token(user)}"}

    with caplog.at_level(logging.INFO):
        response = TestClient(app).post(endpoint, json=body, headers=headers)

    assert response.status_code == 200
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="succeeded",
            auth_method=auth_method,
            reason=reason,
            user_id=user["id"],
        ),
    )
    assert user["tokens_valid_after"] is not None
    _assert_private(capture.calls, response.json(), caplog.text)


@pytest.mark.parametrize("case", ["unlink", "set", "remove"])
def test_account_linking_pre_revocation_failure_emits_no_event(
    monkeypatch,
    case: str,
) -> None:
    capture = AuditCaptureClient()
    fake, user, endpoint, body, _, _ = _linking_case(monkeypatch, case)
    _patch_audit(monkeypatch, capture)
    if case == "unlink":
        body["current_password"] = "wrong-password-value"
    else:
        body["google_token"] = "wrong-google-token"

    response = TestClient(app).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 403
    assert capture.calls == []
    assert user["tokens_valid_after"] is None


@pytest.mark.parametrize(
    ("case", "rpc_name", "rpc_result", "expected_code"),
    [
        (
            "unlink",
            "unlink_google_identity",
            "not_linked",
            "ACCOUNT_METHOD_NOT_LINKED",
        ),
        (
            "unlink",
            "unlink_google_identity",
            "last_method",
            "LAST_LOGIN_METHOD",
        ),
        (
            "set",
            "set_account_password",
            "already_set",
            "PASSWORD_ALREADY_SET",
        ),
        (
            "remove",
            "remove_account_password",
            "not_set",
            "PASSWORD_NOT_SET",
        ),
        (
            "remove",
            "remove_account_password",
            "last_method",
            "LAST_LOGIN_METHOD",
        ),
    ],
)
def test_account_linking_business_precondition_emits_no_event(
    monkeypatch,
    case: str,
    rpc_name: str,
    rpc_result: str,
    expected_code: str,
) -> None:
    capture = AuditCaptureClient()
    base, user, endpoint, body, _, _ = _linking_case(monkeypatch, case)
    fake = ForcedResultLinkingClient(
        base.tables["users"],
        base.tables["user_identities"],
        forced_rpc=rpc_name,
        forced_result=rpc_result,
    )
    patch_all_supabase(monkeypatch, fake)
    patch_google_verifier(
        monkeypatch,
        {
            GOOGLE_SENTINEL: {
                "sub": PROVIDER_SENTINEL,
                "email": EMAIL_SENTINEL,
                "email_verified": True,
            }
        },
    )
    _patch_audit(monkeypatch, capture)

    response = TestClient(app).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == expected_code
    assert capture.calls == []
    assert user["tokens_valid_after"] is None


@pytest.mark.parametrize(
    ("case", "rpc_name"),
    [
        ("unlink", "unlink_google_identity"),
        ("set", "set_account_password"),
        ("remove", "remove_account_password"),
    ],
)
def test_account_linking_known_revocation_failure_is_sanitized(
    monkeypatch,
    caplog,
    case: str,
    rpc_name: str,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake, user, endpoint, body, auth_method, reason = _linking_case(
        monkeypatch,
        case,
        failing_rpc=rpc_name,
    )
    _patch_audit(monkeypatch, capture)

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {linking_token(user)}"},
        )

    assert response.status_code == 500
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="failed",
            auth_method=auth_method,
            reason=reason,
            user_id=user["id"],
            failure_category="internal_error",
        ),
    )
    assert user["tokens_valid_after"] is None
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(capture.calls, response.json(), caplog.text)


@pytest.mark.parametrize(
    ("case", "rpc_name"),
    [
        ("unlink", "unlink_google_identity"),
        ("set", "set_account_password"),
        ("remove", "remove_account_password"),
    ],
)
def test_account_linking_ambiguous_outcome_does_not_claim_durable_result(
    monkeypatch,
    caplog,
    case: str,
    rpc_name: str,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake, user, endpoint, body, _, _ = _linking_case(
        monkeypatch,
        case,
        ambiguous_rpc=rpc_name,
    )
    _patch_audit(monkeypatch, capture)

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {linking_token(user)}"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": {
            "unlink": "Failed to unlink Google account",
            "set": "Failed to set password",
            "remove": "Failed to remove password",
        }[case],
    }
    assert capture.calls == []
    assert user["tokens_valid_after"] is None
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text)


@pytest.mark.parametrize(
    ("failure_code", "expected_category"),
    [
        ("08006", "service_unavailable"),
        ("PGRST202", "invalid_state"),
        ("42501", "invalid_state"),
        ("XX000", "internal_error"),
    ],
)
def test_google_unlink_confirmed_rollback_uses_evidence_based_category(
    monkeypatch,
    failure_code: str,
    expected_category: str,
) -> None:
    capture = AuditCaptureClient()
    _, user, endpoint, body, auth_method, reason = _linking_case(
        monkeypatch,
        "unlink",
        failing_rpc="unlink_google_identity",
        failure_code=failure_code,
    )
    _patch_audit(monkeypatch, capture)

    response = TestClient(app, raise_server_exceptions=False).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Failed to unlink Google account",
    }
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="failed",
            auth_method=auth_method,
            reason=reason,
            user_id=user["id"],
            failure_category=expected_category,
        ),
    )
    assert user["tokens_valid_after"] is None


@pytest.mark.parametrize(
    "client_type",
    [CommitThenValidationLinkingClient, CommitThenMalformedLinkingClient],
)
def test_google_unlink_committed_but_unparseable_response_is_ambiguous(
    monkeypatch,
    caplog,
    client_type,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    base, user, endpoint, body, _, _ = _linking_case(monkeypatch, "unlink")
    fake = client_type(
        base.tables["users"],
        base.tables["user_identities"],
    )
    patch_all_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {linking_token(user)}"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Failed to unlink Google account",
    }
    assert capture.calls == []
    assert user["tokens_valid_after"] is not None
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text, monitoring)


@pytest.mark.parametrize("case", ["unlink", "set", "remove"])
def test_account_linking_jwt_failure_preserves_completed_revocation(
    monkeypatch,
    caplog,
    case: str,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake, user, endpoint, body, auth_method, reason = _linking_case(
        monkeypatch,
        case,
    )
    token = linking_token(user)
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.account_linking.create_access_token",
        lambda **_: (_ for _ in ()).throw(RuntimeError(DATABASE_SENTINEL)),
    )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Account security was updated but the response could not be completed",
    }
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="succeeded",
            auth_method=auth_method,
            reason=reason,
            user_id=user["id"],
        ),
    )
    assert user["tokens_valid_after"] is not None
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), capture.calls, caplog.text)


@pytest.mark.parametrize("case", ["unlink", "set", "remove"])
def test_account_linking_audit_and_observability_failures_are_nonfatal(
    monkeypatch,
    case: str,
) -> None:
    capture = AuditCaptureClient(fail=True)
    fake, user, endpoint, body, _, _ = _linking_case(monkeypatch, case)
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.authentication_audit_events.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("logger failed")),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("monitor failed")),
    )
    monkeypatch.setattr(
        "app.api.auth.logger.info",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("logger failed")),
    )

    response = TestClient(app).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 200
    assert len(capture.calls) == 1
    assert user["tokens_valid_after"] is not None


def _prepare_reset(
    monkeypatch,
    client: FakeResetSupabaseClient,
    capture: AuditCaptureClient,
) -> tuple[TestClient, dict[str, Any], str]:
    configure_reset_settings(monkeypatch)
    user = client.tables["users"][0]
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, client, email)
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.password_reset.secrets.token_urlsafe",
        lambda _: RESET_SENTINEL,
    )
    http = TestClient(app, raise_server_exceptions=False)
    request = http.post(
        "/auth/password-reset/request",
        json={"email": user["email"]},
    )
    assert request.status_code == 200
    return http, user, extract_token(email)


def test_password_reset_success_emits_exact_private_event(
    monkeypatch,
    caplog,
) -> None:
    capture = AuditCaptureClient()
    user = reset_password_user(email=EMAIL_SENTINEL)
    http, user, raw_token = _prepare_reset(
        monkeypatch,
        FakeResetSupabaseClient([user]),
        capture,
    )

    with caplog.at_level(logging.INFO):
        response = http.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": PASSWORD_SENTINEL,
                "password_confirm": PASSWORD_SENTINEL,
            },
        )

    assert response.status_code == 200
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="succeeded",
            auth_method="recovery",
            reason="password_reset",
            user_id=user["id"],
        ),
    )
    assert user["tokens_valid_after"] is not None
    _assert_private(capture.calls, response.json(), caplog.text)


def test_invalid_password_reset_token_emits_no_event(monkeypatch) -> None:
    capture = AuditCaptureClient()
    configure_reset_settings(monkeypatch)
    fake = FakeResetSupabaseClient([reset_password_user()])
    patch_password_reset(monkeypatch, fake, FakeEmailDelivery())
    _patch_audit(monkeypatch, capture)

    response = TestClient(app).post(
        "/auth/password-reset/confirm",
        json={
            "token": RESET_SENTINEL,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        },
    )

    assert response.status_code == 400
    assert capture.calls == []


def test_password_reset_known_revocation_failure_is_sanitized(
    monkeypatch,
    caplog,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake = FailingResetClient([reset_password_user(email=EMAIL_SENTINEL)])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)

    with caplog.at_level(logging.WARNING):
        response = http.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": PASSWORD_SENTINEL,
                "password_confirm": PASSWORD_SENTINEL,
            },
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Password reset could not be completed",
    }
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="failed",
            auth_method="recovery",
            reason="password_reset",
            user_id=None,
            failure_category="internal_error",
        ),
    )
    assert user["tokens_valid_after"] is None
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=None)
    _assert_private(capture.calls, response.json(), caplog.text)


def test_password_reset_ambiguous_outcome_does_not_claim_durable_result(
    monkeypatch,
    caplog,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake = AmbiguousResetClient([reset_password_user(email=EMAIL_SENTINEL)])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)

    with caplog.at_level(logging.WARNING):
        response = http.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": PASSWORD_SENTINEL,
                "password_confirm": PASSWORD_SENTINEL,
            },
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Password reset could not be completed",
    }
    assert capture.calls == []
    assert user["tokens_valid_after"] is None
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text)


@pytest.mark.parametrize(
    ("client_type", "expected_category"),
    [
        (FailingResetClient, "internal_error"),
        (MissingRpcResetClient, "invalid_state"),
    ],
)
def test_password_reset_confirmed_rollback_category(
    monkeypatch,
    client_type,
    expected_category: str,
) -> None:
    capture = AuditCaptureClient()
    fake = client_type([reset_password_user(email=EMAIL_SENTINEL)])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)

    response = http.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        },
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Password reset could not be completed",
    }
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="failed",
            auth_method="recovery",
            reason="password_reset",
            user_id=None,
            failure_category=expected_category,
        ),
    )
    assert user["tokens_valid_after"] is None


@pytest.mark.parametrize(
    "client_type",
    [CommitThenValidationResetClient, CommitThenMalformedResetClient],
)
def test_password_reset_committed_but_unparseable_response_is_ambiguous(
    monkeypatch,
    caplog,
    client_type,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake = client_type([reset_password_user(email=EMAIL_SENTINEL)])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)

    with caplog.at_level(logging.WARNING):
        response = http.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": PASSWORD_SENTINEL,
                "password_confirm": PASSWORD_SENTINEL,
            },
        )

    assert response.status_code == 500
    assert capture.calls == []
    assert user["tokens_valid_after"] is not None
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text, monitoring)


@pytest.mark.parametrize(
    "client_type",
    [ConfirmRateLimitFailureClient, ConfirmRateLimitMalformedClient],
)
@pytest.mark.parametrize(
    "observability_failure",
    ["none", "logger", "monitor", "both"],
)
def test_password_reset_confirm_rate_limit_failure_is_sanitized(
    monkeypatch,
    caplog,
    client_type,
    observability_failure: str,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake = client_type([reset_password_user(email=EMAIL_SENTINEL)])
    http, _, raw_token = _prepare_reset(monkeypatch, fake, capture)
    if observability_failure in {"logger", "both"}:
        monkeypatch.setattr(
            "app.services.password_reset.logger.warning",
            lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
        )
    if observability_failure in {"monitor", "both"}:
        monkeypatch.setattr(
            "app.services.authentication_observability.capture_unexpected_message",
            lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
        )

    with caplog.at_level(logging.WARNING):
        response = http.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": PASSWORD_SENTINEL,
                "password_confirm": PASSWORD_SENTINEL,
            },
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Password reset could not be completed",
    }
    assert capture.calls == []
    if observability_failure == "none":
        assert len(monitoring) == 1
    _assert_private(response.json(), caplog.text, monitoring)


def test_password_reset_confirm_rate_limited_emits_no_event(monkeypatch) -> None:
    capture = AuditCaptureClient()
    fake = FakeResetSupabaseClient([reset_password_user()])
    http, _, raw_token = _prepare_reset(monkeypatch, fake, capture)
    fake.rate_limit_result = {
        "allowed": False,
        "retry_after_seconds": 123,
    }

    response = http.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        },
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "123"
    assert capture.calls == []


def test_password_reset_audit_and_observability_failures_are_nonfatal(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient(fail=True)
    fake = FakeResetSupabaseClient([reset_password_user()])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)
    monkeypatch.setattr(
        "app.services.authentication_audit_events.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("logger failed")),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("monitor failed")),
    )
    monkeypatch.setattr(
        "app.services.password_reset.logger.info",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("logger failed")),
    )

    response = http.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        },
    )

    assert response.status_code == 200
    assert len(capture.calls) == 1
    assert user["tokens_valid_after"] is not None


@pytest.mark.parametrize("auth_method", ["password", "google"])
def test_account_deletion_success_emits_post_delete_null_user_event(
    monkeypatch,
    caplog,
    auth_method: str,
) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    if auth_method == "password":
        user = deletion_password_user(
            email=EMAIL_SENTINEL,
            password_hash=hash_password(PASSWORD_SENTINEL),
        )
        body = {"password": PASSWORD_SENTINEL}
    else:
        user = google_only_user(
            email=EMAIL_SENTINEL,
            google_sub=PROVIDER_SENTINEL,
        )
        body = {"google_token": GOOGLE_SENTINEL}
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    patch_deletion_google(
        monkeypatch,
        {
            GOOGLE_SENTINEL: {
                "sub": PROVIDER_SENTINEL,
                "email": EMAIL_SENTINEL,
                "email_verified": True,
            }
        },
    )
    _patch_audit(monkeypatch, capture)

    with caplog.at_level(logging.INFO):
        response = _delete(
            TestClient(app),
            "/auth/account",
            body=body,
            headers={"Authorization": f"Bearer {deletion_token(user)}"},
        )

    assert response.status_code == 200
    assert fake.tables["users"] == []
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="succeeded",
            auth_method=auth_method,
            reason="account_deleted",
            user_id=None,
        ),
    )
    _assert_private(capture.calls, response.json(), caplog.text)


def test_account_deletion_failed_reauthentication_emits_no_event(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user()
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "wrong-password-value"},
        headers={"Authorization": f"Bearer {deletion_token(user)}"},
    )

    assert response.status_code == 403
    assert capture.calls == []
    assert fake.tables["users"] == [user]


def test_account_deletion_known_revocation_failure_is_sanitized(
    monkeypatch,
    caplog,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(
        email=EMAIL_SENTINEL,
        password_hash=hash_password(PASSWORD_SENTINEL),
    )
    fake = FailingDeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    with caplog.at_level(logging.WARNING):
        response = _delete(
            TestClient(app, raise_server_exceptions=False),
            "/auth/account",
            body={"password": PASSWORD_SENTINEL},
            headers={"Authorization": f"Bearer {deletion_token(user)}"},
        )

    assert response.status_code == 500
    assert fake.tables["users"] == [user]
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="failed",
            auth_method="password",
            reason="account_deleted",
            user_id=user["id"],
            failure_category="internal_error",
        ),
    )
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(capture.calls, response.json(), caplog.text)


def test_account_deletion_ambiguous_outcome_does_not_claim_durable_result(
    monkeypatch,
    caplog,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(
        email=EMAIL_SENTINEL,
        password_hash=hash_password(PASSWORD_SENTINEL),
    )
    fake = AmbiguousDeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    with caplog.at_level(logging.WARNING):
        response = _delete(
            TestClient(app, raise_server_exceptions=False),
            "/auth/account",
            body={"password": PASSWORD_SENTINEL},
            headers={"Authorization": f"Bearer {deletion_token(user)}"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Account deletion could not be completed",
    }
    assert capture.calls == []
    assert fake.tables["users"] == [user]
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text)


@pytest.mark.parametrize(
    ("client_type", "expected_category"),
    [
        (FailingDeletionClient, "internal_error"),
        (MissingRpcDeletionClient, "invalid_state"),
    ],
)
def test_account_deletion_confirmed_rollback_category(
    monkeypatch,
    client_type,
    expected_category: str,
) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(
        email=EMAIL_SENTINEL,
        password_hash=hash_password(PASSWORD_SENTINEL),
    )
    fake = client_type([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    response = _delete(
        TestClient(app, raise_server_exceptions=False),
        "/auth/account",
        body={"password": PASSWORD_SENTINEL},
        headers={"Authorization": f"Bearer {deletion_token(user)}"},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Account deletion could not be completed",
    }
    assert fake.tables["users"] == [user]
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="failed",
            auth_method="password",
            reason="account_deleted",
            user_id=user["id"],
            failure_category=expected_category,
        ),
    )


@pytest.mark.parametrize(
    "client_type",
    [CommitThenValidationDeletionClient, CommitThenMalformedDeletionClient],
)
def test_account_deletion_committed_but_unparseable_response_is_ambiguous(
    monkeypatch,
    caplog,
    client_type,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(
        email=EMAIL_SENTINEL,
        password_hash=hash_password(PASSWORD_SENTINEL),
    )
    fake = client_type([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    with caplog.at_level(logging.WARNING):
        response = _delete(
            TestClient(app, raise_server_exceptions=False),
            "/auth/account",
            body={"password": PASSWORD_SENTINEL},
            headers={"Authorization": f"Bearer {deletion_token(user)}"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Account deletion could not be completed",
    }
    assert fake.tables["users"] == []
    assert capture.calls == []
    assert len(monitoring) == 1
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text, monitoring)


def test_account_deletion_audit_and_observability_failures_are_nonfatal(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient(fail=True)
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user()
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.authentication_audit_events.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("logger failed")),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("monitor failed")),
    )
    monkeypatch.setattr(
        "app.services.account_deletion.logger.info",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("logger failed")),
    )

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {deletion_token(user)}"},
    )

    assert response.status_code == 200
    assert len(capture.calls) == 1
    assert fake.tables["users"] == []


@pytest.mark.parametrize("token_state", ["expired", "consumed"])
def test_unusable_password_reset_token_emits_no_event(
    monkeypatch,
    token_state: str,
) -> None:
    capture = AuditCaptureClient()
    fake = FakeResetSupabaseClient([reset_password_user()])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)
    token_row = fake.tables["password_reset_tokens"][0]
    if token_state == "expired":
        token_row["expires_at"] = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        ).isoformat()
        expected_code = "RESET_TOKEN_EXPIRED"
    else:
        token_row.update(
            status="consumed",
            consumed_at=datetime.now(timezone.utc).isoformat(),
        )
        expected_code = "RESET_TOKEN_CONSUMED"

    response = http.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == expected_code
    assert capture.calls == []
    assert user["tokens_valid_after"] is None


@pytest.mark.parametrize("case", ["unlink", "set", "remove"])
def test_account_linking_endpoint_rate_limit_emits_no_event(
    monkeypatch,
    case: str,
) -> None:
    capture = AuditCaptureClient()
    _, user, endpoint, body, _, _ = _linking_case(monkeypatch, case)
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.api.auth.check_rate_limit_by_user",
        lambda *_, **__: JSONResponse(
            status_code=429,
            content={"code": "RATE_LIMITED"},
        ),
    )

    response = TestClient(app).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 429
    assert capture.calls == []
    assert user["tokens_valid_after"] is None


def test_account_deletion_endpoint_rate_limit_emits_no_event(monkeypatch) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user()
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.api.auth.check_rate_limit_by_user",
        lambda *_, **__: JSONResponse(
            status_code=429,
            content={"code": "RATE_LIMITED"},
        ),
    )

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {deletion_token(user)}"},
    )

    assert response.status_code == 429
    assert capture.calls == []
    assert fake.tables["users"] == [user]


def test_last_admin_deletion_rejection_emits_no_event(monkeypatch) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(role="admin")
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {deletion_token(user)}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "LAST_ADMIN"
    assert capture.calls == []
    assert fake.tables["users"] == [user]


def test_password_reset_cache_and_observability_failures_preserve_success(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    fake = FakeResetSupabaseClient([reset_password_user()])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)
    monkeypatch.setattr(
        "app.services.password_reset.invalidate_cached_user",
        lambda *_: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.password_reset.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )

    response = http.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        },
    )

    assert response.status_code == 200
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="succeeded",
            auth_method="recovery",
            reason="password_reset",
            user_id=user["id"],
        ),
    )


def test_account_deletion_cache_and_observability_failures_preserve_success(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user()
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.account_deletion.invalidate_cached_user",
        lambda *_: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.account_deletion.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {deletion_token(user)}"},
    )

    assert response.status_code == 200
    assert fake.tables["users"] == []
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="succeeded",
            auth_method="password",
            reason="account_deleted",
            user_id=None,
        ),
    )


def test_confirmed_failure_observability_failure_preserves_response(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    _, user, endpoint, body, auth_method, reason = _linking_case(
        monkeypatch,
        "unlink",
        failing_rpc="unlink_google_identity",
    )
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.authentication_audit_events.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 500
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="failed",
            auth_method=auth_method,
            reason=reason,
            user_id=user["id"],
            failure_category="internal_error",
        ),
    )


def test_ambiguous_outcome_observability_failure_preserves_response(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    _, user, endpoint, body, _, _ = _linking_case(
        monkeypatch,
        "unlink",
        ambiguous_rpc="unlink_google_identity",
    )
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.account_linking.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 500
    assert capture.calls == []


def test_jwt_reissue_and_observability_failure_preserves_success_event(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    _, user, endpoint, body, auth_method, reason = _linking_case(
        monkeypatch,
        "unlink",
    )
    _patch_audit(monkeypatch, capture)
    monkeypatch.setattr(
        "app.services.account_linking.create_access_token",
        lambda **_: (_ for _ in ()).throw(RuntimeError(DATABASE_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.account_linking.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        endpoint,
        json=body,
        headers={"Authorization": f"Bearer {linking_token(user)}"},
    )

    assert response.status_code == 500
    _assert_one_event(
        capture,
        _expected_payload(
            outcome="succeeded",
            auth_method=auth_method,
            reason=reason,
            user_id=user["id"],
        ),
    )


def test_independent_operations_receive_distinct_event_and_correlation_ids(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    fake, user, _, _, _, _ = _linking_case(monkeypatch, "set")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "phase-2-test")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.authentication_audit_events.get_supabase_service_role_client",
        lambda: capture,
    )
    token = linking_token(user)

    set_response = TestClient(app).post(
        "/auth/set-password",
        json={
            "google_token": GOOGLE_SENTINEL,
            "password": PASSWORD_SENTINEL,
            "password_confirm": PASSWORD_SENTINEL,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    remove_response = TestClient(app).post(
        "/auth/remove-password",
        json={"google_token": GOOGLE_SENTINEL},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert set_response.status_code == 200
    assert remove_response.status_code == 200
    assert len(capture.calls) == 2
    payloads = [payload for _, payload in capture.calls]
    assert [payload["p_revocation_reason"] for payload in payloads] == [
        "password_set",
        "password_removed",
    ]
    event_ids = [payload["p_event_id"] for payload in payloads]
    correlations = [payload["p_correlation_id"] for payload in payloads]
    assert all(str(UUID(value)) == value for value in event_ids)
    assert len(set(event_ids)) == 2
    assert len(set(correlations)) == 2
    assert all(len(value) == 32 for value in correlations)


@pytest.mark.parametrize("case", ["unlink", "set", "remove"])
@pytest.mark.parametrize(
    "response_data",
    [
        NULL_RPC_RESPONSE,
        None,
        [],
        [{"result": "unexpected"}, {"result": "unexpected"}],
        {"unexpected": DATABASE_SENTINEL},
    ],
    ids=[
        "null-response",
        "null-data",
        "empty-list",
        "multi-row",
        "wrong-dictionary",
    ],
)
def test_account_linking_malformed_success_response_is_ambiguous(
    monkeypatch,
    caplog,
    case: str,
    response_data: Any,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake, user, endpoint, body, _, _ = _linking_case(monkeypatch, case)
    _patch_audit(monkeypatch, capture)
    rpc_name = {
        "unlink": "unlink_google_identity",
        "set": "set_account_password",
        "remove": "remove_account_password",
    }[case]
    _override_rpc_response(
        monkeypatch,
        fake,
        rpc_name=rpc_name,
        response_data=response_data,
    )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {linking_token(user)}"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": {
            "unlink": "Failed to unlink Google account",
            "set": "Failed to set password",
            "remove": "Failed to remove password",
        }[case],
    }
    assert capture.calls == []
    assert user["tokens_valid_after"] is not None
    _assert_one_ambiguous_warning(caplog, monitoring)
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text, monitoring)


@pytest.mark.parametrize(
    "shape",
    [
        "empty-user-id",
        "invalid-user-id",
        "missing-user-id",
        "success-plus-error",
        "extra-contradictory-field",
        "null-response",
        "null-data",
        "empty-list",
        "multi-row",
        "wrong-dictionary",
    ],
)
def test_password_reset_malformed_success_response_is_ambiguous(
    monkeypatch,
    caplog,
    shape: str,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    fake = FakeResetSupabaseClient([reset_password_user(email=EMAIL_SENTINEL)])
    http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)
    response_data_by_shape: dict[str, Any] = {
        "empty-user-id": [{"result": "success", "user_id": ""}],
        "invalid-user-id": [
            {"result": "success", "user_id": MALFORMED_ID_SENTINEL}
        ],
        "missing-user-id": [{"result": "success"}],
        "success-plus-error": [
            {
                "result": "success",
                "user_id": user["id"],
                "error": DATABASE_SENTINEL,
            }
        ],
        "extra-contradictory-field": [
            {
                "result": "success",
                "user_id": user["id"],
                "result_state": DATABASE_SENTINEL,
            }
        ],
        "null-response": NULL_RPC_RESPONSE,
        "null-data": None,
        "empty-list": [],
        "multi-row": [
            {"result": "success", "user_id": user["id"]},
            {"result": "success", "user_id": user["id"]},
        ],
        "wrong-dictionary": {"unexpected": DATABASE_SENTINEL},
    }
    _override_rpc_response(
        monkeypatch,
        fake,
        rpc_name="consume_password_reset_token",
        response_data=response_data_by_shape[shape],
    )

    with caplog.at_level(logging.WARNING):
        response = http.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": PASSWORD_SENTINEL,
                "password_confirm": PASSWORD_SENTINEL,
            },
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Password reset could not be completed",
    }
    assert capture.calls == []
    assert user["tokens_valid_after"] is not None
    _assert_one_ambiguous_warning(caplog, monitoring)
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text, monitoring)


@pytest.mark.parametrize(
    "response_data",
    [
        {
            "deleted": True,
            "games_reconciled": 0,
            "error": DATABASE_SENTINEL,
        },
        {
            "deleted": True,
            "games_reconciled": 0,
            "error": "user_not_found",
        },
        {"deleted": False, "games_reconciled": 0},
        {"games_reconciled": 0},
        {"deleted": True, "games_reconciled": DATABASE_SENTINEL},
        [],
        [
            {"deleted": True, "games_reconciled": 0},
            {"deleted": True, "games_reconciled": 0},
        ],
        NULL_RPC_RESPONSE,
        None,
        {"unexpected": DATABASE_SENTINEL},
    ],
    ids=[
        "success-plus-error",
        "success-plus-user-not-found",
        "deleted-false",
        "missing-deleted",
        "invalid-games-reconciled",
        "empty-list",
        "multi-row",
        "null-response",
        "null-data",
        "wrong-dictionary",
    ],
)
def test_account_deletion_malformed_success_response_is_ambiguous(
    monkeypatch,
    caplog,
    response_data: Any,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(
        email=EMAIL_SENTINEL,
        password_hash=hash_password(PASSWORD_SENTINEL),
    )
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)
    _override_rpc_response(
        monkeypatch,
        fake,
        rpc_name="delete_user_account",
        response_data=response_data,
    )

    with caplog.at_level(logging.WARNING):
        response = _delete(
            TestClient(app, raise_server_exceptions=False),
            "/auth/account",
            body={"password": PASSWORD_SENTINEL},
            headers={"Authorization": f"Bearer {deletion_token(user)}"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "error": True,
        "code": "INTERNAL_SERVER_ERROR",
        "message": "Account deletion could not be completed",
    }
    assert capture.calls == []
    assert fake.tables["users"] == []
    _assert_one_ambiguous_warning(caplog, monitoring)
    _assert_bounded_monitoring(monitoring, user_id=user["id"])
    _assert_private(response.json(), caplog.text, monitoring)


@pytest.mark.parametrize(
    ("verifier_status", "expected_status", "expected_body"),
    [
        (
            401,
            403,
            {
                "error": True,
                "code": "INVALID_GOOGLE_TOKEN",
                "message": "Invalid Google token",
            },
        ),
        (
            403,
            403,
            {
                "error": True,
                "code": "EMAIL_NOT_VERIFIED",
                "message": "Google email address is not verified",
            },
        ),
        (
            500,
            500,
            {
                "error": True,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Google verification could not be completed",
            },
        ),
    ],
)
@pytest.mark.parametrize("case", ["set", "remove"])
def test_google_reauthentication_preserves_sanitized_status(
    monkeypatch,
    caplog,
    verifier_status: int,
    expected_status: int,
    expected_body: dict[str, Any],
    case: str,
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    _, user, endpoint, body, _, _ = _linking_case(monkeypatch, case)
    _patch_audit(monkeypatch, capture)

    def fail_verification(_token: str) -> dict[str, Any]:
        raise HTTPException(
            status_code=verifier_status,
            detail=DATABASE_SENTINEL,
        )

    monkeypatch.setattr(
        "app.services.account_linking._verify_google_token_raw",
        fail_verification,
    )

    with caplog.at_level(logging.WARNING):
        response = TestClient(app, raise_server_exceptions=False).post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {linking_token(user)}"},
        )

    assert response.status_code == expected_status
    assert response.json() == expected_body
    assert capture.calls == []
    assert user["tokens_valid_after"] is None
    assert monitoring == []

    with pytest.raises(HTTPException) as exc_info:
        account_linking._verify_google_token(GOOGLE_SENTINEL)
    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == expected_body
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_private(response.json(), exc_info.value, caplog.text, monitoring)


@pytest.mark.parametrize(
    ("verifier_status", "expected_status", "expected_body"),
    [
        (
            401,
            403,
            {
                "error": True,
                "code": "INVALID_GOOGLE_TOKEN",
                "message": "Invalid Google token",
            },
        ),
        (
            403,
            403,
            {
                "error": True,
                "code": "EMAIL_NOT_VERIFIED",
                "message": "Google email address is not verified",
            },
        ),
        (
            500,
            500,
            {
                "error": True,
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Google verification could not be completed",
            },
        ),
    ],
)
def test_account_deletion_google_reauthentication_uses_sanitized_boundary(
    monkeypatch,
    caplog,
    verifier_status: int,
    expected_status: int,
    expected_body: dict[str, Any],
) -> None:
    capture = AuditCaptureClient()
    monitoring = _capture_monitoring(monkeypatch)
    configure_deletion_settings(monkeypatch)
    user = google_only_user(
        email=EMAIL_SENTINEL,
        google_sub=PROVIDER_SENTINEL,
    )
    fake = DeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    def fail_verification(_token: str) -> dict[str, Any]:
        raise HTTPException(
            status_code=verifier_status,
            detail=DATABASE_SENTINEL,
        )

    monkeypatch.setattr(
        "app.services.account_deletion._verify_google_token_raw",
        fail_verification,
    )
    monkeypatch.setattr(
        "app.services.account_linking._verify_google_token_raw",
        fail_verification,
    )

    with caplog.at_level(logging.WARNING):
        response = _delete(
            TestClient(app, raise_server_exceptions=False),
            "/auth/account",
            body={"google_token": GOOGLE_SENTINEL},
            headers={"Authorization": f"Bearer {deletion_token(user)}"},
        )

    assert response.status_code == expected_status
    assert response.json() == expected_body
    assert capture.calls == []
    assert fake.tables["users"] == [user]
    assert user["tokens_valid_after"] is None
    assert monitoring == []

    with pytest.raises(HTTPException) as exc_info:
        account_deletion._verify_google_token_for_reauth(GOOGLE_SENTINEL)

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == expected_body
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_private(response.json(), exc_info.value, caplog.text, monitoring)


def _force_audit_boundary_failure(
    monkeypatch,
    failure_point: str,
) -> list[str]:
    target = (
        "new_audit_event_id"
        if failure_point == "event_id"
        else "new_auth_correlation_id"
        if failure_point == "correlation_id"
        else "record_authentication_event"
    )

    attempts: list[str] = []

    def fail_once(*_args, **_kwargs):
        attempts.append(failure_point)
        raise RuntimeError(AUDIT_SENTINEL)

    monkeypatch.setattr(
        f"app.services.authentication_audit_events.{target}",
        fail_once,
    )
    monkeypatch.setattr(
        "app.services.authentication_audit_events.logger.warning",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    monkeypatch.setattr(
        "app.services.authentication_observability.capture_unexpected_message",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError(AUDIT_SENTINEL)),
    )
    return attempts


@pytest.mark.parametrize(
    "operation",
    ["unlink", "set", "remove", "reset", "delete"],
)
@pytest.mark.parametrize(
    "failure_point",
    ["event_id", "correlation_id", "recorder"],
)
def test_every_phase_2_success_survives_complete_audit_boundary_failure(
    monkeypatch,
    operation: str,
    failure_point: str,
) -> None:
    capture = AuditCaptureClient()

    if operation in {"unlink", "set", "remove"}:
        fake, user, endpoint, body, _, _ = _linking_case(monkeypatch, operation)
        _patch_audit(monkeypatch, capture)
        attempts = _force_audit_boundary_failure(monkeypatch, failure_point)
        response = TestClient(app).post(
            endpoint,
            json=body,
            headers={"Authorization": f"Bearer {linking_token(user)}"},
        )
        mutation_confirmed = user["tokens_valid_after"] is not None
    elif operation == "reset":
        fake = FakeResetSupabaseClient([reset_password_user()])
        http, user, raw_token = _prepare_reset(monkeypatch, fake, capture)
        attempts = _force_audit_boundary_failure(monkeypatch, failure_point)
        response = http.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": PASSWORD_SENTINEL,
                "password_confirm": PASSWORD_SENTINEL,
            },
        )
        mutation_confirmed = user["tokens_valid_after"] is not None
    else:
        configure_deletion_settings(monkeypatch)
        user = deletion_password_user()
        fake = DeletionClient([user])
        patch_deletion_supabase(monkeypatch, fake)
        _patch_audit(monkeypatch, capture)
        attempts = _force_audit_boundary_failure(monkeypatch, failure_point)
        response = _delete(
            TestClient(app),
            "/auth/account",
            body={"password": "CorrectHorse123"},
            headers={"Authorization": f"Bearer {deletion_token(user)}"},
        )
        mutation_confirmed = fake.tables["users"] == []

    assert response.status_code == 200
    assert mutation_confirmed is True
    assert capture.calls == []
    assert attempts == [failure_point]


@pytest.mark.parametrize(
    ("case", "rpc_name"),
    [
        ("unlink", "unlink_google_identity"),
        ("set", "set_account_password"),
        ("remove", "remove_account_password"),
    ],
)
def test_account_linking_sanitized_exception_has_no_raw_chain(
    monkeypatch,
    case: str,
    rpc_name: str,
) -> None:
    capture = AuditCaptureClient()
    fake, user, _, _, _, _ = _linking_case(
        monkeypatch,
        case,
        failing_rpc=rpc_name,
    )
    _patch_audit(monkeypatch, capture)

    with pytest.raises(HTTPException) as exc_info:
        if case == "unlink":
            account_linking.unlink_google(
                user["id"],
                PASSWORD_SENTINEL,
                _request(),
            )
        elif case == "set":
            account_linking.set_password_for_user(
                user["id"],
                GOOGLE_SENTINEL,
                PASSWORD_SENTINEL,
                PASSWORD_SENTINEL,
            )
        else:
            account_linking.remove_password_for_user(
                user["id"],
                GOOGLE_SENTINEL,
            )

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_private(exc_info.value, capture.calls)


def test_password_reset_sanitized_exception_has_no_raw_chain(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    fake = FailingResetClient([reset_password_user()])
    configure_reset_settings(monkeypatch)
    email = FakeEmailDelivery()
    service = PasswordResetService(email_delivery=email, supabase_client=fake)
    _patch_audit(monkeypatch, capture)
    job = service.request_password_reset(
        email="user@example.com",
        client_ip="peer",
    ).delivery_job
    assert job is not None
    service.deliver_password_reset(job)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_password_reset(
            token=job.raw_token,
            password=PASSWORD_SENTINEL,
            password_confirm=PASSWORD_SENTINEL,
            client_ip="peer",
        )

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_private(exc_info.value, capture.calls)


@pytest.mark.parametrize(
    "client_type",
    [ConfirmRateLimitFailureClient, ConfirmRateLimitMalformedClient],
)
def test_password_reset_rate_limit_failure_has_no_raw_exception_chain(
    monkeypatch,
    client_type,
) -> None:
    capture = AuditCaptureClient()
    configure_reset_settings(monkeypatch)
    fake = client_type([reset_password_user(email=EMAIL_SENTINEL)])
    service = PasswordResetService(
        email_delivery=FakeEmailDelivery(),
        supabase_client=fake,
    )
    _patch_audit(monkeypatch, capture)
    job = service.request_password_reset(
        email=EMAIL_SENTINEL,
        client_ip="peer",
    ).delivery_job
    assert job is not None
    service.deliver_password_reset(job)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_password_reset(
            token=job.raw_token,
            password=PASSWORD_SENTINEL,
            password_confirm=PASSWORD_SENTINEL,
            client_ip="peer",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert capture.calls == []
    _assert_private(exc_info.value)


def test_committed_validation_failure_has_no_raw_chain_for_google_unlink(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    base, user, _, _, _, _ = _linking_case(monkeypatch, "unlink")
    fake = CommitThenValidationLinkingClient(
        base.tables["users"],
        base.tables["user_identities"],
    )
    patch_all_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    with pytest.raises(HTTPException) as exc_info:
        account_linking.unlink_google(
            user["id"],
            PASSWORD_SENTINEL,
            _request(),
        )

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert capture.calls == []
    _assert_private(exc_info.value)


def test_committed_validation_failure_has_no_raw_chain_for_password_reset(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    configure_reset_settings(monkeypatch)
    fake = CommitThenValidationResetClient([reset_password_user()])
    service = PasswordResetService(
        email_delivery=FakeEmailDelivery(),
        supabase_client=fake,
    )
    _patch_audit(monkeypatch, capture)
    job = service.request_password_reset(
        email="user@example.com",
        client_ip="peer",
    ).delivery_job
    assert job is not None
    service.deliver_password_reset(job)

    with pytest.raises(HTTPException) as exc_info:
        service.confirm_password_reset(
            token=job.raw_token,
            password=PASSWORD_SENTINEL,
            password_confirm=PASSWORD_SENTINEL,
            client_ip="peer",
        )

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert capture.calls == []
    _assert_private(exc_info.value)


def test_committed_validation_failure_has_no_raw_chain_for_account_deletion(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(
        password_hash=hash_password(PASSWORD_SENTINEL)
    )
    fake = CommitThenValidationDeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    with pytest.raises(HTTPException) as exc_info:
        delete_account(
            user_id=user["id"],
            password=PASSWORD_SENTINEL,
        )

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    assert capture.calls == []
    _assert_private(exc_info.value)


def test_account_deletion_sanitized_exception_has_no_raw_chain(
    monkeypatch,
) -> None:
    capture = AuditCaptureClient()
    configure_deletion_settings(monkeypatch)
    user = deletion_password_user(
        password_hash=hash_password(PASSWORD_SENTINEL)
    )
    fake = FailingDeletionClient([user])
    patch_deletion_supabase(monkeypatch, fake)
    _patch_audit(monkeypatch, capture)

    with pytest.raises(HTTPException) as exc_info:
        delete_account(
            user_id=user["id"],
            password=PASSWORD_SENTINEL,
        )

    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_private(exc_info.value, capture.calls)


@pytest.mark.parametrize(
    ("target", "operation"),
    [
        (
            "app.services.password_reset.get_supabase_service_role_client",
            lambda: PasswordResetService(),
        ),
        (
            "app.services.account_deletion.get_supabase_service_role_client",
            lambda: delete_account(user_id="00000000-0000-4000-8000-000000000099"),
        ),
    ],
)
def test_service_client_initialization_failure_has_no_raw_chain(
    monkeypatch,
    target: str,
    operation,
) -> None:
    monkeypatch.setattr(
        target,
        lambda: (_ for _ in ()).throw(RuntimeError(DATABASE_SENTINEL)),
    )

    with pytest.raises(HTTPException) as exc_info:
        operation()

    assert exc_info.value.status_code == 500
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    _assert_private(exc_info.value)
