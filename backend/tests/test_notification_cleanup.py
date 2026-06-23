"""ISSUE-032: Notification retention policy cleanup tests.

Verifies POST /admin/notifications/cleanup deletes notifications older
than 90 days and leaves everything else untouched.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_notifications import FakeSupabase


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=90)

ADMIN = {
    "id": "admin-1",
    "email": "admin@example.com",
    "name": "Admin",
    "role": "admin",
    "status": "active",
}
USER = {
    "id": "user-1",
    "email": "user@example.com",
    "name": "User",
    "role": "user",
    "status": "active",
}


def _headers(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def _notification(
    notif_id: str,
    *,
    created_at: str,
    read_at: str | None = None,
    user_id: str = "user-1",
) -> dict[str, Any]:
    return {
        "id": notif_id,
        "user_id": user_id,
        "type": "game_created",
        "title": "Test",
        "body": "Test body",
        "game_id": None,
        "field_id": None,
        "data": None,
        "read_at": read_at,
        "created_at": created_at,
    }


def _setup(
    monkeypatch,
    notifications: list[dict[str, Any]] | None = None,
    notification_preferences: list[dict[str, Any]] | None = None,
    push_tokens: list[dict[str, Any]] | None = None,
) -> tuple[TestClient, FakeSupabase]:
    tables = {
        "users": [deepcopy(ADMIN), deepcopy(USER)],
        "fields": [],
        "games": [],
        "game_players": [],
        "notifications": [deepcopy(n) for n in (notifications or [])],
        "notification_preferences": [deepcopy(p) for p in (notification_preferences or [])],
        "push_tokens": [deepcopy(t) for t in (push_tokens or [])],
    }
    fake = FakeSupabase(tables)

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.api.admin.get_now", lambda: NOW)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: fake)

    return TestClient(app), fake


OLD_DATE = (CUTOFF - timedelta(days=1)).isoformat()
RECENT_DATE = (CUTOFF + timedelta(days=1)).isoformat()
EXACT_CUTOFF_DATE = CUTOFF.isoformat()


# ═══════════════════════════════════════════════════════════════
# 1. Deletes notification older than 90 days
# ═══════════════════════════════════════════════════════════════


def test_deletes_notification_older_than_90_days(monkeypatch):
    old = _notification("old-1", created_at=OLD_DATE)
    client, fake = _setup(monkeypatch, notifications=[old])

    resp = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))

    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted_count"] == 1
    assert data["retention_days"] == 90
    assert len(fake.tables["notifications"]) == 0


# ═══════════════════════════════════════════════════════════════
# 2. Does not delete notification newer than 90 days
# ═══════════════════════════════════════════════════════════════


def test_does_not_delete_recent_notification(monkeypatch):
    recent = _notification("recent-1", created_at=RECENT_DATE)
    client, fake = _setup(monkeypatch, notifications=[recent])

    resp = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 0
    assert len(fake.tables["notifications"]) == 1


# ═══════════════════════════════════════════════════════════════
# 3. Does not delete notification exactly at the 90-day cutoff
# ═══════════════════════════════════════════════════════════════


def test_does_not_delete_notification_at_exact_cutoff(monkeypatch):
    exact = _notification("exact-1", created_at=EXACT_CUTOFF_DATE)
    client, fake = _setup(monkeypatch, notifications=[exact])

    resp = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 0
    assert len(fake.tables["notifications"]) == 1


# ═══════════════════════════════════════════════════════════════
# 4. Deletes old unread notifications
# ═══════════════════════════════════════════════════════════════


def test_deletes_old_unread_notification(monkeypatch):
    old_unread = _notification("old-unread", created_at=OLD_DATE, read_at=None)
    client, fake = _setup(monkeypatch, notifications=[old_unread])

    resp = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 1
    assert len(fake.tables["notifications"]) == 0


# ═══════════════════════════════════════════════════════════════
# 5. Deletes old read notifications
# ═══════════════════════════════════════════════════════════════


def test_deletes_old_read_notification(monkeypatch):
    old_read = _notification("old-read", created_at=OLD_DATE, read_at="2026-03-20T10:00:00+00:00")
    client, fake = _setup(monkeypatch, notifications=[old_read])

    resp = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 1
    assert len(fake.tables["notifications"]) == 0


# ═══════════════════════════════════════════════════════════════
# 6. Does not delete push_tokens
# ═══════════════════════════════════════════════════════════════


def test_does_not_delete_push_tokens(monkeypatch):
    old = _notification("old-1", created_at=OLD_DATE)
    token = {"id": "tok-1", "user_id": "user-1", "token": "fcm-token-abc"}
    client, fake = _setup(monkeypatch, notifications=[old], push_tokens=[token])

    resp = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 1
    assert len(fake.tables["push_tokens"]) == 1
    assert fake.tables["push_tokens"][0]["id"] == "tok-1"


# ═══════════════════════════════════════════════════════════════
# 7. Does not delete notification_preferences
# ═══════════════════════════════════════════════════════════════


def test_does_not_delete_notification_preferences(monkeypatch):
    old = _notification("old-1", created_at=OLD_DATE)
    pref = {
        "id": "pref-1",
        "user_id": "user-1",
        "enabled": True,
        "sport_type": "both",
        "notification_type": "radius",
        "radius_km": 5,
        "lat": 30.0,
        "lng": 34.0,
        "city": None,
        "field_id": None,
    }
    client, fake = _setup(monkeypatch, notifications=[old], notification_preferences=[pref])

    resp = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))

    assert resp.status_code == 200
    assert resp.json()["deleted_count"] == 1
    assert len(fake.tables["notification_preferences"]) == 1
    assert fake.tables["notification_preferences"][0]["id"] == "pref-1"


# ═══════════════════════════════════════════════════════════════
# 8. Non-admin cannot run cleanup
# ═══════════════════════════════════════════════════════════════


def test_non_admin_cannot_run_cleanup(monkeypatch):
    client, _ = _setup(monkeypatch)

    resp = client.post("/admin/notifications/cleanup", headers=_headers(USER))

    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════
# 9. Idempotent: second run deletes 0
# ═══════════════════════════════════════════════════════════════


def test_cleanup_is_idempotent(monkeypatch):
    old = _notification("old-1", created_at=OLD_DATE)
    client, fake = _setup(monkeypatch, notifications=[old])

    resp1 = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))
    assert resp1.status_code == 200
    assert resp1.json()["deleted_count"] == 1
    assert len(fake.tables["notifications"]) == 0

    resp2 = client.post("/admin/notifications/cleanup", headers=_headers(ADMIN))
    assert resp2.status_code == 200
    assert resp2.json()["deleted_count"] == 0
