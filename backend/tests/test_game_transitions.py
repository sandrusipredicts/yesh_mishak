"""ISSUE-020: Game lifecycle state transition validation tests.

Validates illegal transitions are blocked and legal transitions work,
per the state model documented in ISSUE-019 (docs/product-decisions.md).

DB statuses: open, full, finished, cancelled.
Derived states: Scheduled (open/full + future scheduled_at), Active (open/full + started).
Actions: Close → finished, Cancel → cancelled, Extend → updates expires_at.
"""

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient, FakeTableQuery


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(hours=3)
PAST = NOW - timedelta(hours=1)

CREATOR = {
    "id": "creator-1",
    "email": "creator@example.com",
    "name": "Creator",
    "role": "user",
    "status": "active",
}
OTHER_USER = {
    "id": "other-1",
    "email": "other@example.com",
    "name": "Other",
    "role": "user",
    "status": "active",
}
ADMIN = {
    "id": "admin-1",
    "email": "admin@example.com",
    "name": "Admin",
    "role": "admin",
    "status": "active",
}
FIELD = {
    "id": "field-1",
    "name": "Central Court",
    "sport_type": "football",
    "verified": True,
    "approval_status": "approved",
    "status": "open",
}


def _token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def _headers(user: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


def _game(
    *,
    status: str = "open",
    scheduled_at: datetime | None = None,
    created_by: str = CREATOR["id"],
    game_id: str = "game-1",
) -> dict[str, Any]:
    started = scheduled_at or NOW
    return {
        "id": game_id,
        "field_id": FIELD["id"],
        "created_by": created_by,
        "sport_type": "football",
        "players_present": 2,
        "max_players": 10,
        "status": status,
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "started_at": started.isoformat(),
        "expires_at": (started + timedelta(hours=2)).isoformat(),
    }


def _setup(monkeypatch, game: dict[str, Any], *, with_membership: bool = False):
    tables = {
        "users": copy.deepcopy([CREATOR, OTHER_USER, ADMIN]),
        "fields": [copy.deepcopy(FIELD)],
        "games": [copy.deepcopy(game)],
        "game_players": [],
        "notifications": [],
        "notification_preferences": [],
    }
    if with_membership:
        tables["game_players"].append(
            {"id": "gp-1", "game_id": game["id"], "user_id": OTHER_USER["id"]}
        )

    fake = FakeSupabaseClient(tables)

    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.api.admin.get_now", lambda: NOW)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: fake)

    return TestClient(app), tables


# ═══════════════════════════════════════════════════════════════
# Illegal transitions from CANCELLED
# ═══════════════════════════════════════════════════════════════


def test_cancelled_game_cannot_be_joined(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/join", headers=_headers(OTHER_USER))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "cancelled"


def test_cancelled_game_cannot_be_extended_by_creator(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/extend", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "cancelled"


def test_cancelled_game_cannot_be_extended_by_admin(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, game)

    response = client.post("/admin/games/game-1/extend", headers=_headers(ADMIN))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"


def test_cancelled_game_cannot_be_closed_by_creator(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/close", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "cancelled"


def test_cancelled_game_cannot_be_closed_by_admin(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/admin/games/game-1/close", headers=_headers(ADMIN))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"
    assert tables["games"][0]["status"] == "cancelled"


def test_cancelled_game_cannot_be_cancelled_again_by_creator(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"
    assert tables["games"][0]["status"] == "cancelled"


def test_cancelled_game_cannot_be_cancelled_again_by_admin(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/admin/games/game-1/cancel", json={}, headers=_headers(ADMIN))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"
    assert tables["games"][0]["status"] == "cancelled"


def test_cancelled_game_cannot_be_left(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game, with_membership=True)

    response = client.post("/games/game-1/leave", headers=_headers(OTHER_USER))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "cancelled"


# ═══════════════════════════════════════════════════════════════
# Illegal transitions from FINISHED
# ═══════════════════════════════════════════════════════════════


def test_finished_game_cannot_be_joined(monkeypatch):
    game = _game(status="finished")
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/join", headers=_headers(OTHER_USER))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "finished"


def test_finished_game_cannot_be_extended_by_creator(monkeypatch):
    game = _game(status="finished")
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/extend", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "finished"


def test_finished_game_cannot_be_extended_by_admin(monkeypatch):
    game = _game(status="finished")
    client, _ = _setup(monkeypatch, game)

    response = client.post("/admin/games/game-1/extend", headers=_headers(ADMIN))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"


def test_finished_game_cannot_be_cancelled_by_creator(monkeypatch):
    game = _game(status="finished", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"
    assert tables["games"][0]["status"] == "finished"


def test_finished_game_cannot_be_cancelled_by_admin(monkeypatch):
    game = _game(status="finished", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/admin/games/game-1/cancel", json={}, headers=_headers(ADMIN))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"
    assert tables["games"][0]["status"] == "finished"


def test_finished_game_cannot_be_closed_again_by_creator(monkeypatch):
    game = _game(status="finished")
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/close", headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "finished"


def test_finished_game_cannot_be_closed_again_by_admin(monkeypatch):
    game = _game(status="finished")
    client, tables = _setup(monkeypatch, game)

    response = client.post("/admin/games/game-1/close", headers=_headers(ADMIN))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"
    assert tables["games"][0]["status"] == "finished"


def test_finished_game_cannot_be_left(monkeypatch):
    game = _game(status="finished")
    client, tables = _setup(monkeypatch, game, with_membership=True)

    response = client.post("/games/game-1/leave", headers=_headers(OTHER_USER))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game already closed"
    assert tables["games"][0]["status"] == "finished"


# ═══════════════════════════════════════════════════════════════
# Visibility: terminal states excluded from active/upcoming
# ═══════════════════════════════════════════════════════════════


def test_cancelled_game_not_in_active_games(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, game)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []


def test_finished_game_not_in_active_games(monkeypatch):
    game = _game(status="finished")
    client, _ = _setup(monkeypatch, game)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []


def test_cancelled_game_not_in_upcoming_games(monkeypatch):
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, game)

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert response.json() == []


def test_finished_game_not_in_upcoming_games(monkeypatch):
    game = _game(status="finished", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, game)

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert response.json() == []


# ═══════════════════════════════════════════════════════════════
# Legal transitions: scheduled → active, extend, close, cancel
# ═══════════════════════════════════════════════════════════════


def test_scheduled_game_appears_in_upcoming(monkeypatch):
    game = _game(status="open", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, game)

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    ids = [g["id"] for g in response.json()]
    assert "game-1" in ids


def test_scheduled_game_not_in_active_until_time_reached(monkeypatch):
    game = _game(status="open", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, game)

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []


def test_scheduled_game_appears_active_when_time_reached(monkeypatch):
    past_scheduled = NOW - timedelta(minutes=30)
    game = _game(status="open", scheduled_at=past_scheduled)
    client, _ = _setup(monkeypatch, game)

    response = client.get("/games/active")

    assert response.status_code == 200
    ids = [g["id"] for g in response.json()]
    assert "game-1" in ids


def test_active_game_can_be_extended(monkeypatch):
    game = _game(status="open")
    client, tables = _setup(monkeypatch, game)
    original_expires = tables["games"][0]["expires_at"]

    response = client.post("/games/game-1/extend", headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["expires_at"] != original_expires
    assert tables["games"][0]["status"] == "open"


def test_active_game_can_be_closed(monkeypatch):
    game = _game(status="open")
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/close", headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["status"] == "finished"


def test_future_scheduled_game_can_be_cancelled(monkeypatch):
    game = _game(status="open", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["status"] == "cancelled"


def test_full_game_can_be_closed(monkeypatch):
    game = _game(status="full")
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/close", headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["status"] == "finished"


def test_full_scheduled_game_can_be_cancelled(monkeypatch):
    game = _game(status="full", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/cancel", json={}, headers=_headers(CREATOR))

    assert response.status_code == 200
    assert tables["games"][0]["status"] == "cancelled"
