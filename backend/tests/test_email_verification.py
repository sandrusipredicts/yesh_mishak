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
