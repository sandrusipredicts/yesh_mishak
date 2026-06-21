from __future__ import annotations

from copy import deepcopy
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

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)


def field_ids(count: int) -> list[str]:
    return [f"field-{index}" for index in range(count)]


def make_field(field_id: str) -> dict[str, Any]:
    return {
        "id": field_id,
        "name": field_id,
        "verified": True,
        "approval_status": "approved",
        "sport_type": "both",
    }


def test_get_active_games_for_fields_batches_large_field_id_list(monkeypatch) -> None:
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
    monkeypatch.setattr(game_payloads, "get_supabase_client", lambda: fake_client)

    games_by_field = game_payloads.get_active_games_for_fields(ids)

    assert set(games_by_field) == {"field-1", "field-120"}
    assert games_by_field["field-1"]["participants"] == [
        {"user_id": "user-1", "username": "alice", "name": "alice"}
    ]
    assert games_by_field["field-120"]["participants"] == [
        {"user_id": "user-2", "username": None, "name": "Bob"}
    ]
    field_id_batches = [
        values
        for table, column, values in fake_client.in_filter_calls
        if table == "games" and column == "field_id"
    ]
    assert [len(batch) for batch in field_id_batches] == [100, 100, 5]


def test_get_upcoming_games_for_fields_batches_large_field_id_list(monkeypatch) -> None:
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
    monkeypatch.setattr(game_payloads, "get_supabase_client", lambda: fake_client)

    games_by_field = game_payloads.get_upcoming_games_for_fields(ids)

    assert [game["id"] for game in games_by_field["field-4"]] == ["upcoming-1"]
    assert [game["id"] for game in games_by_field["field-204"]] == ["upcoming-2"]
    field_id_batches = [
        values
        for table, column, values in fake_client.in_filter_calls
        if table == "games" and column == "field_id"
    ]
    assert [len(batch) for batch in field_id_batches] == [100, 100, 5]


def test_get_fields_handles_1357_fields_without_large_game_lookup(monkeypatch) -> None:
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
    monkeypatch.setattr(game_payloads, "get_supabase_client", lambda: fake_client)

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
    field_id_batches = [
        values
        for table, column, values in fake_client.in_filter_calls
        if table == "games" and column == "field_id"
    ]
    assert all(len(batch) <= 100 for batch in field_id_batches)
    assert [len(batch) for batch in field_id_batches] == [100] * 13 + [57]


def test_batched_select_retries_temporary_supabase_failure(monkeypatch) -> None:
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
    monkeypatch.setattr(game_payloads, "get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(game_payloads.time, "sleep", lambda _: None)

    games_by_field = game_payloads.get_active_games_for_fields(["field-1"])

    assert set(games_by_field) == {"field-1"}
    games_execute_calls = [
        call for call in fake_client.execute_calls if call[0] == "games"
    ]
    assert len(games_execute_calls) == 2
