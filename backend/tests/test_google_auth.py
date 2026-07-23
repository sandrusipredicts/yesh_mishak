from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Lock
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


class FakeRpc:
    def __init__(self, client: "FakeSupabaseClient", name: str, params: dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.params = params

    def execute(self) -> FakeResponse:
        if self.name != "resolve_google_login":
            raise AssertionError(f"Unexpected RPC: {self.name}")
        return FakeResponse([self.client.resolve_google_login(self.params)])


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
        self._identity_lock = Lock()

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

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, name, params)

    def resolve_google_login(self, params: dict[str, Any]) -> dict[str, Any]:
        subject = params["p_provider_subject"].strip()
        email = params["p_email"].strip().lower()

        with self._identity_lock:
            identity = next(
                (
                    row
                    for row in self.identities
                    if row["provider"] == "google" and row["provider_subject"] == subject
                ),
                None,
            )
            if identity:
                identity["email_at_link"] = email
                return {"result": "existing", "user_id": identity["user_id"]}

            legacy_user = next((row for row in self.users if row.get("google_sub") == subject), None)
            if legacy_user:
                current_identity = next(
                    (
                        row
                        for row in self.identities
                        if row["provider"] == "google" and row["user_id"] == legacy_user["id"]
                    ),
                    None,
                )
                if current_identity and current_identity["provider_subject"] != subject:
                    return {"result": "identity_data_conflict", "user_id": None}
                if current_identity is None:
                    self.identities.append(
                        {
                            "id": f"identity-id-{len(self.identities) + 1}",
                            "user_id": legacy_user["id"],
                            "provider": "google",
                            "provider_subject": subject,
                            "email_at_link": email,
                            "email_verified_at_link": True,
                        }
                    )
                return {"result": "existing", "user_id": legacy_user["id"]}

            existing_email_user = next(
                (row for row in self.users if (row.get("email") or "").strip().lower() == email),
                None,
            )
            if existing_email_user:
                return {"result": "account_link_required", "user_id": existing_email_user["id"]}

            user = {
                "id": f"user-id-{len(self.users) + 1}",
                "role": "user",
                "username": None,
                "phone_number": None,
                "password_hash": None,
                "google_sub": subject,
                "email": email,
                "name": params["p_name"],
                "picture": params.get("p_picture"),
                "email_verified": True,
            }
            self.users.append(user)
            self.identities.append(
                {
                    "id": f"identity-id-{len(self.identities) + 1}",
                    "user_id": user["id"],
                    "provider": "google",
                    "provider_subject": subject,
                    "email_at_link": email,
                    "email_verified_at_link": True,
                }
            )
            return {"result": "created", "user_id": user["id"]}


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def patch_google_token_verifier(monkeypatch, token_claims: dict[str, dict[str, str]]) -> None:
    def fake_verify_oauth2_token(token: str, request: Any, audience: Any) -> dict[str, str]:
        if token not in token_claims:
            raise ValueError("invalid token")
        claims = token_claims[token]
        allowed_audiences = [audience] if isinstance(audience, str) else list(audience)
        token_aud = claims.get("aud")
        if token_aud:
            if token_aud not in allowed_audiences:
                raise ValueError("Audience mismatch")
        else:
            if "test-google-client" not in allowed_audiences:
                raise ValueError("Audience mismatch")
        return claims

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", fake_verify_oauth2_token)


def test_google_login_create_logout_and_login_again_without_phone_or_username(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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


def test_google_login_existing_email_without_identity_requires_explicit_link(monkeypatch) -> None:
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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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

    assert response.status_code == 409
    assert response.json()["code"] == "ACCOUNT_LINK_REQUIRED"
    assert fake_client.identities == []
    assert existing_user["google_sub"] is None


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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    assert fake_client.identities[0]["provider_subject"] == "google-sub-1"
    assert "last_login" not in existing_user


def test_google_login_rejects_unverified_email(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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


def test_google_login_provider_only_email_match_still_requires_explicit_link(monkeypatch) -> None:
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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    assert response.status_code == 409
    assert response.json()["code"] == "ACCOUNT_LINK_REQUIRED"
    assert fake_client.identities == []
    assert existing_user["google_sub"] is None


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
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
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
    assert body["code"] == "ACCOUNT_LINK_REQUIRED"
    assert "connect Google from Settings" in body["message"]

    # Verify no JWT was issued and no identities or google_sub were updated
    assert len(fake_client.identities) == 0
    assert existing_user["google_sub"] is None


def test_google_login_rejects_invalid_token(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_token_verifier(monkeypatch, {})

    response = TestClient(app).post("/auth/google", json={"token": "invalid-token"})

    assert response.status_code == 401
    assert fake_client.users == []
    assert fake_client.identities == []


def test_concurrent_google_login_resolution_creates_one_user_and_identity(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)

    from app.auth.google import find_or_create_google_user

    google_user = {
        "google_sub": "concurrent-google-sub",
        "email": "concurrent@example.com",
        "name": "Concurrent User",
        "picture": None,
    }

    with ThreadPoolExecutor(max_workers=8) as executor:
        users = list(executor.map(lambda _: find_or_create_google_user(google_user), range(16)))

    assert {user["id"] for user in users} == {fake_client.users[0]["id"]}
    assert len(fake_client.users) == 1
    assert len(fake_client.identities) == 1


def test_google_auth_multiple_audiences(monkeypatch) -> None:
    import pytest
    from fastapi import HTTPException

    # Test case 1: Existing website audience is accepted and new Android audience is accepted
    # Set settings with GOOGLE_CLIENT_ID and GOOGLE_CLIENT_IDS
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "936888694089-fu96l9mkv5r98p0iln8e32tri9tt5h71.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_IDS", "946531239565-0r95anarjdbjsr7ejm6nq7auoih8m651.apps.googleusercontent.com,  936888694089-fu96l9mkv5r98p0iln8e32tri9tt5h71.apps.googleusercontent.com")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    settings = get_settings()
    # Confirm settings property allowed_google_client_ids is deduplicated and parses correctly
    assert settings.allowed_google_client_ids == [
        "936888694089-fu96l9mkv5r98p0iln8e32tri9tt5h71.apps.googleusercontent.com",
        "946531239565-0r95anarjdbjsr7ejm6nq7auoih8m651.apps.googleusercontent.com",
    ]

    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)

    from app.auth.google import verify_google_token

    def mock_verify(id_token_str, request_obj, audience):
        allowed = [audience] if isinstance(audience, str) else list(audience)
        if id_token_str == "web-token":
            payload = {
                "sub": "google-sub-web",
                "email": "webuser@example.com",
                "email_verified": True,
                "aud": "936888694089-fu96l9mkv5r98p0iln8e32tri9tt5h71.apps.googleusercontent.com",
                "iss": "https://accounts.google.com"
            }
        elif id_token_str == "android-token":
            payload = {
                "sub": "google-sub-android",
                "email": "androiduser@example.com",
                "email_verified": True,
                "aud": "946531239565-0r95anarjdbjsr7ejm6nq7auoih8m651.apps.googleusercontent.com",
                "iss": "https://accounts.google.com"
            }
        elif id_token_str == "unknown-token":
            payload = {
                "sub": "google-sub-unknown",
                "email": "unknownuser@example.com",
                "email_verified": True,
                "aud": "some-other-audience.apps.googleusercontent.com",
                "iss": "https://accounts.google.com"
            }
        else:
            raise ValueError("Token decoding failed")

        if payload["aud"] not in allowed:
            raise ValueError("Audience mismatch")

        return payload

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", mock_verify)

    # Web token should be accepted
    web_info = verify_google_token("web-token")
    assert web_info["email"] == "webuser@example.com"

    # Android token should be accepted
    android_info = verify_google_token("android-token")
    assert android_info["email"] == "androiduser@example.com"

    # Unknown token should be rejected with 401
    with pytest.raises(HTTPException) as excinfo:
        verify_google_token("unknown-token")
    assert excinfo.value.status_code == 401
    assert excinfo.value.detail == "Invalid Google token"


def test_google_auth_missing_client_ids_preserves_single_client_behavior(monkeypatch) -> None:
    import pytest
    from fastapi import HTTPException

    # Set settings with GOOGLE_CLIENT_ID only
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "936888694089-fu96l9mkv5r98p0iln8e32tri9tt5h71.apps.googleusercontent.com")
    monkeypatch.delenv("GOOGLE_CLIENT_IDS", raising=False)
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    settings = get_settings()
    assert settings.allowed_google_client_ids == [
        "936888694089-fu96l9mkv5r98p0iln8e32tri9tt5h71.apps.googleusercontent.com",
    ]

    from app.auth.google import verify_google_token

    def mock_verify(id_token_str, request_obj, audience):
        allowed = [audience] if isinstance(audience, str) else list(audience)
        if id_token_str == "web-token":
            payload = {
                "sub": "google-sub-web",
                "email": "webuser@example.com",
                "email_verified": True,
                "aud": "936888694089-fu96l9mkv5r98p0iln8e32tri9tt5h71.apps.googleusercontent.com",
                "iss": "https://accounts.google.com"
            }
        elif id_token_str == "android-token":
            payload = {
                "sub": "google-sub-android",
                "email": "androiduser@example.com",
                "email_verified": True,
                "aud": "946531239565-0r95anarjdbjsr7ejm6nq7auoih8m651.apps.googleusercontent.com",
                "iss": "https://accounts.google.com"
            }
        else:
            raise ValueError("Token decoding failed")

        if payload["aud"] not in allowed:
            raise ValueError("Audience mismatch")

        return payload

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", mock_verify)

    # Web token should be accepted
    web_info = verify_google_token("web-token")
    assert web_info["email"] == "webuser@example.com"

    # Android token should be rejected (raises 401)
    with pytest.raises(HTTPException) as excinfo:
        verify_google_token("android-token")
    assert excinfo.value.status_code == 401
