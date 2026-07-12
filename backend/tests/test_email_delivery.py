import logging

import httpx
import pytest

from app.core.config import get_settings
from app.services.email_delivery import EmailDeliveryError, send_email


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, json_error: bool = False) -> None:
        self.status_code = status_code
        self._payload = {"id": "email-123"} if payload is None else payload
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("invalid json")
        return self._payload


@pytest.fixture(autouse=True)
def configure_email_settings(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("RESEND_API_KEY", "re_secret_value")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.setenv("RESEND_API_URL", "https://api.resend.com/emails")
    monkeypatch.setenv("EMAIL_FROM_ADDRESS", "noreply@yesh-mishak.com")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def call_sender():
    return send_email(
        recipient="user@example.com",
        subject="Verify your email",
        text_body="Open https://example.com/verify?token=secret-token",
        html_body='<a href="https://example.com/verify?token=secret-token">Verify</a>',
    )


def test_resend_request_contract(monkeypatch) -> None:
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return FakeResponse()

    monkeypatch.setattr("app.services.email_delivery.httpx.post", fake_post)
    assert call_sender() == "email-123"
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_secret_value"
    assert captured["json"]["from"] == "noreply@yesh-mishak.com"
    assert captured["json"]["to"] == ["user@example.com"]
    assert captured["json"]["subject"] == "Verify your email"
    assert "secret-token" in captured["json"]["text"]
    assert "secret-token" in captured["json"]["html"]
    timeout = captured["timeout"]
    assert timeout.connect == 5.0
    assert timeout.read == 15.0


def test_sends_with_only_smtp_password(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp_compat_secret")
    get_settings.cache_clear()
    captured = {}
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda _url, **kwargs: captured.update(kwargs) or FakeResponse(),
    )
    assert call_sender() == "email-123"
    assert captured["headers"]["Authorization"] == "Bearer smtp_compat_secret"


def test_sends_with_only_resend_api_key(monkeypatch) -> None:
    captured = {}
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda _url, **kwargs: captured.update(kwargs) or FakeResponse(),
    )
    assert call_sender() == "email-123"
    assert captured["headers"]["Authorization"] == "Bearer re_secret_value"


def test_resend_api_key_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_PASSWORD", "smtp_compat_secret")
    get_settings.cache_clear()
    captured = {}
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda _url, **kwargs: captured.update(kwargs) or FakeResponse(),
    )
    assert call_sender() == "email-123"
    assert captured["headers"]["Authorization"] == "Bearer re_secret_value"


def test_missing_configuration_fails_before_http(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    get_settings.cache_clear()
    called = []
    monkeypatch.setattr("app.services.email_delivery.httpx.post", lambda *_a, **_k: called.append(True))
    with pytest.raises(EmailDeliveryError, match="not_configured"):
        call_sender()
    assert called == []


def test_connection_error_is_normalized(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.resend.com/emails")
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda *_a, **_k: (_ for _ in ()).throw(httpx.ConnectError("dns", request=request)),
    )
    with pytest.raises(EmailDeliveryError, match="network_error"):
        call_sender()


def test_timeout_is_normalized(monkeypatch) -> None:
    request = httpx.Request("POST", "https://api.resend.com/emails")
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda *_a, **_k: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=request)),
    )
    with pytest.raises(EmailDeliveryError, match="timeout"):
        call_sender()


@pytest.mark.parametrize("status_code", [400, 401, 403, 422, 429, 500, 503])
def test_provider_errors_are_normalized_without_body(monkeypatch, status_code, caplog) -> None:
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda *_a, **_k: FakeResponse(status_code, {"message": "provider secret detail"}),
    )
    with caplog.at_level(logging.WARNING), pytest.raises(EmailDeliveryError) as exc_info:
        call_sender()
    assert exc_info.value.reason == "provider_error"
    assert exc_info.value.status_code == status_code
    assert "provider secret detail" not in caplog.text
    assert "re_secret_value" not in caplog.text
    assert "secret-token" not in caplog.text


def test_malformed_json_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda *_a, **_k: FakeResponse(json_error=True),
    )
    with pytest.raises(EmailDeliveryError, match="malformed_response"):
        call_sender()


@pytest.mark.parametrize("payload", [{}, {"id": ""}, {"id": None}, []])
def test_success_response_requires_email_id(monkeypatch, payload) -> None:
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda *_a, **_k: FakeResponse(payload=payload),
    )
    with pytest.raises(EmailDeliveryError, match="missing_email_id"):
        call_sender()


def test_success_log_contains_no_sensitive_values(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda *_a, **_k: FakeResponse(201, {"id": "email-456"}),
    )
    with caplog.at_level(logging.INFO):
        assert call_sender() == "email-456"
    assert "re_secret_value" not in caplog.text
    assert "secret-token" not in caplog.text
    assert "user@example.com" not in caplog.text


def test_fallback_secret_is_not_logged_on_provider_error(monkeypatch, caplog) -> None:
    monkeypatch.delenv("RESEND_API_KEY")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp_compat_secret")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.email_delivery.httpx.post",
        lambda *_a, **_k: FakeResponse(401, {"message": "rejected"}),
    )
    with caplog.at_level(logging.WARNING), pytest.raises(EmailDeliveryError):
        call_sender()
    assert "smtp_compat_secret" not in caplog.text
