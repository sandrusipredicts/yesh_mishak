from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import _user_cache
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password
from app.core.config import get_settings
from app.main import app


# ---------------------------------------------------------------------------
# Fake Supabase layer
# ---------------------------------------------------------------------------

@dataclass
class FakeResponse:
    data: Any
    count: int | None = None


class FakeTableQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.selected_columns: list[str] | None = None
        self.delete_mode = False
        self.exact_count = False

    def select(self, columns: str, count: str | None = None) -> "FakeTableQuery":
        self.selected_columns = [c.strip() for c in columns.split(",")]
        self.exact_count = count == "exact"
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeTableQuery":
        self.in_filters.append((column, values))
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def delete(self) -> "FakeTableQuery":
        self.delete_mode = True
        return self

    def execute(self) -> FakeResponse:
        rows = self._filtered_rows()
        if self.delete_mode:
            for row in list(rows):
                self.rows.remove(row)
            return FakeResponse(data=rows)
        data = [self._select_columns(row) for row in rows]
        return FakeResponse(data=data, count=len(rows) if self.exact_count else None)

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = self.rows
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        return rows

    def _select_columns(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None or "*" in self.selected_columns:
            return row
        return {c: row.get(c) for c in self.selected_columns}


class FakeRpc:
    def __init__(self, client: "FakeSupabaseClient", name: str, params: dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.params = params

    def execute(self) -> FakeResponse:
        handler = getattr(self.client, f"rpc_{self.name}", None)
        if handler is None:
            raise AssertionError(f"Unexpected RPC: {self.name}")
        result = handler(self.params)
        return FakeResponse(data=[result] if isinstance(result, dict) else result)


class FakeSupabaseClient:
    def __init__(
        self,
        users: list[dict[str, Any]] | None = None,
        games: list[dict[str, Any]] | None = None,
        game_players: list[dict[str, Any]] | None = None,
    ) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "users": users or [],
            "games": games or [],
            "game_players": game_players or [],
        }
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, name: str) -> FakeTableQuery:
        if name not in self.tables:
            self.tables[name] = []
        return FakeTableQuery(self.tables[name])

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        self.rpc_calls.append((name, params))
        return FakeRpc(self, name, params)

    def rpc_delete_user_account(self, params: dict[str, Any]) -> dict[str, Any]:
        user_id = str(params["p_user_id"])
        users = self.tables["users"]
        user = next((u for u in users if u["id"] == user_id), None)
        if user is None:
            return {"error": "user_not_found"}

        game_players = self.tables["game_players"]
        games = self.tables["games"]
        reconciled = 0
        player_game_ids = [gp["game_id"] for gp in game_players if gp["user_id"] == user_id]
        for game in games:
            if game["id"] in player_game_ids and game.get("status") in ("open", "full"):
                game["players_present"] = max(0, game["players_present"] - 1)
                if game["players_present"] < game["max_players"]:
                    game["status"] = "open"
                reconciled += 1

        self.tables["game_players"] = [gp for gp in game_players if gp["user_id"] != user_id]
        users.remove(user)

        return {"deleted": True, "games_reconciled": reconciled}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def patch_supabase(monkeypatch, fake_client: FakeSupabaseClient) -> None:
    for target in (
        "app.auth.dependencies.get_supabase_client",
        "app.services.account_deletion.get_supabase_service_role_client",
    ):
        monkeypatch.setattr(target, lambda: fake_client)


def patch_google_verifier(monkeypatch, claims_by_token: dict[str, dict[str, Any]]) -> None:
    def fake_verify(token: str, attempt_id: str = "unknown") -> dict[str, Any]:
        if token not in claims_by_token:
            from fastapi import HTTPException, status
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")
        claims = claims_by_token[token]
        return {
            "google_sub": claims["sub"],
            "email": claims["email"],
            "name": claims.get("name", "Google User"),
            "picture": None,
        }

    monkeypatch.setattr("app.services.account_deletion._verify_google_token_raw", fake_verify)


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def password_user(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "user@example.com",
        "name": "Test User",
        "role": "user",
        "status": "active",
        "password_hash": hash_password("CorrectHorse123"),
        "email_verified": True,
        "google_sub": None,
        "tokens_valid_after": None,
    }
    base.update(overrides)
    return base


def google_only_user(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "22222222-2222-2222-2222-222222222222",
        "email": "guser@example.com",
        "name": "Google User",
        "role": "user",
        "status": "active",
        "password_hash": None,
        "email_verified": True,
        "google_sub": "google-sub-1",
        "tokens_valid_after": None,
    }
    base.update(overrides)
    return base


def dual_user(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "33333333-3333-3333-3333-333333333333",
        "email": "dual@example.com",
        "name": "Dual User",
        "role": "user",
        "status": "active",
        "password_hash": hash_password("CorrectHorse123"),
        "email_verified": True,
        "google_sub": "google-sub-dual",
        "tokens_valid_after": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _clear_user_cache():
    _user_cache.clear()
    yield
    _user_cache.clear()


# ---------------------------------------------------------------------------
# Helpers for DELETE-with-body (httpx TestClient.delete doesn't accept json=)
# ---------------------------------------------------------------------------

import json as _json


def _delete(client: TestClient, url: str, *, body: dict | None = None, headers: dict | None = None):
    return client.request(
        "DELETE",
        url,
        content=_json.dumps(body) if body is not None else None,
        headers={**(headers or {}), "Content-Type": "application/json"},
    )


# ---------------------------------------------------------------------------
# DELETE /auth/account — auth and validation
# ---------------------------------------------------------------------------


def test_delete_account_requires_auth(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake = FakeSupabaseClient()
    patch_supabase(monkeypatch, fake)

    response = _delete(TestClient(app), "/auth/account", body={"password": "anything"})
    assert response.status_code == 401


def test_delete_account_requires_credentials_in_body(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 422


def test_delete_account_wrong_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "WrongPassword1"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "REAUTHENTICATION_REQUIRED"


def test_delete_account_with_correct_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Account deleted"
    assert len(fake.tables["users"]) == 0
    assert ("delete_user_account", {"p_user_id": user["id"]}) in fake.rpc_calls


# ---------------------------------------------------------------------------
# Google re-auth
# ---------------------------------------------------------------------------


def test_delete_account_with_valid_google_token(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_only_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)
    patch_google_verifier(monkeypatch, {
        "valid-google-token": {"sub": "google-sub-1", "email": "guser@example.com", "email_verified": True},
    })

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"google_token": "valid-google-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    assert len(fake.tables["users"]) == 0


def test_delete_account_with_wrong_google_sub(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_only_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)
    patch_google_verifier(monkeypatch, {
        "wrong-token": {"sub": "different-sub", "email": "other@example.com", "email_verified": True},
    })

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"google_token": "wrong-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "INVALID_GOOGLE_TOKEN"
    assert len(fake.tables["users"]) == 1


def test_delete_account_with_invalid_google_token(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_only_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)
    patch_google_verifier(monkeypatch, {})

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"google_token": "expired-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "INVALID_GOOGLE_TOKEN"


# ---------------------------------------------------------------------------
# Dual-method user can use either credential
# ---------------------------------------------------------------------------


def test_dual_user_can_delete_with_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dual_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    assert len(fake.tables["users"]) == 0


def test_dual_user_can_delete_with_google(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = dual_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)
    patch_google_verifier(monkeypatch, {
        "dual-google-token": {"sub": "google-sub-dual", "email": "dual@example.com", "email_verified": True},
    })

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"google_token": "dual-google-token"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    assert len(fake.tables["users"]) == 0


# ---------------------------------------------------------------------------
# Google-only user cannot re-auth with password
# ---------------------------------------------------------------------------


def test_google_only_user_with_password_rejected(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = google_only_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "SomePassword1"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "REAUTHENTICATION_REQUIRED"
    assert len(fake.tables["users"]) == 1


# ---------------------------------------------------------------------------
# Last admin protection
# ---------------------------------------------------------------------------


def test_last_admin_cannot_delete(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user(role="admin")
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "LAST_ADMIN"
    assert len(fake.tables["users"]) == 1


def test_non_last_admin_can_delete(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    admin1 = password_user(role="admin")
    admin2 = password_user(
        id="44444444-4444-4444-4444-444444444444",
        email="admin2@example.com",
        role="admin",
    )
    fake = FakeSupabaseClient([admin1, admin2])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(admin1)}"},
    )
    assert response.status_code == 200
    assert len(fake.tables["users"]) == 1
    assert fake.tables["users"][0]["id"] == admin2["id"]


# ---------------------------------------------------------------------------
# Game counter reconciliation
# ---------------------------------------------------------------------------


def test_deletion_reconciles_game_counts(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    game_full = {
        "id": "game-1",
        "players_present": 10,
        "max_players": 10,
        "status": "full",
    }
    game_open = {
        "id": "game-2",
        "players_present": 5,
        "max_players": 10,
        "status": "open",
    }
    game_finished = {
        "id": "game-3",
        "players_present": 8,
        "max_players": 10,
        "status": "finished",
    }
    game_players = [
        {"game_id": "game-1", "user_id": user["id"]},
        {"game_id": "game-2", "user_id": user["id"]},
        {"game_id": "game-3", "user_id": user["id"]},
    ]
    fake = FakeSupabaseClient([user], [game_full, game_open, game_finished], game_players)
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200

    games_by_id = {g["id"]: g for g in fake.tables["games"]}
    assert games_by_id["game-1"]["players_present"] == 9
    assert games_by_id["game-1"]["status"] == "open"
    assert games_by_id["game-2"]["players_present"] == 4
    assert games_by_id["game-2"]["status"] == "open"
    assert games_by_id["game-3"]["players_present"] == 8
    assert games_by_id["game-3"]["status"] == "finished"


def test_deletion_with_no_games(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 200
    assert len(fake.tables["users"]) == 0


# ---------------------------------------------------------------------------
# RPC is called (verifies single-transaction path)
# ---------------------------------------------------------------------------


def test_delete_calls_rpc_not_direct_table_delete(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )

    rpc_names = [name for name, _ in fake.rpc_calls]
    assert "delete_user_account" in rpc_names


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


def test_delete_invalidates_user_cache(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    _user_cache[user["id"]] = user

    _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )

    assert user["id"] not in _user_cache


# ---------------------------------------------------------------------------
# User not found (edge case: deleted between auth and service call)
# ---------------------------------------------------------------------------


def test_delete_account_user_not_found(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    auth_fake = FakeSupabaseClient([user])
    service_fake = FakeSupabaseClient([])
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: auth_fake)
    monkeypatch.setattr(
        "app.services.account_deletion.get_supabase_service_role_client",
        lambda: service_fake,
    )

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_delete_account_response_shape(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = password_user()
    fake = FakeSupabaseClient([user])
    patch_supabase(monkeypatch, fake)

    response = _delete(
        TestClient(app),
        "/auth/account",
        body={"password": "CorrectHorse123"},
        headers={"Authorization": f"Bearer {make_token(user)}"},
    )
    body = response.json()
    assert set(body.keys()) == {"message"}
    assert body["message"] == "Account deleted"
