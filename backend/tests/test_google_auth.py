from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeUsersQuery:
    def __init__(self, rows: list[dict[str, Any]], fail_last_login_without_phone: bool = False) -> None:
        self.rows = rows
        self.fail_last_login_without_phone = fail_last_login_without_phone
        self.filters: list[tuple[str, Any]] = []
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.selected_columns: list[str] | None = None

    def select(self, columns: str) -> "FakeUsersQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeUsersQuery":
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
                "id": f"user-id-{len(self.rows) + 1}",
                "role": "user",
                "username": None,
                "phone_number": None,
                **self.insert_payload,
            }
            self.rows.append(row)
            return FakeResponse([row])

        rows = self._filtered_rows()

        if self.update_payload is not None:
            if (
                self.fail_last_login_without_phone
                and "last_login" in self.update_payload
                and any(row.get("phone_number") is None for row in rows)
            ):
                raise RuntimeError("RLS rejected last_login update for user without phone_number")

            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(rows)

        return FakeResponse([self._select_columns(row) for row in rows])

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = self.rows
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        return rows

    def _select_columns(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None or "*" in self.selected_columns:
            return row

        return {column: row.get(column) for column in self.selected_columns}


class FakeUserIdentitiesQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.selected_columns: list[str] | None = None

    def select(self, columns: str) -> "FakeUserIdentitiesQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeUserIdentitiesQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _: int) -> "FakeUserIdentitiesQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeUserIdentitiesQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeUserIdentitiesQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            row = {
                "id": f"identity-id-{len(self.rows) + 1}",
                "created_at": "2026-07-06T14:31:25",
                "last_used_at": "2026-07-06T14:31:25",
                **self.insert_payload,
            }
            self.rows.append(row)
            return FakeResponse([row])

        rows = self._filtered_rows()

        if self.update_payload is not None:
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(rows)

        return FakeResponse([self._select_columns(row) for row in rows])

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
        identities: list[dict[str, Any]] | None = None,
        *,
        fail_last_login_without_phone: bool = False,
    ) -> None:
        self.users = users or []
        self.identities = identities or []
        self.fail_last_login_without_phone = fail_last_login_without_phone

    def table(self, table_name: str) -> Any:
        if table_name == "users":
            return FakeUsersQuery(
                self.users,
                fail_last_login_without_phone=self.fail_last_login_without_phone,
            )
        elif table_name == "user_identities":
            return FakeUserIdentitiesQuery(self.identities)
        else:
            raise ValueError(f"Unknown table: {table_name}")


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def patch_google_token_verifier(monkeypatch, token_claims: dict[str, dict[str, str]]) -> None:
    def fake_verify_oauth2_token(token: str, request: Any, audience: str) -> dict[str, str]:
        assert audience == "test-google-client"
        return token_claims[token]

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", fake_verify_oauth2_token)


def test_google_login_create_logout_and_login_again_without_phone_or_username(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "first-login-token": {
                "sub": "google-sub-1",
                "email": "google@example.com",
                "email_verified": True,
                "name": "Google User",
            },
            "second-login-token": {
                "sub": "google-sub-1",
                "email": "google@example.com",
                "email_verified": True,
            },
        },
    )

    first_response = TestClient(app).post("/auth/google", json={"token": "first-login-token"})
    second_response = TestClient(app).post("/auth/google", json={"token": "second-login-token"})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert len(fake_client.users) == 1
    assert fake_client.users[0]["google_sub"] == "google-sub-1"
    assert fake_client.users[0]["phone_number"] is None
    assert fake_client.users[0]["username"] is None
    assert second_response.json()["user"]["email"] == "google@example.com"
    assert second_response.json()["user"]["phone_number"] is None
    assert second_response.json()["user"]["username"] is None


def test_google_login_allows_existing_user_without_phone_username_or_google_sub(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    existing_user = {
        "id": "00000000-0000-0000-0000-000000000202",
        "email": "google@example.com",
        "name": "Google User",
        "google_sub": None,
        "username": None,
        "phone_number": None,
        "role": "user",
    }
    fake_client = FakeSupabaseClient([existing_user])
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "valid-google-token": {
                "sub": "google-sub-1",
                "email": "google@example.com",
                "email_verified": True,
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "valid-google-token"})

    assert response.status_code == 200
    assert response.json()["user"] == {
        "id": existing_user["id"],
        "email": existing_user["email"],
        "name": existing_user["name"],
        "username": None,
        "phone_number": None,
    }
    assert existing_user["last_login"]


def test_google_login_succeeds_if_last_login_update_is_blocked_for_user_without_phone(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    existing_user = {
        "id": "00000000-0000-0000-0000-000000000303",
        "email": "google@example.com",
        "name": "Google User",
        "google_sub": "google-sub-1",
        "username": None,
        "phone_number": None,
        "role": "user",
    }
    fake_client = FakeSupabaseClient(
        [existing_user],
        fail_last_login_without_phone=True,
    )
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "valid-google-token": {
                "sub": "google-sub-1",
                "email": "google@example.com",
                "email_verified": True,
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "valid-google-token"})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == existing_user["id"]
    assert "last_login" not in existing_user


def test_google_login_rejects_unverified_email(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "unverified-token": {
                "sub": "google-sub-1",
                "email": "unverified@example.com",
                "email_verified": False,
                "name": "Unverified User",
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "unverified-token"})

    assert response.status_code == 403
    assert response.json()["message"] == "Google email address is not verified"
    assert len(fake_client.users) == 0


def test_google_login_rejects_missing_email_verified(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "no-verified-claim-token": {
                "sub": "google-sub-1",
                "email": "nofield@example.com",
                "name": "No Verified Field",
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "no-verified-claim-token"})

    assert response.status_code == 403
    assert response.json()["message"] == "Google email address is not verified"
    assert len(fake_client.users) == 0


def test_google_login_rejects_unverified_email_for_existing_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    existing_user = {
        "id": "00000000-0000-0000-0000-000000000404",
        "email": "existing@example.com",
        "name": "Existing User",
        "google_sub": "google-sub-existing",
        "username": "existinguser",
        "phone_number": "+1234567890",
        "role": "user",
    }
    fake_client = FakeSupabaseClient([existing_user])
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "unverified-existing-token": {
                "sub": "google-sub-existing",
                "email": "existing@example.com",
                "email_verified": False,
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "unverified-existing-token"})

    assert response.status_code == 403
    assert response.json()["message"] == "Google email address is not verified"
    assert "last_login" not in existing_user


def test_google_login_accepts_verified_email(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "verified-token": {
                "sub": "google-sub-verified",
                "email": "verified@example.com",
                "email_verified": True,
                "name": "Verified User",
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "verified-token"})

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "verified@example.com"
    assert len(fake_client.users) == 1


def test_google_login_existing_linked_subject_logs_in(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    existing_user = {
        "id": "user-uuid-123",
        "email": "user@example.com",
        "name": "User Name",
        "password_hash": None,
        "google_sub": "google-sub-existing",
        "username": "username123",
        "phone_number": "+15555555",
        "role": "user",
    }
    existing_identity = {
        "id": "identity-uuid-1",
        "user_id": "user-uuid-123",
        "provider": "google",
        "provider_subject": "google-sub-existing",
    }
    fake_client = FakeSupabaseClient([existing_user], [existing_identity])
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "google-token": {
                "sub": "google-sub-existing",
                "email": "user@example.com",
                "email_verified": True,
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "google-token"})
    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-uuid-123"
    assert response.json()["access_token"]


def test_google_login_new_user_creates_user_and_identity(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "google-token": {
                "sub": "google-sub-new",
                "email": "newuser@example.com",
                "email_verified": True,
                "name": "New Google User",
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "google-token"})
    assert response.status_code == 200
    assert len(fake_client.users) == 1
    assert len(fake_client.identities) == 1
    assert fake_client.users[0]["email"] == "newuser@example.com"
    assert fake_client.users[0]["google_sub"] == "google-sub-new"
    assert fake_client.identities[0]["provider_subject"] == "google-sub-new"
    assert fake_client.identities[0]["user_id"] == fake_client.users[0]["id"]


def test_google_login_provider_only_user_links_identity(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    existing_user = {
        "id": "provider-only-uuid",
        "email": "provider@example.com",
        "name": "Provider Only User",
        "password_hash": None,
        "google_sub": None,
        "username": None,
        "phone_number": None,
        "role": "user",
    }
    fake_client = FakeSupabaseClient([existing_user], [])
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "google-token": {
                "sub": "google-sub-provider",
                "email": "provider@example.com",
                "email_verified": True,
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "google-token"})
    assert response.status_code == 200
    assert len(fake_client.identities) == 1
    assert fake_client.identities[0]["provider_subject"] == "google-sub-provider"
    assert fake_client.identities[0]["user_id"] == "provider-only-uuid"
    assert existing_user["google_sub"] == "google-sub-provider"


def test_google_login_manual_password_user_gets_409_conflict(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    existing_user = {
        "id": "manual-user-uuid",
        "email": "manual@example.com",
        "name": "Manual Password User",
        "password_hash": "some_bcrypt_hash",
        "google_sub": None,
        "username": "manualuser",
        "phone_number": "+12345678",
        "role": "user",
    }
    fake_client = FakeSupabaseClient([existing_user], [])
    monkeypatch.setattr("app.auth.google.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(
        monkeypatch,
        {
            "google-token": {
                "sub": "google-sub-attacker",
                "email": "manual@example.com",
                "email_verified": True,
            },
        },
    )

    response = TestClient(app).post("/auth/google", json={"token": "google-token"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"] is True
    assert body["code"] == "ACCOUNT_LINKING_REQUIRED"
    assert "Please sign in with your password" in body["message"]

    # Verify no JWT was issued and no identities or google_sub were updated
    assert len(fake_client.identities) == 0
    assert existing_user["google_sub"] is None
