from fastapi.testclient import TestClient

from app.main import app
from tests.test_account_linking import (
    FakeSupabaseClient,
    configure_test_settings,
    google_user,
    make_token,
    manual_user,
    patch_all_supabase,
    patch_google_verifier,
)


def _client_for(monkeypatch, fake: FakeSupabaseClient) -> TestClient:
    configure_test_settings(monkeypatch)
    patch_all_supabase(monkeypatch, fake)
    return TestClient(app)


def test_password_user_can_permanently_delete_account(monkeypatch):
    user = manual_user()
    fake = FakeSupabaseClient(users=[user])
    client = _client_for(monkeypatch, fake)

    response = client.request(
        "DELETE",
        "/auth/account",
        headers={"Authorization": f"Bearer {make_token(user)}"},
        json={
            "confirmation": "DELETE",
            "current_password": "CorrectHorse123",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Account deleted successfully"}
    assert fake.tables["users"] == []


def test_wrong_password_does_not_delete_account_or_end_session(monkeypatch):
    user = manual_user()
    fake = FakeSupabaseClient(users=[user])
    client = _client_for(monkeypatch, fake)

    response = client.request(
        "DELETE",
        "/auth/account",
        headers={"Authorization": f"Bearer {make_token(user)}"},
        json={"confirmation": "DELETE", "current_password": "wrong-password"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "REAUTHENTICATION_REQUIRED"
    assert fake.tables["users"] == [user]


def test_google_only_user_can_delete_after_matching_google_reauthentication(monkeypatch):
    user = google_user()
    identity = {
        "id": "identity-1",
        "user_id": user["id"],
        "provider": "google",
        "provider_subject": "google-sub-123",
        "email_at_link": user["email"],
    }
    fake = FakeSupabaseClient(users=[user], identities=[identity])
    client = _client_for(monkeypatch, fake)
    patch_google_verifier(
        monkeypatch,
        {
            "matching-token": {
                "sub": "google-sub-123",
                "email": user["email"],
                "email_verified": True,
            }
        },
    )

    response = client.request(
        "DELETE",
        "/auth/account",
        headers={"Authorization": f"Bearer {make_token(user)}"},
        json={"confirmation": "DELETE", "google_token": "matching-token"},
    )

    assert response.status_code == 200
    assert fake.tables["users"] == []
    assert fake.tables["user_identities"] == []


def test_deletion_requires_exactly_one_reauthentication_method(monkeypatch):
    user = manual_user()
    fake = FakeSupabaseClient(users=[user])
    client = _client_for(monkeypatch, fake)

    response = client.request(
        "DELETE",
        "/auth/account",
        headers={"Authorization": f"Bearer {make_token(user)}"},
        json={"confirmation": "DELETE"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert fake.tables["users"] == [user]
