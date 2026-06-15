from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class FakeUsersQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.user_id: str | None = None
        self.selected_columns: list[str] | None = None
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.exact_count = False

    def select(self, columns: str, count: str | None = None) -> "FakeUsersQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        self.exact_count = count == "exact"
        return self

    def eq(self, column: str, value: str) -> "FakeUsersQuery":
        if column == "id":
            self.user_id = value
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeUsersQuery":
        self.in_filters.append((column, values))
        return self

    def limit(self, _: int) -> "FakeUsersQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeUsersQuery":
        return self

    def execute(self) -> FakeResponse:
        rows = self._filtered_rows()
        data = [self._select_columns(row) for row in rows]
        return FakeResponse(data=data, count=len(rows) if self.exact_count else None)

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = self.rows
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        return rows

    def _select_columns(self, user: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None:
            return user

        return {column: user.get(column) for column in self.selected_columns}


class FakeSupabaseClient:
    def __init__(
        self,
        users_by_id: dict[str, dict[str, Any]],
        tables: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.tables = tables or {}
        self.tables.setdefault("users", list(users_by_id.values()))

    def table(self, table_name: str) -> FakeUsersQuery:
        assert table_name in self.tables
        return FakeUsersQuery(self.tables[table_name])


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def test_admin_me_returns_current_admin(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({admin_user["id"]: admin_user}),
    )

    response = TestClient(app).get(
        "/admin/me",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert response.json() == admin_user


def test_admin_me_rejects_regular_user(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({regular_user["id"]: regular_user}),
    )

    response = TestClient(app).get(
        "/admin/me",
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403


def test_admin_me_requires_token() -> None:
    response = TestClient(app).get("/admin/me")

    assert response.status_code == 401


def test_admin_users_returns_required_fields_only(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    listed_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "phone_number": None,
        "created_at": "2026-06-15T09:00:00+00:00",
        "last_active": None,
        "role": "user",
        "google_sub": "private-provider-id",
        "picture": "https://example.com/private.png",
    }
    fake_client = FakeSupabaseClient(
        {
            admin_user["id"]: admin_user,
            listed_user["id"]: listed_user,
        }
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        "/admin/users",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": admin_user["id"],
            "name": admin_user["name"],
            "email": admin_user["email"],
            "phone_number": None,
            "created_at": None,
            "last_active": None,
            "role": admin_user["role"],
        },
        {
            "id": listed_user["id"],
            "name": listed_user["name"],
            "email": listed_user["email"],
            "phone_number": None,
            "created_at": listed_user["created_at"],
            "last_active": None,
            "role": listed_user["role"],
        },
    ]


def test_admin_users_rejects_regular_user(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({regular_user["id"]: regular_user}),
    )

    response = TestClient(app).get(
        "/admin/users",
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403


def test_admin_stats_returns_counts_only(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, regular_user],
            "fields": [
                {"id": "field-1", "verified": True, "approval_status": "approved"},
                {"id": "field-2", "verified": True, "approval_status": "approved"},
                {"id": "field-3", "verified": False, "approval_status": "approved"},
                {"id": "field-4", "verified": False, "approval_status": "pending"},
                {"id": "field-5", "verified": False, "approval_status": "rejected"},
            ],
            "games": [
                {"id": "game-1", "status": "open"},
                {"id": "game-2", "status": "full"},
                {"id": "game-3", "status": "finished"},
                {"id": "game-4", "status": "cancelled"},
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        "/admin/stats",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "verified_fields": 2,
        "pending_fields": 1,
        "active_games": 2,
        "total_users": 2,
        "rejected_fields": 1,
        "finished_games": 2,
    }
    assert all(isinstance(value, int) for value in response.json().values())


def test_admin_stats_rejects_regular_user(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({regular_user["id"]: regular_user}),
    )

    response = TestClient(app).get(
        "/admin/stats",
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403
