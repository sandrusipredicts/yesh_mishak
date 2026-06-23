"""ISSUE-023: Game creator ownership validation tests.

Verifies that close, extend, and cancel are restricted to the game
creator (organizer). Non-creators get 403. Identity comes from JWT,
not request body. Ownership checks apply to scheduled/future games.
Terminal-state games reject actions regardless of ownership.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(hours=3)


def _user(uid: str, role: str = "user") -> dict[str, Any]:
    return {
        "id": uid,
        "email": f"{uid}@example.com",
        "name": uid,
        "role": role,
        "status": "active",
    }


CREATOR = _user("creator")
OTHER = _user("other-user")

FIELD = {
    "id": "field-1",
    "name": "Test Field",
    "sport_type": "football",
    "verified": True,
    "approval_status": "approved",
    "status": "open",
}


def _headers(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def _game(
    *,
    status: str = "open",
    scheduled_at: datetime | None = None,
) -> dict[str, Any]:
    started = scheduled_at or NOW
    return {
        "id": "game-1",
        "field_id": FIELD["id"],
        "created_by": CREATOR["id"],
        "sport_type": "football",
        "players_present": 2,
        "max_players": 10,
        "status": status,
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "started_at": started.isoformat(),
        "expires_at": (started + timedelta(hours=2)).isoformat(),
    }


def _setup(monkeypatch, game: dict[str, Any]):
    tables = {
        "users": [CREATOR, OTHER],
        "fields": [FIELD.copy()],
        "games": [game.copy()],
        "game_players": [
            {"id": "gp-creator", "game_id": game["id"], "user_id": CREATOR["id"]},
            {"id": "gp-other", "game_id": game["id"], "user_id": OTHER["id"]},
        ],
        "notifications": [],
        "notification_preferences": [],
    }
    fake = FakeSupabaseClient(tables)

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)

    return TestClient(app), tables


# ═══════════════════════════════════════════════════════════════
# 1. Close — ownership enforcement
# ═══════════════════════════════════════════════════════════════


def test_creator_can_close_own_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game())

    response = client.post("/games/game-1/close", headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["status"] == "finished"


def test_non_creator_cannot_close_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game())

    response = client.post("/games/game-1/close", headers=_headers(OTHER))

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the organizer can close game"
    assert tables["games"][0]["status"] == "open"


# ═══════════════════════════════════════════════════════════════
# 2. Extend — ownership enforcement
# ═══════════════════════════════════════════════════════════════


def test_creator_can_extend_own_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game())
    original_expires = tables["games"][0]["expires_at"]

    response = client.post("/games/game-1/extend", headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["expires_at"] != original_expires


def test_non_creator_cannot_extend_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game())
    original_expires = tables["games"][0]["expires_at"]

    response = client.post("/games/game-1/extend", headers=_headers(OTHER))

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the organizer can extend game"
    assert tables["games"][0]["expires_at"] == original_expires


# ═══════════════════════════════════════════════════════════════
# 3. Cancel — ownership enforcement
# ═══════════════════════════════════════════════════════════════


def test_creator_can_cancel_own_scheduled_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game(scheduled_at=FUTURE))

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["status"] == "cancelled"


def test_non_creator_cannot_cancel_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game(scheduled_at=FUTURE))

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(OTHER))

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the organizer can cancel game"
    assert tables["games"][0]["status"] == "open"


# ═══════════════════════════════════════════════════════════════
# 4. Identity from JWT, not request body
# ═══════════════════════════════════════════════════════════════


def test_close_uses_jwt_identity_ignores_body(monkeypatch):
    """Even if request body contains creator id, a non-creator is rejected."""
    client, tables = _setup(monkeypatch, _game())

    response = client.post(
        "/games/game-1/close",
        headers=_headers(OTHER),
        json={"user_id": CREATOR["id"]},
    )

    assert response.status_code == 403
    assert tables["games"][0]["status"] == "open"


def test_extend_uses_jwt_identity_ignores_body(monkeypatch):
    client, tables = _setup(monkeypatch, _game())

    response = client.post(
        "/games/game-1/extend",
        headers=_headers(OTHER),
        json={"user_id": CREATOR["id"]},
    )

    assert response.status_code == 403


def test_cancel_uses_jwt_identity_ignores_body(monkeypatch):
    client, tables = _setup(monkeypatch, _game(scheduled_at=FUTURE))

    response = client.post(
        "/games/game-1/cancel",
        headers=_headers(OTHER),
        json={"user_id": CREATOR["id"], "reason": "test"},
    )

    assert response.status_code == 403
    assert tables["games"][0]["status"] == "open"


# ═══════════════════════════════════════════════════════════════
# 5. Terminal states reject even the creator
# ═══════════════════════════════════════════════════════════════


def test_creator_cannot_close_finished_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game(status="finished"))

    response = client.post("/games/game-1/close", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"


def test_creator_cannot_close_cancelled_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game(status="cancelled"))

    response = client.post("/games/game-1/close", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"


def test_creator_cannot_extend_finished_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game(status="finished"))

    response = client.post("/games/game-1/extend", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"


def test_creator_cannot_extend_cancelled_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game(status="cancelled"))

    response = client.post("/games/game-1/extend", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"


def test_creator_cannot_cancel_finished_game(monkeypatch):
    client, _ = _setup(monkeypatch, _game(status="finished", scheduled_at=FUTURE))

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"


def test_creator_cannot_cancel_already_cancelled_game(monkeypatch):
    client, _ = _setup(monkeypatch, _game(status="cancelled", scheduled_at=FUTURE))

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"


# ═══════════════════════════════════════════════════════════════
# 6. Scheduled/future games preserve ownership rules
# ═══════════════════════════════════════════════════════════════


def test_non_creator_cannot_cancel_scheduled_game(monkeypatch):
    client, tables = _setup(monkeypatch, _game(scheduled_at=FUTURE))

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(OTHER))

    assert response.status_code == 403
    assert tables["games"][0]["status"] == "open"


def test_non_creator_cannot_close_scheduled_game(monkeypatch):
    """Scheduled game that has started (scheduled_at in past) — ownership still enforced."""
    past_scheduled = NOW - timedelta(minutes=30)
    client, tables = _setup(monkeypatch, _game(scheduled_at=past_scheduled))

    response = client.post("/games/game-1/close", headers=_headers(OTHER))

    assert response.status_code == 403
    assert tables["games"][0]["status"] == "open"


def test_non_creator_cannot_extend_scheduled_game(monkeypatch):
    past_scheduled = NOW - timedelta(minutes=30)
    client, tables = _setup(monkeypatch, _game(scheduled_at=past_scheduled))

    response = client.post("/games/game-1/extend", headers=_headers(OTHER))

    assert response.status_code == 403
