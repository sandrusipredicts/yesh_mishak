from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeUsersQuery:
    def __init__(self, users_by_id: dict[str, dict[str, Any]]) -> None:
        self.users_by_id = users_by_id
        self.user_id: str | None = None
        self.selected_columns: list[str] | None = None

    def select(self, columns: str) -> "FakeUsersQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: str) -> "FakeUsersQuery":
        if column == "id":
            self.user_id = value
        return self

    def limit(self, _: int) -> "FakeUsersQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeUsersQuery":
        return self

    def execute(self) -> FakeResponse:
        if self.user_id is None:
            users = list(self.users_by_id.values())
            return FakeResponse(data=[self._select_columns(user) for user in users])

        user = self.users_by_id.get(self.user_id)
        return FakeResponse(data=[self._select_columns(user)] if user else [])

    def _select_columns(self, user: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None:
            return user

        return {column: user.get(column) for column in self.selected_columns}


class FakeSupabaseClient:
    def __init__(self, users_by_id: dict[str, dict[str, Any]]) -> None:
        self.users_by_id = users_by_id

    def table(self, table_name: str) -> FakeUsersQuery:
        assert table_name == "users"
        return FakeUsersQuery(self.users_by_id)


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
