from dataclasses import dataclass
from datetime import datetime, timezone
import logging
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

    def is_(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append(("__is", (column, value)))
        return self

    def gte(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append(("__gte", (column, value)))
        return self

    def lte(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append(("__lte", (column, value)))
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def order(self, _column: str, *, desc: bool = False) -> "FakeTableQuery":
        return self

    def range(self, _start: int, _end: int) -> "FakeTableQuery":
        return self

    def update(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.update_payload = payload
        return self

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]) -> "FakeTableQuery":
        self.insert_payload = payload
        return self

    def delete(self) -> "FakeTableQuery":
        self.delete_requested = True
        return self

    def execute(self) -> FakeResponse:
        rows = self._filtered_rows()

        if self.insert_payload is not None:
            if isinstance(self.insert_payload, list):
                inserted = []
                for item in self.insert_payload:
                    row = {"id": f"inserted-{len(self.rows) + 1}", **item}
                    self.rows.append(row)
                    inserted.append(row)
                return FakeResponse(inserted)
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
            if column == "__gte":
                col, threshold = value
                rows = [row for row in rows if row.get(col) is not None and row[col] >= threshold]
            elif column == "__lte":
                col, threshold = value
                rows = [row for row in rows if row.get(col) is not None and row[col] <= threshold]
            elif column == "__is":
                col, is_value = value
                if is_value in (None, "null"):
                    rows = [row for row in rows if row.get(col) is None]
                elif is_value == "not.null":
                    rows = [row for row in rows if row.get(col) is not None]
                else:
                    rows = [row for row in rows if row.get(col) == is_value]
            else:
                rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        return rows

    def _select_columns(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None or "*" in self.selected_columns:
            return row
        return {column: row.get(column) for column in self.selected_columns}


class FakeRpcQuery:
    """Simulates game RPCs used by the test application."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]], function_name: str, params: dict[str, Any]) -> None:
        self.tables = tables
        self.function_name = function_name
        self.params = params

    def execute(self) -> FakeResponse:
        if self.function_name == "get_field_game_payloads":
            field_ids = set(self.params["p_field_ids"])
            payloads = [
                {"payload": {**dict(game), "participants": []}}
                for game in self.tables.get("games", [])
                if game.get("field_id") in field_ids
                and game.get("status") in ("open", "full")
            ]
            return FakeResponse(payloads)

        game_id = self.params["p_game_id"]
        user_id = self.params["p_user_id"]

        games = [g for g in self.tables.get("games", []) if g["id"] == game_id]
        if not games:
            return FakeResponse([{"error": "Game not found"}])
        game = games[0]

        if game["status"] not in ("open", "full"):
            return FakeResponse([{"error": "Game already closed"}])

        if game["players_present"] >= game["max_players"]:
            return FakeResponse([{"error": "Game is full"}])

        already = [
            gp for gp in self.tables.get("game_players", [])
            if gp.get("game_id") == game_id and gp.get("user_id") == user_id
        ]
        if already:
            return FakeResponse([{"error": "User already joined"}])

        self.tables["game_players"].append(
            {"id": f"gp-rpc-{len(self.tables['game_players'])}", "game_id": game_id, "user_id": user_id}
        )
        game["players_present"] += 1
        game["status"] = "full" if game["players_present"] >= game["max_players"] else "open"

        return FakeResponse([{"game": dict(game)}])


class FakeSupabaseClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, table_name: str) -> FakeTableQuery:
        assert table_name in self.tables
        return FakeTableQuery(self.tables[table_name])

    def rpc(self, function_name: str, params: dict[str, Any]) -> FakeRpcQuery:
        assert function_name in ("join_game_atomic", "get_field_game_payloads")
        return FakeRpcQuery(self.tables, function_name, params)


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


def make_approved_field(field_id: str = "field-1", sport_type: str = "football") -> dict[str, Any]:
    return {
        "id": field_id,
        "name": "Central Field",
        "sport_type": sport_type,
        "verified": True,
        "approval_status": "approved",
        "status": "open",
    }


def freeze_game_time(monkeypatch, now: datetime) -> None:
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: now)
    monkeypatch.setattr("app.routers.games.get_now", lambda: now)


def test_create_current_game_without_scheduled_at_still_works(monkeypatch, caplog) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    freeze_game_time(monkeypatch, now)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "fields": [make_approved_field()],
        "games": [],
        "game_players": [],
        "notification_preferences": [],
    }
    client = make_client(monkeypatch, tables)

    with caplog.at_level(logging.INFO, logger="app.routers.games"):
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
    created_game = response.json()["game"]
    assert created_game["scheduled_at"] is None
    assert created_game["started_at"] == "2026-06-16T18:00:00+00:00"
    assert tables["game_players"][0]["user_id"] == creator["id"]
    create_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "games.create.success"
    ]
    assert create_records
    assert create_records[-1].game_id == created_game["id"]
    assert create_records[-1].field_id == "field-1"
    assert create_records[-1].user_id == creator["id"]


def test_create_scheduled_game_in_future_works(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    freeze_game_time(monkeypatch, now)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "fields": [make_approved_field()],
        "games": [],
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
            "scheduled_at": "2026-06-17T18:30:00Z",
        },
        headers=auth_headers(creator),
    )

    assert response.status_code == 200
    created_game = response.json()["game"]
    assert created_game["scheduled_at"] == "2026-06-17T18:30:00+00:00"
    assert created_game["started_at"] == "2026-06-17T18:30:00+00:00"
    assert created_game["expires_at"] == "2026-06-17T20:30:00+00:00"
    assert tables["game_players"][0]["user_id"] == creator["id"]


def test_create_scheduled_game_in_past_fails(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    freeze_game_time(monkeypatch, now)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "fields": [make_approved_field()],
        "games": [],
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
            "scheduled_at": "2026-06-16T17:59:00Z",
        },
        headers=auth_headers(creator),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "scheduled_at must be in the future"
    assert response.json()["error"] is True
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert tables["games"] == []


def test_upcoming_endpoint_returns_future_games(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    freeze_game_time(monkeypatch, now)
    user = make_user("user")
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-now",
                "field_id": "field-1",
                "status": "open",
                "scheduled_at": None,
            },
            {
                "id": "game-future",
                "field_id": "field-1",
                "status": "open",
                "scheduled_at": "2026-06-17T18:30:00+00:00",
                "players_present": 1,
                "max_players": 5,
            },
        ],
        "game_players": [{"game_id": "game-future", "user_id": user["id"]}],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert [game["id"] for game in response.json()] == ["game-future"]
    assert response.json()[0]["participants"] == [
        {"user_id": user["id"], "username": None, "name": user["name"]}
    ]


def test_active_endpoint_excludes_future_scheduled_games(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    freeze_game_time(monkeypatch, now)
    user = make_user("user")
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-active",
                "field_id": "field-1",
                "status": "open",
                "scheduled_at": None,
                "expires_at": "2026-06-16T19:00:00+00:00",
            },
            {
                "id": "game-future",
                "field_id": "field-1",
                "status": "open",
                "scheduled_at": "2026-06-17T18:30:00+00:00",
                "expires_at": "2026-06-17T20:30:00+00:00",
            },
        ],
        "game_players": [],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert [game["id"] for game in response.json()] == ["game-active"]


def test_field_details_include_upcoming_but_not_as_active_game(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    freeze_game_time(monkeypatch, now)
    user = make_user("user")
    tables = {
        "users": [user],
        "fields": [make_approved_field()],
        "games": [
            {
                "id": "game-future",
                "field_id": "field-1",
                "sport_type": "football",
                "status": "open",
                "scheduled_at": "2026-06-17T18:30:00+00:00",
                "expires_at": "2026-06-17T20:30:00+00:00",
            },
        ],
        "game_players": [{"game_id": "game-future", "user_id": user["id"]}],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    field = response.json()
    assert field["active_game"] is None
    assert [game["id"] for game in field["upcoming_games"]] == ["game-future"]
    assert field["upcoming_games"][0]["participants"] == [
        {"user_id": user["id"], "username": None, "name": user["name"]}
    ]


def test_duplicate_exact_scheduled_game_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime(2026, 6, 16, 18, 0, tzinfo=timezone.utc)
    freeze_game_time(monkeypatch, now)
    creator = make_user("creator")
    tables = {
        "users": [creator],
        "fields": [make_approved_field()],
        "games": [
            {
                "id": "game-existing",
                "field_id": "field-1",
                "sport_type": "football",
                "status": "open",
                "scheduled_at": "2026-06-17T18:30:00+00:00",
                "expires_at": "2026-06-17T20:30:00+00:00",
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
            "scheduled_at": "2026-06-17T18:30:00Z",
        },
        headers=auth_headers(creator),
    )

    assert response.status_code == 400
    assert response.json()["message"] == (
        "Scheduled game already exists for this field and sport at this time"
    )
    assert response.json()["error"] is True
    assert response.json()["code"] == "CONFLICT"
    assert len(tables["games"]) == 1


def test_game_creator_can_close_game(monkeypatch, caplog) -> None:
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

    with caplog.at_level(logging.INFO, logger="app.routers.games"):
        response = client.post("/games/game-1/close", headers=auth_headers(creator))

    assert response.status_code == 200
    assert response.json()["game"]["status"] == "finished"
    assert tables["games"][0]["status"] == "finished"
    close_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "games.close.success"
    ]
    assert close_records
    assert close_records[-1].game_id == "game-1"
    assert close_records[-1].user_id == creator["id"]
    assert close_records[-1].closed_by_role == "creator"


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


def test_active_games_include_participant_usernames(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = {**make_user("user-1"), "username": "Marom"}
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-active",
                "field_id": "field-1",
                "status": "open",
                "players_present": 1,
                "max_players": 5,
            },
        ],
        "game_players": [
            {
                "id": "player-1",
                "game_id": "game-active",
                "user_id": user["id"],
            },
        ],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json()[0]["participants"] == [
        {
            "user_id": user["id"],
            "username": "Marom",
            "name": "Marom",
        }
    ]


def test_active_games_keep_participant_when_username_is_missing(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = {**make_user("user-1"), "username": None}
    tables = {
        "users": [user],
        "games": [
            {
                "id": "game-active",
                "field_id": "field-1",
                "status": "open",
                "players_present": 1,
                "max_players": 5,
            },
        ],
        "game_players": [
            {
                "id": "player-1",
                "game_id": "game-active",
                "user_id": user["id"],
            },
        ],
    }
    client = make_client(monkeypatch, tables)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json()[0]["participants"] == [
        {
            "user_id": user["id"],
            "username": None,
            "name": user["name"],
        }
    ]


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
                "status": "open",
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
                "status": "open",
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
    assert response.json()["message"] == "Game already closed"
    assert response.json()["error"] is True
    assert response.json()["code"] == "GAME_NOT_ACTIONABLE"


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
    assert response.json()["message"] == "Game already closed"
    assert response.json()["error"] is True
    assert response.json()["code"] == "GAME_NOT_ACTIONABLE"
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
    assert len(tables["game_players"]) == 1
    assert tables["game_players"][0]["game_id"] == "game-1"
    assert tables["game_players"][0]["user_id"] == user_a["id"]


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
    assert response.json()["message"] == "Game already closed"
    assert response.json()["error"] is True
    assert response.json()["code"] == "GAME_NOT_ACTIONABLE"


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
    assert response.json()["message"] == "Game already closed"
    assert response.json()["error"] is True
    assert response.json()["code"] == "GAME_NOT_ACTIONABLE"
    assert tables["games"][0]["status"] == "finished"
