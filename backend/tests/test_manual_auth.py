from dataclasses import dataclass
import logging
from pathlib import Path
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
    ) -> None:
        self.rows = rows
        self.allow_insert = allow_insert
        self.allow_select = allow_select
        self.insert_calls = insert_calls
        self.select_calls = select_calls
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
            raise AssertionError("non-privileged test client must not insert users")
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

    def table(self, table_name: str) -> FakeUsersQuery:
        assert table_name == "users"
        self.table_calls.append(table_name)
        return FakeUsersQuery(
            self.users,
            allow_insert=self.allow_insert,
            allow_select=self.allow_select,
            insert_calls=self.insert_calls,
            select_calls=self.select_calls,
        )


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def patch_auth_supabase_clients(
    monkeypatch,
    anon_client: FakeSupabaseClient,
    service_role_client: FakeSupabaseClient | None = None,
) -> None:
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: anon_client)
    monkeypatch.setattr(
        "app.api.auth.get_supabase_service_role_client",
        lambda: service_role_client or anon_client,
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
    if private_credential_field in response.text:
        raise AssertionError("auth response contains a private credential field")


def test_register_uses_service_role_insert_without_anon_insert(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    anon_client = FakeSupabaseClient(allow_insert=False, allow_select=False)
    service_role_client = FakeSupabaseClient()
    patch_auth_supabase_clients(monkeypatch, anon_client, service_role_client)

    response = TestClient(app).post("/auth/register", json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert "access_token" not in body
    assert "token_type" not in body
    assert body["user"]["email"] == "manual@example.com"
    assert body["user"]["name"] == "Manual User"
    assert body["user"]["username"] == "manual-user"
    assert_public_auth_response(response)
    assert anon_client.users == []
    assert anon_client.table_calls == []
    assert anon_client.select_calls == []
    assert len(anon_client.insert_calls) == 0
    assert service_role_client.table_calls == ["users", "users", "users", "users"]
    assert service_role_client.select_calls == [["id"], ["id"], ["id"]]
    assert len(service_role_client.insert_calls) == 1
    if not verify_password(
        "strongpass123",
        service_role_client.users[0]["password_hash"],
    ):
        raise AssertionError("registered credential was not hashed correctly")
    assert service_role_client.users[0]["last_login"]
    assert service_role_client.users[0]["email_verified"] is False
    assert body["email_verification_required"] is True
    assert body["email_verification_sent"] is False


def test_register_rejects_duplicate_username(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient([{"id": "user-1", "username": "manual-user"}])
    patch_auth_supabase_clients(monkeypatch, fake_client)

    response = TestClient(app).post("/auth/register", json=register_payload())

    assert response.status_code == 409
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "CONFLICT"
    assert err["message"] == "Username is already taken"


def test_register_rejects_duplicate_email(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient([{"id": "user-1", "email": "manual@example.com"}])
    patch_auth_supabase_clients(monkeypatch, fake_client)

    response = TestClient(app).post("/auth/register", json=register_payload(username="new-user"))

    assert response.status_code == 409
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "CONFLICT"
    assert err["message"] == "Email is already registered"


def test_register_rejects_duplicate_phone_number(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient([{"id": "user-1", "phone_number": "0501234567"}])
    patch_auth_supabase_clients(monkeypatch, fake_client)

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
    patch_auth_supabase_clients(monkeypatch, fake_client)

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
    anon_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([password_user()])
    patch_auth_supabase_clients(monkeypatch, anon_client, service_role_client)

    with caplog.at_level(logging.INFO, logger="app.api.auth"):
        response = TestClient(app).post(
            "/auth/login",
            json={"username": "manual-user", "password": "strongpass123"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "manual-user"
    assert_public_auth_response(response)
    assert anon_client.select_calls == []
    expected_login_projection = [
        [
            "id",
            "email",
            "name",
            "username",
            "phone_number",
            "password_hash",
            "email_verified",
            "email_verified_at",
            "terms_accepted_at",
        ]
    ]
    if service_role_client.select_calls != expected_login_projection:
        raise AssertionError("password login did not use the required projection")
    success_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.login.success"
    ]
    assert success_records
    assert success_records[-1].auth_method == "password"
    assert success_records[-1].user_id == response.json()["user"]["id"]
    assert "manual@example.com" not in caplog.text
    assert "strongpass123" not in caplog.text


def test_login_accepts_valid_email_and_password(monkeypatch, caplog) -> None:
    configure_test_settings(monkeypatch)
    register_client = FakeSupabaseClient()
    patch_auth_supabase_clients(monkeypatch, register_client)
    TestClient(app).post("/auth/register", json=register_payload())
    register_client.users[0]["email_verified"] = True

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
    patch_auth_supabase_clients(monkeypatch, register_client)
    TestClient(app).post("/auth/register", json=register_payload())
    register_client.users[0]["email_verified"] = True

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "  Manual@Example.COM  ", "password": "strongpass123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "manual@example.com"


def test_login_rejects_unknown_identifier(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    anon_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient()
    patch_auth_supabase_clients(monkeypatch, anon_client, service_role_client)

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "nonexistent@example.com", "password": "pass123"},
    )

    assert response.status_code == 401
    err = response.json()
    assert err["code"] == "AUTH_INVALID"
    assert_public_auth_response(response)
    assert anon_client.select_calls == []
    assert len(service_role_client.select_calls) == 2


def test_login_rejects_wrong_password(monkeypatch, caplog) -> None:
    configure_test_settings(monkeypatch)
    anon_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([password_user()])
    patch_auth_supabase_clients(monkeypatch, anon_client, service_role_client)

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
    assert_public_auth_response(response)
    assert anon_client.select_calls == []
    assert len(service_role_client.select_calls) == 1
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


def test_login_rejects_unverified_service_role_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    anon_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([password_user(email_verified=False)])
    patch_auth_supabase_clients(monkeypatch, anon_client, service_role_client)

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "manual-user", "password": "strongpass123"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert "access_token" not in response.json()
    assert_public_auth_response(response)
    assert anon_client.select_calls == []
    assert len(service_role_client.select_calls) == 1


@pytest.mark.parametrize(
    ("path", "payload", "existing_user"),
    [
        (
            "/auth/check-username",
            {"username": "manual-user"},
            {"id": "user-1", "username": "manual-user"},
        ),
        (
            "/auth/check-email",
            {"email": "manual@example.com"},
            {"id": "user-1", "email": "manual@example.com"},
        ),
    ],
)
def test_availability_checks_use_service_role_id_only(
    monkeypatch,
    path: str,
    payload: dict[str, str],
    existing_user: dict[str, str],
) -> None:
    configure_test_settings(monkeypatch)
    anon_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient([existing_user])
    patch_auth_supabase_clients(monkeypatch, anon_client, service_role_client)

    response = TestClient(app).post(path, json=payload)

    assert response.status_code == 200
    assert response.json() == {"available": False}
    assert_public_auth_response(response)
    assert anon_client.select_calls == []
    assert service_role_client.select_calls == [["id"]]


def test_resend_verification_uses_service_role_minimum_fields(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    anon_client = FakeSupabaseClient(allow_select=False)
    service_role_client = FakeSupabaseClient(
        [
            {
                "id": "user-1",
                "email": "manual@example.com",
                "email_verified": False,
                "password_hash": "stored-credential",
            }
        ]
    )
    patch_auth_supabase_clients(monkeypatch, anon_client, service_role_client)
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
    assert_public_auth_response(response)
    assert deliveries == [("user-1", "manual@example.com")]
    assert anon_client.select_calls == []
    expected_resend_projection = [
        ["id", "email_verified", "password_hash"]
    ]
    if service_role_client.select_calls != expected_resend_projection:
        raise AssertionError("verification resend did not use the minimum projection")


def test_registration_service_role_grant_is_minimal_and_canonical() -> None:
    backend_dir = Path(__file__).parents[1]
    migration = (
        backend_dir / "migrations" / "user_registration_service_role_grant.sql"
    ).read_text(encoding="utf-8").lower()
    schema = (backend_dir / "schema.sql").read_text(encoding="utf-8").lower()

    statements = [
        line.strip()
        for line in migration.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    assert statements == ["grant insert on table public.users to service_role;"]
    assert "disable row level security" not in migration
    assert "create policy" not in migration
    assert "to anon" not in migration
    assert "to authenticated" not in migration
    assert "grant select, insert, update on public.users to service_role;" in schema
