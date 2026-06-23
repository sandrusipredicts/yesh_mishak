"""Integration tests: content moderation on API endpoints (ISSUE-053).

Verifies that moderation rejects bad content before DB insertion.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient


USER = {
    "id": "user-1",
    "email": "test@example.com",
    "name": "Test User",
    "role": "user",
    "status": "active",
}

FIELD = {
    "id": "field-1",
    "name": "Test Field",
    "sport_type": "football",
    "verified": True,
    "approval_status": "approved",
    "status": "open",
}


def _headers() -> dict[str, str]:
    token = create_access_token(subject=USER["id"], email=USER["email"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    tables = {
        "users": [USER.copy()],
        "fields": [FIELD.copy()],
        "field_reports": [],
        "games": [],
        "game_players": [],
        "notifications": [],
        "notification_preferences": [],
        "push_tokens": [],
    }
    fake = FakeSupabaseClient(tables)

    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.field_reports.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)

    return TestClient(app), tables


# ═══════════════════════════════════════════════════════════
# Field submission — moderation
# ═══════════════════════════════════════════════════════════


def test_valid_field_submission_passes(setup):
    client, tables = setup
    resp = client.post(
        "/fields/",
        json={
            "name": "מגרש כדורגל חדש",
            "lat": 32.0,
            "lng": 34.8,
            "sport_type": "football",
            "surface_type": "grass",
            "has_nets": True,
            "has_water": False,
        },
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert len(tables["fields"]) == 2


def test_offensive_field_name_rejected_not_inserted(setup):
    client, tables = setup
    resp = client.post(
        "/fields/",
        json={
            "name": "fuck you field",
            "lat": 32.0,
            "lng": 34.8,
            "sport_type": "football",
            "surface_type": "grass",
            "has_nets": True,
            "has_water": False,
        },
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert len(tables["fields"]) == 1
    assert "fuck" not in resp.json().get("detail", "").lower()


def test_fake_field_name_rejected(setup):
    client, tables = setup
    resp = client.post(
        "/fields/",
        json={
            "name": "test",
            "lat": 32.0,
            "lng": 34.8,
            "sport_type": "football",
            "surface_type": "grass",
            "has_nets": True,
            "has_water": False,
        },
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert len(tables["fields"]) == 1


def test_spam_notes_rejected(setup):
    client, tables = setup
    resp = client.post(
        "/fields/",
        json={
            "name": "Good Field",
            "lat": 32.0,
            "lng": 34.8,
            "sport_type": "football",
            "surface_type": "grass",
            "has_nets": True,
            "has_water": False,
            "notes": "!!!!!!!!!!!",
        },
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert len(tables["fields"]) == 1


# ═══════════════════════════════════════════════════════════
# Field report — moderation
# ═══════════════════════════════════════════════════════════


def test_valid_field_report_passes(setup):
    client, tables = setup
    resp = client.post(
        "/field-reports",
        json={
            "field_id": "field-1",
            "category": "field_closed",
            "description": "Gate locked permanently",
        },
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert len(tables["field_reports"]) == 1


def test_offensive_field_report_rejected(setup):
    client, tables = setup
    resp = client.post(
        "/field-reports",
        json={
            "field_id": "field-1",
            "category": "other",
            "description": "fuck you all",
        },
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert len(tables["field_reports"]) == 0


def test_spam_field_report_rejected(setup):
    client, tables = setup
    resp = client.post(
        "/field-reports",
        json={
            "field_id": "field-1",
            "category": "other",
            "description": "aaaaaaaaaaaaa",
        },
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert len(tables["field_reports"]) == 0


# ═══════════════════════════════════════════════════════════
# Existing tests still work — valid content accepted
# ═══════════════════════════════════════════════════════════


def test_field_report_with_none_description_passes(setup):
    client, tables = setup
    resp = client.post(
        "/field-reports",
        json={
            "field_id": "field-1",
            "category": "field_closed",
        },
        headers=_headers(),
    )
    assert resp.status_code == 200
