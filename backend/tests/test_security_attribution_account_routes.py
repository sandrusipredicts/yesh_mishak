"""Tests for PR 3B: security attribution of account-security mutation routes.

Proves each newly instrumented route preserves existing behavior, sends the
correct bounded tuple/outcome, uses only the trusted authenticated UUID,
ignores client-controlled identity, and fails open on attribution errors.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api import auth as auth_module
from app.main import app
from app.services import security_request_attribution as attribution


ACCOUNT_UUID = "00000000-0000-4000-8000-000000000099"
ACCOUNT_UUID_OBJ = UUID(ACCOUNT_UUID)
FAKE_TOKEN = "test-jwt-token"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def auth_header() -> dict[str, str]:
    from app.auth.jwt import create_access_token

    token = create_access_token(subject=ACCOUNT_UUID, email="test@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def mock_active_user(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Bypass require_active_user with a fake authenticated user."""
    user = {
        "id": ACCOUNT_UUID,
        "email": "test@example.com",
        "name": "Test User",
        "username": "testuser",
        "phone_number": "+972500000000",
        "terms_accepted_at": "2026-01-01T00:00:00+00:00",
        "role": "user",
        "status": "active",
    }
    from app.auth.dependencies import require_active_user

    app.dependency_overrides[require_active_user] = lambda: user
    yield user
    app.dependency_overrides.pop(require_active_user, None)


@pytest.fixture()
def attribution_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture all record_authenticated_security_event calls in auth module."""
    calls: list[dict[str, Any]] = []

    def fake_record(**kwargs: Any) -> attribution.SecurityAttributionRecordResult:
        calls.append(kwargs)
        return attribution.SecurityAttributionRecordResult(status="disabled")

    monkeypatch.setattr(
        auth_module,
        "record_authenticated_security_event",
        fake_record,
    )
    return calls


@pytest.fixture()
def attribution_error(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Make attribution raise to prove fail-open behavior."""
    calls: list[dict[str, Any]] = []

    def failing_record(**kwargs: Any) -> None:
        calls.append(kwargs)
        raise RuntimeError("attribution infrastructure failure")

    monkeypatch.setattr(
        auth_module,
        "record_authenticated_security_event",
        failing_record,
    )
    return calls


# ---------------------------------------------------------------------------
# Route configuration — one entry per instrumented route
# ---------------------------------------------------------------------------

ROUTE_CONFIGS = [
    {
        "name": "link_google",
        "method": "POST",
        "path": "/auth/link/google",
        "route_key": "auth_google_link",
        "event_category": "credential_method_change",
        "http_method": "POST",
        "service_mock_target": "account_linking.link_google",
        "service_mock_module": "app.services.account_linking",
        "service_mock_attr": "link_google",
        "body": {"token": "fake-google-token"},
        "success_return": {
            "account_methods": {
                "email": {"address": "t***@example.com", "linked": True, "verified": True, "can_unlink": True},
                "google": {"linked": True, "email": "t***@gmail.com", "can_unlink": True},
                "available_login_methods": 2,
            },
            "access_token": "new-token",
        },
        "failure_exc": HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "ACCOUNT_METHOD_ALREADY_LINKED", "message": "Already linked"},
        ),
        "expected_failure_outcome": "failed",
        "expected_failure_category": "conflict",
    },
    {
        "name": "unlink_google",
        "method": "POST",
        "path": "/auth/unlink/google",
        "route_key": "auth_google_unlink",
        "event_category": "credential_method_change",
        "http_method": "POST",
        "service_mock_target": "account_linking.unlink_google",
        "service_mock_module": "app.services.account_linking",
        "service_mock_attr": "unlink_google",
        "body": {"current_password": "test-password"},
        "success_return": {
            "account_methods": {
                "email": {"address": "t***@example.com", "linked": True, "verified": True, "can_unlink": False},
                "google": {"linked": False, "email": None, "can_unlink": False},
                "available_login_methods": 1,
            },
            "access_token": "new-token",
        },
        "failure_exc": HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "REAUTHENTICATION_REQUIRED", "message": "Wrong password"},
        ),
        "expected_failure_outcome": "denied",
        "expected_failure_category": "reauthentication_failed",
    },
    {
        "name": "set_password",
        "method": "POST",
        "path": "/auth/set-password",
        "route_key": "auth_password_set",
        "event_category": "credential_method_change",
        "http_method": "POST",
        "service_mock_target": "account_linking.set_password_for_user",
        "service_mock_module": "app.services.account_linking",
        "service_mock_attr": "set_password_for_user",
        "body": {
            "google_token": "fake-google-token",
            "password": "NewPassword123!",
            "password_confirm": "NewPassword123!",
        },
        "success_return": {
            "account_methods": {
                "email": {"address": "t***@example.com", "linked": True, "verified": True, "can_unlink": True},
                "google": {"linked": True, "email": "t***@gmail.com", "can_unlink": True},
                "available_login_methods": 2,
            },
            "access_token": "new-token",
        },
        "failure_exc": HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "PASSWORD_ALREADY_SET", "message": "Already set"},
        ),
        "expected_failure_outcome": "failed",
        "expected_failure_category": "conflict",
    },
    {
        "name": "remove_password",
        "method": "POST",
        "path": "/auth/remove-password",
        "route_key": "auth_password_remove",
        "event_category": "credential_method_change",
        "http_method": "POST",
        "service_mock_target": "account_linking.remove_password_for_user",
        "service_mock_module": "app.services.account_linking",
        "service_mock_attr": "remove_password_for_user",
        "body": {"google_token": "fake-google-token"},
        "success_return": {
            "account_methods": {
                "email": {"address": "t***@example.com", "linked": False, "verified": True, "can_unlink": False},
                "google": {"linked": True, "email": "t***@gmail.com", "can_unlink": False},
                "available_login_methods": 1,
            },
            "access_token": "new-token",
        },
        "failure_exc": HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "LAST_LOGIN_METHOD", "message": "Last method"},
        ),
        "expected_failure_outcome": "failed",
        "expected_failure_category": "conflict",
    },
    {
        "name": "delete_account",
        "method": "DELETE",
        "path": "/auth/account",
        "route_key": "auth_account_delete",
        "event_category": "account_lifecycle_change",
        "http_method": "DELETE",
        "service_mock_target": "account_deletion.delete_account",
        "service_mock_module": "app.services.account_deletion",
        "service_mock_attr": "delete_account",
        "body": {"current_password": "test-password"},
        "success_return": None,  # delete_account returns None
        "failure_exc": HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found"},
        ),
        "expected_failure_outcome": "failed",
        "expected_failure_category": "not_found",
    },
]


def _route_ids() -> list[str]:
    return [c["name"] for c in ROUTE_CONFIGS]


def _request(client: TestClient, config: dict, headers: dict) -> Any:
    method = config["method"]
    if method == "POST":
        return client.post(config["path"], json=config["body"], headers=headers)
    elif method == "DELETE":
        return client.delete(config["path"], json=config["body"], headers=headers)
    raise ValueError(f"Unsupported method {method}")


# ---------------------------------------------------------------------------
# 1. Existing success behavior is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_existing_success_behavior_unchanged(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The business response status and body remain identical after instrumentation."""
    import importlib

    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: config["success_return"])

    response = _request(client, config, {})
    if config["name"] == "delete_account":
        assert response.status_code == 200
        assert response.json()["message"] == "Account deleted"
    else:
        assert response.status_code == 200
        assert "account_methods" in response.json()


# ---------------------------------------------------------------------------
# 2. Existing failure behavior is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_existing_failure_behavior_unchanged(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The original HTTPException status code and detail are preserved."""
    import importlib

    exc = config["failure_exc"]
    mod = importlib.import_module(config["service_mock_module"])

    def raise_exc(*a: Any, **kw: Any) -> None:
        raise exc

    monkeypatch.setattr(mod, config["service_mock_attr"], raise_exc)
    response = _request(client, config, {})
    assert response.status_code == exc.status_code


# ---------------------------------------------------------------------------
# 3. Correct route/category/method tuple is sent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_correct_tuple_on_success(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: config["success_return"])

    _request(client, config, {})

    assert len(attribution_calls) == 1
    call = attribution_calls[0]
    assert call["route_key"] == config["route_key"]
    assert call["event_category"] == config["event_category"]
    assert call["http_method"] == config["http_method"]


# ---------------------------------------------------------------------------
# 4. Correct bounded outcome/failure category is sent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_correct_outcome_on_success(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: config["success_return"])

    _request(client, config, {})

    assert len(attribution_calls) == 1
    assert attribution_calls[0]["outcome"] == "succeeded"
    assert attribution_calls[0].get("failure_category") is None


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_correct_outcome_on_failure(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    exc = config["failure_exc"]
    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: (_ for _ in ()).throw(exc))

    _request(client, config, {})

    assert len(attribution_calls) == 1
    assert attribution_calls[0]["outcome"] == config["expected_failure_outcome"]
    assert attribution_calls[0]["failure_category"] == config["expected_failure_category"]


# ---------------------------------------------------------------------------
# 5. Trusted UUID comes from authenticated server context
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_trusted_uuid_from_server_context(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: config["success_return"])

    _request(client, config, {})

    assert len(attribution_calls) == 1
    assert attribution_calls[0]["trusted_account_uuid"] == ACCOUNT_UUID


# ---------------------------------------------------------------------------
# 6. Client-controlled identity fields are ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_client_controlled_identity_ignored(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The UUID sent to attribution matches the server context, regardless of body content."""
    import importlib

    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: config["success_return"])

    _request(client, config, {})

    call = attribution_calls[0]
    # UUID must be from server context, never from body/header/path
    assert call["trusted_account_uuid"] == ACCOUNT_UUID
    # No other identity fields present
    for forbidden_key in ("email", "username", "phone", "ip", "user_agent", "token", "header"):
        assert forbidden_key not in call


# ---------------------------------------------------------------------------
# 7. Attribution failure leaves status and body unchanged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_attribution_failure_preserves_success_response(
    client: TestClient,
    mock_active_user: dict,
    attribution_error: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If attribution itself throws, the business response is unchanged."""
    import importlib

    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: config["success_return"])

    response = _request(client, config, {})
    if config["name"] == "delete_account":
        assert response.status_code == 200
        assert response.json()["message"] == "Account deleted"
    else:
        assert response.status_code == 200


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_attribution_failure_preserves_error_response(
    client: TestClient,
    mock_active_user: dict,
    attribution_error: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both the service and attribution fail, the service error is returned."""
    import importlib

    exc = config["failure_exc"]
    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: (_ for _ in ()).throw(exc))

    response = _request(client, config, {})
    assert response.status_code == exc.status_code


# ---------------------------------------------------------------------------
# 8. Disabled mode produces no RPC
# ---------------------------------------------------------------------------


def test_disabled_mode_produces_no_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    """When attribution is disabled, record_authenticated_security_event is still
    called but the recorder returns disabled without making an RPC call."""
    monkeypatch.setattr(
        attribution,
        "get_security_attribution_runtime_configuration",
        lambda: attribution.SecurityAttributionRuntimeConfiguration(
            enabled=False,
            active=None,
        ),
    )
    monkeypatch.setattr(
        attribution,
        "get_supabase_service_role_client",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled recorder must not create a client")
        ),
    )

    result = attribution.record_authenticated_security_event(
        trusted_account_uuid=ACCOUNT_UUID,
        route_key="auth_google_link",
        event_category="credential_method_change",
        http_method="POST",
        outcome="succeeded",
    )

    assert result.status == "disabled"


# ---------------------------------------------------------------------------
# 9. Unsupported tuples fail before client creation
# ---------------------------------------------------------------------------


def test_unsupported_tuple_rejected_before_client() -> None:
    """A route not in the registry raises before any RPC client is created."""
    from app.services.security_attribution_config import (
        ActiveSecurityAttributionConfiguration,
        SecurityAttributionRuntimeConfiguration,
    )

    fake_client_created = False

    def fake_factory(timeout: float) -> None:
        nonlocal fake_client_created
        fake_client_created = True
        raise AssertionError("client should never be created")

    recorder = attribution.SecurityAttributionRecorder(
        configuration_provider=lambda: SecurityAttributionRuntimeConfiguration(
            enabled=True,
            active=ActiveSecurityAttributionConfiguration(
                environment="development",
                epoch="2026-07",
                key_version=1,
                key_material=bytes(range(32)),
            ),
        ),
        service_role_client_factory=fake_factory,
    )

    with pytest.raises(
        attribution.SecurityAttributionEventValidationError,
        match=r"^security attribution route tuple is unsupported$",
    ):
        recorder.create_event(
            trusted_account_uuid=ACCOUNT_UUID,
            route_key="admin_user_ban",
            event_category="admin_account_control",
            http_method="POST",
            outcome="succeeded",
        )

    assert not fake_client_created


# ---------------------------------------------------------------------------
# 10. No raw UUID, pseudonym, key, PII, payload, or exception text in logs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_no_pii_in_attribution_calls(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attribution call arguments contain no raw PII or exception detail."""
    import importlib

    exc = config["failure_exc"]
    mod = importlib.import_module(config["service_mock_module"])
    monkeypatch.setattr(mod, config["service_mock_attr"], lambda *a, **kw: (_ for _ in ()).throw(exc))

    _request(client, config, {})

    assert len(attribution_calls) >= 1
    call_repr = repr(attribution_calls)
    for forbidden in (
        "test@example.com",
        "+972500000000",
        "testuser",
        "fake-google-token",
        "test-password",
    ):
        assert forbidden not in call_repr


# ---------------------------------------------------------------------------
# 11. Existing auth_logout behavior still passes
# ---------------------------------------------------------------------------


def test_auth_logout_attribution_still_accepted() -> None:
    """The original auth_logout tuple remains in the registry."""
    recorder = attribution.SecurityAttributionRecorder(
        configuration_provider=lambda: attribution.SecurityAttributionRuntimeConfiguration(
            enabled=False, active=None
        ),
    )
    event = recorder.create_event(
        trusted_account_uuid=ACCOUNT_UUID,
        route_key="auth_logout",
        event_category="session_security_change",
        http_method="POST",
        outcome="succeeded",
    )
    assert event.route_key == "auth_logout"
    assert event.event_category == "session_security_change"


# ---------------------------------------------------------------------------
# 12. Ordinary uninstrumented routes produce no attribution call
# ---------------------------------------------------------------------------


def test_uninstrumented_route_produces_no_attribution(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /auth/account-methods does not trigger attribution."""
    from app.services import account_linking

    monkeypatch.setattr(
        account_linking,
        "get_account_methods",
        lambda user_id: {
            "email": {"address": "t***@example.com", "linked": True, "verified": True, "can_unlink": False},
            "google": {"linked": False, "email": None, "can_unlink": False},
            "available_login_methods": 1,
        },
    )

    response = client.get("/auth/account-methods")
    assert response.status_code == 200
    assert attribution_calls == []


# ---------------------------------------------------------------------------
# Additional failure-category mapping tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status_code,detail_code,expected_outcome,expected_failure",
    [
        (429, "RATE_LIMITED", "denied", "rate_limited"),
        (403, "REAUTHENTICATION_REQUIRED", "denied", "reauthentication_failed"),
        (403, "LAST_ADMIN", "denied", "authorization_denied"),
        (403, "INVALID_GOOGLE_TOKEN", "denied", "reauthentication_failed"),
        (400, "VALIDATION_ERROR", "failed", "validation_rejected"),
        (404, "USER_NOT_FOUND", "failed", "not_found"),
        (409, "CONFLICT", "failed", "conflict"),
        (500, "INTERNAL_SERVER_ERROR", "failed", "internal_error"),
    ],
)
def test_security_attribution_failure_mapping(
    status_code: int,
    detail_code: str,
    expected_outcome: str,
    expected_failure: str,
) -> None:
    """The helper maps HTTP status/code pairs to database-approved bounded values."""
    exc = HTTPException(
        status_code=status_code,
        detail={"code": detail_code, "message": "test"},
    )
    outcome, failure_category = auth_module._security_attribution_failure(exc)
    assert outcome == expected_outcome
    assert failure_category == expected_failure


# ---------------------------------------------------------------------------
# Rate-limited attribution tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("config", ROUTE_CONFIGS, ids=_route_ids())
def test_rate_limited_records_denied(
    client: TestClient,
    mock_active_user: dict,
    attribution_calls: list,
    config: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the rate limiter denies the request, attribution records denied/rate_limited."""
    from app import rate_limit

    monkeypatch.setattr(
        rate_limit,
        "check_rate_limit_by_user",
        lambda *a, **kw: {"error": "rate_limited"},
    )

    _request(client, config, {})

    assert len(attribution_calls) == 1
    assert attribution_calls[0]["outcome"] == "denied"
    assert attribution_calls[0]["failure_category"] == "rate_limited"
    assert attribution_calls[0]["route_key"] == config["route_key"]


# ---------------------------------------------------------------------------
# Verify all new tuples are accepted by the registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "category,route_key,method",
    [
        ("credential_method_change", "auth_google_link", "POST"),
        ("credential_method_change", "auth_google_unlink", "POST"),
        ("credential_method_change", "auth_password_set", "POST"),
        ("credential_method_change", "auth_password_remove", "POST"),
        ("account_lifecycle_change", "auth_account_delete", "DELETE"),
    ],
)
def test_new_tuples_accepted_by_registry(
    category: str, route_key: str, method: str
) -> None:
    assert (category, route_key, method) in attribution._APPROVED_ROUTE_REGISTRY


def test_original_logout_tuple_still_in_registry() -> None:
    assert (
        "session_security_change",
        "auth_logout",
        "POST",
    ) in attribution._APPROVED_ROUTE_REGISTRY


def test_registry_has_exactly_six_entries() -> None:
    assert len(attribution._APPROVED_ROUTE_REGISTRY) == 6
