import pytest
from fastapi.testclient import TestClient
from fastapi.security import HTTPAuthorizationCredentials
from app.main import app
from app.auth.jwt import create_access_token
from app.auth.dependencies import get_current_user
from tests.test_jwt_lifecycle import patch_all_supabase, FakeSupabaseClient

client = TestClient(app)

def test_accept_terms_succeeds_for_existing_user(monkeypatch):
    user_id = "0de2cc4f-6519-4b8c-9260-aeb1172d9bd0"
    fake_client = FakeSupabaseClient(
        users=[{"id": user_id, "email": "test@example.com", "name": "Test User", "terms_accepted_at": None}]
    )
    patch_all_supabase(monkeypatch, fake_client)
    
    token = create_access_token(subject=user_id, email="test@example.com")
    response = client.post("/auth/accept-terms", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 200
    assert response.json()["message"] == "Terms accepted"
    
    # Verify the fake client saw an update
    assert fake_client.users[0].get("terms_accepted_at") is not None


def test_accept_terms_missing_user_returns_401(monkeypatch):
    fake_client = FakeSupabaseClient(users=[])
    patch_all_supabase(monkeypatch, fake_client)
    
    token = create_access_token(subject="nonexistent-id", email="missing@example.com")
    response = client.post("/auth/accept-terms", headers={"Authorization": f"Bearer {token}"})
    
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID"


def test_existing_jwt_subject_resolves_row(monkeypatch):
    """
    Proves an existing JWT subject resolves the matching public.users row.
    The dependency fix changed _fetch_user_row to use get_supabase_service_role_client,
    which bypasses RLS and allows server-authenticated backend identity resolution
    for users who might otherwise be hidden by RLS.
    """
    user_id = "0de2cc4f-6519-4b8c-9260-aeb1172d9bd0"
    fake_client = FakeSupabaseClient(
        users=[{"id": user_id, "email": "test@example.com", "name": "Test User", "role": "user"}]
    )
    patch_all_supabase(monkeypatch, fake_client)
    
    token = create_access_token(subject=user_id, email="test@example.com")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    
    user = get_current_user(creds)
    assert user["id"] == user_id
    assert user["email"] == "test@example.com"
