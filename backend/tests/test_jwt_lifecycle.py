from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import _user_cache, invalidate_cached_user
from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class FakeTableQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.selected_columns: list[str] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.exact_count = False

    def select(self, columns: str, count: str | None = None) -> "FakeTableQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        self.exact_count = count == "exact"
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def neq(self, column: str, value: Any) -> "FakeTableQuery":
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeTableQuery":
        return self

    def gte(self, column: str, value: Any) -> "FakeTableQuery":
        return self

    def lte(self, column: str, value: Any) -> "FakeTableQuery":
        return self

    def gt(self, column: str, value: Any) -> "FakeTableQuery":
        return self

    def is_(self, column: str, value: str) -> "FakeTableQuery":
        return self

    def or_(self, *args: Any, **kwargs: Any) -> "FakeTableQuery":
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeTableQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            row = {
                "id": "00000000-0000-0000-0000-000000000101",
                "role": "user",
                **self.insert_payload,
            }
            self.rows.append(row)
            return FakeResponse(data=[row])

        rows = self._filtered_rows()

        if self.update_payload is not None:
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(data=rows)

        data = [self._select_columns(row) for row in rows]
        return FakeResponse(data=data, count=len(rows) if self.exact_count else None)

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = self.rows
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        return rows

    def _select_columns(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None or "*" in self.selected_columns:
            return row
        return {column: row.get(column) for column in self.selected_columns}


class FakeSupabaseClient:
    def __init__(
        self,
        users: list[dict[str, Any]] | None = None,
        tables: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.tables = tables or {}
        if users is not None:
            self.tables.setdefault("users", users)
        else:
            self.tables.setdefault("users", [])
        self.tables.setdefault("game_players", [])
        self.tables.setdefault("games", [])

    @property
    def users(self) -> list[dict[str, Any]]:
        return self.tables["users"]

    def table(self, table_name: str) -> FakeTableQuery:
        return FakeTableQuery(self.tables.get(table_name, []))


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def patch_all_supabase(monkeypatch, fake_client: FakeSupabaseClient) -> None:
    for module in (
        "app.auth.dependencies",
        "app.api.auth",
        "app.api.admin",
        "app.routers.games",
        "app.routers.game_payloads",
    ):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: fake_client)


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


REGULAR_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "user@example.com",
    "name": "Regular User",
    "role": "user",
    "status": "active",
    "tokens_valid_after": None,
}

ADMIN_USER = {
    "id": "00000000-0000-0000-0000-000000000002",
    "email": "admin@example.com",
    "name": "Admin User",
    "role": "admin",
    "status": "active",
    "tokens_valid_after": None,
}


@pytest.fixture(autouse=True)
def _clear_user_cache():
    _user_cache.clear()
    yield
    _user_cache.clear()


# ---- Login issues a usable JWT ----


def test_login_issues_usable_jwt(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    patch_all_supabase(monkeypatch, fake_client)

    TestClient(app).post(
        "/auth/register",
        json={
            "full_name": "Test User",
            "username": "testuser",
            "email": "test@example.com",
            "phone_number": "0501234567",
            "password": "strongpass123",
            "password_confirm": "strongpass123",
        },
    )
    fake_client.users[0]["email_verified"] = True

    login_response = TestClient(app).post(
        "/auth/login",
        json={"username": "testuser", "password": "strongpass123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401


# ---- Protected endpoint accepts valid JWT ----


def test_protected_endpoint_accepts_valid_jwt(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = make_token(user)
    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401


# ---- Expired JWT is rejected ----


def test_expired_jwt_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": REGULAR_USER["id"],
        "email": REGULAR_USER["email"],
        "iat": now - timedelta(hours=2),
        "exp": now - timedelta(hours=1),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ---- Malformed JWT is rejected ----


def test_malformed_jwt_is_rejected() -> None:
    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401


# ---- Missing JWT is rejected ----


def test_missing_jwt_is_rejected() -> None:
    response = TestClient(app).get("/games/me")
    assert response.status_code == 401


# ---- JWT signed with wrong secret is rejected ----


def test_wrong_secret_jwt_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    now = datetime.now(timezone.utc)
    payload = {
        "sub": REGULAR_USER["id"],
        "email": REGULAR_USER["email"],
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    token = pyjwt.encode(payload, "wrong-secret", algorithm="HS256")

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ---- Logout invalidates token ----


def _make_token_seconds_ago(user: dict[str, Any], seconds: int = 2) -> str:
    """Create a token with iat in the past, simulating a real session
    where the token was issued before logout."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    past = now - timedelta(seconds=seconds)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "iat": past,
        "exp": now + timedelta(hours=1),
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def test_logout_invalidates_token(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = _make_token_seconds_ago(user)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401

    invalidate_cached_user(user["id"])

    logout_response = TestClient(app).post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 200
    assert logout_response.json()["message"] == "Logged out successfully"
    assert user.get("tokens_valid_after") is not None

    invalidate_cached_user(user["id"])

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ---- Token rejected after logout has TOKEN_REVOKED code ----


def test_token_rejected_after_logout_has_revoked_code(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = _make_token_seconds_ago(user)
    TestClient(app).post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    invalidate_cached_user(user["id"])

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_REVOKED"


# ---- New login after logout issues valid token ----


def test_new_login_after_logout_works(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    patch_all_supabase(monkeypatch, fake_client)

    TestClient(app).post(
        "/auth/register",
        json={
            "full_name": "Test User",
            "username": "testuser",
            "email": "test@example.com",
            "phone_number": "0501234567",
            "password": "strongpass123",
            "password_confirm": "strongpass123",
        },
    )

    user = fake_client.users[0]
    user["email_verified"] = True
    token1 = _make_token_seconds_ago(user)

    TestClient(app).post("/auth/logout", headers={"Authorization": f"Bearer {token1}"})
    invalidate_cached_user(user["id"])

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token1}"},
    )
    assert response.status_code == 401

    login2 = TestClient(app).post(
        "/auth/login",
        json={"username": "testuser", "password": "strongpass123"},
    )
    assert login2.status_code == 200
    token2 = login2.json()["access_token"]

    invalidate_cached_user(user["id"])

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert response.status_code != 401


# ---- Banned user is rejected ----


def test_banned_user_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER, status="banned")
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = make_token(user)
    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_RESTRICTED"


# ---- Suspended user is rejected ----


def test_suspended_user_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER, status="suspended")
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = make_token(user)
    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_RESTRICTED"


# ---- Admin route works for active admin ----


def test_admin_route_works_for_active_admin(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    admin = dict(ADMIN_USER)
    fake_client = FakeSupabaseClient([admin])
    patch_all_supabase(monkeypatch, fake_client)

    token = make_token(admin)
    response = TestClient(app).get(
        "/admin/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200


# ---- Admin route rejects banned admin ----


def test_admin_route_rejects_banned_admin(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    admin = dict(ADMIN_USER, status="banned")
    fake_client = FakeSupabaseClient([admin])
    patch_all_supabase(monkeypatch, fake_client)

    token = make_token(admin)
    response = TestClient(app).get(
        "/admin/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_RESTRICTED"


# ---- Admin route rejects suspended admin ----


def test_admin_route_rejects_suspended_admin(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    admin = dict(ADMIN_USER, status="suspended")
    fake_client = FakeSupabaseClient([admin])
    patch_all_supabase(monkeypatch, fake_client)

    token = make_token(admin)
    response = TestClient(app).get(
        "/admin/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_RESTRICTED"


# ---- Token without sub claim is rejected ----


def test_token_without_sub_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "email": "user@example.com",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ---- Logout endpoint requires authentication ----


def test_logout_requires_authentication() -> None:
    response = TestClient(app).post("/auth/logout")
    assert response.status_code == 401


# ---- Token issued after revocation timestamp is accepted ----


def test_token_issued_after_revocation_is_accepted(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    user = dict(REGULAR_USER, tokens_valid_after=past)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = make_token(user)
    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401


# ---- Same-second logout/login: new token must be accepted ----


def test_same_second_logout_login_token_accepted(monkeypatch) -> None:
    """Tokens issued in the same second as tokens_valid_after must not
    be rejected. JWT iat has second precision; tokens_valid_after may
    have sub-second precision. The comparison truncates both to seconds."""
    configure_test_settings(monkeypatch)
    settings = get_settings()
    now = datetime.now(timezone.utc)
    tokens_valid_after_subsecond = now.replace(microsecond=500_000).isoformat()
    user = dict(REGULAR_USER, tokens_valid_after=tokens_valid_after_subsecond)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    payload = {
        "sub": user["id"],
        "email": user["email"],
        "iat": int(now.timestamp()),
        "exp": now + timedelta(hours=1),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code != 401


# ---- Token from prior second is still rejected ----


def test_token_from_prior_second_rejected_after_revocation(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()
    now = datetime.now(timezone.utc)
    tokens_valid_after = now.isoformat()
    user = dict(REGULAR_USER, tokens_valid_after=tokens_valid_after)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    one_second_ago = now - timedelta(seconds=1)
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "iat": int(one_second_ago.timestamp()),
        "exp": now + timedelta(hours=1),
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_REVOKED"
