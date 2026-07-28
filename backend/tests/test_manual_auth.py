from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeUsersQuery:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        update_error: Exception | None = None,
        empty_updates: bool = False,
        update_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        self.rows = rows
        self.update_error = update_error
        self.empty_updates = empty_updates
        self.update_calls = update_calls if update_calls is not None else []
        self.filters: list[tuple[str, Any]] = []
        self.selected_columns: list[str] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None

    def select(self, columns: str) -> "FakeUsersQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: str) -> "FakeUsersQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _: int) -> "FakeUsersQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeUsersQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeUsersQuery":
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
            self.update_calls.append(
                {
                    "filters": list(self.filters),
                    "payload": dict(self.update_payload),
                }
            )
            if self.update_error is not None:
                raise self.update_error
            if self.empty_updates:
                return FakeResponse(data=[])
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(data=rows)

        return FakeResponse(data=[self._select_columns(row) for row in rows])

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
        *,
        update_error: Exception | None = None,
        empty_updates: bool = False,
    ) -> None:
        self.users = users or []
        self.update_error = update_error
        self.empty_updates = empty_updates
        self.update_calls: list[dict[str, Any]] = []

    def table(self, table_name: str) -> FakeUsersQuery:
        assert table_name == "users"
        return FakeUsersQuery(
            self.users,
            update_error=self.update_error,
            empty_updates=self.empty_updates,
            update_calls=self.update_calls,
        )


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")
    get_settings.cache_clear()


def register_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "full_name": "Manual User",
        "username": "manual-user",
        "email": "manual@example.com",
        "phone_number": "0501234567",
        "password": "strongpass123",
        "password_confirm": "strongpass123",
    }
    payload.update(overrides)
    return payload


def test_register_creates_unverified_manual_user_without_session(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)

    response = TestClient(app).post("/auth/register", json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert "access_token" not in body
    assert "token_type" not in body
    assert body["user"]["email"] == "manual@example.com"
    assert body["user"]["name"] == "Manual User"
    assert body["user"]["username"] == "manual-user"
    assert fake_client.users[0]["password_hash"] != "strongpass123"
    assert fake_client.users[0]["last_login"]
    assert fake_client.users[0]["email_verified"] is False
    assert body["email_verification_required"] is True
    assert body["email_verification_sent"] is False


def test_register_rejects_duplicate_username(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient([{"id": "user-1", "username": "manual-user"}])
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)

    response = TestClient(app).post("/auth/register", json=register_payload())

    assert response.status_code == 409
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "CONFLICT"
    assert err["message"] == "Username is already taken"


def test_register_rejects_duplicate_email(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient([{"id": "user-1", "email": "manual@example.com"}])
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)

    response = TestClient(app).post("/auth/register", json=register_payload(username="new-user"))

    assert response.status_code == 409
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "CONFLICT"
    assert err["message"] == "Email is already registered"


def test_register_rejects_duplicate_phone_number(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient([{"id": "user-1", "phone_number": "0501234567"}])
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)

    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(username="new-user", email="new@example.com"),
    )

    assert response.status_code == 409
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "CONFLICT"
    assert err["message"] == "Phone number is already registered"


def test_register_rejects_password_mismatch(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)

    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password_confirm="different123"),
    )

    assert response.status_code == 400
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "VALIDATION_ERROR"
    assert err["message"] == "Passwords do not match"


def test_login_accepts_valid_username_and_password(monkeypatch, caplog) -> None:
    configure_test_settings(monkeypatch)
    register_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: register_client)
    TestClient(app).post("/auth/register", json=register_payload())
    register_client.users[0]["email_verified"] = True
    original_last_login = "2026-01-01T00:00:00+00:00"
    register_client.users[0]["last_login"] = original_last_login
    service_client = FakeSupabaseClient([dict(register_client.users[0])])
    monkeypatch.setattr(
        "app.api.auth.get_supabase_service_role_client",
        lambda: service_client,
    )

    with caplog.at_level(logging.INFO, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual-user", "password": "strongpass123"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "manual-user"
    success_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.login.success"
    ]
    assert success_records
    assert success_records[-1].auth_method == "password"
    assert success_records[-1].user_id == response.json()["user"]["id"]
    assert register_client.users[0]["last_login"] == original_last_login
    persisted_last_login = service_client.users[0]["last_login"]
    assert datetime.fromisoformat(persisted_last_login).tzinfo is not None
    assert datetime.fromisoformat(persisted_last_login) > datetime.fromisoformat(original_last_login)
    assert service_client.update_calls == [
        {
            "filters": [("id", response.json()["user"]["id"])],
            "payload": {"last_login": persisted_last_login},
        }
    ]
    assert "manual@example.com" not in caplog.text
    assert "strongpass123" not in caplog.text


def test_login_accepts_valid_email_and_password(monkeypatch, caplog) -> None:
    configure_test_settings(monkeypatch)
    register_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: register_client)
    TestClient(app).post("/auth/register", json=register_payload())
    register_client.users[0]["email_verified"] = True
    monkeypatch.setattr(
        "app.api.auth.get_supabase_service_role_client",
        lambda: register_client,
    )

    with caplog.at_level(logging.INFO, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual@example.com", "password": "strongpass123"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == "manual@example.com"
    assert body["user"]["username"] == "manual-user"
    success_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.login.success"
    ]
    assert success_records


def test_login_email_is_case_insensitive(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    register_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: register_client)
    TestClient(app).post("/auth/register", json=register_payload())
    register_client.users[0]["email_verified"] = True
    monkeypatch.setattr(
        "app.api.auth.get_supabase_service_role_client",
        lambda: register_client,
    )

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "  Manual@Example.COM  ", "password": "strongpass123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "manual@example.com"


def test_login_last_login_database_failure_is_observable_and_non_fatal(
    monkeypatch,
    caplog,
) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: standard_client)
    TestClient(app).post("/auth/register", json=register_payload())
    standard_client.users[0]["email_verified"] = True
    user_id = standard_client.users[0]["id"]

    secret_sentinels = (
        "password=warning-secret",
        "access_token=warning-token",
        "refresh_token=warning-refresh",
    )
    service_client = FakeSupabaseClient(
        [dict(standard_client.users[0])],
        update_error=RuntimeError(" ".join(secret_sentinels)),
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_service_role_client",
        lambda: service_client,
    )
    monitoring_calls: list[dict[str, Any]] = []

    def capture_message(message: str, level: str = "warning", **tags: Any) -> None:
        monitoring_calls.append({"message": message, "level": level, "tags": tags})

    monkeypatch.setattr("app.api.auth.capture_unexpected_message", capture_message)

    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual-user", "password": "strongpass123"},
        )

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["user"]["id"] == user_id
    failure_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.last_login.failure"
    ]
    assert len(failure_records) == 1
    warning = failure_records[0]
    assert warning.auth_flow == "password"
    assert warning.auth_method == "password"
    assert warning.environment == "test"
    assert warning.user_id == user_id
    assert warning.endpoint == "/auth/login"
    assert warning.result == "partial_failure"
    assert warning.error_code == "DATABASE_ERROR"
    assert warning.error_category == "database_error"
    assert warning.exception_type == "RuntimeError"
    assert service_client.update_calls[0]["filters"] == [("id", user_id)]

    assert monitoring_calls == [
        {
            "message": "Authentication last_login update failed",
            "level": "warning",
            "tags": {
                "event": "auth.last_login.failure",
                "auth_flow": "password",
                "auth_method": "password",
                "environment": "test",
                "user_id": user_id,
                "endpoint": "/auth/login",
                "error_code": "DATABASE_ERROR",
                "error_category": "database_error",
                "exception_type": "RuntimeError",
                "attempt_id": None,
            },
        }
    ]
    serialized_observability = caplog.text + repr(monitoring_calls)
    for sentinel in secret_sentinels:
        assert sentinel not in serialized_observability
    assert "strongpass123" not in serialized_observability
    assert response.json()["access_token"] not in serialized_observability


def test_login_empty_last_login_update_response_warns_and_still_succeeds(
    monkeypatch,
    caplog,
) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: standard_client)
    TestClient(app).post("/auth/register", json=register_payload())
    standard_client.users[0]["email_verified"] = True
    service_client = FakeSupabaseClient(
        [dict(standard_client.users[0])],
        empty_updates=True,
    )
    monkeypatch.setattr(
        "app.api.auth.get_supabase_service_role_client",
        lambda: service_client,
    )
    monkeypatch.setattr(
        "app.api.auth.capture_unexpected_message",
        lambda *_args, **_kwargs: None,
    )

    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual-user", "password": "strongpass123"},
        )

    assert response.status_code == 200
    failure_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.last_login.failure"
    ]
    assert len(failure_records) == 1
    assert failure_records[0].error_category == "no_rows_updated"
    assert failure_records[0].exception_type == "_LastLoginUpdateNotPersisted"


def test_login_rejects_unknown_identifier(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "nonexistent@example.com", "password": "pass123"},
    )

    assert response.status_code == 401
    err = response.json()
    assert err["code"] == "AUTH_INVALID"


def test_login_rejects_wrong_password(monkeypatch, caplog) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    TestClient(app).post("/auth/register", json=register_payload())

    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual-user", "password": "wrongpass123"},
        )

    assert response.status_code == 401
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "AUTH_INVALID"
    assert err["message"] == "Invalid username or password"
    failure_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.login.failure"
    ]
    assert failure_records
    assert failure_records[-1].auth_method == "password"
    assert failure_records[-1].error_code == "AUTH_INVALID"
    assert "manual-user" not in caplog.text
    assert "wrongpass123" not in caplog.text
