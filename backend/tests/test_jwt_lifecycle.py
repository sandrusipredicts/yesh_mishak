from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import _user_cache, invalidate_cached_user
from app.auth.jwt import create_access_token, decode_access_token
from app.core.config import get_settings
from app.main import app

_EPOCH = datetime.fromtimestamp(0, tz=timezone.utc)


def _as_datetime(value: Any) -> datetime:
    if value is None:
        return _EPOCH
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value


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


@dataclass
class FakeRpcResponse:
    data: list[dict[str, Any]]


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

    def rpc(self, name: str, params: dict[str, Any]) -> "FakeRpcCall":
        if name != "revoke_user_tokens":
            raise AssertionError(f"Unexpected RPC {name}")
        return FakeRpcCall(self, params["p_user_id"])


class FakeRpcCall:
    """Mirrors migrations/token_revocation_monotonic.sql's revoke_user_tokens:
    an atomic, monotonic (GREATEST) bump of tokens_valid_after."""

    def __init__(self, client: FakeSupabaseClient, user_id: str) -> None:
        self.client = client
        self.user_id = user_id

    def execute(self) -> FakeRpcResponse:
        user = next((u for u in self.client.users if u["id"] == self.user_id), None)
        if user is None:
            return FakeRpcResponse(data=[{"result": "user_not_found"}])
        now = datetime.now(timezone.utc)
        current = _as_datetime(user.get("tokens_valid_after"))
        user["tokens_valid_after"] = max(current, now).isoformat()
        return FakeRpcResponse(data=[{"result": "revoked"}])


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
        "app.services.api_request_metrics",
    ):
        monkeypatch.setattr(f"{module}.get_supabase_client", lambda: fake_client, raising=False)
    monkeypatch.setattr("app.api.auth.get_supabase_service_role_client", lambda: fake_client)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_service_role_client", lambda: fake_client)
    monkeypatch.setattr("app.services.api_request_metrics.get_supabase_service_role_client", lambda: fake_client, raising=False)



def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def make_payload(
    user: dict[str, Any] | None = None,
    *,
    iat: datetime | int | None = None,
    exp: datetime | None = None,
    include_issuer: bool = True,
    include_audience: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    settings = get_settings()
    selected_user = user or REGULAR_USER
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": selected_user["id"],
        "email": selected_user["email"],
        "iat": iat if iat is not None else now,
        "exp": exp if exp is not None else now + timedelta(hours=1),
    }
    if include_issuer:
        payload["iss"] = settings.jwt_issuer
    if include_audience:
        payload["aud"] = settings.jwt_audience
    payload.update(overrides)
    return payload


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


# ---- Issued JWT includes configured issuer and audience ----


def test_create_access_token_includes_configured_issuer_and_audience(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()

    token = make_token(REGULAR_USER)
    payload = pyjwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
    )

    assert payload["iss"] == settings.jwt_issuer
    assert payload["aud"] == settings.jwt_audience


def test_decode_access_token_accepts_valid_issuer_and_audience(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    token = make_token(REGULAR_USER)

    payload = decode_access_token(token)

    assert payload["sub"] == REGULAR_USER["id"]
    assert payload["iss"] == get_settings().jwt_issuer
    assert payload["aud"] == get_settings().jwt_audience


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
    payload = make_payload(
        iat=now - timedelta(hours=2),
        exp=now - timedelta(hours=1),
    )
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
    payload = make_payload()
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
    payload = make_payload(user, iat=past, exp=now + timedelta(hours=1))
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
    payload = make_payload()
    payload.pop("sub")
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


# ---- Missing or incorrect issuer/audience are rejected ----


def test_token_without_issuer_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()
    payload = make_payload(include_issuer=False)
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_token_with_wrong_issuer_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()
    payload = make_payload(iss="wrong-issuer")
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_token_without_audience_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()
    payload = make_payload(include_audience=False)
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_token_with_wrong_audience_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    settings = get_settings()
    payload = make_payload(aud="wrong-audience")
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

    payload = make_payload(user, iat=int(now.timestamp()), exp=now + timedelta(hours=1))
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
    payload = make_payload(user, iat=int(one_second_ago.timestamp()), exp=now + timedelta(hours=1))
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    response = TestClient(app).get(
        "/games/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_REVOKED"


# ---- E01-05: multi-worker in-process cache lag on token revocation -------
#
# app.auth.dependencies._user_cache is a module-level dict: in a real
# multi-worker/multi-instance deployment each worker process has its own
# copy. These tests simulate that by swapping in independent dict objects
# for "worker A" and "worker B" instead of sharing the single process-wide
# cache the way the other tests in this file do.


import app.auth.dependencies as deps


@pytest.fixture
def enable_cache(monkeypatch):
    monkeypatch.setattr(deps, "_enable_cache_in_tests", True)
    monkeypatch.setenv("AUTH_USER_CACHE_TTL_SECONDS", "300")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_worker_a_stale_cache_rejects_token_after_worker_b_revokes(monkeypatch, enable_cache) -> None:
    """Core E01-05 proof: Worker A populates its own cache, Worker B revokes
    via logout (writing tokens_valid_after in the shared database and
    clearing only *its own* local cache), and Worker A - which never had its
    local cache invalidated - must still reject the old token because
    revocation state is always re-read from the database, never trusted
    from a stale in-process cache."""
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    shared_db = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, shared_db)

    worker_a_cache: dict = {}
    worker_b_cache: dict = {}

    token = _make_token_seconds_ago(user)

    # Worker A serves a request: cache miss, populates worker_a_cache.
    monkeypatch.setattr(deps, "_user_cache", worker_a_cache)
    response = TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code != 401
    assert user["id"] in worker_a_cache

    # Worker B serves the logout: revokes in the shared DB, invalidates only
    # its own (empty) local cache. Worker A's cache is untouched.
    monkeypatch.setattr(deps, "_user_cache", worker_b_cache)
    logout_response = TestClient(app).post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_response.status_code == 200
    assert user["id"] not in worker_b_cache
    assert user["id"] in worker_a_cache  # still stale on Worker A

    # Worker A serves the same old token again: its cache is a hit, but the
    # DB-authoritative refresh must still reject the token.
    monkeypatch.setattr(deps, "_user_cache", worker_a_cache)
    response = TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["code"] == "TOKEN_REVOKED"


def test_worker_a_accepts_new_token_after_worker_b_revokes(monkeypatch, enable_cache) -> None:
    """Companion to the above: a fresh login after the revocation must work
    on Worker A even though Worker A's cache still holds the pre-revocation
    entry for this user."""
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    shared_db = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, shared_db)

    worker_a_cache: dict = {}
    worker_b_cache: dict = {}

    old_token = _make_token_seconds_ago(user)

    monkeypatch.setattr(deps, "_user_cache", worker_a_cache)
    TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {old_token}"})
    assert user["id"] in worker_a_cache

    monkeypatch.setattr(deps, "_user_cache", worker_b_cache)
    TestClient(app).post("/auth/logout", headers={"Authorization": f"Bearer {old_token}"})

    new_token = create_access_token(subject=user["id"], email=user["email"])

    monkeypatch.setattr(deps, "_user_cache", worker_a_cache)
    response = TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {new_token}"})
    assert response.status_code != 401


def test_cached_role_is_refreshed_from_database(monkeypatch, enable_cache) -> None:
    """A cached copy of `role` must never outlive a database change: role
    gates admin authorization (require_admin), so it is refreshed on every
    request exactly like status and tokens_valid_after."""
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER, role="user")
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = create_access_token(subject=user["id"], email=user["email"])

    # Populate the cache while role="user".
    response = TestClient(app).get("/admin/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert user["id"] in deps._user_cache

    # Promote to admin directly in the database (as a real admin action
    # would, from any worker) without touching the cache at all.
    user["role"] = "admin"

    response = TestClient(app).get("/admin/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


def test_db_unavailable_fails_closed_on_cache_miss(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    class BrokenSupabaseClient:
        def table(self, name: str):
            raise ConnectionError("database unreachable")

    monkeypatch.setattr(deps, "get_supabase_client", lambda: BrokenSupabaseClient())

    token = create_access_token(subject=REGULAR_USER["id"], email=REGULAR_USER["email"])
    response = TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_SERVICE_UNAVAILABLE"


def test_db_unavailable_fails_closed_on_cache_hit(monkeypatch, enable_cache) -> None:
    """A cache hit must not bypass the DB-unavailable fail-closed path: the
    security fields are always re-read from the database, so if that read
    fails, the request is rejected rather than silently trusting the cache."""
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = create_access_token(subject=user["id"], email=user["email"])
    first = TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code != 401
    assert user["id"] in deps._user_cache

    class BrokenSupabaseClient:
        def table(self, name: str):
            raise ConnectionError("database unreachable")

    monkeypatch.setattr(deps, "get_supabase_client", lambda: BrokenSupabaseClient())
    monkeypatch.setattr(deps, "get_supabase_service_role_client", lambda: BrokenSupabaseClient())

    response = TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_SERVICE_UNAVAILABLE"


def test_malformed_tokens_valid_after_does_not_crash(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER, tokens_valid_after="not-a-timestamp")
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = create_access_token(subject=user["id"], email=user["email"])
    response = TestClient(app).get("/games/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.json()["code"] == "AUTH_SERVICE_UNAVAILABLE"


def test_concurrent_revocations_do_not_move_tokens_valid_after_backward(monkeypatch) -> None:
    """Race C: revoke_user_tokens uses GREATEST(existing, now()), so a write
    that captured an *earlier* wall-clock timestamp can never overwrite a
    value already advanced by a write that captured a *later* one - however
    the two commits are ordered/interleaved in a real multi-worker
    deployment. This exercises the same GREATEST semantics implemented in
    migrations/token_revocation_monotonic.sql's revoke_user_tokens (and
    mirrored by FakeRpcCall), independent of any single request's auth
    state."""
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    fake_client = FakeSupabaseClient([user])

    # A later-committing revocation already advanced tokens_valid_after into
    # the near future (simulating Worker B's write landing first).
    future = datetime.now(timezone.utc) + timedelta(seconds=5)
    user["tokens_valid_after"] = future.isoformat()

    # Worker A's revocation captured an earlier timestamp but its write
    # reaches the database second. It must not roll tokens_valid_after back.
    fake_client.rpc("revoke_user_tokens", {"p_user_id": user["id"]}).execute()

    final_value = datetime.fromisoformat(user["tokens_valid_after"])
    assert final_value == future


def test_revocation_timestamp_only_advances(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    fake_client = FakeSupabaseClient([user])

    before = datetime.now(timezone.utc)
    fake_client.rpc("revoke_user_tokens", {"p_user_id": user["id"]}).execute()
    after = datetime.now(timezone.utc)

    final_value = datetime.fromisoformat(user["tokens_valid_after"])
    assert before <= final_value <= after


def test_logout_revoke_missing_user_does_not_error(monkeypatch) -> None:
    """If the user row disappears between auth and the revoke RPC executing,
    revoke_user_tokens reports user_not_found; logout must not blow up."""
    configure_test_settings(monkeypatch)
    user = dict(REGULAR_USER)
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    token = create_access_token(subject=user["id"], email=user["email"])
    # Simulate the row vanishing only for the RPC call (get_current_user's
    # own lookup, resolved as a dependency before the handler body runs,
    # still sees the user).
    original_rpc = fake_client.rpc

    def rpc_user_missing(name, params):
        fake_client.users.clear()
        return original_rpc(name, params)

    monkeypatch.setattr(fake_client, "rpc", rpc_user_missing)

    response = TestClient(app).post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
