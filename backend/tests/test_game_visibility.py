"""ISSUE-025: Game visibility rules tests.

Verifies that each endpoint returns only the games allowed by the
visibility spec in docs/product-decisions.md (ISSUE-024).

Spec summary:
- /games/active: open/full, started, not expired. Excludes finished, cancelled, future scheduled.
- /games/upcoming: open/full, scheduled_at > now. Excludes finished, cancelled, started.
- /fields/{id}: active_game (single started game) + upcoming_games (list). No finished/cancelled.
- /admin/games: active = open/full; finished = finished + cancelled.
- Expired games are auto-finished by finish_expired_games.
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


CREATOR = {
    "id": "creator-1",
    "email": "creator@example.com",
    "name": "Creator",
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
}


def _headers(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def _game(
    game_id: str = "game-1",
    *,
    status: str = "open",
    scheduled_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    started = scheduled_at or PAST_START
    return {
        "id": game_id,
        "field_id": FIELD["id"],
        "created_by": CREATOR["id"],
        "sport_type": "football",
        "players_present": 2,
        "max_players": 10,
        "status": status,
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "started_at": started.isoformat(),
        "expires_at": (expires_at or started + timedelta(hours=2)).isoformat(),
    }


def _setup(monkeypatch, games: list[dict[str, Any]]):
    tables = {
        "users": [copy.deepcopy(CREATOR), copy.deepcopy(ADMIN)],
        "fields": [copy.deepcopy(FIELD)],
        "games": [copy.deepcopy(g) for g in games],
        "game_players": [
            {"id": "gp-creator", "game_id": games[0]["id"], "user_id": CREATOR["id"]}
        ] if games else [],
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
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_now", lambda: NOW)

    return TestClient(app), tables


def _game_ids(response_json):
    if isinstance(response_json, list):
        return [g["id"] for g in response_json]
    return []


# ═══════════════════════════════════════════════════════════════
# 1. /games/active visibility
# ═══════════════════════════════════════════════════════════════


def test_active_includes_open_started_game(monkeypatch):
    """Spec: open current game appears in /games/active."""
    game = _game(status="open")
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/active")

    assert response.status_code == 200
    assert "game-1" in _game_ids(response.json())


def test_active_includes_full_started_game(monkeypatch):
    """Spec: full current game appears in /games/active."""
    game = _game(status="full")
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/active")

    assert response.status_code == 200
    assert "game-1" in _game_ids(response.json())


def test_active_excludes_finished_game(monkeypatch):
    """Spec: finished games do not appear in /games/active."""
    game = _game(status="finished")
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []


def test_active_excludes_cancelled_game(monkeypatch):
    """Spec: cancelled games do not appear in /games/active."""
    game = _game(status="cancelled")
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []


def test_active_excludes_future_scheduled_game(monkeypatch):
    """Spec: future scheduled games do not appear in /games/active."""
    game = _game(status="open", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []


def test_active_excludes_expired_game(monkeypatch):
    """Spec: expired games are auto-finished and excluded from /games/active."""
    expired_at = NOW - timedelta(minutes=5)
    game = _game(status="open", expires_at=expired_at)
    client, tables = _setup(monkeypatch, [game])

    response = client.get("/games/active")

    assert response.status_code == 200
    assert response.json() == []
    assert tables["games"][0]["status"] == "finished"


# ═══════════════════════════════════════════════════════════════
# 2. /games/upcoming visibility
# ═══════════════════════════════════════════════════════════════


def test_upcoming_includes_future_open_game(monkeypatch):
    """Spec: future scheduled open game appears in /games/upcoming."""
    game = _game(status="open", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert "game-1" in _game_ids(response.json())


def test_upcoming_includes_future_full_game(monkeypatch):
    """Spec: future scheduled full game appears in /games/upcoming."""
    game = _game(status="full", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert "game-1" in _game_ids(response.json())


def test_upcoming_excludes_finished_game(monkeypatch):
    """Spec: finished games do not appear in /games/upcoming."""
    game = _game(status="finished", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert response.json() == []


def test_upcoming_excludes_cancelled_game(monkeypatch):
    """Spec: cancelled games do not appear in /games/upcoming."""
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert response.json() == []


def test_upcoming_excludes_started_game(monkeypatch):
    """Spec: already-started games (scheduled_at in the past) do not appear in /games/upcoming."""
    past_scheduled = NOW - timedelta(minutes=30)
    game = _game(status="open", scheduled_at=past_scheduled)
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert response.json() == []


def test_upcoming_excludes_instant_game(monkeypatch):
    """Spec: instant (non-scheduled) games do not appear in /games/upcoming."""
    game = _game(status="open")
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/games/upcoming")

    assert response.status_code == 200
    assert response.json() == []


# ═══════════════════════════════════════════════════════════════
# 3. /fields/{id} visibility
# ═══════════════════════════════════════════════════════════════


def test_field_details_shows_active_game_for_started_open(monkeypatch):
    """Spec: field active_game is populated for a started open game."""
    game = _game(status="open")
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    data = response.json()
    assert data["active_game"] is not None
    assert data["active_game"]["id"] == "game-1"


def test_field_details_separates_active_from_upcoming(monkeypatch):
    """Spec: field details separate active_game from upcoming_games."""
    active = _game("active-1", status="open")
    upcoming = _game("upcoming-1", status="open", scheduled_at=FUTURE)
    client, tables = _setup(monkeypatch, [active, upcoming])
    tables["game_players"].append(
        {"id": "gp-upcoming", "game_id": "upcoming-1", "user_id": CREATOR["id"]}
    )

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    data = response.json()
    assert data["active_game"]["id"] == "active-1"
    upcoming_ids = [g["id"] for g in data["upcoming_games"]]
    assert "upcoming-1" in upcoming_ids
    assert "active-1" not in upcoming_ids


def test_field_details_excludes_finished_game(monkeypatch):
    """Spec: finished games do not appear in field active_game or upcoming_games."""
    game = _game(status="finished")
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    data = response.json()
    assert data["active_game"] is None
    assert data["upcoming_games"] == []


def test_field_details_excludes_cancelled_game(monkeypatch):
    """Spec: cancelled games do not appear in field active_game or upcoming_games."""
    game = _game(status="cancelled", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    data = response.json()
    assert data["active_game"] is None
    assert data["upcoming_games"] == []


def test_field_details_excludes_expired_game(monkeypatch):
    """Spec: expired games are auto-finished and excluded from field details."""
    expired_at = NOW - timedelta(minutes=5)
    game = _game(status="open", expires_at=expired_at)
    client, tables = _setup(monkeypatch, [game])

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    data = response.json()
    assert data["active_game"] is None
    assert tables["games"][0]["status"] == "finished"


# ═══════════════════════════════════════════════════════════════
# 4. /admin/games visibility
# ═══════════════════════════════════════════════════════════════


def test_admin_games_active_shows_open_and_full(monkeypatch):
    """Spec: admin active tab includes open and full games."""
    open_game = _game("open-1", status="open")
    full_game = _game("full-1", status="full")
    client, _ = _setup(monkeypatch, [open_game, full_game])

    response = client.get("/admin/games?status=active", headers=_headers(ADMIN))

    assert response.status_code == 200
    active_ids = _game_ids(response.json()["active"])
    assert "open-1" in active_ids
    assert "full-1" in active_ids


def test_admin_games_finished_shows_finished_and_cancelled(monkeypatch):
    """Spec: admin finished tab includes both finished and cancelled games."""
    finished_game = _game("finished-1", status="finished")
    cancelled_game = _game("cancelled-1", status="cancelled", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [finished_game, cancelled_game])

    response = client.get("/admin/games?status=finished", headers=_headers(ADMIN))

    assert response.status_code == 200
    finished_ids = _game_ids(response.json()["finished"])
    assert "finished-1" in finished_ids
    assert "cancelled-1" in finished_ids


def test_admin_games_no_filter_returns_both_sections(monkeypatch):
    """Spec: admin with no filter returns active + finished sections."""
    open_game = _game("open-1", status="open")
    finished_game = _game("finished-1", status="finished")
    client, _ = _setup(monkeypatch, [open_game, finished_game])

    response = client.get("/admin/games", headers=_headers(ADMIN))

    assert response.status_code == 200
    data = response.json()
    assert "active" in data
    assert "finished" in data
    active_ids = _game_ids(data["active"])
    finished_ids = _game_ids(data["finished"])
    assert "open-1" in active_ids
    assert "finished-1" in finished_ids


def test_admin_active_excludes_finished_and_cancelled(monkeypatch):
    """Spec: admin active tab does not include finished or cancelled games."""
    finished_game = _game("finished-1", status="finished")
    cancelled_game = _game("cancelled-1", status="cancelled")
    client, _ = _setup(monkeypatch, [finished_game, cancelled_game])

    response = client.get("/admin/games?status=active", headers=_headers(ADMIN))

    assert response.status_code == 200
    assert response.json()["active"] == []


def test_admin_finished_excludes_open_and_full(monkeypatch):
    """Spec: admin finished tab does not include open or full games."""
    open_game = _game("open-1", status="open")
    full_game = _game("full-1", status="full")
    client, _ = _setup(monkeypatch, [open_game, full_game])

    response = client.get("/admin/games?status=finished", headers=_headers(ADMIN))

    assert response.status_code == 200
    assert response.json()["finished"] == []


# ═══════════════════════════════════════════════════════════════
# 5. Expired game auto-finish consistency
# ═══════════════════════════════════════════════════════════════


def test_expired_game_auto_finished_in_active_endpoint(monkeypatch):
    """Spec: finish_expired_games auto-transitions expired games to finished."""
    expired_at = NOW - timedelta(minutes=1)
    game = _game(status="open", expires_at=expired_at)
    client, tables = _setup(monkeypatch, [game])

    client.get("/games/active")

    assert tables["games"][0]["status"] == "finished"


def test_expired_game_auto_finished_in_upcoming_endpoint(monkeypatch):
    """Spec: finish_expired_games runs on upcoming queries too."""
    expired_at = NOW - timedelta(minutes=1)
    game = _game(status="open", scheduled_at=FUTURE, expires_at=expired_at)
    client, tables = _setup(monkeypatch, [game])

    client.get("/games/upcoming")

    assert tables["games"][0]["status"] == "finished"


# ═══════════════════════════════════════════════════════════════
# 6. Mixed-status comprehensive test
# ═══════════════════════════════════════════════════════════════


def test_mixed_statuses_filtered_correctly_across_endpoints(monkeypatch):
    """All four statuses in one game set — each endpoint shows only what the spec allows."""
    games = [
        _game("open-1", status="open"),
        _game("full-1", status="full"),
        _game("finished-1", status="finished"),
        _game("cancelled-1", status="cancelled"),
        _game("upcoming-1", status="open", scheduled_at=FUTURE),
    ]
    client, tables = _setup(monkeypatch, games)
    for g in games[1:]:
        tables["game_players"].append(
            {"id": f"gp-{g['id']}", "game_id": g["id"], "user_id": CREATOR["id"]}
        )

    active_resp = client.get("/games/active")
    active_ids = _game_ids(active_resp.json())
    assert "open-1" in active_ids
    assert "full-1" in active_ids
    assert "finished-1" not in active_ids
    assert "cancelled-1" not in active_ids
    assert "upcoming-1" not in active_ids

    upcoming_resp = client.get("/games/upcoming")
    upcoming_ids = _game_ids(upcoming_resp.json())
    assert "upcoming-1" in upcoming_ids
    assert "open-1" not in upcoming_ids
    assert "finished-1" not in upcoming_ids
    assert "cancelled-1" not in upcoming_ids

    field_resp = client.get("/fields/field-1")
    field_data = field_resp.json()
    assert field_data["active_game"] is not None
    assert field_data["active_game"]["id"] in ("open-1", "full-1")
    upcoming_field_ids = [g["id"] for g in field_data["upcoming_games"]]
    assert "upcoming-1" in upcoming_field_ids
    assert "finished-1" not in upcoming_field_ids
    assert "cancelled-1" not in upcoming_field_ids

    admin_resp = client.get("/admin/games", headers=_headers(ADMIN))
    admin_data = admin_resp.json()
    admin_active_ids = _game_ids(admin_data["active"])
    admin_finished_ids = _game_ids(admin_data["finished"])
    assert "open-1" in admin_active_ids
    assert "full-1" in admin_active_ids
    assert "upcoming-1" in admin_active_ids
    assert "finished-1" in admin_finished_ids
    assert "cancelled-1" in admin_finished_ids
    assert "finished-1" not in admin_active_ids
    assert "cancelled-1" not in admin_active_ids
