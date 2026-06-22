"""ISSUE-028: Organizer activity history tests.

Validates that GET /games/me returns is_creator correctly so the frontend
can filter to show only games the authenticated user organized.
"""

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
FUTURE = NOW + timedelta(hours=3)
PAST_START = NOW - timedelta(hours=1)

USER_A = {
    "id": "user-a",
    "email": "a@example.com",
    "name": "User A",
    "role": "user",
    "status": "active",
}
USER_B = {
    "id": "user-b",
    "email": "b@example.com",
    "name": "User B",
    "role": "user",
    "status": "active",
}
FIELD = {
    "id": "field-1",
    "name": "Central Court",
    "sport_type": "football",
    "verified": True,
    "approval_status": "approved",
}


def _headers(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def _game(
    game_id: str = "game-1",
    *,
    created_by: str = "user-a",
    status: str = "open",
    scheduled_at: datetime | None = None,
    expires_at: datetime | None = None,
    cancelled_at: datetime | None = None,
) -> dict[str, Any]:
    started = scheduled_at or PAST_START
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
        "expires_at": (expires_at or started + timedelta(hours=2)).isoformat(),
        "cancelled_at": cancelled_at.isoformat() if cancelled_at else None,
    }


def _setup(
    monkeypatch,
    games: list[dict[str, Any]],
    game_players: list[dict[str, Any]] | None = None,
):
    tables = {
        "users": [copy.deepcopy(USER_A), copy.deepcopy(USER_B)],
        "fields": [copy.deepcopy(FIELD)],
        "games": [copy.deepcopy(g) for g in games],
        "game_players": [copy.deepcopy(gp) for gp in (game_players or [])],
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


def _all_games(data: dict) -> list[dict]:
    result = []
    for section in ("active_games", "upcoming_games", "past_games", "cancelled_games"):
        result.extend(data.get(section, []))
    return result


# ═══════════════════════════════════════════════════════════════
# 1. Organizer sees created games with is_creator=True
# ═══════════════════════════════════════════════════════════════


def test_organizer_games_have_is_creator_true(monkeypatch):
    games = [
        _game("g1", created_by="user-a", status="open"),
        _game("g2", created_by="user-a", status="finished"),
        _game("g3", created_by="user-a", status="cancelled", cancelled_at=NOW),
        _game("g4", created_by="user-a", status="open", scheduled_at=FUTURE),
    ]
    client, _ = _setup(monkeypatch, games)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    for g in _all_games(resp.json()):
        assert g["is_creator"] is True


# ═══════════════════════════════════════════════════════════════
# 2. Participant games have is_creator=False
# ═══════════════════════════════════════════════════════════════


def test_participant_games_have_is_creator_false(monkeypatch):
    game = _game("g1", created_by="user-b", status="open")
    gp = {"id": "gp-1", "game_id": "g1", "user_id": "user-a"}
    client, _ = _setup(monkeypatch, [game], [gp])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    g = resp.json()["active_games"][0]
    assert g["is_creator"] is False


# ═══════════════════════════════════════════════════════════════
# 3. Organizer games span all statuses
# ═══════════════════════════════════════════════════════════════


def test_organizer_games_across_all_statuses(monkeypatch):
    games = [
        _game("active-1", created_by="user-a", status="open"),
        _game("upcoming-1", created_by="user-a", status="open", scheduled_at=FUTURE),
        _game("past-1", created_by="user-a", status="finished"),
        _game("cancelled-1", created_by="user-a", status="cancelled", cancelled_at=NOW),
    ]
    client, _ = _setup(monkeypatch, games)

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    assert data["active_games"][0]["id"] == "active-1"
    assert data["upcoming_games"][0]["id"] == "upcoming-1"
    assert data["past_games"][0]["id"] == "past-1"
    assert data["cancelled_games"][0]["id"] == "cancelled-1"
    for g in _all_games(data):
        assert g["is_creator"] is True


# ═══════════════════════════════════════════════════════════════
# 4. Organizer does not see other users' games
# ═══════════════════════════════════════════════════════════════


def test_organizer_does_not_see_other_users_games(monkeypatch):
    games = [
        _game("g1", created_by="user-a", status="open"),
        _game("g2", created_by="user-b", status="open"),
    ]
    client, _ = _setup(monkeypatch, games)

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    all_ids = [g["id"] for g in _all_games(data)]
    assert "g1" in all_ids
    assert "g2" not in all_ids


# ═══════════════════════════════════════════════════════════════
# 5. Multi-user isolation
# ═══════════════════════════════════════════════════════════════


def test_multi_user_isolation(monkeypatch):
    games = [
        _game("g1", created_by="user-a", status="open"),
        _game("g2", created_by="user-b", status="open"),
    ]
    client, _ = _setup(monkeypatch, games)

    resp_a = client.get("/games/me", headers=_headers(USER_A))
    resp_b = client.get("/games/me", headers=_headers(USER_B))

    data_a = resp_a.json()
    data_b = resp_b.json()

    a_ids = [g["id"] for g in _all_games(data_a)]
    b_ids = [g["id"] for g in _all_games(data_b)]

    assert "g1" in a_ids and "g2" not in a_ids
    assert "g2" in b_ids and "g1" not in b_ids

    assert all(g["is_creator"] for g in _all_games(data_a))
    assert all(g["is_creator"] for g in _all_games(data_b))


# ═══════════════════════════════════════════════════════════════
# 6. Organizer does not rely on game_players
# ═══════════════════════════════════════════════════════════════


def test_organizer_visible_without_game_players_row(monkeypatch):
    game = _game("g1", created_by="user-a", status="open")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    assert data["active_games"][0]["id"] == "g1"
    assert data["active_games"][0]["is_creator"] is True


# ═══════════════════════════════════════════════════════════════
# 7. Mixed creator and participant games
# ═══════════════════════════════════════════════════════════════


def test_mixed_creator_and_participant_games(monkeypatch):
    games = [
        _game("created-1", created_by="user-a", status="open"),
        _game("joined-1", created_by="user-b", status="open"),
    ]
    gp = {"id": "gp-1", "game_id": "joined-1", "user_id": "user-a"}
    client, _ = _setup(monkeypatch, games, [gp])

    resp = client.get("/games/me", headers=_headers(USER_A))

    active = resp.json()["active_games"]
    by_id = {g["id"]: g for g in active}
    assert by_id["created-1"]["is_creator"] is True
    assert by_id["joined-1"]["is_creator"] is False
