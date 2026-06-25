from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from app.rate_limit import check_rate_limit_by_ip, get_limiter


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.selected_columns: list[str] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.limit_count: int | None = None
        self._count_mode = False
        self._head_mode = False
        self._in_filters: list[tuple[str, list]] = []
        self._is_filters: list[tuple[str, str]] = []
        self._delete_mode = False

    def select(self, columns: str = "*", count: str | None = None, head: bool = False) -> "FakeQuery":
        self.selected_columns = [c.strip() for c in columns.split(",")]
        self._count_mode = count is not None
        self._head_mode = head
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list) -> "FakeQuery":
        self._in_filters.append((column, values))
        return self

    def is_(self, column: str, value: str) -> "FakeQuery":
        self._is_filters.append((column, value))
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def gte(self, column: str, value: Any) -> "FakeQuery":
        return self

    def lte(self, column: str, value: Any) -> "FakeQuery":
        return self

    def lt(self, column: str, value: Any) -> "FakeQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        return self

    def insert(self, payload: dict[str, Any] | list) -> "FakeQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.update_payload = payload
        return self

    def delete(self) -> "FakeQuery":
        self._delete_mode = True
        return self

    def rpc(self, name: str, params: dict) -> "FakeQuery":
        return self

    def execute(self) -> FakeResponse:
        if self._head_mode and self._count_mode:
            rows = self.database.tables.get(self.table_name, [])
            for col, val in self.filters:
                rows = [r for r in rows if r.get(col) == val]
            return FakeResponse(data=[], count=len(rows))

        if self.insert_payload is not None:
            row = dict(self.insert_payload) if isinstance(self.insert_payload, dict) else self.insert_payload
            if isinstance(row, dict):
                row.setdefault("id", f"{self.table_name}-{len(self.database.tables.get(self.table_name, [])) + 1}")
                self.database.tables.setdefault(self.table_name, []).append(row)
                return FakeResponse([dict(row)])
            return FakeResponse([])

        if self._delete_mode:
            return FakeResponse([])

        if self.update_payload is not None:
            rows = self.database.tables.get(self.table_name, [])
            for col, val in self.filters:
                rows = [r for r in rows if r.get(col) == val]
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(rows)

        rows = self.database.tables.get(self.table_name, [])
        for col, val in self.filters:
            rows = [r for r in rows if r.get(col) == val]
        for col, vals in self._in_filters:
            rows = [r for r in rows if r.get(col) in vals]
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return FakeResponse([dict(r) for r in rows])


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = tables or {}
        self.table_calls: list[str] = []

    def table(self, table_name: str) -> FakeQuery:
        self.table_calls.append(table_name)
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)

    def rpc(self, name: str, params: dict) -> FakeQuery:
        return FakeQuery(self, "rpc")


def configure_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def make_user(user_id: str = "user-1", role: str = "user") -> dict[str, Any]:
    return {
        "id": user_id,
        "email": f"{user_id}@example.com",
        "name": f"User {user_id}",
        "username": user_id,
        "phone_number": f"050{user_id[-4:].zfill(7)}",
        "role": role,
        "status": "active",
        "password_hash": "$2b$12$fakehashvalue",
    }


def auth_headers(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=str(user["id"]), email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def _patch_supabase(monkeypatch, fake: FakeSupabase) -> None:
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.field_reports.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)


# ---- Login rate limiting ----


def test_login_11th_request_returns_429(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeSupabase({"users": []})
    _patch_supabase(monkeypatch, fake)
    client = TestClient(app)

    for _ in range(10):
        client.post("/auth/login", json={"username": "user-1", "password": "wrong"})

    response = client.post("/auth/login", json={"username": "user-1", "password": "wrong"})
    assert response.status_code == 429


def test_login_429_includes_retry_after_and_rate_limited_code(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeSupabase({"users": []})
    _patch_supabase(monkeypatch, fake)
    client = TestClient(app)

    for _ in range(10):
        client.post("/auth/login", json={"username": "user-1", "password": "wrong"})

    response = client.post("/auth/login", json={"username": "user-1", "password": "wrong"})
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
    body = response.json()
    assert body["error"] is True
    assert body["code"] == "RATE_LIMITED"
    assert body["message"] == "Too many requests. Please try again later."


def test_login_rate_limit_does_not_reveal_username_exists(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeSupabase({"users": []})
    _patch_supabase(monkeypatch, fake)
    client = TestClient(app)

    for _ in range(10):
        client.post("/auth/login", json={"username": "real-user", "password": "wrong"})

    response_existing = client.post(
        "/auth/login", json={"username": "user-1", "password": "wrong"}
    )

    get_limiter().reset()

    for _ in range(10):
        client.post("/auth/login", json={"username": "no-such-user", "password": "wrong"})

    response_nonexistent = client.post(
        "/auth/login", json={"username": "no-such-user", "password": "wrong"}
    )

    assert response_existing.status_code == 429
    assert response_nonexistent.status_code == 429
    assert response_existing.json() == response_nonexistent.json()


def test_ip_based_limits_use_client_ip_without_trusting_forwarded_headers() -> None:
    request_ip_1 = SimpleNamespace(
        client=SimpleNamespace(host="1.2.3.4"),
        headers={"x-forwarded-for": "9.9.9.9"},
    )
    request_ip_2 = SimpleNamespace(
        client=SimpleNamespace(host="5.6.7.8"),
        headers={"x-forwarded-for": "9.9.9.9"},
    )

    for _ in range(10):
        assert check_rate_limit_by_ip(request_ip_1, "auth_login", [(10, 60)]) is None

    response_limited = check_rate_limit_by_ip(request_ip_1, "auth_login", [(10, 60)])
    assert response_limited is not None
    assert response_limited.status_code == 429

    response_other_ip = check_rate_limit_by_ip(request_ip_2, "auth_login", [(10, 60)])
    assert response_other_ip is None


# ---- Registration rate limiting ----


def test_register_6th_request_returns_429(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeSupabase({"users": []})
    _patch_supabase(monkeypatch, fake)
    hash_mock = MagicMock(return_value="$2b$12$validhash")
    monkeypatch.setattr("app.api.auth.hash_password", hash_mock)
    client = TestClient(app)

    for i in range(5):
        client.post(
            "/auth/register",
            json={
                "full_name": f"User {i}",
                "username": f"user{i}",
                "email": f"user{i}@example.com",
                "phone_number": f"050000000{i}",
                "password": "strongpass123",
                "password_confirm": "strongpass123",
            },
        )

    response = client.post(
        "/auth/register",
        json={
            "full_name": "User 5",
            "username": "user5",
            "email": "user5@example.com",
            "phone_number": "0500000005",
            "password": "strongpass123",
            "password_confirm": "strongpass123",
        },
    )
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert hash_mock.call_count == 5
    assert len(fake.tables["users"]) == 5


# ---- Google login rate limiting ----


def test_google_login_11th_request_returns_429(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake = FakeSupabase({"users": []})
    _patch_supabase(monkeypatch, fake)
    client = TestClient(app)

    mock_verify = MagicMock(
        side_effect=HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )
    )

    with patch("app.api.auth.verify_google_token", mock_verify):
        for _ in range(10):
            client.post("/auth/google", json={"token": "fake-google-token"})

        response = client.post("/auth/google", json={"token": "fake-google-token"})

    assert response.status_code == 429
    assert mock_verify.call_count == 10


# ---- Game creation rate limiting ----


def test_game_creation_6th_request_returns_429(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake = FakeSupabase({
        "users": [user],
        "fields": [{
            "id": "field-1", "name": "Test Field", "verified": True,
            "approval_status": "approved", "status": "open", "sport_type": "football",
            "lat": 31.0, "lng": 34.0,
        }],
        "games": [],
        "game_players": [],
    })
    _patch_supabase(monkeypatch, fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_settings", lambda: type("S", (), {"disable_game_created_notifications": True})())
    client = TestClient(app)

    game_payload = {
        "field_id": "field-1",
        "sport_type": "football",
        "players_present": 1,
        "max_players": 10,
    }

    for _ in range(5):
        client.post("/games/", json=game_payload, headers=auth_headers(user))

    game_count_before = len(fake.tables["games"])
    game_player_count_before = len(fake.tables["game_players"])
    response = client.post("/games/", json=game_payload, headers=auth_headers(user))
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert len(fake.tables["games"]) == game_count_before
    assert len(fake.tables["game_players"]) == game_player_count_before


# ---- Field submission rate limiting ----


def test_field_submission_4th_request_returns_429(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake = FakeSupabase({"users": [user], "fields": []})
    _patch_supabase(monkeypatch, fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    client = TestClient(app)

    field_payload = {
        "name": "Test Field",
        "lat": 31.0,
        "lng": 34.0,
        "sport_type": "football",
        "surface_type": "grass",
        "has_nets": True,
        "has_water": True,
    }

    for _ in range(3):
        client.post("/fields/", json=field_payload, headers=auth_headers(user))

    field_count_before = len(fake.tables["fields"])
    response = client.post("/fields/", json=field_payload, headers=auth_headers(user))
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert len(fake.tables["fields"]) == field_count_before


# ---- Field report rate limiting ----


def test_field_report_6th_request_returns_429(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake = FakeSupabase({
        "users": [user],
        "fields": [{"id": "field-1", "name": "Central Court"}],
        "field_reports": [],
    })
    _patch_supabase(monkeypatch, fake)
    monkeypatch.setattr("app.routers.field_reports.get_supabase_client", lambda: fake)
    client = TestClient(app)

    report_payload = {
        "field_id": "field-1",
        "category": "wrong_location",
        "description": "Wrong pin.",
    }

    for _ in range(5):
        client.post("/field-reports", json=report_payload, headers=auth_headers(user))

    report_count_before = len(fake.tables["field_reports"])
    response = client.post("/field-reports", json=report_payload, headers=auth_headers(user))
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert len(fake.tables["field_reports"]) == report_count_before


# ---- Test push rate limiting ----


def test_test_push_4th_request_returns_429_and_fcm_not_called(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake = FakeSupabase({
        "users": [user],
        "push_tokens": [{"id": "tok-1", "user_id": user["id"], "token": "device-token"}],
    })
    _patch_supabase(monkeypatch, fake)

    fcm_mock = MagicMock(return_value={"ok": True})
    monkeypatch.setattr("app.routers.notifications.send_fcm_notification", fcm_mock)
    client = TestClient(app)

    for _ in range(3):
        client.post("/notifications/test-push", headers=auth_headers(user))

    fcm_call_count_before = fcm_mock.call_count
    response = client.post("/notifications/test-push", headers=auth_headers(user))

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert fcm_mock.call_count == fcm_call_count_before


# ---- Unread count rate limiting ----


def test_unread_count_31st_request_returns_429(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake = FakeSupabase({
        "users": [user],
        "notifications": [],
    })
    _patch_supabase(monkeypatch, fake)
    client = TestClient(app)

    for _ in range(30):
        client.get("/notifications/unread-count", headers=auth_headers(user))

    notification_table_calls_before = fake.table_calls.count("notifications")
    response = client.get("/notifications/unread-count", headers=auth_headers(user))
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert fake.table_calls.count("notifications") == notification_table_calls_before


# ---- User isolation ----


def test_different_users_do_not_share_user_based_limits(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user1 = make_user("user-1")
    user2 = make_user("user-2")
    fake = FakeSupabase({
        "users": [user1, user2],
        "notifications": [],
    })
    _patch_supabase(monkeypatch, fake)
    client = TestClient(app)

    for _ in range(30):
        client.get("/notifications/unread-count", headers=auth_headers(user1))

    response_limited = client.get("/notifications/unread-count", headers=auth_headers(user1))
    assert response_limited.status_code == 429

    response_user2 = client.get("/notifications/unread-count", headers=auth_headers(user2))
    assert response_user2.status_code == 200


# ---- Rate limiter unit tests ----


def test_rate_limiter_reset_clears_state() -> None:
    limiter = get_limiter()
    for _ in range(10):
        limiter.check("test-key", 10, 60)
    allowed, _ = limiter.check("test-key", 10, 60)
    assert not allowed

    limiter.reset()
    allowed, _ = limiter.check("test-key", 10, 60)
    assert allowed


def test_rate_limiter_retry_after_is_positive() -> None:
    limiter = get_limiter()
    for _ in range(5):
        limiter.check("retry-key", 5, 60)
    allowed, retry_after = limiter.check("retry-key", 5, 60)
    assert not allowed
    assert retry_after > 0
    assert retry_after <= 61
