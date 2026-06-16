from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fastapi.testclient import TestClient

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
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.counters: dict[str, int] = {}

    def table(self, table_name: str) -> FakeQuery:
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)

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
        }
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    return fake


@pytest.fixture
def fake_service_supabase() -> FakeSupabase:
    return FakeSupabase({"notifications": []})


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
    assert notifications[0]["read_at"] is None


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
