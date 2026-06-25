from typing import Any

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.auth.passwords import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    validate_password,
)
from app.core.config import get_settings
from app.main import app

from test_manual_auth import FakeSupabaseClient, configure_test_settings, register_payload


def _patch_supabase(monkeypatch, fake_client: FakeSupabaseClient) -> None:
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)


# ---- Unit tests for validate_password ----


def test_validate_password_accepts_minimum_length() -> None:
    assert validate_password("a" * PASSWORD_MIN_LENGTH) == []


def test_validate_password_accepts_above_minimum() -> None:
    assert validate_password("a" * (PASSWORD_MIN_LENGTH + 1)) == []


def test_validate_password_rejects_below_minimum() -> None:
    errors = validate_password("a" * (PASSWORD_MIN_LENGTH - 1))
    assert len(errors) == 1
    assert "at least" in errors[0]


def test_validate_password_rejects_empty() -> None:
    errors = validate_password("")
    assert len(errors) == 1
    assert "at least" in errors[0]


def test_validate_password_rejects_single_char() -> None:
    errors = validate_password("x")
    assert len(errors) == 1


def test_validate_password_accepts_maximum_length() -> None:
    assert validate_password("a" * PASSWORD_MAX_LENGTH) == []


def test_validate_password_rejects_above_maximum() -> None:
    errors = validate_password("a" * (PASSWORD_MAX_LENGTH + 1))
    assert len(errors) == 1
    assert "at most" in errors[0]


def test_validate_password_accepts_whitespace_passphrase() -> None:
    assert validate_password("correct horse battery staple") == []


def test_validate_password_accepts_spaces_only_if_long_enough() -> None:
    assert validate_password(" " * PASSWORD_MIN_LENGTH) == []


def test_validate_password_accepts_unicode() -> None:
    assert validate_password("סיסמאבגד") == []


def test_validate_password_constants() -> None:
    assert PASSWORD_MIN_LENGTH == 8
    assert PASSWORD_MAX_LENGTH == 128


# ---- Integration tests: registration endpoint ----


def test_register_rejects_short_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    short_pw = "a" * (PASSWORD_MIN_LENGTH - 1)
    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password=short_pw, password_confirm=short_pw),
    )

    assert response.status_code == 422


def test_register_rejects_empty_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password="", password_confirm=""),
    )

    assert response.status_code == 422


def test_register_accepts_minimum_length_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    exact_min = "a" * PASSWORD_MIN_LENGTH
    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password=exact_min, password_confirm=exact_min),
    )

    assert response.status_code == 201


def test_register_accepts_maximum_length_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    exact_max = "b" * PASSWORD_MAX_LENGTH
    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password=exact_max, password_confirm=exact_max),
    )

    assert response.status_code == 201


def test_register_rejects_over_maximum_length_password(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    over_max = "c" * (PASSWORD_MAX_LENGTH + 1)
    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password=over_max, password_confirm=over_max),
    )

    assert response.status_code == 422


def test_register_accepts_passphrase_with_spaces(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    passphrase = "correct horse battery staple"
    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password=passphrase, password_confirm=passphrase),
    )

    assert response.status_code == 201


def test_register_does_not_return_password_in_response(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    response = TestClient(app).post("/auth/register", json=register_payload())

    assert response.status_code == 201
    body = response.json()
    body_text = str(body)
    assert "strongpass123" not in body_text
    assert "password_hash" not in body_text


def test_register_does_not_log_password(monkeypatch, caplog) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient())

    password = "my_secret_password_42"
    response = TestClient(app).post(
        "/auth/register",
        json=register_payload(password=password, password_confirm=password),
    )

    assert response.status_code == 201
    assert password not in caplog.text


def test_login_still_works_after_validation_changes(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    _patch_supabase(monkeypatch, fake_client)

    TestClient(app).post("/auth/register", json=register_payload())

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "manual-user", "password": "strongpass123"},
    )

    assert response.status_code == 200
    assert response.json()["user"]["username"] == "manual-user"


def test_login_does_not_enforce_min_length_on_login_attempt(monkeypatch) -> None:
    """Login should not reject short passwords at the schema level —
    it should just fail auth. This prevents leaking whether a user exists."""
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    _patch_supabase(monkeypatch, fake_client)

    response = TestClient(app).post(
        "/auth/login",
        json={"username": "nobody", "password": "short"},
    )

    assert response.status_code == 401


def test_google_login_unaffected(monkeypatch) -> None:
    """Google login doesn't use passwords — verify schema is unchanged."""
    configure_test_settings(monkeypatch)

    def reject_google_token(token: str, attempt_id: str = "unknown") -> None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    monkeypatch.setattr("app.api.auth.verify_google_token", reject_google_token)

    response = TestClient(app).post(
        "/auth/google",
        json={"token": "not-a-real-token"},
    )

    assert response.status_code != 422
