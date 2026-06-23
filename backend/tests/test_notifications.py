from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from app.routers.notifications import (
    create_game_extended_notifications,
    generate_scheduled_game_reminders,
)


class _LtSentinel:
    def __init__(self, column: str) -> None:
        self.column = column


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

    def lt(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((_LtSentinel(column), value))
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
            if isinstance(column, _LtSentinel):
                rows = [row for row in rows if row.get(column.column) is not None and str(row[column.column]) < str(value)]
            else:
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

    def rpc(self, function_name: str, params: dict[str, Any]) -> "FakeRpcQueryNotif":
        assert function_name == "join_game_atomic"
        return FakeRpcQueryNotif(self, params)


class FakeRpcQueryNotif:
    """Simulates join_game_atomic RPC for notification tests."""

    def __init__(self, database: FakeSupabase, params: dict[str, Any]) -> None:
        self.database = database
        self.params = params

    def execute(self) -> FakeResponse:
        game_id = self.params["p_game_id"]
        user_id = self.params["p_user_id"]

        games = [g for g in self.database.tables.get("games", []) if g["id"] == game_id]
        if not games:
            return FakeResponse([{"error": "Game not found"}])
        game = games[0]

        if game.get("status") not in ("open", "full"):
            return FakeResponse([{"error": "Game already closed"}])

        if game["players_present"] >= game["max_players"]:
            return FakeResponse([{"error": "Game is full"}])

        already = [
            gp for gp in self.database.tables.get("game_players", [])
            if gp.get("game_id") == game_id and gp.get("user_id") == user_id
        ]
        if already:
            return FakeResponse([{"error": "User already joined"}])

        row = {"game_id": game_id, "user_id": user_id, "id": self.database.next_id("game_players")}
        self.database.tables["game_players"].append(row)
        game["players_present"] += 1
        game["status"] = "full" if game["players_present"] >= game["max_players"] else "open"

        return FakeResponse([{"game": dict(game)}])


class DenyTablesSupabase(FakeSupabase):
    def __init__(self, tables: dict[str, list[dict[str, Any]]], denied_tables: set[str]) -> None:
        super().__init__(tables)
        self.denied_tables = denied_tables

    def table(self, table_name: str) -> FakeQuery:
        if table_name in self.denied_tables:
            raise AssertionError(f"regular client should not access {table_name}")
        return super().table(table_name)


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
                    "status": "open",
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
    monkeypatch.setattr("app.routers.games.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)

    fixed_now = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: fixed_now)
    monkeypatch.setattr("app.routers.games.get_now", lambda: fixed_now)

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


def test_mark_read_decreases_unread_count_by_one(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notif-a",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "A",
            "body": "body",
            "read_at": None,
            "created_at": "2026-06-16T10:00:00+00:00",
        },
        {
            "id": "notif-b",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "B",
            "body": "body",
            "read_at": None,
            "created_at": "2026-06-16T09:00:00+00:00",
        },
    ]
    client = TestClient(app)
    headers = auth_headers(users["candidate"])

    before = client.get("/notifications/unread-count", headers=headers)
    assert before.json() == {"unread_count": 2}

    client.patch("/notifications/notif-a/read", headers=headers)

    after = client.get("/notifications/unread-count", headers=headers)
    assert after.json() == {"unread_count": 1}


def test_marking_already_read_notification_does_not_change_unread_count(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {
            "id": "notif-read",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "Already read",
            "body": "body",
            "read_at": "2026-06-16T10:00:00+00:00",
            "created_at": "2026-06-16T09:00:00+00:00",
        },
        {
            "id": "notif-unread",
            "user_id": users["candidate"]["id"],
            "type": "game_created",
            "title": "Still unread",
            "body": "body",
            "read_at": None,
            "created_at": "2026-06-16T08:00:00+00:00",
        },
    ]
    client = TestClient(app)
    headers = auth_headers(users["candidate"])

    before = client.get("/notifications/unread-count", headers=headers)
    assert before.json() == {"unread_count": 1}

    client.patch("/notifications/notif-read/read", headers=headers)

    after = client.get("/notifications/unread-count", headers=headers)
    assert after.json() == {"unread_count": 1}


def test_mark_all_read_sets_unread_count_to_zero(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notifications"] = [
        {"id": "n1", "user_id": users["candidate"]["id"], "read_at": None},
        {"id": "n2", "user_id": users["candidate"]["id"], "read_at": None},
        {"id": "n3", "user_id": users["candidate"]["id"], "read_at": None},
    ]
    client = TestClient(app)
    headers = auth_headers(users["candidate"])

    before = client.get("/notifications/unread-count", headers=headers)
    assert before.json() == {"unread_count": 3}

    client.patch("/notifications/read-all", headers=headers)

    after = client.get("/notifications/unread-count", headers=headers)
    assert after.json() == {"unread_count": 0}


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


def test_test_push_firebase_config_error_returns_clean_api_error(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["push_tokens"] = [
        {"id": "own-token", "user_id": users["candidate"]["id"], "token": "own-token"},
    ]

    from app.services.firebase_push import FirebaseConfigError

    def failing_send(*args, **kwargs) -> dict[str, Any]:
        raise FirebaseConfigError("Firebase credentials are not configured")

    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", failing_send)

    response = TestClient(app).post(
        "/notifications/test-push",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 502
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "EXTERNAL_SERVICE_ERROR"
    assert err["message"] == "Firebase push service configuration error"



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


def game_closed_notifications(fake_supabase: FakeSupabase) -> list[dict[str, Any]]:
    return [
        notification
        for notification in fake_supabase.tables["notifications"]
        if notification.get("type") == "game_closed"
    ]


def game_extended_notifications(fake_supabase: FakeSupabase) -> list[dict[str, Any]]:
    return [
        notification
        for notification in fake_supabase.tables["notifications"]
        if notification.get("type") == "game_extended"
    ]


def scheduled_game_reminder_notifications(fake_supabase: FakeSupabase) -> list[dict[str, Any]]:
    return [
        notification
        for notification in fake_supabase.tables["notifications"]
        if notification.get("type") == "scheduled_game_reminder"
    ]


def set_game_participants(
    fake_supabase: FakeSupabase,
    game_id: str,
    user_ids: list[str],
) -> None:
    fake_supabase.tables["game_players"] = [
        {
            "id": f"membership-{index}",
            "game_id": game_id,
            "user_id": user_id,
        }
        for index, user_id in enumerate(user_ids, start=1)
    ]


def assert_game_closed_notification(
    notification: dict[str, Any],
    *,
    user_id: str,
    game_id: str = "00000000-0000-0000-0000-000000000301",
) -> None:
    assert notification["user_id"] == user_id
    assert notification["type"] == "game_closed"
    assert notification["title"] == "המשחק נסגר"
    assert notification["body"] == "המשחק במגרש Central Court נסגר על ידי המארגן."
    assert notification["game_id"] == game_id
    assert notification["field_id"] == "00000000-0000-0000-0000-000000000101"
    assert notification["data"] == {
        "game_id": game_id,
        "field_id": "00000000-0000-0000-0000-000000000101",
        "type": "game_closed",
        "closed_by_user_id": notification["data"]["closed_by_user_id"],
    }


def assert_game_extended_notification(
    notification: dict[str, Any],
    *,
    user_id: str,
    new_end_time: str,
    new_end_time_label: str,
    extended_by_user_id: str,
    game_id: str = "00000000-0000-0000-0000-000000000301",
) -> None:
    assert notification["user_id"] == user_id
    assert notification["type"] == "game_extended"
    assert notification["title"] == "המשחק הוארך"
    assert notification["body"] == f"שעת הסיום החדשה של המשחק היא {new_end_time_label}"
    assert new_end_time_label in notification["body"]
    assert notification["game_id"] == game_id
    assert notification["field_id"] == "00000000-0000-0000-0000-000000000101"
    assert notification["data"] == {
        "game_id": game_id,
        "field_id": "00000000-0000-0000-0000-000000000101",
        "type": "game_extended",
        "new_end_time": new_end_time,
        "extended_by_user_id": extended_by_user_id,
    }


def assert_scheduled_game_reminder_notification(
    notification: dict[str, Any],
    *,
    user_id: str,
    game_id: str = "00000000-0000-0000-0000-000000000301",
    scheduled_at: str = "2026-06-22T20:00:00+00:00",
) -> None:
    assert notification["user_id"] == user_id
    assert notification["type"] == "scheduled_game_reminder"
    assert notification["title"] == "תזכורת למשחק שמתקרב"
    assert notification["body"] == "המשחק שלך מתחיל בעוד שעה. אל תשכח להגיע בזמן."
    assert notification["game_id"] == game_id
    assert notification["field_id"] == "00000000-0000-0000-0000-000000000101"
    assert notification["data"] == {
        "type": "scheduled_game_reminder",
        "game_id": game_id,
        "field_id": "00000000-0000-0000-0000-000000000101",
        "scheduled_at": scheduled_at,
    }
    # New reminders must default to unread under either schema so they show
    # up in the in-app notification center until the user opens them.
    assert notification.get("read_at") is None
    assert notification.get("is_read") in (None, False)


def test_creator_close_notifies_one_participant(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["candidate"]["id"]])

    response = TestClient(app).post(
        f"/games/{game['id']}/close",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = game_closed_notifications(fake_supabase)
    assert len(notifications) == 1
    assert_game_closed_notification(notifications[0], user_id=users["candidate"]["id"])
    assert notifications[0]["data"]["closed_by_user_id"] == users["organizer"]["id"]


def test_creator_close_notifies_multiple_participants(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["candidate"]["id"], users["other"]["id"]],
    )

    response = TestClient(app).post(
        f"/games/{game['id']}/close",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = game_closed_notifications(fake_supabase)
    assert len(notifications) == 2
    assert {notification["user_id"] for notification in notifications} == {
        users["candidate"]["id"],
        users["other"]["id"],
    }
    for notification in notifications:
        assert notification["title"] == "המשחק נסגר"
        assert notification["body"] == "המשחק במגרש Central Court נסגר על ידי המארגן."


@pytest.mark.parametrize("participant_count", [5, 10])
def test_creator_close_notifies_each_participant_once_for_large_games(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
    participant_count: int,
) -> None:
    game = make_open_game(users)
    fake_supabase.tables["games"] = [game]
    recipient_ids = [
        f"00000000-0000-0000-0000-0000000004{index:02d}"
        for index in range(1, participant_count)
    ]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], *recipient_ids],
    )

    response = TestClient(app).post(
        f"/games/{game['id']}/close",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = game_closed_notifications(fake_supabase)
    assert len(notifications) == participant_count - 1
    assert {notification["user_id"] for notification in notifications} == set(recipient_ids)
    assert users["organizer"]["id"] not in {
        notification["user_id"] for notification in notifications
    }
    assert all(
        len([
            notification
            for notification in notifications
            if notification["user_id"] == recipient_id
        ]) == 1
        for recipient_id in recipient_ids
    )
    for notification in notifications:
        assert_game_closed_notification(notification, user_id=notification["user_id"])
        assert "Central Court" in notification["body"]
        assert notification["data"]["closed_by_user_id"] == users["organizer"]["id"]


def test_admin_close_notifies_participants_except_admin_participant(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"], users["admin"]["id"]],
    )

    response = TestClient(app).post(
        f"/admin/games/{game['id']}/close",
        headers=auth_headers(users["admin"]),
    )

    assert response.status_code == 200
    notifications = game_closed_notifications(fake_supabase)
    assert len(notifications) == 2
    assert {notification["user_id"] for notification in notifications} == {
        users["organizer"]["id"],
        users["candidate"]["id"],
    }
    assert users["admin"]["id"] not in {notification["user_id"] for notification in notifications}
    assert {notification["data"]["closed_by_user_id"] for notification in notifications} == {
        users["admin"]["id"],
    }


def test_closer_does_not_receive_game_closed_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )

    response = TestClient(app).post(
        f"/games/{game['id']}/close",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = game_closed_notifications(fake_supabase)
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == users["candidate"]["id"]


def test_duplicate_close_does_not_create_duplicate_game_closed_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["candidate"]["id"]])
    client = TestClient(app)

    first_response = client.post(
        f"/games/{game['id']}/close",
        headers=auth_headers(users["organizer"]),
    )
    second_response = client.post(
        f"/games/{game['id']}/close",
        headers=auth_headers(users["organizer"]),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 400
    err = second_response.json()
    assert err["error"] is True
    assert err["code"] == "GAME_NOT_ACTIONABLE"
    assert "already closed" in err["message"].lower()
    assert len(game_closed_notifications(fake_supabase)) == 1


def test_close_game_with_no_participants_creates_no_game_closed_notifications(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users)
    fake_supabase.tables["games"] = [game]
    fake_supabase.tables["game_players"] = []

    response = TestClient(app).post(
        f"/games/{game['id']}/close",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert game_closed_notifications(fake_supabase) == []


def test_extend_game_creates_game_extended_notification_for_participants(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users, expires_at="2026-06-22T19:30:00+00:00")
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )

    response = TestClient(app).post(
        f"/games/{game['id']}/extend",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert response.json()["new_expires_at"] == "2026-06-22T20:30:00+00:00"
    notifications = game_extended_notifications(fake_supabase)
    assert len(notifications) == 1
    assert_game_extended_notification(
        notifications[0],
        user_id=users["candidate"]["id"],
        new_end_time="2026-06-22T20:30:00+00:00",
        new_end_time_label="20:30",
        extended_by_user_id=users["organizer"]["id"],
    )


def test_organizer_does_not_receive_game_extended_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users, expires_at="2026-06-22T19:30:00+00:00")
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )

    response = TestClient(app).post(
        f"/games/{game['id']}/extend",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = game_extended_notifications(fake_supabase)
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == users["candidate"]["id"]
    assert users["organizer"]["id"] not in {
        notification["user_id"] for notification in notifications
    }


def test_multiple_consecutive_extensions_create_multiple_notifications(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users, expires_at="2026-06-22T19:30:00+00:00")
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )
    client = TestClient(app)

    first_response = client.post(
        f"/games/{game['id']}/extend",
        headers=auth_headers(users["organizer"]),
    )
    second_response = client.post(
        f"/games/{game['id']}/extend",
        headers=auth_headers(users["organizer"]),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    notifications = game_extended_notifications(fake_supabase)
    assert len(notifications) == 2
    assert [notification["body"] for notification in notifications] == [
        "שעת הסיום החדשה של המשחק היא 20:30",
        "שעת הסיום החדשה של המשחק היא 21:30",
    ]
    assert [notification["data"]["new_end_time"] for notification in notifications] == [
        "2026-06-22T20:30:00+00:00",
        "2026-06-22T21:30:00+00:00",
    ]


def test_duplicate_game_extended_notification_is_not_created_for_same_extension(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users, expires_at="2026-06-22T19:30:00+00:00")
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )
    new_end_time = datetime(2026, 6, 22, 20, 30, tzinfo=timezone.utc)

    first_notifications = create_game_extended_notifications(
        supabase=fake_supabase,
        game=game,
        new_end_time=new_end_time,
        extended_by_user_id=users["organizer"]["id"],
    )
    second_notifications = create_game_extended_notifications(
        supabase=fake_supabase,
        game=game,
        new_end_time=new_end_time,
        extended_by_user_id=users["organizer"]["id"],
    )

    assert len(first_notifications) == 1
    assert second_notifications == []
    assert len(game_extended_notifications(fake_supabase)) == 1


def test_failed_extend_does_not_create_game_extended_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users, expires_at="2026-06-22T19:30:00+00:00")
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )

    response = TestClient(app).post(
        f"/games/{game['id']}/extend",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 403
    assert game_extended_notifications(fake_supabase) == []


def test_extend_game_with_no_participants_except_creator_creates_no_notification(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_open_game(users, expires_at="2026-06-22T19:30:00+00:00")
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["organizer"]["id"]])

    response = TestClient(app).post(
        f"/games/{game['id']}/extend",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert game_extended_notifications(fake_supabase) == []


@pytest.mark.parametrize("participant_count", [5, 10])
def test_extend_game_notifies_each_non_creator_participant_once_for_large_games(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
    participant_count: int,
) -> None:
    game = make_open_game(users, expires_at="2026-06-22T19:30:00+00:00")
    fake_supabase.tables["games"] = [game]
    recipient_ids = [
        f"00000000-0000-0000-0000-0000000005{index:02d}"
        for index in range(1, participant_count)
    ]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], *recipient_ids],
    )

    response = TestClient(app).post(
        f"/games/{game['id']}/extend",
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    notifications = game_extended_notifications(fake_supabase)
    assert len(notifications) == participant_count - 1
    assert {notification["user_id"] for notification in notifications} == set(recipient_ids)
    assert users["organizer"]["id"] not in {
        notification["user_id"] for notification in notifications
    }
    assert all(
        len([
            notification
            for notification in notifications
            if notification["user_id"] == recipient_id
        ]) == 1
        for recipient_id in recipient_ids
    )
    for notification in notifications:
        assert_game_extended_notification(
            notification,
            user_id=notification["user_id"],
            new_end_time="2026-06-22T20:30:00+00:00",
            new_end_time_label="20:30",
            extended_by_user_id=users["organizer"]["id"],
        )


def make_scheduled_game(users: dict[str, dict[str, Any]], **overrides: Any) -> dict[str, Any]:
    game = make_open_game(
        users,
        scheduled_at="2026-06-22T20:00:00+00:00",
        started_at="2026-06-22T20:00:00+00:00",
        expires_at="2026-06-22T22:00:00+00:00",
        scheduled_reminder_processed_at=None,
    )
    game.update(overrides)
    return game


def run_scheduled_reminders(fake_supabase: FakeSupabase, current_time: datetime) -> dict[str, Any]:
    return generate_scheduled_game_reminders(supabase=fake_supabase, now=current_time)


def test_scheduled_game_reminder_created_for_current_participants_including_organizer(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert result["notifications_created"] == 2
    assert result["processed_game_ids"] == [game["id"]]
    assert fake_supabase.tables["games"][0]["scheduled_reminder_processed_at"] == (
        "2026-06-22T19:00:00+00:00"
    )
    notifications = scheduled_game_reminder_notifications(fake_supabase)
    assert len(notifications) == 2
    assert {notification["user_id"] for notification in notifications} == {
        users["organizer"]["id"],
        users["candidate"]["id"],
    }
    for notification in notifications:
        assert_scheduled_game_reminder_notification(
            notification,
            user_id=notification["user_id"],
        )


def test_scheduled_game_reminder_not_created_before_reminder_time(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["organizer"]["id"]])

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 18, 59, tzinfo=timezone.utc),
    )

    assert result["notifications_created"] == 0
    assert scheduled_game_reminder_notifications(fake_supabase) == []
    assert fake_supabase.tables["games"][0]["scheduled_reminder_processed_at"] is None


@pytest.mark.parametrize(
    "game_overrides",
    [
        {"scheduled_at": None},
        {"scheduled_at": "2026-06-22T18:59:00+00:00"},
        {"status": "finished"},
        {"status": "cancelled"},
    ],
)
def test_scheduled_game_reminder_excludes_ineligible_games(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
    game_overrides: dict[str, Any],
) -> None:
    game = make_scheduled_game(users, **game_overrides)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["organizer"]["id"]])

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert result["notifications_created"] == 0
    assert scheduled_game_reminder_notifications(fake_supabase) == []


def test_full_scheduled_game_still_sends_reminders(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users, status="full", players_present=5, max_players=5)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["organizer"]["id"]])

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert result["notifications_created"] == 1
    assert len(scheduled_game_reminder_notifications(fake_supabase)) == 1


def test_user_who_left_before_reminder_execution_does_not_receive_reminder(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["candidate"]["id"]])

    run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    notifications = scheduled_game_reminder_notifications(fake_supabase)
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == users["candidate"]["id"]
    assert users["organizer"]["id"] not in {
        notification["user_id"] for notification in notifications
    }


def test_late_join_after_reminder_ran_does_not_receive_retroactive_reminder(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["organizer"]["id"]])

    first_result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )
    second_result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 20, tzinfo=timezone.utc),
    )

    assert first_result["notifications_created"] == 1
    assert second_result["notifications_created"] == 0
    notifications = scheduled_game_reminder_notifications(fake_supabase)
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == users["organizer"]["id"]


def test_scheduled_game_reminder_job_is_idempotent(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )

    first_result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )
    second_result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 1, tzinfo=timezone.utc),
    )

    assert first_result["notifications_created"] == 2
    assert second_result["notifications_created"] == 0
    assert len(scheduled_game_reminder_notifications(fake_supabase)) == 2


def test_scheduled_game_reminder_existing_notification_prevents_late_duplicates(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    fake_supabase.tables["notifications"] = [
        {
            "id": "existing-reminder",
            "user_id": users["organizer"]["id"],
            "type": "scheduled_game_reminder",
            "title": "תזכורת למשחק שמתקרב",
            "body": "המשחק שלך מתחיל בעוד שעה. אל תשכח להגיע בזמן.",
            "game_id": game["id"],
            "field_id": game["field_id"],
            "data": {
                "type": "scheduled_game_reminder",
                "game_id": game["id"],
                "field_id": game["field_id"],
                "scheduled_at": game["scheduled_at"],
            },
        }
    ]
    set_game_participants(
        fake_supabase,
        game["id"],
        [users["organizer"]["id"], users["candidate"]["id"]],
    )

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert result["notifications_created"] == 0
    assert result["skipped_game_ids"] == [game["id"]]
    assert len(scheduled_game_reminder_notifications(fake_supabase)) == 1
    assert fake_supabase.tables["games"][0]["scheduled_reminder_processed_at"] == (
        "2026-06-22T19:00:00+00:00"
    )


def test_admin_scheduled_reminder_runner_uses_service_role_for_internal_tables(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["organizer"]["id"]])
    regular_client = DenyTablesSupabase(
        {"users": list(users.values())},
        denied_tables={"games", "game_players", "notifications", "push_tokens"},
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: regular_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: regular_client)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake_supabase)
    monkeypatch.setattr(
        "app.routers.notifications.datetime",
        type(
            "FrozenDateTime",
            (),
            {
                "now": staticmethod(lambda tz=None: datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc)),
            },
        ),
    )

    response = TestClient(app).post(
        "/admin/reminders/scheduled-games/run",
        headers=auth_headers(users["admin"]),
    )

    assert response.status_code == 200
    assert response.json()["notifications_created"] == 1
    assert len(scheduled_game_reminder_notifications(fake_supabase)) == 1
    assert fake_supabase.tables["games"][0]["scheduled_reminder_processed_at"] == (
        "2026-06-22T19:00:00+00:00"
    )


def test_no_participants_marks_scheduled_game_reminder_processed_without_notifications(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    fake_supabase.tables["game_players"] = []

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert result["notifications_created"] == 0
    assert result["processed_game_ids"] == [game["id"]]
    assert scheduled_game_reminder_notifications(fake_supabase) == []
    assert fake_supabase.tables["games"][0]["scheduled_reminder_processed_at"] == (
        "2026-06-22T19:00:00+00:00"
    )


def test_push_failure_does_not_block_scheduled_game_reminder_creation(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    fake_supabase.tables["push_tokens"] = [
        {"id": "candidate-token", "user_id": users["candidate"]["id"], "token": "bad-token"}
    ]
    set_game_participants(fake_supabase, game["id"], [users["candidate"]["id"]])

    def fail_push(*_: Any, **__: Any) -> dict[str, Any]:
        raise RuntimeError("push failed")

    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", fail_push)

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert result["notifications_created"] == 1
    assert len(scheduled_game_reminder_notifications(fake_supabase)) == 1


def test_scheduled_game_reminder_visible_to_recipient_via_get_notifications(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["candidate"]["id"]])

    run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    response = TestClient(app).get(
        "/notifications",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    reminders = [
        row for row in response.json() if row.get("type") == "scheduled_game_reminder"
    ]
    assert len(reminders) == 1
    reminder = reminders[0]
    # The notification center surfaces the Hebrew copy and the routing data
    # the click handler relies on to open the relevant game.
    assert reminder["title"] == "תזכורת למשחק שמתקרב"
    assert reminder["body"] == "המשחק שלך מתחיל בעוד שעה. אל תשכח להגיע בזמן."
    assert reminder["game_id"] == game["id"]
    assert reminder["field_id"] == game["field_id"]
    assert reminder["data"]["type"] == "scheduled_game_reminder"
    # Unread by default so the inbox badge surfaces it.
    assert reminder.get("read_at") is None


def test_scheduled_game_reminder_not_visible_to_unrelated_user(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["candidate"]["id"]])

    run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    response = TestClient(app).get(
        "/notifications",
        headers=auth_headers(users["other"]),
    )

    assert response.status_code == 200
    assert [
        row for row in response.json() if row.get("type") == "scheduled_game_reminder"
    ] == []


def test_scheduled_game_reminder_can_be_marked_read_by_recipient(
    fake_supabase: FakeSupabase,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["candidate"]["id"]])

    run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    reminders = scheduled_game_reminder_notifications(fake_supabase)
    assert len(reminders) == 1
    reminder_id = reminders[0]["id"]

    response = TestClient(app).patch(
        f"/notifications/{reminder_id}/read",
        headers=auth_headers(users["candidate"]),
    )

    assert response.status_code == 200
    assert response.json()["read_at"] is not None
    stored = next(
        row
        for row in fake_supabase.tables["notifications"]
        if row["id"] == reminder_id
    )
    assert stored["read_at"] is not None


def test_scheduled_game_created_after_reminder_window_is_marked_processed(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    now = datetime(2026, 6, 22, 19, 30, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    monkeypatch.setattr("app.routers.games.get_now", lambda: now)

    response = TestClient(app).post(
        "/games/",
        json={
            "field_id": "00000000-0000-0000-0000-000000000101",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 5,
            "scheduled_at": "2026-06-22T20:00:00Z",
        },
        headers=auth_headers(users["organizer"]),
    )

    assert response.status_code == 200
    assert response.json()["game"]["scheduled_reminder_processed_at"] == (
        "2026-06-22T19:30:00+00:00"
    )


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
    assert notifications[0]["type"] == "player_joined_game"
    assert notifications[0]["user_id"] == users["organizer"]["id"]
    assert notifications[0]["title"] == "שחקן חדש הצטרף למשחק שלך"
    assert notifications[0]["body"] == "Candidate הצטרף למשחק שלך ב-Central Court"
    assert notifications[0]["game_id"] == "00000000-0000-0000-0000-000000000301"
    assert notifications[0]["field_id"] == "00000000-0000-0000-0000-000000000101"
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
    err = second_response.json()
    assert err["error"] is True
    assert err["code"] == "CONFLICT"
    assert "already joined" in err["message"].lower()
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
    err = response.json()
    assert err["error"] is True
    if expected_detail == "Game is full":
        assert err["code"] == "GAME_FULL"
    elif expected_detail == "Game already closed":
        assert err["code"] == "GAME_NOT_ACTIONABLE"
    elif expected_detail == "Game not found":
        assert err["code"] == "GAME_NOT_FOUND"
    assert err["message"] == expected_detail
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
        {
            "user_id": users["candidate"]["id"],
            "username": None,
            "name": users["candidate"]["name"],
        }
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
    err = response.json()
    assert err["error"] is True
    if expected_detail == "Game is full":
        assert err["code"] == "GAME_FULL"
    elif expected_detail == "Game already closed":
        assert err["code"] == "GAME_NOT_ACTIONABLE"
    elif expected_detail == "User already joined":
        assert err["code"] == "CONFLICT"
    elif expected_detail == "Game not found":
        assert err["code"] == "GAME_NOT_FOUND"
    assert err["message"] == expected_detail


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


# ═══════════════════════════════════════════════════════════════
# ISSUE-040: Notification failure handling tests
# ═══════════════════════════════════════════════════════════════


def test_game_creation_succeeds_when_notification_creation_raises(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    fake_supabase.tables["notification_preferences"] = [
        {
            "id": "pref-candidate",
            "user_id": users["candidate"]["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "specific_field",
            "field_id": "00000000-0000-0000-0000-000000000101",
        },
    ]

    monkeypatch.setattr(
        "app.routers.games.create_game_created_notifications",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("DB exploded")),
    )

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
    assert response.json()["message"] == "Game created"
    assert response.json()["game"]["id"] is not None
    assert len(fake_supabase.tables["games"]) == 1


def test_game_creation_still_creates_notifications_on_success(
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
    notifications = fake_service_supabase.tables["notifications"]
    assert len(notifications) == 1
    assert notifications[0]["type"] == "game_created"
    assert notifications[0]["user_id"] == users["candidate"]["id"]


def test_game_creation_notification_failure_is_logged(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
    caplog,
) -> None:
    monkeypatch.setattr(
        "app.routers.games.create_game_created_notifications",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("template boom")),
    )

    with caplog.at_level(logging.ERROR, logger="app.routers.games"):
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
    assert any(
        "Failed to create game_created notifications" in record.message
        for record in caplog.records
    )


def test_scheduled_reminder_batch_continues_after_one_game_fails(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    game_ok_1 = make_scheduled_game(users, id="game-ok-1", field_id="00000000-0000-0000-0000-000000000101")
    game_bad = make_scheduled_game(users, id="game-bad", field_id="00000000-0000-0000-0000-000000000101")
    game_ok_2 = make_scheduled_game(users, id="game-ok-2", field_id="00000000-0000-0000-0000-000000000101")

    fake_supabase.tables["games"] = [game_ok_1, game_bad, game_ok_2]
    fake_supabase.tables["game_players"] = [
        {"id": "gp-1", "game_id": "game-ok-1", "user_id": users["organizer"]["id"]},
        {"id": "gp-2", "game_id": "game-bad", "user_id": users["organizer"]["id"]},
        {"id": "gp-3", "game_id": "game-ok-2", "user_id": users["organizer"]["id"]},
    ]

    original_insert = FakeQuery.insert

    def failing_insert(self, payload):
        payloads = payload if isinstance(payload, list) else [payload]
        for row in payloads:
            if row.get("game_id") == "game-bad" and row.get("type") == "scheduled_game_reminder":
                raise RuntimeError("DB insert failed for game-bad")
        return original_insert(self, payload)

    monkeypatch.setattr(FakeQuery, "insert", failing_insert)
    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", lambda *a, **kw: {"ok": True})

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert "game-ok-1" in result["processed_game_ids"]
    assert "game-ok-2" in result["processed_game_ids"]
    assert "game-bad" in result["failed_game_ids"]
    assert len(result["errors"]) == 1
    assert result["errors"][0]["game_id"] == "game-bad"
    assert result["notifications_created"] == 2

    reminders = scheduled_game_reminder_notifications(fake_supabase)
    reminder_game_ids = {r["game_id"] for r in reminders}
    assert "game-ok-1" in reminder_game_ids
    assert "game-ok-2" in reminder_game_ids
    assert "game-bad" not in reminder_game_ids


def test_scheduled_reminder_batch_idempotent_after_partial_failure(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    game_ok = make_scheduled_game(users, id="game-ok", field_id="00000000-0000-0000-0000-000000000101")
    game_bad = make_scheduled_game(users, id="game-bad", field_id="00000000-0000-0000-0000-000000000101")

    fake_supabase.tables["games"] = [game_ok, game_bad]
    fake_supabase.tables["game_players"] = [
        {"id": "gp-1", "game_id": "game-ok", "user_id": users["organizer"]["id"]},
        {"id": "gp-2", "game_id": "game-bad", "user_id": users["organizer"]["id"]},
    ]

    call_count = {"n": 0}
    original_insert = FakeQuery.insert

    def failing_insert_once(self, payload):
        payloads = payload if isinstance(payload, list) else [payload]
        for row in payloads:
            if row.get("game_id") == "game-bad" and row.get("type") == "scheduled_game_reminder":
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("transient failure")
        return original_insert(self, payload)

    monkeypatch.setattr(FakeQuery, "insert", failing_insert_once)
    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", lambda *a, **kw: {"ok": True})

    run1 = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )
    assert "game-ok" in run1["processed_game_ids"]
    assert "game-bad" in run1["failed_game_ids"]

    run2 = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 1, tzinfo=timezone.utc),
    )

    assert "game-ok" in run2["skipped_game_ids"]
    assert "game-bad" in run2["processed_game_ids"]
    assert run2["notifications_created"] == 1

    reminders = scheduled_game_reminder_notifications(fake_supabase)
    ok_reminders = [r for r in reminders if r["game_id"] == "game-ok"]
    bad_reminders = [r for r in reminders if r["game_id"] == "game-bad"]
    assert len(ok_reminders) == 1
    assert len(bad_reminders) == 1


def test_scheduled_reminder_failure_is_logged(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
    caplog,
) -> None:
    game = make_scheduled_game(users, id="game-fail")
    fake_supabase.tables["games"] = [game]
    fake_supabase.tables["game_players"] = [
        {"id": "gp-1", "game_id": "game-fail", "user_id": users["organizer"]["id"]},
    ]

    original_insert = FakeQuery.insert

    def failing_insert(self, payload):
        payloads = payload if isinstance(payload, list) else [payload]
        for row in payloads:
            if row.get("game_id") == "game-fail" and row.get("type") == "scheduled_game_reminder":
                raise RuntimeError("db error")
        return original_insert(self, payload)

    monkeypatch.setattr(FakeQuery, "insert", failing_insert)

    with caplog.at_level(logging.ERROR, logger="app.routers.notifications"):
        result = run_scheduled_reminders(
            fake_supabase,
            datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
        )

    assert "game-fail" in result["failed_game_ids"]
    assert any(
        "Failed to process scheduled game reminder" in record.message
        for record in caplog.records
    )


def test_scheduled_reminder_result_shape_includes_failure_fields(
    fake_supabase: FakeSupabase,
    monkeypatch,
    users: dict[str, dict[str, Any]],
) -> None:
    game = make_scheduled_game(users)
    fake_supabase.tables["games"] = [game]
    set_game_participants(fake_supabase, game["id"], [users["organizer"]["id"]])
    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", lambda *a, **kw: {"ok": True})

    result = run_scheduled_reminders(
        fake_supabase,
        datetime(2026, 6, 22, 19, 0, tzinfo=timezone.utc),
    )

    assert "processed_game_ids" in result
    assert "skipped_game_ids" in result
    assert "failed_game_ids" in result
    assert "errors" in result
    assert "notifications_created" in result
    assert "notifications" in result
    assert result["failed_game_ids"] == []
    assert result["errors"] == []
