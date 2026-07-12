from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.main import app


@dataclass
class FakeResponse:
    data: object


class FakeRpcClient:
    def __init__(self, result: str) -> None:
        self.result = result
        self.params = None

    def rpc(self, name: str, params: dict) -> "FakeRpcClient":
        assert name == "verify_email_token"
        self.params = params
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self.result)


class FakeIssueQuery:
    def __init__(self) -> None:
        self.update_payload = None

    def update(self, payload: dict) -> "FakeIssueQuery":
        self.update_payload = payload
        return self

    def eq(self, *_args) -> "FakeIssueQuery":
        return self

    def is_(self, *_args) -> "FakeIssueQuery":
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse([])


class FakeIssueClient:
    def __init__(self) -> None:
        self.query = FakeIssueQuery()

    def rpc(self, name: str, params: dict) -> FakeRpcClient:
        assert name == "prepare_email_verification_token"
        assert params["p_token_hash"]
        return FakeRpcClient("created")

    def table(self, name: str) -> FakeIssueQuery:
        assert name == "email_verification_tokens"
        return self.query


def test_verify_token_hashes_raw_token_before_rpc(monkeypatch) -> None:
    from app.services import email_verification

    fake = FakeRpcClient("verified")
    monkeypatch.setattr(email_verification, "get_supabase_service_role_client", lambda: fake)
    raw = "a" * 48

    assert email_verification.verify_email_token(raw) == "verified"
    assert fake.params["p_token_hash"] != raw
    assert len(fake.params["p_token_hash"]) == 64


def test_verify_email_endpoint_maps_success(monkeypatch) -> None:
    monkeypatch.setattr("app.api.auth.verify_email_token", lambda _: "verified")
    response = TestClient(app).post("/auth/verify-email", json={"token": "a" * 48})
    assert response.status_code == 200
    assert response.json()["status"] == "verified"


def test_verify_email_endpoint_maps_expired(monkeypatch) -> None:
    monkeypatch.setattr("app.api.auth.verify_email_token", lambda _: "expired")
    response = TestClient(app).post("/auth/verify-email", json={"token": "a" * 48})
    assert response.status_code == 200
    assert response.json()["status"] == "expired"


def test_verify_email_endpoint_rejects_missing_token() -> None:
    response = TestClient(app).post("/auth/verify-email", json={})
    assert response.status_code == 422


def test_resend_response_does_not_enumerate_unknown_email(monkeypatch) -> None:
    monkeypatch.setattr("app.api.auth._get_user_by_column", lambda *_: None)
    response = TestClient(app).post(
        "/auth/resend-verification", json={"email": "missing@example.com"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_resend_sends_for_unverified_password_user(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "app.api.auth._get_user_by_column",
        lambda *_: {"id": "user-1", "email_verified": False, "password_hash": "hash"},
    )
    monkeypatch.setattr("app.api.auth.issue_verification_email", lambda uid, email: calls.append((uid, email)))
    response = TestClient(app).post(
        "/auth/resend-verification", json={"email": "USER@example.com"}
    )
    assert response.status_code == 200
    assert calls == [("user-1", "user@example.com")]


def test_resend_skips_verified_user(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "app.api.auth._get_user_by_column",
        lambda *_: {"id": "user-1", "email_verified": True, "password_hash": "hash"},
    )
    monkeypatch.setattr("app.api.auth.issue_verification_email", lambda *args: calls.append(args))
    response = TestClient(app).post(
        "/auth/resend-verification", json={"email": "user@example.com"}
    )
    assert response.status_code == 200
    assert calls == []


def test_resend_cooldown_is_reported_without_token(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.auth._get_user_by_column",
        lambda *_: {"id": "user-1", "email_verified": False, "password_hash": "hash"},
    )
    monkeypatch.setattr(
        "app.api.auth.issue_verification_email",
        lambda *_: (_ for _ in ()).throw(ValueError("VERIFICATION_COOLDOWN")),
    )
    response = TestClient(app).post(
        "/auth/resend-verification", json={"email": "user@example.com"}
    )
    assert response.status_code == 429
    assert "token" not in response.text.lower()


def test_direct_login_is_denied_without_jwt_before_verification(monkeypatch) -> None:
    from app.auth.passwords import hash_password

    user = {
        "id": "user-1",
        "email": "user@example.com",
        "name": "User",
        "username": "user",
        "phone_number": None,
        "password_hash": hash_password("strongpass123"),
        "email_verified": False,
        "email_verified_at": None,
    }
    monkeypatch.setattr("app.api.auth._get_user_by_column", lambda *_: user)
    response = TestClient(app).post(
        "/auth/login", json={"username": "user", "password": "strongpass123"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "EMAIL_NOT_VERIFIED"
    assert "access_token" not in response.text


def test_login_succeeds_after_user_is_verified(monkeypatch) -> None:
    from app.auth.passwords import hash_password

    user = {
        "id": "00000000-0000-0000-0000-000000000777",
        "email": "user@example.com",
        "name": "User",
        "username": "user",
        "phone_number": None,
        "password_hash": hash_password("strongpass123"),
        "email_verified": True,
        "email_verified_at": "2026-07-12T12:00:00+00:00",
    }
    monkeypatch.setattr("app.api.auth._get_user_by_column", lambda *_: user)
    monkeypatch.setattr("app.api.auth._update_last_login", lambda *_args, **_kwargs: None)
    response = TestClient(app).post(
        "/auth/login", json={"username": "user", "password": "strongpass123"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_legacy_user_without_verification_column_still_logs_in(monkeypatch) -> None:
    from app.auth.passwords import hash_password

    legacy_user = {
        "id": "00000000-0000-0000-0000-000000000778",
        "email": "legacy@example.com",
        "name": "Legacy User",
        "username": "legacy",
        "phone_number": None,
        "password_hash": hash_password("strongpass123"),
    }
    monkeypatch.setattr("app.api.auth._get_user_by_column", lambda *_: legacy_user)
    monkeypatch.setattr("app.api.auth._update_last_login", lambda *_args, **_kwargs: None)
    response = TestClient(app).post(
        "/auth/login", json={"username": "legacy", "password": "strongpass123"}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_registration_delivery_failure_keeps_account_recoverable_without_session(monkeypatch) -> None:
    from test_manual_auth import FakeSupabaseClient, configure_test_settings, register_payload
    from app.services.email_verification import VerificationDeliveryError

    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.api.auth.issue_verification_email",
        lambda *_: (_ for _ in ()).throw(VerificationDeliveryError("smtp failed")),
    )
    response = TestClient(app).post("/auth/register", json=register_payload())
    assert response.status_code == 201
    assert response.json()["email_verification_sent"] is False
    assert "access_token" not in response.text
    assert fake_client.users[0]["email_verified"] is False


def test_resend_can_recover_after_registration_delivery_failure(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "app.api.auth._get_user_by_column",
        lambda *_: {"id": "user-1", "email_verified": False, "password_hash": "hash"},
    )
    monkeypatch.setattr("app.api.auth.issue_verification_email", lambda *args: calls.append(args))
    response = TestClient(app).post(
        "/auth/resend-verification", json={"email": "user@example.com"}
    )
    assert response.status_code == 200
    assert calls == [("user-1", "user@example.com")]


def test_resend_delivery_failure_returns_generic_recoverable_response(monkeypatch) -> None:
    from app.services.email_verification import VerificationDeliveryError

    monkeypatch.setattr(
        "app.api.auth._get_user_by_column",
        lambda *_: {"id": "user-1", "email_verified": False, "password_hash": "hash"},
    )
    monkeypatch.setattr(
        "app.api.auth.issue_verification_email",
        lambda *_: (_ for _ in ()).throw(VerificationDeliveryError("smtp failed")),
    )
    response = TestClient(app).post(
        "/auth/resend-verification", json={"email": "user@example.com"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert "smtp" not in response.text.lower()


def test_verification_url_uses_configured_public_app_url(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services import email_verification

    monkeypatch.setenv("PUBLIC_APP_URL", "https://yesh-mishak.com/")
    get_settings.cache_clear()
    try:
        assert email_verification._verification_url("a b") == (
            "https://yesh-mishak.com/verify-email?token=a%20b"
        )
    finally:
        get_settings.cache_clear()


def test_delivery_failure_invalidates_undelivered_token_for_immediate_recovery(monkeypatch) -> None:
    from app.core.config import get_settings
    from app.services import email_verification

    fake = FakeIssueClient()
    monkeypatch.setattr(email_verification, "get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr(
        email_verification,
        "_send_email",
        lambda *_: (_ for _ in ()).throw(email_verification.VerificationDeliveryError("failed")),
    )
    get_settings.cache_clear()
    try:
        try:
            email_verification.issue_verification_email("user-1", "user@example.com")
        except email_verification.VerificationDeliveryError:
            pass
        else:
            raise AssertionError("delivery failure should propagate")
        assert fake.query.update_payload.get("used_at")
    finally:
        get_settings.cache_clear()
