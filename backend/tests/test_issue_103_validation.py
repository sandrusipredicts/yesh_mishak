import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.main import app
from app.errors import validate_uuid_id
from app.schemas.auth import RegisterRequest
from app.auth.jwt import create_access_token
from test_manual_auth import FakeSupabaseClient, configure_test_settings, register_payload


def auth_headers(user) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def _patch_supabase(monkeypatch, fake_client) -> None:
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.routers.field_reports.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)


# ---- Unit Tests for validate_uuid_id ----

def test_validate_uuid_id_accepts_valid_uuid() -> None:
    valid_uuid = "3a0d5c80-5b12-4d1e-8a2f-90e82c5a610c"
    assert validate_uuid_id(valid_uuid) == valid_uuid


def test_validate_uuid_id_rejects_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_uuid_id("not-a-uuid")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_ID"


def test_validate_uuid_id_mock_rejected_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ALLOW_TEST_MOCK_IDS", raising=False)
    with pytest.raises(HTTPException) as exc_info:
        validate_uuid_id("game-1")
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "INVALID_ID"


def test_validate_uuid_id_mock_accepted_when_flag_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_TEST_MOCK_IDS", "true")
    assert validate_uuid_id("game-1") == "game-1"


# ---- Path Parameter Validation Integration Tests ----

def test_public_get_field_rejects_invalid_uuid(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    response = TestClient(app).get("/fields/not-a-uuid")
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ID"


def test_public_get_field_accepts_valid_uuid(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    
    class FakeFieldsTable:
        def select(self, *args, **kwargs):
            return self
        def eq(self, *args, **kwargs):
            return self
        def execute(self):
            return type("Response", (), {"data": [{"id": "3a0d5c80-5b12-4d1e-8a2f-90e82c5a610c", "name": "Field 1"}]})()

    class FakeClient:
        def table(self, table_name):
            return FakeFieldsTable()

    _patch_supabase(monkeypatch, FakeClient())
    
    # Mock game payloads to return empty to prevent deep dependency calls
    monkeypatch.setattr("app.routers.fields.get_game_payloads_for_fields", lambda ids: ({}, {}))

    response = TestClient(app).get("/fields/3a0d5c80-5b12-4d1e-8a2f-90e82c5a610c")
    assert response.status_code == 200


# ---- Geographic Coordinates Bounds Validation ----

def test_get_fields_rejects_invalid_bounds(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    client = TestClient(app)

    # latitude out of range
    res1 = client.get("/fields?north=91.0&south=30.0&east=34.0&west=32.0")
    assert res1.status_code == 400
    assert "north must be between" in res1.json()["message"]

    # longitude out of range
    res2 = client.get("/fields?north=33.0&south=30.0&east=185.0&west=32.0")
    assert res2.status_code == 400
    assert "east must be between" in res2.json()["message"]

    # north < south
    res3 = client.get("/fields?north=30.0&south=32.0&east=34.0&west=32.0")
    assert res3.status_code == 400
    assert "north must be greater" in res3.json()["message"]

    # east < west
    res4 = client.get("/fields?north=33.0&south=30.0&east=32.0&west=34.0")
    assert res4.status_code == 400
    assert "east must be greater" in res4.json()["message"]


# ---- Availability Checks Validation ----

def test_check_username_rejects_invalid_payloads(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    client = TestClient(app)

    # too short
    res1 = client.post("/auth/check-username", json={"username": "ab"})
    assert res1.status_code == 422

    # invalid characters
    res2 = client.post("/auth/check-username", json={"username": "user@name"})
    assert res2.status_code == 422

    # whitespace only
    res3 = client.post("/auth/check-username", json={"username": "    "})
    assert res3.status_code == 422


def test_check_email_rejects_invalid_payloads(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    client = TestClient(app)

    # invalid format
    res1 = client.post("/auth/check-email", json={"email": "invalid-email"})
    assert res1.status_code == 422

    # whitespace only
    res2 = client.post("/auth/check-email", json={"email": "    "})
    assert res2.status_code == 422


# ---- Phone Number Validation ----

def test_register_rejects_invalid_phone_number_formats(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    client = TestClient(app)

    # alphabetic characters
    res1 = client.post("/auth/register", json=register_payload(phone_number="050-PHONE-NUM"))
    assert res1.status_code == 422

    # too short
    res2 = client.post("/auth/register", json=register_payload(phone_number="12345"))
    assert res2.status_code == 422

    # too long
    res3 = client.post("/auth/register", json=register_payload(phone_number="12345678901234567890123"))
    assert res3.status_code == 422


# ---- Free Text Length Limits ----

def test_cancellation_reason_length_limits(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = {"id": "user-1", "email": "user1@example.com", "role": "user", "status": "active"}
    fake_client = FakeSupabaseClient([user])
    _patch_supabase(monkeypatch, fake_client)
    client = TestClient(app)

    # cancel reason too long (> 500 chars)
    overlong_reason = "a" * 501
    res1 = client.post(
        "/games/3a0d5c80-5b12-4d1e-8a2f-90e82c5a610c/cancel",
        json={"reason": overlong_reason},
        headers=auth_headers(user)
    )
    assert res1.status_code == 422


# ---- Enum Validation ----

def test_field_create_schema_rejects_invalid_sport_type(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    user = {"id": "user-1", "email": "user1@example.com", "role": "user", "status": "active"}
    fake_client = FakeSupabaseClient([user])
    _patch_supabase(monkeypatch, fake_client)
    client = TestClient(app)

    payload = {
        "name": "Invalid Field",
        "lat": 32.0,
        "lng": 34.0,
        "sport_type": "tennis",  # invalid enum
        "surface_type": "grass",
        "has_nets": True,
        "has_water": True,
    }
    # Validate that Pydantic literal blocks it
    res = client.post("/fields/", json=payload, headers=auth_headers(user))
    assert res.status_code == 422


# ---- Database Unique Constraints Conflict Handling ----

def test_registration_database_uniqueness_conflict_handling(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    class FakeConflictSupabase:
        def table(self, table_name: str):
            class Query:
                def __init__(self) -> None:
                    self.is_insert = False
                def select(self, *args, **kwargs):
                    return self
                def eq(self, *args, **kwargs):
                    return self
                def limit(self, *args, **kwargs):
                    return self
                def insert(self, *args, **kwargs):
                    self.is_insert = True
                    return self
                def execute(self):
                    if self.is_insert:
                        # Raise PostgreSQL duplicate key error code 23505
                        raise APIError({"code": "23505", "message": "duplicate key value violates unique constraint 'users_username_key'"})
                    # pre-checks return no existing user so it attempts insertion
                    return type("Response", (), {"data": []})()
            return Query()

    _patch_supabase(monkeypatch, FakeConflictSupabase())

    response = TestClient(app).post("/auth/register", json=register_payload())
    assert response.status_code == 409
    assert response.json()["code"] == "USERNAME_TAKEN"
