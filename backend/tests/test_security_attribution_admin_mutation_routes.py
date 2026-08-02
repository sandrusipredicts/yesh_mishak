"""Focused attribution tests for five high-risk authenticated admin mutations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import admin
from app.main import app
from app.services import security_request_attribution as attribution
from tests.test_admin_user_moderation import (
    ADMIN_USER,
    ANOTHER_ADMIN,
    BANNED_USER,
    REGULAR_USER,
    SUSPENDED_USER,
    make_client as make_moderation_client,
    make_token,
)
from tests.test_field_delete import (
    ADMIN as FIELD_ADMIN,
    DELETE_PATH,
    VALID_BODY,
    FakeTableQuery,
    _base_tables,
    _configure as configure_field_test,
    _field,
    _headers as field_headers,
    _make_client as make_field_client,
)


MODERATION_CASES = (
    (
        "ban",
        REGULAR_USER,
        {"reason": "Spamming"},
        "admin_user_ban",
    ),
    (
        "unban",
        BANNED_USER,
        {},
        "admin_user_unban",
    ),
    (
        "suspend",
        REGULAR_USER,
        {"reason": "Abusive behavior"},
        "admin_user_suspend",
    ),
    (
        "unsuspend",
        SUSPENDED_USER,
        {},
        "admin_user_unsuspend",
    ),
)

BASE_REGISTRY = {
    ("session_security_change", "auth_logout", "POST"),
    ("credential_method_change", "auth_google_link", "POST"),
    ("credential_method_change", "auth_google_unlink", "POST"),
    ("credential_method_change", "auth_password_set", "POST"),
    ("credential_method_change", "auth_password_remove", "POST"),
    ("account_lifecycle_change", "auth_account_delete", "DELETE"),
}
SELECTED_REGISTRY = {
    ("admin_account_control", "admin_user_ban", "POST"),
    ("admin_account_control", "admin_user_unban", "POST"),
    ("admin_account_control", "admin_user_suspend", "POST"),
    ("admin_account_control", "admin_user_unsuspend", "POST"),
    ("admin_content_control", "admin_field_delete", "DELETE"),
}


def capture_attribution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failure: Exception | None = None,
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def record(**kwargs: Any) -> None:
        calls.append(kwargs)
        if failure is not None:
            raise failure

    monkeypatch.setattr(admin, "record_authenticated_security_event", record)
    return calls


def assert_event(
    event: dict[str, Any],
    *,
    actor_id: str,
    route_key: str,
    event_category: str,
    method: str,
    outcome: str,
    failure_category: str | None,
) -> None:
    assert event == {
        "trusted_account_uuid": actor_id,
        "route_key": route_key,
        "event_category": event_category,
        "http_method": method,
        "outcome": outcome,
        "failure_category": failure_category,
        "server_correlation_id": None,
    }


def test_registry_expands_from_six_to_exactly_eleven_approved_tuples() -> None:
    assert attribution._APPROVED_ROUTE_REGISTRY == frozenset(
        BASE_REGISTRY | SELECTED_REGISTRY
    )


@pytest.mark.parametrize(
    "action,target,body,route_key",
    MODERATION_CASES,
)
def test_successful_account_control_attributes_authenticated_admin_only(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    target: dict[str, Any],
    body: dict[str, str],
    route_key: str,
) -> None:
    client, _ = make_moderation_client(monkeypatch)
    calls = capture_attribution(monkeypatch)

    response = client.post(
        f"/admin/users/{target['id']}/{action}",
        json=body,
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert_event(
        calls[0],
        actor_id=ADMIN_USER["id"],
        route_key=route_key,
        event_category="admin_account_control",
        method="POST",
        outcome="succeeded",
        failure_category=None,
    )
    serialized = repr(calls[0])
    assert target["id"] not in serialized
    assert target["email"] not in serialized
    assert body.get("reason", "not-present") not in serialized


def test_successful_field_removal_attributes_authenticated_admin_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_field_test(monkeypatch)
    client = make_field_client(monkeypatch, _base_tables(_field()))
    calls = capture_attribution(monkeypatch)

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json=VALID_BODY,
        headers=field_headers(FIELD_ADMIN),
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert_event(
        calls[0],
        actor_id=FIELD_ADMIN["id"],
        route_key="admin_field_delete",
        event_category="admin_content_control",
        method="DELETE",
        outcome="succeeded",
        failure_category=None,
    )
    serialized = repr(calls[0])
    assert "field-1" not in serialized
    assert VALID_BODY["reason"] not in serialized
    assert FIELD_ADMIN["email"] not in serialized


@pytest.mark.parametrize(
    "path,body,expected_route,expected_outcome,expected_failure",
    (
        (
            "/admin/users/00000000-0000-0000-0000-000000099999/ban",
            {"reason": "test"},
            "admin_user_ban",
            "failed",
            "not_found",
        ),
        (
            f"/admin/users/{ANOTHER_ADMIN['id']}/ban",
            {"reason": "test"},
            "admin_user_ban",
            "denied",
            "authorization_denied",
        ),
        (
            f"/admin/users/{REGULAR_USER['id']}/unban",
            {},
            "admin_user_unban",
            "failed",
            "conflict",
        ),
    ),
)
def test_account_control_failures_use_bounded_categories(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    body: dict[str, str],
    expected_route: str,
    expected_outcome: str,
    expected_failure: str,
) -> None:
    client, _ = make_moderation_client(monkeypatch)
    calls = capture_attribution(monkeypatch)

    response = client.post(
        path,
        json=body,
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code in {400, 404}
    assert len(calls) == 1
    assert_event(
        calls[0],
        actor_id=ADMIN_USER["id"],
        route_key=expected_route,
        event_category="admin_account_control",
        method="POST",
        outcome=expected_outcome,
        failure_category=expected_failure,
    )


def test_repeated_field_removal_records_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_field_test(monkeypatch)
    removed = _field(
        removed_at="2026-01-02T00:00:00+00:00",
        removed_by="admin-1",
        removal_reason="other",
    )
    client = make_field_client(monkeypatch, _base_tables(removed))
    calls = capture_attribution(monkeypatch)

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json=VALID_BODY,
        headers=field_headers(FIELD_ADMIN),
    )

    assert response.status_code == 409
    assert len(calls) == 1
    assert_event(
        calls[0],
        actor_id=FIELD_ADMIN["id"],
        route_key="admin_field_delete",
        event_category="admin_content_control",
        method="DELETE",
        outcome="failed",
        failure_category="conflict",
    )


def test_field_removal_database_failure_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_field_test(monkeypatch)
    client = make_field_client(monkeypatch, _base_tables(_field()))
    calls = capture_attribution(monkeypatch)

    def failing_update(self: FakeTableQuery, payload: dict[str, Any]) -> FakeTableQuery:
        self.update_payload = payload

        def fail_execute() -> None:
            raise RuntimeError("sensitive provider error")

        self.execute = fail_execute
        return self

    monkeypatch.setattr(FakeTableQuery, "update", failing_update)

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json=VALID_BODY,
        headers=field_headers(FIELD_ADMIN),
    )

    assert response.status_code == 500
    assert "sensitive provider error" not in response.text
    assert len(calls) == 1
    assert_event(
        calls[0],
        actor_id=FIELD_ADMIN["id"],
        route_key="admin_field_delete",
        event_category="admin_content_control",
        method="DELETE",
        outcome="ambiguous",
        failure_category="outcome_unknown",
    )


def test_unexpected_account_control_failure_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    make_moderation_client(monkeypatch)
    calls = capture_attribution(monkeypatch)

    def fail_operation(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError("sensitive provider error")

    monkeypatch.setattr(admin, "_execute_moderation_action", fail_operation)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/suspend",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 500
    assert "sensitive provider error" not in response.text
    assert len(calls) == 1
    assert_event(
        calls[0],
        actor_id=ADMIN_USER["id"],
        route_key="admin_user_suspend",
        event_category="admin_account_control",
        method="POST",
        outcome="ambiguous",
        failure_category="outcome_unknown",
    )


@pytest.mark.parametrize(
    "action,target,body,route_key",
    MODERATION_CASES,
)
def test_attribution_failure_does_not_change_successful_account_control(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    target: dict[str, Any],
    body: dict[str, str],
    route_key: str,
) -> None:
    del route_key
    client, _ = make_moderation_client(monkeypatch)
    capture_attribution(
        monkeypatch,
        failure=RuntimeError("attribution unavailable"),
    )

    response = client.post(
        f"/admin/users/{target['id']}/{action}",
        json=body,
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200


def test_attribution_failure_does_not_change_successful_field_removal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_field_test(monkeypatch)
    client = make_field_client(monkeypatch, _base_tables(_field()))
    capture_attribution(
        monkeypatch,
        failure=RuntimeError("attribution unavailable"),
    )

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json=VALID_BODY,
        headers=field_headers(FIELD_ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["field"]["removed_at"] is not None


def test_attribution_failure_does_not_change_business_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = make_moderation_client(monkeypatch)
    capture_attribution(
        monkeypatch,
        failure=RuntimeError("attribution unavailable"),
    )

    response = client.post(
        "/admin/users/00000000-0000-0000-0000-000000099999/ban",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "USER_NOT_FOUND"


def test_ordinary_user_denial_happens_before_attribution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = make_moderation_client(monkeypatch)
    calls = capture_attribution(monkeypatch)

    response = client.post(
        f"/admin/users/{BANNED_USER['id']}/unban",
        json={},
        headers={"Authorization": f"Bearer {make_token(REGULAR_USER)}"},
    )

    assert response.status_code == 403
    assert calls == []


@pytest.mark.parametrize(
    "factory",
    (
        lambda: ("admin_account_control", "admin_user_ban", "POST"),
        lambda: ("admin_content_control", "admin_field_delete", "DELETE"),
    ),
)
def test_selected_registry_tuples_create_valid_events(
    factory: Callable[[], tuple[str, str, str]],
) -> None:
    category, route_key, method = factory()
    recorder = attribution.SecurityAttributionRecorder()

    event = recorder.create_event(
        trusted_account_uuid="00000000-0000-0000-0000-000000000001",
        route_key=route_key,
        event_category=category,
        http_method=method,
        outcome="succeeded",
        failure_category=None,
    )

    assert event.route_key == route_key
