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

    def select(self, _: str) -> "FakeUsersQuery":
        return self

    def eq(self, column: str, value: str) -> "FakeUsersQuery":
        if column == "id":
            self.user_id = value
        return self

    def limit(self, _: int) -> "FakeUsersQuery":
        return self

    def execute(self) -> FakeResponse:
        if self.user_id is None:
            return FakeResponse(data=[])

        user = self.users_by_id.get(self.user_id)
        return FakeResponse(data=[user] if user else [])


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
