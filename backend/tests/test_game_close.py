from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeTableQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.update_payload: dict[str, Any] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.delete_requested = False
        self.selected_columns: list[str] | None = None

    def select(self, columns: str, count: str | None = None) -> "FakeTableQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeTableQuery":
        self.in_filters.append((column, values))
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def update(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.update_payload = payload
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.insert_payload = payload
        return self

    def delete(self) -> "FakeTableQuery":
        self.delete_requested = True
        return self

    def execute(self) -> FakeResponse:
        rows = self._filtered_rows()

        if self.insert_payload is not None:
            row = {"id": f"inserted-{len(self.rows) + 1}", **self.insert_payload}
            self.rows.append(row)
            return FakeResponse([row])

        if self.update_payload is not None:
            for row in rows:
                row.update(self.update_payload)
            if any(row.get("_return_empty_on_update") for row in rows):
                return FakeResponse([])
            return FakeResponse(rows)

        if self.delete_requested:
            for row in rows:
                self.rows.remove(row)
            return FakeResponse(rows)

        return FakeResponse([self._select_columns(row) for row in rows])

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = self.rows
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        return rows

    def _select_columns(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None or "*" in self.selected_columns:
            return row
        return {column: row.get(column) for column in self.selected_columns}


class FakeSupabaseClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, table_name: str) -> FakeTableQuery:
        assert table_name in self.tables
        return FakeTableQuery(self.tables[table_name])


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def make_user(user_id: str) -> dict[str, str]:
    return {
        "id": user_id,
        "email": f"{user_id}@example.com",
        "name": user_id,
        "role": "user",
    }


def make_token(user: dict[str, str]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def make_client(monkeypatch, tables: dict[str, list[dict[str, Any]]]) -> TestClient:
    fake_client = FakeSupabaseClient(tables)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake_client)
    return TestClient(app)


def auth_headers(user: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user)}"}


def test_game_creator_can_close_game(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "games": [
            {
                "id": "game-1",
                "created_by": creator["id"],
                "status": "open",
                "players_present": 1,
                "max_players": 5,
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/close", headers=auth_headers(creator))

    assert response.status_code == 200
    assert response.json()["game"]["status"] == "finished"
    assert tables["games"][0]["status"] == "finished"


def test_non_creator_cannot_close_game(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    creator = make_user("creator")
    other_user = make_user("other")
    tables = {
        "users": [other_user],
        "games": [
            {
                "id": "game-1",
                "created_by": creator["id"],
                "status": "open",
                "players_present": 1,
                "max_players": 5,
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/close", headers=auth_headers(other_user))

    assert response.status_code == 403
    assert tables["games"][0]["status"] == "open"


def test_close_game_reads_and_updates_with_standard_game_client(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "games": [
            {
                "id": "game-1",
                "created_by": creator["id"],
                "status": "open",
                "players_present": 1,
                "max_players": 5,
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/close", headers=auth_headers(creator))

    assert response.status_code == 200
    assert response.json()["game"]["status"] == "finished"
    assert tables["games"][0]["status"] == "finished"


def test_close_game_refetches_when_update_returns_no_rows(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "games": [
            {
                "id": "game-1",
                "created_by": creator["id"],
                "status": "open",
                "players_present": 1,
                "max_players": 5,
                "_return_empty_on_update": True,
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/close", headers=auth_headers(creator))

    assert response.status_code == 200
    assert response.json()["game"]["status"] == "finished"
    assert tables["games"][0]["status"] == "finished"


def test_closed_game_is_not_returned_as_active(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = make_user("user")
    tables = {
        "users": [user],
        "games": [
            {"id": "game-open", "field_id": "field-1", "status": "open"},
            {"id": "game-closed", "field_id": "field-2", "status": "finished"},
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert [game["id"] for game in response.json()] == ["game-open"]


def test_game_before_end_time_is_returned_as_active(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    user = make_user("user")
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-active",
                "field_id": "field-1",
                "status": "open",
                "started_at": "2026-06-16T17:00:00+00:00",
                "expires_at": "2026-06-16T19:00:00+00:00",
            },
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert [game["id"] for game in response.json()] == ["game-active"]
    assert tables["games"][0]["status"] == "open"


def test_game_at_end_time_is_finished_and_hidden_from_active_games(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 20, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    user = make_user("user")
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-expired",
                "field_id": "field-1",
                "status": "open",
                "started_at": "2026-06-16T18:00:00+00:00",
                "expires_at": "2026-06-16T20:00:00+00:00",
            },
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []
    assert tables["games"][0]["status"] == "finished"


def test_expired_game_is_not_returned_as_field_active_game(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 20, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    user = make_user("user")
    tables = {
        "users": [user],
        "fields": [
            {
                "id": "field-1",
                "name": "Central Field",
                "verified": True,
                "approval_status": "approved",
            },
        ],
        "games": [
            {
                "id": "game-expired",
                "field_id": "field-1",
                "status": "open",
                "started_at": "2026-06-16T18:00:00+00:00",
                "expires_at": "2026-06-16T20:00:00+00:00",
            },
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    assert response.json()["active_game"] is None
    assert tables["games"][0]["status"] == "finished"


def test_expired_game_does_not_block_new_game_creation(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 20, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "fields": [
            {
                "id": "field-1",
                "name": "Central Field",
                "sport_type": "football",
                "verified": True,
                "approval_status": "approved",
            },
        ],
        "games": [
            {
                "id": "game-expired",
                "field_id": "field-1",
                "created_by": "other-user",
                "sport_type": "football",
                "status": "open",
                "players_present": 3,
                "max_players": 5,
                "started_at": "2026-06-16T18:00:00+00:00",
                "expires_at": "2026-06-16T20:00:00+00:00",
            },
        ],
        "game_players": [],
        "notification_preferences": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post(
        "/games/",
        json={
            "field_id": "field-1",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 5,
        },
        headers=auth_headers(creator),
    )

    assert response.status_code == 200
    assert response.json()["game"]["field_id"] == "field-1"
    assert tables["games"][0]["status"] == "finished"
    assert len(tables["games"]) == 2


def test_user_cannot_join_closed_game(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = make_user("user")
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-1",
                "created_by": "creator",
                "status": "finished",
                "players_present": 1,
                "max_players": 5,
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/join", headers=auth_headers(user))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"


def test_user_cannot_join_game_after_end_time(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 20, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    user = make_user("user")
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-1",
                "created_by": "creator",
                "status": "open",
                "players_present": 1,
                "max_players": 5,
                "expires_at": "2026-06-16T20:00:00+00:00",
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/join", headers=auth_headers(user))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "finished"


def test_join_game_uses_authenticated_user_not_request_body(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user_a = make_user("user-a")
    user_b = make_user("user-b")
    tables = {
        "users": [user_a, user_b],
        "games": [
            {
                "id": "game-1",
                "created_by": "creator",
                "status": "open",
                "players_present": 1,
                "max_players": 5,
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post(
        "/games/game-1/join",
        headers=auth_headers(user_a),
        json={"user_id": user_b["id"]},
    )

    assert response.status_code == 200
    assert tables["game_players"] == [
        {
            "id": "inserted-1",
            "game_id": "game-1",
            "user_id": user_a["id"],
        }
    ]


def test_two_jwt_users_join_independently(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user_a = make_user("user-a")
    user_b = make_user("user-b")
    tables = {
        "users": [user_a, user_b],
        "games": [
            {
                "id": "game-1",
                "created_by": "creator",
                "status": "open",
                "players_present": 1,
                "max_players": 5,
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    first_response = client.post("/games/game-1/join", headers=auth_headers(user_a))
    second_response = client.post("/games/game-1/join", headers=auth_headers(user_b))

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert [player["user_id"] for player in tables["game_players"]] == [
        user_a["id"],
        user_b["id"],
    ]


def test_creator_cannot_extend_closed_game(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "games": [
            {
                "id": "game-1",
                "created_by": creator["id"],
                "status": "finished",
                "players_present": 1,
                "max_players": 5,
                "expires_at": "2026-06-16T10:00:00+00:00",
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/extend", headers=auth_headers(creator))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"


def test_creator_cannot_extend_game_after_end_time(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 20, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "games": [
            {
                "id": "game-1",
                "created_by": creator["id"],
                "status": "open",
                "players_present": 1,
                "max_players": 5,
                "expires_at": "2026-06-16T20:00:00+00:00",
            }
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.post("/games/game-1/extend", headers=auth_headers(creator))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "finished"
