from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import re
import threading
from typing import Any

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import _user_cache
from app.auth.passwords import hash_password, verify_password
from app.core.config import get_settings
from app.main import app
from app.services.email_delivery import EmailDeliveryResult
from app.services.password_reset import PasswordResetService


@dataclass
class FakeResponse:
    data: Any


class FakeQuery:
    def __init__(self, client: "FakeResetSupabaseClient", table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.selected_columns: list[str] | None = None
        self.update_payload: dict[str, Any] | None = None

    def select(self, columns: str, *args: Any, **kwargs: Any) -> "FakeQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _: int) -> "FakeQuery":
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        rows = self.client.tables[self.table_name]
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]

        if self.update_payload is not None:
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(data=rows)

        if self.selected_columns is None:
            return FakeResponse(data=rows)
        return FakeResponse(
            data=[
                {column: row.get(column) for column in self.selected_columns}
                for row in rows
            ]
        )


class FakeRpc:
    def __init__(self, client: "FakeResetSupabaseClient", name: str, params: dict[str, Any]) -> None:
        self.client = client
        self.name = name
        self.params = params

    def execute(self) -> FakeResponse:
        if self.name == "check_password_reset_rate_limit":
            return FakeResponse(data=self.client.check_rate_limit(self.params))
        if self.name == "create_password_reset_token":
            return FakeResponse(data=self.client.create_reset_token(self.params))
        if self.name == "consume_password_reset_token":
            return FakeResponse(data=[self.client.consume_reset_token(self.params)])
        raise AssertionError(f"Unexpected RPC {self.name}")


class FakeResetSupabaseClient:
    def __init__(self, users: list[dict[str, Any]] | None = None) -> None:
        self.tables = {
            "users": users or [],
            "password_reset_tokens": [],
        }
        self._lock = threading.Lock()
        self.rate_limit_result: dict[str, Any] = {"allowed": True}
        self.fail_create = False

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, name, params)

    def check_rate_limit(self, params: dict[str, Any]) -> dict[str, Any]:
        assert "@" not in params["p_email_key"]
        assert "." not in params["p_ip_key"]
        return self.rate_limit_result

    def create_reset_token(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        if self.fail_create:
            raise RuntimeError("database unavailable")
        with self._lock:
            for token in self.tables["password_reset_tokens"]:
                if (
                    token["user_id"] == params["p_user_id"]
                    and token["status"] in {"pending_delivery", "active"}
                    and token.get("consumed_at") is None
                    and token.get("invalidated_at") is None
                ):
                    token["status"] = "invalidated"
                    token["invalidated_at"] = datetime.now(timezone.utc).isoformat()
            row = {
                "id": f"token-{len(self.tables['password_reset_tokens']) + 1}",
                "user_id": params["p_user_id"],
                "token_hash": params["p_token_hash"],
                "status": "pending_delivery",
                "delivery_status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": params["p_expires_at"],
                "consumed_at": None,
                "invalidated_at": None,
            }
            self.tables["password_reset_tokens"].append(row)
            return [{"id": row["id"]}]

    def consume_reset_token(self, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            token = next(
                (
                    row
                    for row in self.tables["password_reset_tokens"]
                    if row["token_hash"] == params["p_token_hash"]
                ),
                None,
            )
            if token is None:
                return {"result": "invalid", "user_id": None}
            if token.get("consumed_at") or token["status"] == "consumed":
                return {"result": "consumed", "user_id": token["user_id"]}
            if token.get("invalidated_at") or token["status"] in {"invalidated", "delivery_failed"}:
                return {"result": "invalid", "user_id": token["user_id"]}
            if token["status"] != "active":
                return {"result": "invalid", "user_id": token["user_id"]}
            expires_at = datetime.fromisoformat(token["expires_at"])
            if expires_at <= datetime.now(timezone.utc):
                return {"result": "expired", "user_id": token["user_id"]}

            user = next(row for row in self.tables["users"] if row["id"] == token["user_id"])
            user["password_hash"] = params["p_password_hash"]
            user["tokens_valid_after"] = params["p_tokens_valid_after"]
            token["status"] = "consumed"
            token["consumed_at"] = params["p_tokens_valid_after"]
            for other in self.tables["password_reset_tokens"]:
                if (
                    other is not token
                    and other["user_id"] == token["user_id"]
                    and other["status"] in {"pending_delivery", "active"}
                    and other.get("consumed_at") is None
                    and other.get("invalidated_at") is None
                ):
                    other["status"] = "invalidated"
                    other["invalidated_at"] = params["p_tokens_valid_after"]
            return {"result": "success", "user_id": token["user_id"]}


class FakeEmailDelivery:
    def __init__(self, result: EmailDeliveryResult | None = None) -> None:
        self.result = result or EmailDeliveryResult(accepted=True, provider_message_id="msg_1")
        self.sent: list[dict[str, str]] = []

    def send_email(self, *, to_email: str, subject: str, html_body: str, text_body: str) -> EmailDeliveryResult:
        self.sent.append(
            {
                "to_email": to_email,
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body,
            }
        )
        return self.result


def configure_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("PASSWORD_RESET_TOKEN_SECRET", "test-reset-secret")
    monkeypatch.setenv("PASSWORD_RESET_TOKEN_TTL_MINUTES", "30")
    monkeypatch.setenv("PUBLIC_WEB_BASE_URL", "https://yesh-mishak.com")
    monkeypatch.setenv("RESEND_API_KEY", "test-resend-key")
    monkeypatch.setenv("PASSWORD_RESET_FROM_EMAIL", "no-reply@yesh-mishak.com")
    monkeypatch.setenv("PASSWORD_RESET_FROM_NAME", "Yesh Mishak")
    get_settings.cache_clear()


def password_user(**overrides: Any) -> dict[str, Any]:
    user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "user@example.com",
        "name": "Password User",
        "username": "password-user",
        "password_hash": hash_password("oldpassword123"),
        "role": "user",
        "status": "active",
        "tokens_valid_after": None,
    }
    user.update(overrides)
    return user


def patch_password_reset(monkeypatch, fake_client: FakeResetSupabaseClient, email: FakeEmailDelivery) -> None:
    monkeypatch.setattr(
        "app.services.password_reset.get_supabase_service_role_client",
        lambda: fake_client,
    )
    monkeypatch.setattr(
        "app.services.password_reset.ResendEmailDelivery",
        lambda: email,
    )
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)


def extract_token(email: FakeEmailDelivery) -> str:
    text = email.sent[-1]["text_body"]
    match = re.search(r"https://yesh-mishak\.com/reset-password\?token=([A-Za-z0-9_-]+)", text)
    assert match
    return match.group(1)


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    _user_cache.clear()
    yield
    _user_cache.clear()


def test_existing_password_account_request_sends_generic_response_and_email(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["message"].startswith("If an eligible account exists")
    assert len(email.sent) == 1
    token_row = fake_client.tables["password_reset_tokens"][0]
    assert token_row["status"] == "active"
    assert token_row["delivery_status"] == "sent"


def test_unknown_email_returns_generic_response_and_sends_no_email(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)

    response = TestClient(app).post(
        "/auth/password-reset/request",
        json={"email": "missing@example.com"},
    )

    assert response.status_code == 200
    assert len(email.sent) == 0
    assert fake_client.tables["password_reset_tokens"] == []


def test_google_only_account_returns_generic_response_and_sends_no_email(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user(password_hash=None)])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    assert len(email.sent) == 0


def test_linked_google_and_password_account_receives_flow(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user(google_sub="google-1")])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)

    response = TestClient(app).post(
        "/auth/password-reset/request",
        json={"email": "USER@EXAMPLE.COM"},
    )

    assert response.status_code == 200
    assert len(email.sent) == 1
    assert email.sent[0]["to_email"] == "user@example.com"


def test_raw_token_is_never_stored_and_hmac_hash_is_stored(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)

    TestClient(app).post("/auth/password-reset/request", json={"email": "user@example.com"})

    raw_token = extract_token(email)
    stored_hash = fake_client.tables["password_reset_tokens"][0]["token_hash"]
    assert raw_token not in str(fake_client.tables["password_reset_tokens"])
    assert stored_hash == PasswordResetService.hash_reset_token(raw_token)
    assert not hmac.compare_digest(stored_hash, raw_token)


def test_previous_token_invalidated_on_new_request(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)
    client = TestClient(app)

    client.post("/auth/password-reset/request", json={"email": "user@example.com"})
    client.post("/auth/password-reset/request", json={"email": "user@example.com"})

    first, second = fake_client.tables["password_reset_tokens"]
    assert first["status"] == "invalidated"
    assert second["status"] == "active"


def test_provider_rejection_marks_token_delivery_failed(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery(EmailDeliveryResult(accepted=False, reason="provider_rejected"))
    patch_password_reset(monkeypatch, fake_client, email)

    response = TestClient(app).post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    token_row = fake_client.tables["password_reset_tokens"][0]
    assert token_row["status"] == "delivery_failed"
    assert token_row["delivery_status"] == "failed"


def test_provider_timeout_keeps_public_response_generic(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery(EmailDeliveryResult(accepted=False, reason="timeout"))
    patch_password_reset(monkeypatch, fake_client, email)

    response = TestClient(app).post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["message"].startswith("If an eligible account exists")
    assert fake_client.tables["password_reset_tokens"][0]["status"] == "delivery_failed"


def test_confirm_rejects_invalid_token(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    patch_password_reset(monkeypatch, fake_client, FakeEmailDelivery())

    response = TestClient(app).post(
        "/auth/password-reset/confirm",
        json={
            "token": "invalid-token-value-with-enough-length",
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "RESET_TOKEN_INVALID"


def test_confirm_rejects_expired_token(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)
    client = TestClient(app)
    client.post("/auth/password-reset/request", json={"email": "user@example.com"})
    raw_token = extract_token(email)
    fake_client.tables["password_reset_tokens"][0]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat()

    response = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "RESET_TOKEN_EXPIRED"


def test_confirm_rejects_password_mismatch_and_policy_failure(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    patch_password_reset(monkeypatch, fake_client, FakeEmailDelivery())
    client = TestClient(app)

    mismatch = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": "token-value-with-enough-length-for-validation",
            "password": "newpassword123",
            "password_confirm": "different123",
        },
    )
    short_password = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": "token-value-with-enough-length-for-validation",
            "password": "short",
            "password_confirm": "short",
        },
    )

    assert mismatch.status_code == 400
    assert mismatch.json()["message"] == "Passwords do not match"
    assert short_password.status_code == 422


def test_successful_reset_updates_password_invalidates_jwt_and_rejects_replay(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = password_user()
    fake_client = FakeResetSupabaseClient([user])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)
    client = TestClient(app)
    now = datetime.now(timezone.utc)
    settings = get_settings()
    old_jwt = pyjwt.encode(
        {
            "sub": user["id"],
            "email": user["email"],
            "iat": now - timedelta(seconds=2),
            "exp": now + timedelta(hours=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    request_response = client.post("/auth/password-reset/request", json={"email": "user@example.com"})
    assert request_response.status_code == 200
    raw_token = extract_token(email)

    response = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": "newpassword123",
            "password_confirm": "newpassword123",
        },
    )

    assert response.status_code == 200
    assert verify_password("newpassword123", user["password_hash"])
    assert not verify_password("oldpassword123", user["password_hash"])
    assert user["tokens_valid_after"] is not None
    assert fake_client.tables["password_reset_tokens"][0]["status"] == "consumed"

    replay = client.post(
        "/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": "anotherpassword123",
            "password_confirm": "anotherpassword123",
        },
    )
    assert replay.status_code == 400
    assert replay.json()["code"] == "RESET_TOKEN_CONSUMED"

    protected = client.get("/games/me", headers={"Authorization": f"Bearer {old_jwt}"})
    assert protected.status_code == 401
    assert protected.json()["code"] == "TOKEN_REVOKED"

    login_old = client.post(
        "/auth/login",
        json={"username": "user@example.com", "password": "oldpassword123"},
    )
    login_new = client.post(
        "/auth/login",
        json={"username": "user@example.com", "password": "newpassword123"},
    )
    assert login_old.status_code == 401
    assert login_new.status_code == 200


def test_concurrent_confirmation_only_one_succeeds(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)
    client = TestClient(app)
    client.post("/auth/password-reset/request", json={"email": "user@example.com"})
    raw_token = extract_token(email)

    results: list[int] = []

    def confirm() -> None:
        response = client.post(
            "/auth/password-reset/confirm",
            json={
                "token": raw_token,
                "password": "newpassword123",
                "password_confirm": "newpassword123",
            },
        )
        results.append(response.status_code)

    threads = [threading.Thread(target=confirm), threading.Thread(target=confirm)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [200, 400]


def test_rate_limiting_uses_structured_error(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    fake_client.rate_limit_result = {"allowed": False, "retry_after_seconds": 123}
    patch_password_reset(monkeypatch, fake_client, FakeEmailDelivery())

    response = TestClient(app, raise_server_exceptions=False).post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "123"
    assert response.json()["code"] == "RATE_LIMITED"


def test_database_create_failure_does_not_send_email(monkeypatch) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    fake_client.fail_create = True
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 500
    assert email.sent == []


def test_sensitive_token_and_full_url_absent_from_logs(monkeypatch, caplog) -> None:
    configure_settings(monkeypatch)
    fake_client = FakeResetSupabaseClient([password_user()])
    email = FakeEmailDelivery()
    patch_password_reset(monkeypatch, fake_client, email)

    with caplog.at_level("INFO"):
        TestClient(app).post("/auth/password-reset/request", json={"email": "user@example.com"})

    raw_token = extract_token(email)
    assert raw_token not in caplog.text
    assert "https://yesh-mishak.com/reset-password?token=" not in caplog.text
    assert "user@example.com" not in caplog.text
