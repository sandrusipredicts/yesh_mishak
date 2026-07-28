from dataclasses import dataclass
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import hash_password, verify_password
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
        allow_insert: bool,
        allow_select: bool,
        insert_calls: list[dict[str, Any]],
        select_calls: list[list[str]],
        select_filters: list[list[tuple[str, Any]]],
    ) -> None:
        self.rows = rows
        self.allow_insert = allow_insert
        self.allow_select = allow_select
        self.insert_calls = insert_calls
        self.select_calls = select_calls
        self.select_filters = select_filters
        self.filters: list[tuple[str, Any]] = []
        self.selected_columns: list[str] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None

    def select(self, columns: str) -> "FakeUsersQuery":
        if not self.allow_select:
            raise AssertionError("non-privileged test client must not select users")
        self.selected_columns = [column.strip() for column in columns.split(",")]
        self.select_calls.append(list(self.selected_columns))
        return self

    def eq(self, column: str, value: str) -> "FakeUsersQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _: int) -> "FakeUsersQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeUsersQuery":
        if not self.allow_insert:
            raise AssertionError("test client must not insert users")
        self.insert_payload = payload
        self.insert_calls.append(dict(payload))
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
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(data=rows)

        self.select_filters.append(list(self.filters))
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
        allow_insert: bool = True,
        allow_select: bool = True,
    ) -> None:
        self.users = users or []
        self.allow_insert = allow_insert
        self.allow_select = allow_select
        self.table_calls: list[str] = []
        self.insert_calls: list[dict[str, Any]] = []
        self.select_calls: list[list[str]] = []
        self.select_filters: list[list[tuple[str, Any]]] = []

    def table(self, table_name: str) -> FakeUsersQuery:
        assert table_name == "users"
        self.table_calls.append(table_name)
        return FakeUsersQuery(
            self.users,
            allow_insert=self.allow_insert,
            allow_select=self.allow_select,
            insert_calls=self.insert_calls,
            select_calls=self.select_calls,
            select_filters=self.select_filters,
        )


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def patch_auth_supabase_clients(
    monkeypatch,
    standard_client: FakeSupabaseClient,
    service_role_client: FakeSupabaseClient | None = None,
) -> None:
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: standard_client)
    monkeypatch.setattr(
        "app.api.auth.get_supabase_service_role_client",
        lambda: service_role_client or standard_client,
    )


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


def password_user(*, email_verified: bool = True) -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000201",
        "email": "manual@example.com",
        "name": "Manual User",
        "username": "manual-user",
        "phone_number": "0501234567",
        "password_hash": hash_password("strongpass123"),
        "email_verified": email_verified,
        "email_verified_at": "2026-07-26T08:00:00+00:00" if email_verified else None,
        "terms_accepted_at": None,
    }


def assert_public_auth_response(response) -> None:
    private_credential_field = "_".join(("password", "hash"))
    assert private_credential_field not in response.text


def assert_secret_values_not_logged(caplog, *values: str) -> None:
    for value in values:
        assert value not in caplog.text


def test_register_uses_service_role_for_uniqueness_and_preserves_main_insert_path(
    monkeypatch,
) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient(allow_insert=False)
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)
    monkeypatch.setattr("app.api.auth.issue_verification_email", lambda *_: None)

    response = TestClient(app).post("/auth/register", json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert "access_token" not in body
    assert "token_type" not in body
    assert body["user"]["email"] == "manual@example.com"
    assert body["user"]["name"] == "Manual User"
    assert body["user"]["username"] == "manual-user"
    assert_public_auth_response(response)
    assert standard_client.select_calls == []
    assert len(standard_client.insert_calls) == 1
    assert service_role_client.select_calls == [["id"], ["id"], ["id"]]
    assert service_role_client.insert_calls == []
    assert verify_password(
        "strongpass123",
        standard_client.users[0]["password_hash"],
    )
    assert standard_client.users[0]["last_login"]
    assert standard_client.users[0]["email_verified"] is False
    assert body["email_verification_required"] is True
    assert body["email_verification_sent"] is True


@pytest.mark.parametrize(
    ("existing_user", "overrides", "message"),
    [
        (
            {"id": "user-1", "username": "manual-user"},
            {},
            "Username is already taken",
        ),
        (
            {"id": "user-1", "email": "manual@example.com"},
            {"username": "new-user"},
            "Email is already registered",
        ),
        (
            {"id": "user-1", "phone_number": "0501234567"},
            {"username": "new-user", "email": "new@example.com"},
            "Phone number is already registered",
        ),
    ],
)
def test_register_uniqueness_checks_use_authorized_client(
    monkeypatch,
    existing_user: dict[str, str],
    overrides: dict[str, str],
    message: str,
) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([existing_user])
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)

    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(**overrides),
    )

    assert response.status_code == 409
    assert response.json() == {
        "error": True,
        "code": "CONFLICT",
        "message": message,
    }
    assert standard_client.select_calls == []
    assert service_role_client.select_calls
    assert all(columns == ["id"] for columns in service_role_client.select_calls)


def test_register_rejects_password_mismatch_before_lookup(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient()
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)

    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password_confirm="different123"),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert standard_client.table_calls == []
    assert service_role_client.table_calls == []


def test_username_login_uses_authorized_lookup_and_reaches_password_verification(
    monkeypatch,
    caplog,
) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([user])
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)
    verification_calls: list[tuple[str, str | None]] = []

    def record_verification(password: str, stored_hash: str | None) -> bool:
        verification_calls.append((password, stored_hash))
        return verify_password(password, stored_hash)

    monkeypatch.setattr("app.api.auth.verify_password", record_verification)

    with caplog.at_level(logging.INFO, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual-user", "password": "strongpass123"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "manual-user"
    assert len(verification_calls) == 1
    assert verification_calls[0][1] == user["password_hash"]
    assert standard_client.select_calls == []
    assert service_role_client.select_filters == [[("username", "manual-user")]]
    assert_public_auth_response(response)
    assert_secret_values_not_logged(
        caplog,
        "manual@example.com",
        "strongpass123",
        user["password_hash"],
        response.json()["access_token"],
    )


def test_email_fallback_uses_authorized_lookup_and_reaches_password_verification(
    monkeypatch,
    caplog,
) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([user])
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)
    verification_calls: list[tuple[str, str | None]] = []

    def record_verification(password: str, stored_hash: str | None) -> bool:
        verification_calls.append((password, stored_hash))
        return verify_password(password, stored_hash)

    monkeypatch.setattr("app.api.auth.verify_password", record_verification)

    with caplog.at_level(logging.INFO, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "  Manual@Example.COM  ", "password": "strongpass123"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "manual@example.com"
    assert len(verification_calls) == 1
    assert verification_calls[0][1] == user["password_hash"]
    assert standard_client.select_calls == []
    assert service_role_client.select_filters == [
        [("username", "manual@example.com")],
        [("email", "manual@example.com")],
    ]
    assert_public_auth_response(response)
    assert_secret_values_not_logged(
        caplog,
        "manual@example.com",
        "strongpass123",
        user["password_hash"],
        response.json()["access_token"],
    )


def test_nonexistent_user_returns_existing_non_enumerating_failure(
    monkeypatch,
    caplog,
) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient()
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)

    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "nonexistent@example.com", "password": "pass123"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": True,
        "code": "AUTH_INVALID",
        "message": "Invalid username or password",
    }
    assert standard_client.select_calls == []
    assert service_role_client.select_filters == [
        [("username", "nonexistent@example.com")],
        [("email", "nonexistent@example.com")],
    ]
    assert_public_auth_response(response)
    assert_secret_values_not_logged(
        caplog,
        "nonexistent@example.com",
        "pass123",
    )


def test_wrong_password_matches_nonexistent_user_failure_and_logs_no_credentials(
    monkeypatch,
    caplog,
) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([user])
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)

    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual-user", "password": "wrongpass123"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "error": True,
        "code": "AUTH_INVALID",
        "message": "Invalid username or password",
    }
    assert standard_client.select_calls == []
    assert service_role_client.select_filters == [[("username", "manual-user")]]
    assert_public_auth_response(response)
    failure_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.login.failure"
    ]
    assert failure_records
    assert failure_records[-1].auth_method == "password"
    assert failure_records[-1].error_code == "AUTH_INVALID"
    assert_secret_values_not_logged(
        caplog,
        "manual-user",
        "wrongpass123",
        user["password_hash"],
    )


def test_unverified_user_is_found_by_authorized_lookup_without_session(
    monkeypatch,
) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient(
        [password_user(email_verified=False)]
    )
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "manual-user", "password": "strongpass123"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert "access_token" not in response.json()
    assert standard_client.select_calls == []
    assert service_role_client.select_filters == [[("username", "manual-user")]]
    assert_public_auth_response(response)


@pytest.mark.parametrize(
    ("path", "payload", "existing_user", "expected_available"),
    [
        (
            "/auth/check-username",
            {"username": "manual-user"},
            {"id": "user-1", "username": "manual-user"},
            False,
        ),
        (
            "/auth/check-username",
            {"username": "unused-user"},
            None,
            True,
        ),
        (
            "/auth/check-email",
            {"email": "manual@example.com"},
            {"id": "user-1", "email": "manual@example.com"},
            False,
        ),
    ],
)
def test_public_availability_semantics_use_service_role_and_return_only_boolean(
    monkeypatch,
    path: str,
    payload: dict[str, str],
    existing_user: dict[str, str] | None,
    expected_available: bool,
) -> None:
    """Availability intentionally discloses only a registration-oriented boolean."""
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient(
        [existing_user] if existing_user else []
    )
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)

    response = TestClient(app).post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {"available": expected_available}
    assert standard_client.select_calls == []
    assert service_role_client.select_calls == [["id"]]
    assert_public_auth_response(response)


def test_resend_verification_uses_service_role_minimum_fields(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    standard_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient(
        [
            {
                "id": "user-1",
                "email": "manual@example.com",
                "email_verified": False,
                "password_hash": "stored-test-credential",
            }
        ]
    )
    patch_auth_supabase_clients(monkeypatch, standard_client, service_role_client)
    deliveries: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.api.auth.issue_verification_email",
        lambda user_id, email: deliveries.append((user_id, email)),
    )

    response = TestClient(app).post(
        "/auth/resend-verification",
        json={"email": "manual@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert deliveries == [("user-1", "manual@example.com")]
    assert standard_client.select_calls == []
    assert service_role_client.select_calls == [
        ["id", "email_verified", "password_hash"]
    ]
    assert_public_auth_response(response)
