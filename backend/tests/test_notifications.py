from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]], count: int | None = None) -> None:
        self.data = data
        self.count = count


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.selected_columns: list[str] | None = None
        self.order_by: tuple[str, bool] | None = None
        self.limit_count: int | None = None
        self.insert_payload: dict[str, Any] | list[dict[str, Any]] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.delete_requested = False

    def select(self, columns: str = "*", count: str | None = None) -> "FakeQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.database.raise_if_missing_column(self.table_name, column)
        self.filters.append((column, value))
        return self

    def is_(self, column: str, value: Any) -> "FakeQuery":
        if value == "null":
            self.filters.append((column, None))
        else:
            self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.in_filters.append((column, values))
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.order_by = (column, desc)
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "FakeQuery":
        payloads = payload if isinstance(payload, list) else [payload]
        for row in payloads:
            for column in row:
                self.database.raise_if_missing_column(self.table_name, column)
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.update_payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self.delete_requested = True
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            payloads = self.insert_payload if isinstance(self.insert_payload, list) else [self.insert_payload]
            inserted = []
            for payload in payloads:
                row = dict(payload)
                row.setdefault("id", self.database.next_id(self.table_name))
                self.database.tables[self.table_name].append(row)
                inserted.append(deepcopy(row))
            return FakeResponse(inserted)

        rows = self._filtered_rows()

        if self.update_payload is not None:
            updated = []
            for row in rows:
                row.update(self.update_payload)
                updated.append(deepcopy(row))
            return FakeResponse(updated)

        if self.delete_requested:
            ids_to_delete = {id(row) for row in rows}
            self.database.tables[self.table_name] = [
                row for row in self.database.tables[self.table_name] if id(row) not in ids_to_delete
            ]
            return FakeResponse([])

        return FakeResponse([self._select(row) for row in rows])

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = self.database.tables.setdefault(self.table_name, [])
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        if self.order_by:
            column, desc = self.order_by
            rows = sorted(rows, key=lambda row: row.get(column) or "", reverse=desc)
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return rows

    def _select(self, row: dict[str, Any]) -> dict[str, Any]:
        if not self.selected_columns or "*" in self.selected_columns:
            return deepcopy(row)
        return {column: row.get(column) for column in self.selected_columns}


class FakeSupabase:
    def __init__(
        self,
        tables: dict[str, list[dict[str, Any]]],
        missing_columns: dict[str, set[str]] | None = None,
    ) -> None:
        self.tables = tables
        self.counters: dict[str, int] = {}
        self.missing_columns = missing_columns or {}

    def table(self, table_name: str) -> FakeQuery:
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)

    def raise_if_missing_column(self, table_name: str, column_name: str) -> None:
        if column_name in self.missing_columns.get(table_name, set()):
            raise APIError(
                {
                    "code": "42703",
                    "details": None,
                    "hint": None,
                    "message": f"column {table_name}.{column_name} does not exist",
                }
            )

    def next_id(self, table_name: str) -> str:
        self.counters[table_name] = self.counters.get(table_name, 0) + 1
        return f"{table_name}-{self.counters[table_name]}"


@pytest.fixture
def users() -> dict[str, dict[str, Any]]:
    return {
        "organizer": {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "organizer@example.com",
            "name": "Organizer",
            "role": "user",
        },
        "candidate": {
            "id": "00000000-0000-0000-0000-000000000002",
            "email": "candidate@example.com",
            "name": "Candidate",
            "role": "user",
        },
        "other": {
            "id": "00000000-0000-0000-0000-000000000003",
            "email": "other@example.com",
            "name": "Other",
            "role": "user",
        },
        "admin": {
            "id": "00000000-0000-0000-0000-000000000004",
            "email": "admin@example.com",
            "name": "Admin",
            "role": "admin",
        },
    }


@pytest.fixture
def fake_supabase(monkeypatch, users: dict[str, dict[str, Any]]) -> FakeSupabase:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    fake = FakeSupabase(
        {
            "users": list(users.values()),
            "fields": [
                {
                    "id": "00000000-0000-0000-0000-000000000101",
                    "name": "Central Court",
                    "lat": 30.9872,
                    "lng": 34.9314,
                    "city": "ירוחם",
                    "sport_type": "both",
                    "verified": True,
                    "approval_status": "approved",
                }
            ],
            "games": [],
            "game_players": [],
            "notification_preferences": [],
            "notifications": [],
            "push_tokens": [],
        }
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    return fake


@pytest.fixture
def fake_service_supabase() -> FakeSupabase:
    return FakeSupabase({"notifications": [], "push_tokens": []})


def auth_headers(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def test_get_notifications_returns_only_current_user_notifications(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notification-older",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "Older",
            "body": "Older body",
            "read_at": None,
            "created_at": "2026-06-15T10:00:00+00:00",
        },
        {
            "id": "notification-other",
            "user_id": users["other"]["id"],
            "type": "game_created",
            "title": "Other",
            "body": "Other body",
            "read_at": None,
            "created_at": "2026-06-16T10:00:00+00:00",
        },
        {
            "id": "notification-newer",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "Newer",
            "body": "Newer body",
            "read_at": "2026-06-16T11:30:00+00:00",
            "created_at": "2026-06-16T11:00:00+00:00",
        },
    ]

    response = TestClient(app).get("/notifications", headers=auth_headers(users["candidate"]))

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["notification-newer", "notification-older"]


def test_get_notifications_uses_service_role_client_and_filters_current_user(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    service_supabase = FakeSupabase(
        {
            "notifications": [
                {
                    "id": "notification-own",
                    "user_id": users["candidate"]["id"],
                    "type": "game_created",
                    "title": "Own",
                    "body": "Own body",
                    "read_at": None,
                    "created_at": "2026-06-16T10:00:00+00:00",
                },
                {
                    "id": "notification-other",
                    "user_id": users["other"]["id"],
                    "type": "game_created",
                    "title": "Other",
                    "body": "Other body",
                    "read_at": None,
                    "created_at": "2026-06-16T11:00:00+00:00",
                },
            ]
        }
    )
    fake_supabase.tables["notifications"] = []
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: service_supabase,
    )

    response = TestClient(app).get("/notifications", headers=auth_headers(users["candidate"]))

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == ["notification-own"]


def test_get_notifications_normalizes_legacy_related_targets(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notification-legacy",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "Legacy",
            "body": "Legacy body",
            "related_game_id": "game-1",
            "related_field_id": "field-1",
            "is_read": False,
            "created_at": "2026-06-16T10:00:00+00:00",
        }
    ]

    response = TestClient(app).get("/notifications", headers=auth_headers(users["candidate"]))

    assert response.status_code == 200
    assert response.json()[0]["game_id"] == "game-1"
    assert response.json()[0]["field_id"] == "field-1"


def test_get_notifications_normalizes_data_payload_targets(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notification-player-joined",
            "user_id": users["organizer"]["id"],
            "type": "player_joined_game",
            "title": "שחקן חדש הצטרף למשחק שלך",
            "body": "Candidate הצטרף למשחק שלך ב-Central Court",
            "game_id": None,
            "field_id": None,
            "data": {
                "game_id": "game-1",
                "field_id": "field-1",
                "type": "player_joined_game",
                "joined_user_id": users["candidate"]["id"],
            },
            "read_at": None,
            "created_at": "2026-06-16T10:00:00+00:00",
        }
    ]

    response = TestClient(app).get("/notifications", headers=auth_headers(users["organizer"]))

    assert response.status_code == 200
    assert response.json()[0]["game_id"] == "game-1"
    assert response.json()[0]["field_id"] == "field-1"


def test_unread_count_returns_current_users_unread_notifications(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {"id": "own-unread", "user_id": users["candidate"]["id"], "read_at": None},
        {
            "id": "own-read",
            "user_id": users["candidate"]["id"],
            "read_at": "2026-06-16T10:00:00+00:00",
        },
        {"id": "other-unread", "user_id": users["other"]["id"], "read_at": None},
    ]

    response = TestClient(app).get(
        "/notifications/unread-count",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert response.json() == {"unread_count": 1}


def test_unread_count_uses_service_role_client_for_existing_notifications(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    service_supabase = FakeSupabase(
        {
            "notifications": [
                {"id": "own-unread-1", "user_id": users["candidate"]["id"], "read_at": None},
                {"id": "own-unread-2", "user_id": users["candidate"]["id"], "read_at": None},
                {
                    "id": "own-read",
                    "user_id": users["candidate"]["id"],
                    "read_at": "2026-06-16T10:00:00+00:00",
                },
                {"id": "other-unread", "user_id": users["other"]["id"], "read_at": None},
            ]
        }
    )
    fake_supabase.tables["notifications"] = []
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: service_supabase,
    )

    response = TestClient(app).get(
        "/notifications/unread-count",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert response.json() == {"unread_count": 2}


def test_unread_count_supports_legacy_is_read_schema(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {"id": "own-unread", "user_id": users["candidate"]["id"], "is_read": False},
        {"id": "own-read", "user_id": users["candidate"]["id"], "is_read": True},
        {"id": "other-unread", "user_id": users["other"]["id"], "is_read": False},
    ]

    response = TestClient(app).get(
        "/notifications/unread-count",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert response.json() == {"unread_count": 1}


def test_mark_notification_read_sets_read_at(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notification-own",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "Own",
            "body": "Own body",
            "read_at": None,
            "created_at": "2026-06-16T10:00:00+00:00",
        }
    ]

    response = TestClient(app).patch(
        "/notifications/notification-own/read",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert response.json()["read_at"] is not None
    assert fake_supabase.tables["notifications"][0]["read_at"] is not None


def test_read_notification_cannot_mark_another_users_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notification-other",
            "user_id": users["other"]["id"],
            "type": "game_created",
            "title": "Other",
            "body": "Other body",
            "read_at": None,
            "created_at": "2026-06-16T10:00:00+00:00",
        }
    ]

    response = TestClient(app).patch(
        "/notifications/notification-other/read",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 404
    assert fake_supabase.tables["notifications"][0]["read_at"] is None


def test_read_all_marks_only_current_users_notifications(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {"id": "own", "user_id": users["candidate"]["id"], "read_at": None},
        {"id": "other", "user_id": users["other"]["id"], "read_at": None},
    ]

    response = TestClient(app).patch("/notifications/read-all", headers=auth_headers(users["candidate"]))

    assert response.status_code == 200
    assert fake_supabase.tables["notifications"][0]["read_at"] is not None
    assert fake_supabase.tables["notifications"][1]["read_at"] is None


def test_mark_notification_read_sets_is_read_on_legacy_schema(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notification-legacy",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "Legacy",
            "body": "Legacy body",
            "is_read": False,
            "created_at": "2026-06-16T10:00:00+00:00",
        }
    ]

    response = TestClient(app).patch(
        "/notifications/notification-legacy/read",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert response.json()["is_read"] is True
    stored = fake_supabase.tables["notifications"][0]
    assert stored["is_read"] is True
    # The legacy schema has no read_at column, so it must not be written.
    assert "read_at" not in stored


def test_read_all_sets_is_read_on_legacy_schema(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {"id": "own", "user_id": users["candidate"]["id"], "is_read": False},
        {"id": "other", "user_id": users["other"]["id"], "is_read": False},
    ]

    response = TestClient(app).patch(
        "/notifications/read-all",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert fake_supabase.tables["notifications"][0]["is_read"] is True
    assert fake_supabase.tables["notifications"][1]["is_read"] is False
    assert "read_at" not in fake_supabase.tables["notifications"][0]


def test_save_push_token_stores_token_for_current_user(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    response = TestClient(app).post(
        "/notifications/push-token",
        json={"token": "fcm-token-1"},
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert fake_supabase.tables["push_tokens"] == [
        {
            "id": "push_tokens-1",
            "user_id": users["candidate"]["id"],
            "token": "fcm-token-1",
        }
    ]


def test_save_push_token_supports_multiple_devices_for_same_user(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    client = TestClient(app)

    first = client.post(
        "/notifications/push-token",
        json={"token": "chrome-token"},
        headers=auth_headers(users["candidate"]),
    )
    second = client.post(
        "/notifications/push-token",
        json={"token": "edge-token"},
        headers=auth_headers(users["candidate"]),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    tokens = fake_supabase.tables["push_tokens"]
    assert {row["token"] for row in tokens} == {"chrome-token", "edge-token"}
    assert all(row["user_id"] == users["candidate"]["id"] for row in tokens)


def test_save_push_token_reregistering_same_token_does_not_duplicate(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    client = TestClient(app)

    client.post(
        "/notifications/push-token",
        json={"token": "chrome-token"},
        headers=auth_headers(users["candidate"]),
    )
    client.post(
        "/notifications/push-token",
        json={"token": "chrome-token"},
        headers=auth_headers(users["candidate"]),
    )

    tokens = fake_supabase.tables["push_tokens"]
    assert [row["token"] for row in tokens] == ["chrome-token"]


def test_delete_push_token_removes_current_users_token(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["push_tokens"] = [
        {"id": "own-token", "user_id": users["candidate"]["id"], "token": "own-token"},
        {"id": "own-other-device", "user_id": users["candidate"]["id"], "token": "own-other-device"},
        {"id": "other-token", "user_id": users["other"]["id"], "token": "other-token"},
    ]

    response = TestClient(app).request(
        "DELETE",
        "/notifications/push-token",
        json={"token": "own-token"},
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    # Only the current device token is removed; the user's other device and
    # other users' tokens are untouched.
    assert fake_supabase.tables["push_tokens"] == [
        {"id": "own-other-device", "user_id": users["candidate"]["id"], "token": "own-other-device"},
        {"id": "other-token", "user_id": users["other"]["id"], "token": "other-token"},
    ]


def test_delete_push_token_requires_token_and_keeps_all_when_missing(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["push_tokens"] = [
        {"id": "device-a", "user_id": users["candidate"]["id"], "token": "device-a"},
        {"id": "device-b", "user_id": users["candidate"]["id"], "token": "device-b"},
    ]

    response = TestClient(app).request(
        "DELETE",
        "/notifications/push-token",
        json={},
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 400
    # Nothing deleted when no token is supplied.
    assert len(fake_supabase.tables["push_tokens"]) == 2


def test_test_push_requires_authentication(fake_supabase: FakeSupabase) -> None:
    response = TestClient(app).post("/notifications/test-push")

    assert response.status_code == 401


def test_test_push_sends_to_current_users_tokens(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    sent_tokens: list[str] = []
    fake_supabase.tables["push_tokens"] = [
        {"id": "own-token", "user_id": users["candidate"]["id"], "token": "own-token"},
        {"id": "other-token", "user_id": users["other"]["id"], "token": "other-token"},
    ]

    def fake_send(token: str, title: str, body: str, data: dict[str, Any]) -> dict[str, Any]:
        sent_tokens.append(token)
        assert title == "Test notification"
        assert body == "Push notifications are ready."
        assert data == {"type": "test_push"}
        return {"ok": True}

    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", fake_send)

    response = TestClient(app).post(
        "/notifications/test-push",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert response.json() == {"sent": 1, "invalid_tokens": 0}
    assert sent_tokens == ["own-token"]


def test_save_settings_deletes_unchecked_specific_field_preferences(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    unchecked_field_id = "00000000-0000-0000-0000-000000000101"
    kept_field_id = "00000000-0000-0000-0000-000000000202"
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-radius",
            "user_id": users["candidate"]["id"],
            "enabled": False,
            "sport_type": "both",
            "notification_type": "radius",
        },
        {
            "id": "pref-city",
            "user_id": users["candidate"]["id"],
            "enabled": False,
            "sport_type": "both",
            "notification_type": "city",
        },
        {
            "id": "pref-unchecked-field",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": unchecked_field_id,
        },
        {
            "id": "pref-kept-field",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": kept_field_id,
        },
    ]

    response = TestClient(app).put(
        "/notifications/preferences",
        json={
            "distance_enabled": False,
            "distance_radius_km": 5,
            "distance_lat": None,
            "distance_lng": None,
            "city_enabled": False,
            "city_name": "ירוחם",
            "specific_fields_enabled": True,
            "selected_field_ids": [kept_field_id],
        },
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    remaining_specific_fields = [
        preference.get("field_id")
        for preference in fake_supabase.tables["notification_preferences"]
        if preference.get("notification_type") == "specific_field"
    ]
    assert remaining_specific_fields == [kept_field_id]


def test_create_game_does_not_notify_for_unchecked_specific_field(
    fake_supabase: FakeSupabase,
    fake_service_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    sent_tokens: list[str] = []
    unchecked_field_id = "00000000-0000-0000-0000-000000000101"
    selected_field_id = "00000000-0000-0000-0000-000000000202"
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: fake_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-radius-disabled",
            "user_id": users["candidate"]["id"],
            "enabled": False,
            "sport_type": "both",
            "notification_type": "radius",
            "radius_km": 100,
            "lat": 30.9872,
            "lng": 34.9314,
        },
        {
            "id": "pref-city-disabled",
            "user_id": users["candidate"]["id"],
            "enabled": False,
            "sport_type": "both",
            "notification_type": "city",
            "city": "ירוחם",
        },
        {
            "id": "pref-selected-other-field",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": selected_field_id,
        },
    ]
    fake_service_supabase.tables["push_tokens"] = [
        {"id": "candidate-token", "user_id": users["candidate"]["id"], "token": "candidate-token"}
    ]

    monkeypatch.setattr(
        "app.routers.notifications.send_fcm_notification",
        lambda token, title, body, data: sent_tokens.append(token) or {"ok": True},
    )

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": unchecked_field_id,
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert fake_service_supabase.tables["notifications"] == []
    assert sent_tokens == []


def test_create_game_generates_notifications_for_matching_candidates_except_organizer(
    fake_supabase: FakeSupabase,
    fake_service_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: fake_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-organizer",
            "user_id": users["organizer"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": "00000000-0000-0000-0000-000000000101",
        },
        {
            "id": "pref-candidate",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": "00000000-0000-0000-0000-000000000101",
        },
    ]

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert fake_supabase.tables["notifications"] == []
    notifications = fake_service_supabase.tables["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == users["candidate"]["id"]
    assert notifications[0]["type"] == "game_created"
    assert notifications[0]["title"] == "נפתח משחק חדש"
    assert notifications[0]["body"] == "נפתח משחק football במגרש Central Court"
    assert notifications[0]["game_id"] == response.json()["game"]["id"]
    assert notifications[0]["field_id"] == "00000000-0000-0000-0000-000000000101"
    # New notifications omit the read marker so they default to unread under
    # either schema (read_at NULL / is_read false).
    assert notifications[0].get("read_at") is None
    assert "read_at" not in notifications[0]


def test_create_game_sends_push_to_matching_candidate_and_removes_invalid_tokens(
    fake_supabase: FakeSupabase,
    fake_service_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    sent_tokens: list[str] = []
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: fake_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-organizer",
            "user_id": users["organizer"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": "00000000-0000-0000-0000-000000000101",
        },
        {
            "id": "pref-candidate",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": "00000000-0000-0000-0000-000000000101",
        },
    ]
    fake_service_supabase.tables["push_tokens"] = [
        {"id": "candidate-token", "user_id": users["candidate"]["id"], "token": "invalid-token"},
        {"id": "organizer-token", "user_id": users["organizer"]["id"], "token": "organizer-token"},
    ]

    def fake_send(token: str, title: str, body: str, data: dict[str, Any]) -> dict[str, Any]:
        sent_tokens.append(token)
        assert title == "נפתח משחק חדש"
        assert body == "נפתח משחק football במגרש Central Court"
        assert data["type"] == "game_created"
        return {"ok": False, "invalid_token": True}

    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", fake_send)

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert sent_tokens == ["invalid-token"]
    assert fake_service_supabase.tables["push_tokens"] == [
        {"id": "organizer-token", "user_id": users["organizer"]["id"], "token": "organizer-token"}
    ]


def test_create_game_notifications_support_legacy_related_game_columns(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    legacy_service_supabase = FakeSupabase(
        {"notifications": []},
        missing_columns={"notifications": {"game_id", "field_id"}},
    )
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: legacy_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-candidate",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "city",
            "city": "ירוחם",
        },
    ]

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = legacy_service_supabase.tables["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["related_game_id"] == response.json()["game"]["id"]
    assert notifications[0]["related_field_id"] == "00000000-0000-0000-0000-000000000101"
    assert "game_id" not in notifications[0]
    assert "field_id" not in notifications[0]


def test_create_game_matches_by_city(
    fake_supabase: FakeSupabase,
    fake_service_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: fake_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-candidate-city",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "city",
            "city": " ירוחם ",
        },
        {
            "id": "pref-other-city",
            "user_id": users["other"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "city",
            "city": "תל אביב",
        },
    ]

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = fake_service_supabase.tables["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == users["candidate"]["id"]


def test_create_game_does_not_notify_non_matching_city(
    fake_supabase: FakeSupabase,
    fake_service_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: fake_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-candidate-city",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "city",
            "city": "תל אביב",
        },
    ]

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert fake_service_supabase.tables["notifications"] == []


def test_create_game_does_not_notify_organizer_for_own_matching_city(
    fake_supabase: FakeSupabase,
    fake_service_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: fake_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-organizer-city",
            "user_id": users["organizer"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "city",
            "city": "ירוחם",
        },
    ]

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert fake_service_supabase.tables["notifications"] == []


def test_create_game_avoids_duplicate_notifications_for_same_user_game_and_type(
    fake_supabase: FakeSupabase,
    fake_service_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client",
        lambda: fake_service_supabase,
    )
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-candidate-specific-field",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": "00000000-0000-0000-0000-000000000101",
        },
        {
            "id": "pref-candidate-city",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "city",
            "city": "ירוחם",
        },
    ]

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert fake_supabase.tables["notifications"] == []
    assert len(fake_service_supabase.tables["notifications"]) == 1
    assert fake_service_supabase.tables["notifications"][0]["user_id"] == users["candidate"]["id"]


def make_open_game(users: dict[str, dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    game = {
        "id": "00000000-0000-0000-0000-000000000301",
        "field_id": "00000000-0000-0000-0000-000000000101",
        "created_by": users["organizer"]["id"],
        "sport_type": "football",
        "players_present": 1,
        "max_players": 5,
        "status": "open",
    }
    game.update(overrides)
    return game


def player_joined_notifications(fake_supabase: FakeSupabase) -> list[dict[str, Any]]:
    return [
        notification
        for notification in fake_supabase.tables["notifications"]
        if notification.get("type") == "player_joined_game"
    ]


def test_join_game_notifies_organizer_when_another_user_joins(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["games"] = [make_open_game(users)]
    fake_supabase.tables["game_players"] = [
        {"id": "membership-organizer", "game_id": "00000000-0000-0000-0000-000000000301", "user_id": users["organizer"]["id"]}
    ]

    response = TestClient(app).post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    notifications = player_joined_notifications(fake_supabase)
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == users["organizer"]["id"]
    assert notifications[0]["title"] == "שחקן חדש הצטרף למשחק שלך"
    assert notifications[0]["body"] == "Candidate הצטרף למשחק שלך ב-Central Court"
    assert notifications[0]["data"] == {
        "game_id": "00000000-0000-0000-0000-000000000301",
        "field_id": "00000000-0000-0000-0000-000000000101",
        "type": "player_joined_game",
        "joined_user_id": users["candidate"]["id"],
    }


def test_joining_user_does_not_receive_player_joined_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["games"] = [make_open_game(users)]

    response = TestClient(app).post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    notifications = player_joined_notifications(fake_supabase)
    assert len(notifications) == 1
    assert notifications[0]["user_id"] != users["candidate"]["id"]


def test_duplicate_join_does_not_create_duplicate_player_joined_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["games"] = [make_open_game(users)]
    client = TestClient(app)

    first_response = client.post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )
    second_response = client.post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    assert second_response.json()["detail"] == "User already joined"
    assert len(player_joined_notifications(fake_supabase)) == 1


def test_organizer_joining_own_game_does_not_create_player_joined_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["games"] = [make_open_game(users, players_present=0)]

    response = TestClient(app).post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert player_joined_notifications(fake_supabase) == []


@pytest.mark.parametrize(
    ("game", "expected_status", "expected_detail"),
    [
        (make_open_game({"organizer": {"id": "00000000-0000-0000-0000-000000000001"}}, players_present=5, max_players=5), 400, "Game is full"),
        (make_open_game({"organizer": {"id": "00000000-0000-0000-0000-000000000001"}}, status="finished"), 400, "Game already closed"),
        (None, 404, "Game not found"),
    ],
)
def test_failed_join_does_not_create_player_joined_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
    game: dict[str, Any] | None,
    expected_status: int,
    expected_detail: str,
) -> None:
    fake_supabase.tables["games"] = [game] if game else []

    response = TestClient(app).post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert player_joined_notifications(fake_supabase) == []


def test_join_game_increases_organizer_unread_notification_count(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["games"] = [make_open_game(users)]
    client = TestClient(app)

    before_response = client.get(
        "/notifications/unread-count",
        headers=auth_headers(users["organizer"]),
    )
    join_response = client.post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )
    after_response = client.get(
        "/notifications/unread-count",
        headers=auth_headers(users["organizer"]),
    )

    assert before_response.status_code == 200
    assert join_response.status_code == 200
    assert after_response.status_code == 200
    assert before_response.json() == {"unread_count": 0}
    assert after_response.json() == {"unread_count": 1}


def test_join_game_succeeds_when_player_joined_notification_fails(
    fake_supabase: FakeSupabase,
    monkeypatch,
    caplog,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["games"] = [make_open_game(users)]
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake_supabase)

    def fail_notification(*_: Any, **__: Any) -> None:
        raise RuntimeError("notifications insert failed")

    monkeypatch.setattr(
        "app.routers.games.create_player_joined_game_notification",
        fail_notification,
    )

    client = TestClient(app)
    caplog.set_level(logging.ERROR, logger="app.routers.games")

    join_response = client.post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )
    active_response = client.get("/games/active")

    assert join_response.status_code == 200
    assert join_response.json()["message"] == "Joined successfully"
    assert {
        "game_id": "00000000-0000-0000-0000-000000000301",
        "user_id": users["candidate"]["id"],
    }.items() <= fake_supabase.tables["game_players"][0].items()
    assert active_response.status_code == 200
    assert active_response.json()[0]["participants"] == [
        {"user_id": users["candidate"]["id"], "name": users["candidate"]["name"]}
    ]
    assert "Failed to create player joined game notification after successful join" in caplog.text


@pytest.mark.parametrize(
    ("game", "existing_players", "expected_status", "expected_detail"),
    [
        (make_open_game({"organizer": {"id": "00000000-0000-0000-0000-000000000001"}}, players_present=5, max_players=5), [], 400, "Game is full"),
        (make_open_game({"organizer": {"id": "00000000-0000-0000-0000-000000000001"}}, status="finished"), [], 400, "Game already closed"),
        (
            make_open_game({"organizer": {"id": "00000000-0000-0000-0000-000000000001"}}),
            [{"id": "membership-candidate", "game_id": "00000000-0000-0000-0000-000000000301", "user_id": "00000000-0000-0000-0000-000000000002"}],
            400,
            "User already joined",
        ),
        (None, [], 404, "Game not found"),
    ],
)
def test_real_join_failures_still_return_errors_when_notification_would_fail(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
    game: dict[str, Any] | None,
    existing_players: list[dict[str, Any]],
    expected_status: int,
    expected_detail: str,
) -> None:
    fake_supabase.tables["games"] = [game] if game else []
    fake_supabase.tables["game_players"] = existing_players

    def fail_if_called(*_: Any, **__: Any) -> None:
        raise AssertionError("notification side effect should not run for failed joins")

    monkeypatch.setattr(
        "app.routers.games.create_player_joined_game_notification",
        fail_if_called,
    )

    response = TestClient(app).post(
        "/games/00000000-0000-0000-0000-000000000301/join",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail


def test_notification_candidates_endpoint_rejects_regular_users(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    response = TestClient(app).post(
        "/notifications/candidates",
        json={"field_id": "00000000-0000-0000-0000-000000000101", "sport_type": "football"},
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 403
