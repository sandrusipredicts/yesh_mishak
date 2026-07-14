from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.selected_columns: list[str] | None = None
        self.order_column: str | None = None
        self.order_desc: bool = False
        self.limit_count: int | None = None

    def select(self, columns: str = "*") -> "FakeQuery":
        self.selected_columns = [c.strip() for c in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.in_filters.append((column, values))
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.order_column = column
        self.order_desc = desc
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def execute(self) -> FakeResponse:
        rows = list(self.database.tables.setdefault(self.table_name, []))
        for column, value in self.filters:
            rows = [r for r in rows if r.get(column) == value]
        for column, values in self.in_filters:
            rows = [r for r in rows if r.get(column) in values]
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        if not self.selected_columns or "*" in self.selected_columns:
            return FakeResponse([dict(r) for r in rows])
        return FakeResponse(
            [{c: r.get(c) for c in self.selected_columns} for r in rows]
        )


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, table_name: str) -> FakeQuery:
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)


def configure_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def make_user(user_id: str = "user-1") -> dict[str, str]:
    return {
        "id": user_id,
        "email": f"{user_id}@example.com",
        "name": user_id,
        "role": "user",
    }


def auth_headers(user: dict[str, str]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def make_report(
    report_id: str,
    user_id: str,
    field_id: str = "field-1",
    status: str = "open",
    admin_note: str | None = None,
) -> dict[str, Any]:
    return {
        "id": report_id,
        "field_id": field_id,
        "user_id": user_id,
        "category": "wrong_location",
        "description": "Test",
        "status": status,
        "admin_note": admin_note,
        "created_at": "2026-06-21T12:00:00+00:00",
        "reviewed_at": None,
        "reviewed_by": None,
    }


def setup(monkeypatch, users, reports, fields=None):
    configure_settings(monkeypatch)
    tables = {
        "users": users,
        "fields": fields or [{"id": "field-1", "name": "Central Court"}],
        "field_reports": reports,
    }
    fake_supabase = FakeSupabase(tables)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_supabase)
    monkeypatch.setattr("app.routers.field_reports.get_supabase_client", lambda: fake_supabase)
    return TestClient(app), fake_supabase


def test_mine_returns_own_reports(monkeypatch) -> None:
    user = make_user("user-1")
    report = make_report("r1", "user-1")
    client, _ = setup(monkeypatch, [user], [report])

    response = client.get("/field-reports/mine", headers=auth_headers(user))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "r1"
    assert data[0]["field_name"] == "Central Court"


def test_mine_excludes_other_users_reports(monkeypatch) -> None:
    user1 = make_user("user-1")
    user2 = make_user("user-2")
    r1 = make_report("r1", "user-1")
    r2 = make_report("r2", "user-2")
    client, _ = setup(monkeypatch, [user1, user2], [r1, r2])

    response = client.get("/field-reports/mine", headers=auth_headers(user1))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "r1"


def test_mine_does_not_expose_reviewed_by(monkeypatch) -> None:
    user = make_user("user-1")
    report = make_report("r1", "user-1")
    report["reviewed_by"] = "admin-uuid"
    client, _ = setup(monkeypatch, [user], [report])

    response = client.get("/field-reports/mine", headers=auth_headers(user))

    assert response.status_code == 200
    data = response.json()
    assert "reviewed_by" not in data[0]


def test_mine_does_not_expose_user_id(monkeypatch) -> None:
    user = make_user("user-1")
    report = make_report("r1", "user-1")
    client, _ = setup(monkeypatch, [user], [report])

    response = client.get("/field-reports/mine", headers=auth_headers(user))

    assert response.status_code == 200
    data = response.json()
    assert "user_id" not in data[0]


def test_mine_shows_admin_note(monkeypatch) -> None:
    user = make_user("user-1")
    report = make_report("r1", "user-1", admin_note="Fixed the pin location.")
    client, _ = setup(monkeypatch, [user], [report])

    response = client.get("/field-reports/mine", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json()[0]["admin_note"] == "Fixed the pin location."


def test_mine_returns_empty_list_for_no_reports(monkeypatch) -> None:
    user = make_user("user-1")
    client, _ = setup(monkeypatch, [user], [])

    response = client.get("/field-reports/mine", headers=auth_headers(user))

    assert response.status_code == 200
    assert response.json() == []


def test_mine_requires_authentication(monkeypatch) -> None:
    user = make_user("user-1")
    client, _ = setup(monkeypatch, [user], [])

    response = client.get("/field-reports/mine")

    assert response.status_code == 401
