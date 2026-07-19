from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import _user_cache
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: Any


class FakeTableQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.selected_columns: list[str] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None

    def select(self, columns: str, *args: Any, **kwargs: Any) -> "FakeTableQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            row = {"id": f"row-{len(self.rows) + 1}", **self.insert_payload}
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


class FakeRpc:
    def __init__(self, client: "FakeSupabaseClient", name: str, params: dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.params = params

    def execute(self) -> FakeResponse:
        handler = getattr(self.client, f"rpc_{self.name}", None)
        if handler is None:
            raise AssertionError(f"Unexpected RPC {self.name}")
        result = handler(self.params)
        return FakeResponse(data=[result if isinstance(result, dict) else {"result": result}])


class FakeSupabaseClient:
    def __init__(
        self,
        users: list[dict[str, Any]] | None = None,
        identities: list[dict[str, Any]] | None = None,
    ) -> None:
        self.tables = {
            "users": users or [],
            "user_identities": identities or [],
        }

    def table(self, table_name: str) -> FakeTableQuery:
        return FakeTableQuery(self.tables[table_name])

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, name, params)

    def _find_user(self, user_id: str) -> dict[str, Any] | None:
        return next((u for u in self.tables["users"] if u["id"] == user_id), None)

    def _find_google_identity(self, user_id: str) -> dict[str, Any] | None:
        return next(
            (
                i
                for i in self.tables["user_identities"]
                if i["user_id"] == user_id and i["provider"] == "google"
            ),
            None,
        )

    def rpc_link_google_identity(self, params: dict[str, Any]) -> str:
        user = self._find_user(params["p_user_id"])
        if user is None:
            return "user_not_found"
        current_identity = self._find_google_identity(params["p_user_id"])
        if current_identity is not None:
            if current_identity["provider_subject"] == params["p_provider_subject"]:
                return "already_linked_same"
            return "already_linked"
        for identity in self.tables["user_identities"]:
            if identity["provider"] == "google" and identity["provider_subject"] == params["p_provider_subject"]:
                return "conflict_other_user"
        for other in self.tables["users"]:
            if other["id"] != params["p_user_id"] and other.get("google_sub") == params["p_provider_subject"]:
                return "conflict_other_user"
            if (
                other["id"] != params["p_user_id"]
                and (other.get("email") or "").strip().lower()
                == params["p_email_at_link"].strip().lower()
            ):
                return "email_conflict_other_user"

        self.tables["user_identities"].append(
            {
                "id": f"identity-{len(self.tables['user_identities']) + 1}",
                "user_id": params["p_user_id"],
                "provider": "google",
                "provider_subject": params["p_provider_subject"],
                "email_at_link": params["p_email_at_link"],
                "email_verified_at_link": True,
            }
        )
        user["google_sub"] = params["p_provider_subject"]
        return "linked"

    def rpc_resolve_google_login(self, params: dict[str, Any]) -> dict[str, Any]:
        subject = params["p_provider_subject"]
        identity = next(
            (
                row
                for row in self.tables["user_identities"]
                if row["provider"] == "google" and row["provider_subject"] == subject
            ),
            None,
        )
        if identity:
            return {"result": "existing", "user_id": identity["user_id"]}

        legacy_user = next(
            (row for row in self.tables["users"] if row.get("google_sub") == subject),
            None,
        )
        if legacy_user:
            self.tables["user_identities"].append(
                {
                    "id": f"identity-{len(self.tables['user_identities']) + 1}",
                    "user_id": legacy_user["id"],
                    "provider": "google",
                    "provider_subject": subject,
                    "email_at_link": params["p_email"],
                    "email_verified_at_link": True,
                }
            )
            return {"result": "existing", "user_id": legacy_user["id"]}

        existing_email = next(
            (
                row
                for row in self.tables["users"]
                if (row.get("email") or "").lower() == params["p_email"].lower()
            ),
            None,
        )
        if existing_email:
            return {"result": "account_link_required", "user_id": existing_email["id"]}

        raise AssertionError("New-user Google login is not expected in account-linking tests")

    def rpc_unlink_google_identity(self, params: dict[str, Any]) -> str:
        user = self._find_user(params["p_user_id"])
        if user is None:
            return "user_not_found"
        identity = self._find_google_identity(params["p_user_id"])
        if identity is None:
            return "not_linked"
        if not user.get("password_hash") or user.get("email_verified") is not True:
            return "last_method"

        self.tables["user_identities"].remove(identity)
        user["google_sub"] = None
        user["tokens_valid_after"] = "2026-01-01T00:00:00+00:00"
        return "unlinked"

    def rpc_set_account_password(self, params: dict[str, Any]) -> str:
        user = self._find_user(params["p_user_id"])
        if user is None:
            return "user_not_found"
        if user.get("password_hash"):
            return "already_set"
        user["password_hash"] = params["p_password_hash"]
        user["tokens_valid_after"] = "2026-01-01T00:00:00+00:00"
        return "set"

    def rpc_remove_account_password(self, params: dict[str, Any]) -> str:
        user = self._find_user(params["p_user_id"])
        if user is None:
            return "user_not_found"
        if not user.get("password_hash"):
            return "not_set"
        if self._find_google_identity(params["p_user_id"]) is None:
            return "last_method"
        user["password_hash"] = None
        user["tokens_valid_after"] = "2026-01-01T00:00:00+00:00"
        return "removed"


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def patch_all_supabase(monkeypatch, fake_client: FakeSupabaseClient) -> None:
    for target in (
        "app.auth.dependencies.get_supabase_client",
        "app.services.account_linking.get_supabase_service_role_client",
        "app.auth.google.get_supabase_service_role_client",
    ):
        monkeypatch.setattr(target, lambda: fake_client)


def patch_google_verifier(monkeypatch, claims_by_token: dict[str, dict[str, Any]]) -> None:
    def fake_verify(token: str, attempt_id: str = "unknown") -> dict[str, Any]:
        if token not in claims_by_token:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")
        claims = claims_by_token[token]
        if claims.get("email_verified") is not True:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Google email address is not verified",
            )
        return {
            "google_sub": claims["sub"],
            "email": claims["email"],
            "name": claims.get("name", "Google User"),
            "picture": None,
        }

    monkeypatch.setattr("app.services.account_linking._verify_google_token_raw", fake_verify)


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def manual_user(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "manual@example.com",
        "name": "Manual User",
        "role": "user",
        "status": "active",
        "password_hash": hash_password("CorrectHorse123"),
        "email_verified": True,
        "google_sub": None,
        "tokens_valid_after": None,
    }
    base.update(overrides)
    return base


def google_user(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "22222222-2222-2222-2222-222222222222",
        "email": "googleuser@example.com",
        "name": "Google User",
        "role": "user",
        "status": "active",
        "password_hash": None,
        "email_verified": True,
        "google_sub": "google-sub-existing",
        "tokens_valid_after": None,
    }
    base.update(overrides)
    return base


def google_identity_for(user: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    base = {
        "id": "identity-existing",
        "user_id": user["id"],
        "provider": "google",
        "provider_subject": user["google_sub"],
        "email_at_link": user["email"],
        "email_verified_at_link": True,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clear_user_cache():
    _user_cache.clear()
    yield
    _user_cache.clear()


# ---- GET /auth/account-methods ---------------------------------------------


def test_account_methods_requires_auth(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).get("/auth/account-methods")
    assert response.status_code == 401


def test_account_methods_for_manual_only_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).get(
        "/auth/account-methods", headers={"Authorization": f"Bearer {make_token(user)}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"]["linked"] is True
    assert body["email"]["verified"] is True
    assert body["email"]["can_unlink"] is False
    assert body["google"]["linked"] is False
    assert body["google"]["can_unlink"] is False
    assert body["available_login_methods"] == 1
    assert "m***@example.com" == body["email"]["address"]


def test_account_methods_for_google_only_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).get(
        "/auth/account-methods", headers={"Authorization": f"Bearer {make_token(user)}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"]["linked"] is False
    assert body["email"]["can_unlink"] is False
    assert body["google"]["linked"] is True
    assert body["google"]["can_unlink"] is False
    assert body["available_login_methods"] == 1


def test_account_methods_for_user_with_both_methods(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="google-sub-both")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).get(
        "/auth/account-methods", headers={"Authorization": f"Bearer {make_token(user)}"}
    )
    body = response.json()
    assert body["email"]["can_unlink"] is True
    assert body["google"]["can_unlink"] is True
    assert body["available_login_methods"] == 2


def test_account_methods_never_exposes_password_hash_or_sub(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="google-sub-both")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).get(
        "/auth/account-methods", headers={"Authorization": f"Bearer {make_token(user)}"}
    )
    raw = response.text
    assert "google-sub-both" not in raw
    assert hash_password("CorrectHorse123")[:20] not in raw


# ---- POST /auth/link/google -------------------------------------------------


def test_link_google_success(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"good-token": {"sub": "new-google-sub", "email": "manual@example.com", "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/link/google",
        json={"token": "good-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["account_methods"]["google"]["linked"] is True
    assert body["access_token"]
    assert len(fake_client.tables["user_identities"]) == 1
    assert fake_client.tables["user_identities"][0]["user_id"] == user["id"]
    # No new user was created; same user id owns the identity.
    assert len(fake_client.tables["users"]) == 1
    # Additive linking does not revoke the session that authorized it.
    assert user["tokens_valid_after"] is None


def test_linking_same_google_identity_twice_is_idempotent(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"same-token": {"sub": "same-sub", "email": user["email"], "email_verified": True}},
    )
    headers = {"Authorization": f"Bearer {make_token(user)}"}

    first = TestClient(app).post("/auth/link/google", json={"token": "same-token"}, headers=headers)
    second = TestClient(app).post("/auth/link/google", json={"token": "same-token"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["account_methods"]["google"]["linked"] is True
    assert len(fake_client.tables["users"]) == 1
    assert len(fake_client.tables["user_identities"]) == 1


def test_link_google_does_not_change_user_id_or_email(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    original_id = user["id"]
    original_email = user["email"]
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"good-token": {"sub": "new-google-sub", "email": "different-google-email@example.com", "email_verified": True}},
    )

    TestClient(app).post(
        "/auth/link/google",
        json={"token": "good-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert user["id"] == original_id
    assert user["email"] == original_email


def test_link_google_already_linked_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="existing-sub")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"good-token": {"sub": "another-sub", "email": "manual@example.com", "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/link/google",
        json={"token": "good-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ACCOUNT_METHOD_ALREADY_LINKED"


def test_link_google_identity_used_by_another_account_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    victim = manual_user(id="victim-id", google_sub="shared-sub")
    victim_identity = google_identity_for(victim)
    attacker = manual_user(id="attacker-id", email="attacker@example.com")
    fake_client = FakeSupabaseClient([victim, attacker], [victim_identity])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"stolen-token": {"sub": "shared-sub", "email": "attacker@example.com", "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/link/google",
        json={"token": "stolen-token"},
        headers={"Authorization": f"Bearer {make_token(attacker)}"},
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "ACCOUNT_METHOD_IN_USE_BY_ANOTHER_ACCOUNT"
    # No account details about the victim are leaked.
    assert "victim" not in response.text
    # Nothing was mutated.
    assert len(fake_client.tables["user_identities"]) == 1


def test_link_google_email_owned_by_another_user_is_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    current_user = manual_user(id="current-user", email="current@example.com")
    email_owner = manual_user(id="email-owner", email="google@example.com")
    fake_client = FakeSupabaseClient([current_user, email_owner])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"token": {"sub": "unclaimed-sub", "email": email_owner["email"], "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/link/google",
        json={"token": "token"},
        headers={"Authorization": f"Bearer {make_token(current_user)}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ACCOUNT_METHOD_IN_USE_BY_ANOTHER_ACCOUNT"
    assert fake_client.tables["user_identities"] == []
    assert current_user["google_sub"] is None


def test_link_google_invalid_token_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(monkeypatch, {})

    response = TestClient(app).post(
        "/auth/link/google",
        json={"token": "bad-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    # 403, not 401: a 401 here would trip the frontend's "401 clears the
    # session" interceptor and force-log an otherwise validly logged-in user out.
    assert response.status_code == 403
    assert len(fake_client.tables["user_identities"]) == 0


def test_link_google_unverified_email_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"unverified": {"sub": "sub", "email": user["email"], "email_verified": False}},
    )

    response = TestClient(app).post(
        "/auth/link/google",
        json={"token": "unverified"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )

    assert response.status_code == 403
    assert fake_client.tables["user_identities"] == []


def test_password_user_links_then_both_login_methods_return_original_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(profile_id="profile-1", owned_game_ids=["game-1", "game-2"])
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_google_verifier(
        monkeypatch,
        {"link-token": {"sub": "linked-sub", "email": user["email"], "email_verified": True}},
    )

    original_session = make_token(user)
    link_response = TestClient(app).post(
        "/auth/link/google",
        json={"token": "link-token"},
        headers={"Authorization": f"Bearer {original_session}"},
    )
    assert link_response.status_code == 200

    def fake_verify_oauth2_token(token: str, request: Any, audience: str) -> dict[str, Any]:
        assert audience == "test-google-client"
        return {
            "sub": "linked-sub",
            "email": user["email"],
            "email_verified": True,
            "name": user["name"],
        }

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", fake_verify_oauth2_token)

    google_login = TestClient(app).post("/auth/google", json={"token": "google-login-token"})
    password_login = TestClient(app).post(
        "/auth/login",
        json={"username": user["email"], "password": "CorrectHorse123"},
    )
    original_session_check = TestClient(app).get(
        "/auth/account-methods",
        headers={"Authorization": f"Bearer {original_session}"},
    )

    assert google_login.status_code == 200
    assert password_login.status_code == 200
    assert original_session_check.status_code == 200
    assert google_login.json()["user"]["id"] == user["id"]
    assert password_login.json()["user"]["id"] == user["id"]
    assert len(fake_client.tables["users"]) == 1
    assert len(fake_client.tables["user_identities"]) == 1
    assert user["profile_id"] == "profile-1"
    assert user["owned_game_ids"] == ["game-1", "game-2"]


def test_link_google_requires_auth(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post("/auth/link/google", json={"token": "x"})
    assert response.status_code == 401


# ---- POST /auth/unlink/google -----------------------------------------------


def test_unlink_google_success_when_password_exists_and_verified(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="sub-1")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/unlink/google",
        json={"current_password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["account_methods"]["google"]["linked"] is False
    assert user["google_sub"] is None
    assert fake_client.tables["user_identities"] == []


def test_unlink_google_blocked_for_google_only_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/unlink/google",
        json={"current_password": "irrelevant-but-min-length"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    # Google-only user has no password to verify: reauth fails first, which
    # is itself the correct outcome — unlink never proceeds either way.
    assert response.status_code == 403
    assert response.json()["code"] == "REAUTHENTICATION_REQUIRED"
    assert identity in fake_client.tables["user_identities"]


def test_unlink_google_blocked_when_email_unverified_even_with_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="sub-1", email_verified=False)
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/unlink/google",
        json={"current_password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "LAST_LOGIN_METHOD"
    assert identity in fake_client.tables["user_identities"]


def test_unlink_google_not_linked(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/unlink/google",
        json={"current_password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ACCOUNT_METHOD_NOT_LINKED"


def test_unlink_google_wrong_current_password_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="sub-1")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/unlink/google",
        json={"current_password": "totally-wrong-pass"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "REAUTHENTICATION_REQUIRED"
    assert identity in fake_client.tables["user_identities"]


def test_unlink_google_does_not_delete_user_row(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="sub-1")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    TestClient(app).post(
        "/auth/unlink/google",
        json={"current_password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert len(fake_client.tables["users"]) == 1
    assert fake_client.tables["users"][0]["id"] == user["id"]


# ---- POST /auth/set-password ------------------------------------------------


def test_set_password_success_for_google_only_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"fresh-token": {"sub": user["google_sub"], "email": user["email"], "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/set-password",
        json={"google_token": "fresh-token", "password": "NewStrongPass1", "password_confirm": "NewStrongPass1"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["account_methods"]["email"]["linked"] is True
    assert user["password_hash"] is not None


def test_set_password_mismatch_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/set-password",
        json={"google_token": "x", "password": "NewStrongPass1", "password_confirm": "Different1"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 400
    assert user["password_hash"] is None


def test_set_password_weak_password_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/set-password",
        json={"google_token": "x", "password": "short", "password_confirm": "short"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    # Below PASSWORD_MIN_LENGTH is rejected by pydantic Field validation
    # before it reaches the handler (same as RegisterRequest/reset-confirm).
    assert response.status_code == 422
    assert user["password_hash"] is None


def test_set_password_already_set_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="sub-1")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"fresh-token": {"sub": user["google_sub"], "email": user["email"], "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/set-password",
        json={"google_token": "fresh-token", "password": "NewStrongPass1", "password_confirm": "NewStrongPass1"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PASSWORD_ALREADY_SET"


def test_set_password_google_token_mismatch_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"someone-elses-token": {"sub": "not-the-linked-sub", "email": "other@example.com", "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/set-password",
        json={
            "google_token": "someone-elses-token",
            "password": "NewStrongPass1",
            "password_confirm": "NewStrongPass1",
        },
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "INVALID_GOOGLE_TOKEN"
    assert user["password_hash"] is None


def test_set_password_enables_manual_login(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    # Manual login goes through app.api.auth's own client instance.
    fake_client = FakeSupabaseClient([user], [identity])
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"fresh-token": {"sub": user["google_sub"], "email": user["email"], "email_verified": True}},
    )
    user["username"] = "googleuser"

    TestClient(app).post(
        "/auth/set-password",
        json={"google_token": "fresh-token", "password": "NewStrongPass1", "password_confirm": "NewStrongPass1"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )

    login_response = TestClient(app).post(
        "/auth/login", json={"username": "googleuser", "password": "NewStrongPass1"}
    )
    assert login_response.status_code == 200
    assert login_response.json()["user"]["id"] == user["id"]


# ---- POST /auth/remove-password ---------------------------------------------


def test_remove_password_success_when_google_linked(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="sub-1")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"fresh-token": {"sub": user["google_sub"], "email": user["email"], "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/remove-password",
        json={"google_token": "fresh-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    assert user["password_hash"] is None


def test_remove_password_blocked_as_last_login_method(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/remove-password",
        json={"google_token": "irrelevant"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    # No Google linked at all: reauth fails first (INVALID_GOOGLE_TOKEN) —
    # the mutation never gets a chance to run, so the password is untouched.
    assert response.status_code == 403
    assert user["password_hash"] is not None


def test_remove_password_not_set_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_user()
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"fresh-token": {"sub": user["google_sub"], "email": user["email"], "email_verified": True}},
    )

    response = TestClient(app).post(
        "/auth/remove-password",
        json={"google_token": "fresh-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PASSWORD_NOT_SET"


def test_remove_password_then_google_login_still_works(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user(google_sub="sub-1")
    identity = google_identity_for(user)
    fake_client = FakeSupabaseClient([user], [identity])
    monkeypatch.setattr("app.auth.google.get_supabase_service_role_client", lambda: fake_client)
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(
        monkeypatch,
        {"fresh-token": {"sub": user["google_sub"], "email": user["email"], "email_verified": True}},
    )

    TestClient(app).post(
        "/auth/remove-password",
        json={"google_token": "fresh-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )

    def fake_verify_oauth2_token(token: str, request: Any, audience: str) -> dict[str, Any]:
        return {"sub": user["google_sub"], "email": user["email"], "email_verified": True}

    monkeypatch.setattr("app.auth.google.id_token.verify_oauth2_token", fake_verify_oauth2_token)

    google_login_response = TestClient(app).post("/auth/google", json={"token": "any"})
    assert google_login_response.status_code == 200
    assert google_login_response.json()["user"]["id"] == user["id"]


# ---- Rate limiting sanity (does not break existing login rate limits) ------


def test_account_linking_endpoints_are_rate_limited_per_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = manual_user()
    fake_client = FakeSupabaseClient([user])
    patch_all_supabase(monkeypatch, fake_client)
    patch_google_verifier(monkeypatch, {})

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {make_token(user)}"}
    last_status = None
    for _ in range(15):
        last_status = client.post("/auth/link/google", json={"token": "bad"}, headers=headers).status_code
    assert last_status == 429
