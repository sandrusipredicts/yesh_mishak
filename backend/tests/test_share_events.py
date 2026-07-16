from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class FakeTableQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.inserted: dict[str, Any] | None = None
        self.exact_count = False

    def select(self, _: str = "*", count: str | None = None) -> "FakeTableQuery":
        self.exact_count = count == "exact"
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def gte(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append(("__gte", (column, value)))
        return self

    def lt(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append(("__lt", (column, value)))
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.inserted = dict(payload)
        return self

    def execute(self) -> FakeResponse:
        if self.inserted is not None:
            self.rows.append(dict(self.inserted))
            return FakeResponse([dict(self.inserted)])

        rows = self.rows
        for column, value in self.filters:
            if column == "__gte":
                col, threshold = value
                rows = [row for row in rows if (row.get(col) or "") >= threshold]
            elif column == "__lt":
                col, threshold = value
                rows = [row for row in rows if (row.get(col) or "") < threshold]
            else:
                rows = [row for row in rows if row.get(column) == value]
        return FakeResponse([dict(row) for row in rows], len(rows) if self.exact_count else None)


class FakeSupabaseClient:
    def __init__(self, user: dict[str, Any], *, fail_share_insert: bool = False) -> None:
        self.tables = {
            "users": [user],
            "share_events": [],
            "api_request_metrics": [],
        }
        self.fail_share_insert = fail_share_insert

    def table(self, table_name: str) -> FakeTableQuery:
        if table_name == "share_events" and self.fail_share_insert:
            raise RuntimeError("share event table unavailable")
        return FakeTableQuery(self.tables.setdefault(table_name, []))


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def make_user() -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "user@example.com",
        "name": "User",
        "role": "user",
        "status": "active",
    }


def make_client(monkeypatch, *, fail_share_insert: bool = False) -> tuple[TestClient, FakeSupabaseClient, dict[str, Any]]:
    configure_test_settings(monkeypatch)
    user = make_user()
    fake_client = FakeSupabaseClient(user, fail_share_insert=fail_share_insert)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.services.share_events.get_supabase_service_role_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: fake_client,
    )
    return TestClient(app), fake_client, user


def post_event(client: TestClient, user: dict[str, Any], payload: dict[str, Any]):
    return client.post(
        "/analytics/share-events",
        json=payload,
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )


def valid_share_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "event_name": "share_action",
        "entity_type": "game",
        "platform": "android",
        "mechanism": "native_share",
        "outcome": "shared",
        **overrides,
    }


def valid_link_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "event_name": "link_open",
        "entity_type": "field",
        "platform": "web",
        "outcome": "valid",
        **overrides,
    }


def test_valid_share_action_persists_closed_payload(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_event(client, user, valid_share_payload())

    assert response.status_code == 202
    assert fake_client.tables["share_events"] == [valid_share_payload()]


def test_valid_link_open_persists_without_mechanism(monkeypatch) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_event(client, user, valid_link_payload(outcome="not_found", error_category="resource_not_found"))

    assert response.status_code == 202
    assert fake_client.tables["share_events"] == [
        valid_link_payload(outcome="not_found", error_category="resource_not_found")
    ]


@pytest.mark.parametrize(
    "payload",
    [
        valid_share_payload(event_name="share_sent"),
        valid_share_payload(mechanism="sms"),
        valid_share_payload(platform="desktop"),
        valid_share_payload(outcome="delivered"),
        valid_share_payload(entity_type="app"),
        valid_link_payload(mechanism="native_share"),
        valid_link_payload(outcome="copied"),
    ],
)
def test_invalid_enum_values_are_rejected(monkeypatch, payload: dict[str, Any]) -> None:
    client, fake_client, user = make_client(monkeypatch)

    response = post_event(client, user, payload)

    assert response.status_code == 422
    assert fake_client.tables["share_events"] == []


@pytest.mark.parametrize("field_name", ["user_id", "game_id", "field_id", "url", "query", "receiving_app", "metadata"])
def test_prohibited_and_unexpected_fields_are_rejected(monkeypatch, field_name: str) -> None:
    client, fake_client, user = make_client(monkeypatch)
    payload = valid_share_payload(**{field_name: "prohibited"})

    response = post_event(client, user, payload)

    assert response.status_code == 422
    assert fake_client.tables["share_events"] == []


def test_requires_authenticated_user(monkeypatch) -> None:
    client, fake_client, _ = make_client(monkeypatch)

    response = client.post("/analytics/share-events", json=valid_share_payload())

    assert response.status_code == 401
    assert fake_client.tables["share_events"] == []


def test_rate_limit_applies_per_user(monkeypatch) -> None:
    client, _, user = make_client(monkeypatch)

    for _ in range(60):
        assert post_event(client, user, valid_share_payload()).status_code == 202

    response = post_event(client, user, valid_share_payload())

    assert response.status_code == 429


def test_persistence_failure_returns_unavailable_without_leaking_payload(monkeypatch, caplog) -> None:
    client, _, user = make_client(monkeypatch, fail_share_insert=True)

    response = post_event(client, user, valid_share_payload())

    assert response.status_code == 503
    assert response.json()["code"] == "ANALYTICS_UNAVAILABLE"
    assert "00000000" not in caplog.text
    assert "https://" not in caplog.text
