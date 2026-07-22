from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.routers import game_payloads


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, client: "FakeSupabaseClient", table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.selected_columns: list[str] | None = None
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.range_filter: tuple[int, int] | None = None

    def select(self, columns: str) -> "FakeQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def is_(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((f"__is__{column}", value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        if len(values) > self.client.max_in_values:
            raise AssertionError(f"{column} in_ batch exceeded {self.client.max_in_values}: {len(values)}")
        self.client.in_filter_calls.append((self.table_name, column, list(values)))
        self.in_filters.append((column, values))
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.client.range_calls.append((self.table_name, start, end))
        self.range_filter = (start, end)
        return self

    def execute(self) -> FakeResponse:
        self.client.execute_calls.append((self.table_name, list(self.in_filters)))
        if self.client.fail_next_execute_count > 0:
            self.client.fail_next_execute_count -= 1
            raise RuntimeError("temporary supabase transport failure")

        rows = self.client.tables.get(self.table_name, [])
        for column, value in self.filters:
            if column.startswith("__is__"):
                real_column = column[len("__is__"):]
                if value in (None, "null"):
                    rows = [row for row in rows if row.get(real_column) is None]
                elif value == "not.null":
                    rows = [row for row in rows if row.get(real_column) is not None]
                else:
                    rows = [row for row in rows if row.get(real_column) == value]
            else:
                rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        if self.range_filter is None and self.table_name == "fields":
            rows = rows[: self.client.default_fields_limit]
        elif self.range_filter is not None:
            start, end = self.range_filter
            rows = rows[start : end + 1]
        return FakeResponse([self._select(row) for row in rows])

    def _select(self, row: dict[str, Any]) -> dict[str, Any]:
        if not self.selected_columns or "*" in self.selected_columns:
            return deepcopy(row)
        return {column: row.get(column) for column in self.selected_columns}


class FakeSupabaseClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]], max_in_values: int = 100) -> None:
        self.tables = tables
        self.max_in_values = max_in_values
        self.in_filter_calls: list[tuple[str, str, list[Any]]] = []
        self.range_calls: list[tuple[str, int, int]] = []
        self.execute_calls: list[tuple[str, list[tuple[str, list[Any]]]]] = []
        self.fail_next_execute_count = 0
        self.default_fields_limit = 1000
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def rpc(self, function_name: str, params: dict[str, Any]) -> "FakeRpcQuery":
        self.rpc_calls.append((function_name, deepcopy(params)))
        return FakeRpcQuery(self, function_name, params)


class FakeRpcQuery:
    def __init__(self, client: FakeSupabaseClient, function_name: str, params: dict[str, Any]) -> None:
        self.client = client
        self.function_name = function_name
        self.params = params

    def execute(self) -> FakeResponse:
        self.client.execute_calls.append((f"rpc:{self.function_name}", []))
        if self.client.fail_next_execute_count > 0:
            self.client.fail_next_execute_count -= 1
            raise RuntimeError("temporary supabase transport failure")

        assert self.function_name == "get_field_game_payloads"
        requested = set(self.params["p_field_ids"])
        now = datetime.now(timezone.utc)
        users = {str(user["id"]): user for user in self.client.tables.get("users", [])}
        player_rows = self.client.tables.get("game_players", [])
        payloads = []
        for game in self.client.tables.get("games", []):
            if game.get("field_id") not in requested or game.get("status") not in ("open", "full"):
                continue
            expires_at = game.get("expires_at")
            if expires_at and datetime.fromisoformat(str(expires_at).replace("Z", "+00:00")) <= now:
                game["status"] = "finished"
                continue
            participants = []
            for player in player_rows:
                if player.get("game_id") != game.get("id"):
                    continue
                user = users.get(str(player.get("user_id")), {})
                participants.append({
                    "user_id": player.get("user_id"),
                    "username": user.get("username"),
                    "name": user.get("username") or user.get("name") or "Unknown player",
                })
            payloads.append({"payload": {**deepcopy(game), "participants": participants}})
        return FakeResponse(payloads)


def field_ids(count: int) -> list[str]:
    return [f"field-{index}" for index in range(count)]


def make_field(field_id: str) -> dict[str, Any]:
    return {
        "id": field_id,
        "name": field_id,
        "verified": True,
        "approval_status": "approved",
        "status": "open",
        "sport_type": "both",
    }


def test_get_active_games_for_fields_uses_one_rpc_for_large_field_id_list(monkeypatch) -> None:
    ids = field_ids(205)
    fake_client = FakeSupabaseClient(
        {
            "games": [
                {"id": "game-1", "field_id": "field-1", "status": "open", "scheduled_at": None},
                {"id": "game-2", "field_id": "field-120", "status": "full", "scheduled_at": None},
                {"id": "finished", "field_id": "field-150", "status": "finished", "scheduled_at": None},
            ],
            "game_players": [
                {"game_id": "game-1", "user_id": "user-1"},
                {"game_id": "game-2", "user_id": "user-2"},
            ],
            "users": [
                {"id": "user-1", "username": "alice", "name": "Alice"},
                {"id": "user-2", "username": None, "name": "Bob"},
            ],
        }
    )
    monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: fake_client)

    games_by_field, _ = game_payloads.get_map_game_payloads_for_fields(ids)

    assert set(games_by_field) == {"field-1", "field-120"}
    assert games_by_field["field-1"]["participants"] == [
        {"user_id": "user-1", "username": "alice", "name": "alice"}
    ]
    assert games_by_field["field-120"]["participants"] == [
        {"user_id": "user-2", "username": None, "name": "Bob"}
    ]
    assert fake_client.rpc_calls == [("get_field_game_payloads", {"p_field_ids": ids})]


def test_get_upcoming_games_for_fields_uses_one_rpc_for_large_field_id_list(monkeypatch) -> None:
    ids = field_ids(205)
    fake_client = FakeSupabaseClient(
        {
            "games": [
                {
                    "id": "upcoming-1",
                    "field_id": "field-4",
                    "status": "open",
                    "scheduled_at": "2999-01-01T18:00:00+00:00",
                },
                {
                    "id": "upcoming-2",
                    "field_id": "field-204",
                    "status": "open",
                    "scheduled_at": "2999-01-02T18:00:00+00:00",
                },
            ],
            "game_players": [],
            "users": [],
        }
    )
    monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: fake_client)

    _, games_by_field = game_payloads.get_map_game_payloads_for_fields(ids)

    assert [game["id"] for game in games_by_field["field-4"]] == ["upcoming-1"]
    assert [game["id"] for game in games_by_field["field-204"]] == ["upcoming-2"]
    assert fake_client.rpc_calls == [("get_field_game_payloads", {"p_field_ids": ids})]


def test_get_fields_handles_1357_fields_with_one_game_payload_request(monkeypatch) -> None:
    ids = field_ids(1357)
    fake_client = FakeSupabaseClient(
        {
            "fields": [make_field(field_id) for field_id in ids],
            "games": [
                {"id": "game-1", "field_id": "field-1", "status": "open", "scheduled_at": None},
                {
                    "id": "upcoming-1",
                    "field_id": "field-1200",
                    "status": "open",
                    "scheduled_at": "2999-01-01T18:00:00+00:00",
                },
            ],
            "game_players": [],
            "users": [],
        }
    )
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: fake_client)

    response = TestClient(app).get("/fields/")

    assert response.status_code == 200
    fields = response.json()
    assert len(fields) == 1357
    assert fake_client.range_calls[:2] == [
        ("fields", 0, 999),
        ("fields", 1000, 1999),
    ]
    assert fields[1]["active_game"]["id"] == "game-1"
    assert fields[1200]["upcoming_games"][0]["id"] == "upcoming-1"
    assert fake_client.rpc_calls == [("get_field_game_payloads", {"p_field_ids": ids})]


def test_fields_map_request_count_is_constant_for_normal_field_counts(monkeypatch) -> None:
    for count in (1, 10, 50):
        ids = field_ids(count)
        fake_client = FakeSupabaseClient({
            "fields": [make_field(field_id) for field_id in ids],
            "games": [],
            "game_players": [],
            "users": [],
        })
        monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake_client)
        monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: fake_client)

        response = TestClient(app).get("/fields/")

        assert response.status_code == 200
        assert len(response.json()) == count
        assert len(fake_client.execute_calls) == 2
        assert [call[0] for call in fake_client.execute_calls] == ["fields", "rpc:get_field_game_payloads"]


def test_fields_map_no_games_removed_fields_multiple_games_and_marker_state(monkeypatch) -> None:
    fields = [make_field("no-game"), make_field("busy"), {**make_field("removed"), "removed_at": "2026-01-01T00:00:00Z"}]
    fake_client = FakeSupabaseClient({
        "fields": fields,
        "games": [
            {"id": "active", "field_id": "busy", "status": "open", "scheduled_at": None, "players_present": 2},
            {"id": "upcoming-1", "field_id": "busy", "status": "open", "scheduled_at": "2999-01-01T18:00:00+00:00", "players_present": 1},
            {"id": "upcoming-2", "field_id": "busy", "status": "full", "scheduled_at": "2999-01-02T18:00:00+00:00", "players_present": 2},
        ],
        "game_players": [
            {"game_id": "active", "user_id": "user-1"},
            {"game_id": "active", "user_id": "user-2"},
        ],
        "users": [
            {"id": "user-1", "username": "alice", "name": "Alice"},
            {"id": "user-2", "username": None, "name": "Bob"},
        ],
    })
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: fake_client)

    response = TestClient(app).get("/fields/")

    assert response.status_code == 200
    result = {field["id"]: field for field in response.json()}
    assert set(result) == {"no-game", "busy"}
    assert result["no-game"]["active_game"] is None
    assert result["no-game"]["upcoming_games"] == []
    assert result["busy"]["active_game"]["players_present"] == 2
    assert result["busy"]["active_game"]["participants"] == [
        {"user_id": "user-1", "username": "alice", "name": "alice"},
        {"user_id": "user-2", "username": None, "name": "Bob"},
    ]
    assert [game["id"] for game in result["busy"]["upcoming_games"]] == ["upcoming-1", "upcoming-2"]
    assert len(fake_client.execute_calls) == 2


def test_game_payload_rpc_retries_transport_failure_without_fan_out(monkeypatch) -> None:
    fake_client = FakeSupabaseClient(
        {
            "games": [
                {"id": "game-1", "field_id": "field-1", "status": "open", "scheduled_at": None},
            ],
            "game_players": [],
            "users": [],
        }
    )
    fake_client.fail_next_execute_count = 1
    monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: fake_client)
    monkeypatch.setattr(game_payloads.time, "sleep", lambda _: None)

    games_by_field, _ = game_payloads.get_map_game_payloads_for_fields(["field-1"])

    assert set(games_by_field) == {"field-1"}
    assert [call[0] for call in fake_client.execute_calls] == [
        "rpc:get_field_game_payloads",
        "rpc:get_field_game_payloads",
    ]


def test_fields_map_rpc_uses_service_role_and_never_public_client(monkeypatch) -> None:
    public_client = FakeSupabaseClient({
        "fields": [make_field("field-1")],
        "games": [],
        "game_players": [],
        "users": [],
    })
    service_client = FakeSupabaseClient({
        "games": [{"id": "game-1", "field_id": "field-1", "status": "open", "scheduled_at": None}],
        "game_players": [],
        "users": [],
    })
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: public_client)
    monkeypatch.setattr(game_payloads, "get_supabase_client", lambda: public_client)
    monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: service_client)

    response = TestClient(app).get("/fields/")

    assert response.status_code == 200
    assert response.json()[0]["active_game"]["id"] == "game-1"
    assert public_client.rpc_calls == []
    assert service_client.rpc_calls == [
        ("get_field_game_payloads", {"p_field_ids": ["field-1"]})
    ]


def test_fields_map_rpc_reconciles_expired_games(monkeypatch) -> None:
    expired_game = {
        "id": "expired",
        "field_id": "field-1",
        "status": "open",
        "scheduled_at": None,
        "expires_at": "2000-01-01T00:00:00+00:00",
    }
    fake_client = FakeSupabaseClient({
        "games": [expired_game],
        "game_players": [],
        "users": [],
    })
    monkeypatch.setattr(game_payloads, "get_supabase_service_role_client", lambda: fake_client)

    active, upcoming = game_payloads.get_map_game_payloads_for_fields(["field-1"])

    assert active == {}
    assert upcoming == {"field-1": []}
    assert expired_game["status"] == "finished"


def test_fields_map_migration_locks_rpc_to_service_role() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "fields_map_payload_rpc.sql"
    ).read_text(encoding="utf-8").lower()

    assert "begin;" in migration
    assert migration.strip().endswith("commit;")
    assert "security invoker" in migration
    assert "set search_path = public" in migration
    for role in ("public", "anon", "authenticated"):
        assert (
            "revoke all on function public.get_field_game_payloads(uuid[]) "
            f"from {role};"
        ) in migration
    assert (
        "grant execute on function public.get_field_game_payloads(uuid[]) "
        "to service_role;"
    ) in migration
    assert "to anon" not in migration
    assert "to authenticated" not in migration
    assert "update public.games" in migration
    assert "from public.game_players" in migration
    assert "left join public.users" in migration
    assert "from public.games g" in migration
    assert " drop " not in migration
    assert " delete " not in migration
    assert " truncate " not in migration
