from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from app.services.phone_verification import (
    InvalidPhoneOtp,
    PhoneProviderError,
    normalize_phone_number,
)


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.insert_payload: dict[str, Any] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.selected_columns: list[str] | None = None

    def select(self, columns: str) -> "FakeQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _: int) -> "FakeQuery":
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        rows = self.database.tables.setdefault(self.table_name, [])
        if self.insert_payload is not None:
            row = {
                "id": f"{self.table_name}-{len(rows) + 1}",
                **self.insert_payload,
            }
            rows.append(row)
            return FakeResponse([dict(row)])

        filtered = rows
        for column, value in self.filters:
            filtered = [row for row in filtered if row.get(column) == value]

        if self.update_payload is not None:
            for row in filtered:
                row.update(self.update_payload)
            return FakeResponse([dict(row) for row in filtered])

        return FakeResponse([self._select(row) for row in filtered])

    def _select(self, row: dict[str, Any]) -> dict[str, Any]:
        if not self.selected_columns or "*" in self.selected_columns:
            return dict(row)
        return {column: row.get(column) for column in self.selected_columns}


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)


class FakePhoneProvider:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.verified: list[tuple[str, str]] = []
        self.fail_start = False
        self.fail_verify = False

    def start_otp(self, phone_e164: str) -> None:
        if self.fail_start:
            raise PhoneProviderError()
        self.started.append(phone_e164)

    def verify_otp(self, phone_e164: str, otp: str) -> str:
        if self.fail_verify:
            raise InvalidPhoneOtp()
        self.verified.append((phone_e164, otp))
        return phone_e164


def configure_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def active_user(**overrides: Any) -> dict[str, Any]:
    user = {
        "id": "00000000-0000-0000-0000-000000000111",
        "email": "user@example.com",
        "name": "Verified User",
        "username": "verified-user",
        "phone_number": None,
        "role": "user",
        "status": "active",
        "tokens_valid_after": None,
    }
    user.update(overrides)
    return user


def auth_headers(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def patch_clients(monkeypatch, fake: FakeSupabase, provider: FakePhoneProvider) -> None:
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.services.phone_verification.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr(
        "app.services.phone_verification.SupabasePhoneVerificationProvider",
        lambda: provider,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+972501234567", "+972501234567"),
        ("050-123-4567", "+972501234567"),
        ("00 1 202 555 0100", "+12025550100"),
    ],
)
def test_normalize_phone_number(raw: str, expected: str) -> None:
    assert normalize_phone_number(raw) == expected


@pytest.mark.parametrize("raw", ["1234567", "+012345678", "050ABC4567", "+972"])
def test_normalize_rejects_invalid_phone(raw: str) -> None:
    with pytest.raises(ValueError):
        normalize_phone_number(raw)


def test_phone_start_requires_authentication(monkeypatch) -> None:
    configure_settings(monkeypatch)
    response = TestClient(app).post("/auth/phone/start", json={"phone_number": "+972501234567"})
    assert response.status_code == 401


def test_phone_start_calls_provider_with_normalized_phone(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = active_user(phone_number="0501234567")
    fake = FakeSupabase({"users": [user], "user_identities": []})
    provider = FakePhoneProvider()
    patch_clients(monkeypatch, fake, provider)

    response = TestClient(app).post(
        "/auth/phone/start",
        json={"phone_number": "050 123 4567"},
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    assert provider.started == ["+972501234567"]
    assert response.json()["cooldown_seconds"] == 60


def test_phone_verify_records_phone_identity_and_updates_user(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = active_user(phone_number="0501234567")
    fake = FakeSupabase({"users": [user], "user_identities": []})
    provider = FakePhoneProvider()
    patch_clients(monkeypatch, fake, provider)

    response = TestClient(app).post(
        "/auth/phone/verify",
        json={"phone_number": "0501234567", "otp": "123456"},
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    assert response.json()["phone_number"] == "+972501234567"
    assert fake.tables["user_identities"] == [
        {
            "id": "user_identities-1",
            "user_id": user["id"],
            "provider": "phone",
            "provider_subject": "+972501234567",
            "phone_verified_at": fake.tables["user_identities"][0]["phone_verified_at"],
        }
    ]
    assert user["phone_number"] == "+972501234567"
    assert provider.verified == [("+972501234567", "123456")]


def test_phone_verify_rejects_phone_linked_to_another_user(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = active_user(phone_number=None)
    fake = FakeSupabase(
        {
            "users": [user],
            "user_identities": [
                {
                    "id": "identity-1",
                    "user_id": "00000000-0000-0000-0000-000000000999",
                    "provider": "phone",
                    "provider_subject": "+972501234567",
                }
            ],
        }
    )
    provider = FakePhoneProvider()
    patch_clients(monkeypatch, fake, provider)

    response = TestClient(app).post(
        "/auth/phone/verify",
        json={"phone_number": "+972501234567", "otp": "123456"},
        headers=auth_headers(user),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PHONE_VERIFICATION_UNAVAILABLE"
    assert provider.verified == []


def test_phone_verify_rejects_invalid_otp_without_logging_sensitive_values(monkeypatch, caplog) -> None:
    configure_settings(monkeypatch)
    user = active_user(phone_number=None)
    fake = FakeSupabase({"users": [user], "user_identities": []})
    provider = FakePhoneProvider()
    provider.fail_verify = True
    patch_clients(monkeypatch, fake, provider)

    with caplog.at_level("WARNING"):
        response = TestClient(app).post(
            "/auth/phone/verify",
            json={"phone_number": "+972501234567", "otp": "123456"},
            headers=auth_headers(user),
        )

    assert response.status_code == 400
    assert response.json()["code"] == "PHONE_OTP_INVALID"
    assert "123456" not in caplog.text
    assert "+972501234567" not in caplog.text


def test_phone_start_rate_limit_applies_before_provider(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = active_user(phone_number=None)
    fake = FakeSupabase({"users": [user], "user_identities": []})
    provider = FakePhoneProvider()
    patch_clients(monkeypatch, fake, provider)
    client = TestClient(app)

    first = client.post(
        "/auth/phone/start",
        json={"phone_number": "+972501234567"},
        headers=auth_headers(user),
    )
    second = client.post(
        "/auth/phone/start",
        json={"phone_number": "+972501234567"},
        headers=auth_headers(user),
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert provider.started == ["+972501234567"]
