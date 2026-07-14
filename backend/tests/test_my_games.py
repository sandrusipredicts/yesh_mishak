"""ISSUE-027: User game history / My Games endpoint tests.

Verifies GET /games/me returns four sections (active_games, upcoming_games,
past_games, cancelled_games) filtered to the authenticated user's games only.
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


def _ids(games_list):
    return [g["id"] for g in games_list]


# ═══════════════════════════════════════════════════════════════
# 1. User sees games they created
# ═══════════════════════════════════════════════════════════════


def test_creator_sees_active_game(monkeypatch):
    game = _game("g1", status="open")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert "g1" in _ids(resp.json()["active_games"])


def test_creator_sees_finished_game_in_past(monkeypatch):
    game = _game("g1", status="finished")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert "g1" in _ids(resp.json()["past_games"])


def test_creator_sees_cancelled_game(monkeypatch):
    game = _game("g1", status="cancelled", cancelled_at=NOW)
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert "g1" in _ids(resp.json()["cancelled_games"])


def test_creator_sees_upcoming_game(monkeypatch):
    game = _game("g1", status="open", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert "g1" in _ids(resp.json()["upcoming_games"])


# ═══════════════════════════════════════════════════════════════
# 2. User sees games they joined (participant)
# ═══════════════════════════════════════════════════════════════


def test_participant_sees_active_game(monkeypatch):
    game = _game("g1", created_by="user-b", status="open")
    gp = {"id": "gp-1", "game_id": "g1", "user_id": "user-a"}
    client, _ = _setup(monkeypatch, [game], [gp])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert "g1" in _ids(resp.json()["active_games"])


def test_participant_sees_finished_game(monkeypatch):
    game = _game("g1", created_by="user-b", status="finished")
    gp = {"id": "gp-1", "game_id": "g1", "user_id": "user-a"}
    client, _ = _setup(monkeypatch, [game], [gp])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert "g1" in _ids(resp.json()["past_games"])


# ═══════════════════════════════════════════════════════════════
# 3. User does NOT see unrelated games
# ═══════════════════════════════════════════════════════════════


def test_user_does_not_see_unrelated_game(monkeypatch):
    game = _game("g1", created_by="user-b", status="open")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    data = resp.json()
    all_ids = _ids(data["active_games"]) + _ids(data["upcoming_games"]) + _ids(data["past_games"]) + _ids(data["cancelled_games"])
    assert "g1" not in all_ids


# ═══════════════════════════════════════════════════════════════
# 4. Status-based section placement
# ═══════════════════════════════════════════════════════════════


def test_finished_game_in_past_not_active(monkeypatch):
    game = _game("g1", status="finished")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    assert "g1" in _ids(data["past_games"])
    assert "g1" not in _ids(data["active_games"])
    assert "g1" not in _ids(data["upcoming_games"])
    assert "g1" not in _ids(data["cancelled_games"])


def test_cancelled_game_in_cancelled_not_past(monkeypatch):
    game = _game("g1", status="cancelled", cancelled_at=NOW)
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    assert "g1" in _ids(data["cancelled_games"])
    assert "g1" not in _ids(data["past_games"])


def test_upcoming_game_in_upcoming_not_active(monkeypatch):
    game = _game("g1", status="open", scheduled_at=FUTURE)
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    assert "g1" in _ids(data["upcoming_games"])
    assert "g1" not in _ids(data["active_games"])


def test_full_active_game_appears_in_active(monkeypatch):
    game = _game("g1", status="full")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert "g1" in _ids(resp.json()["active_games"])


# ═══════════════════════════════════════════════════════════════
# 5. Left games are not included
# ═══════════════════════════════════════════════════════════════


def test_left_game_not_visible(monkeypatch):
    """User left (no game_players row), not creator — game is invisible."""
    game = _game("g1", created_by="user-b", status="open")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    all_ids = _ids(data["active_games"]) + _ids(data["upcoming_games"]) + _ids(data["past_games"]) + _ids(data["cancelled_games"])
    assert "g1" not in all_ids


# ═══════════════════════════════════════════════════════════════
# 6. Response includes field/date/status
# ═══════════════════════════════════════════════════════════════


def test_response_includes_field_name_and_metadata(monkeypatch):
    game = _game("g1", status="open")
    client, _ = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    active = resp.json()["active_games"]
    assert len(active) == 1
    g = active[0]
    assert g["field_name"] == "Central Court"
    assert g["status"] == "open"
    assert g["sport_type"] == "football"
    assert "started_at" in g
    assert "expires_at" in g
    assert g["is_creator"] is True
    assert g["players_present"] == 2
    assert g["max_players"] == 10


def test_is_creator_false_for_participant(monkeypatch):
    game = _game("g1", created_by="user-b", status="open")
    gp = {"id": "gp-1", "game_id": "g1", "user_id": "user-a"}
    client, _ = _setup(monkeypatch, [game], [gp])

    resp = client.get("/games/me", headers=_headers(USER_A))

    g = resp.json()["active_games"][0]
    assert g["is_creator"] is False


# ═══════════════════════════════════════════════════════════════
# 7. Unauthenticated request is rejected
# ═══════════════════════════════════════════════════════════════


def test_unauthenticated_request_rejected(monkeypatch):
    client, _ = _setup(monkeypatch, [])

    resp = client.get("/games/me")

    assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════
# 8. Expired game auto-finished
# ═══════════════════════════════════════════════════════════════


def test_expired_game_auto_finished_into_past(monkeypatch):
    expired_at = NOW - timedelta(minutes=5)
    game = _game("g1", status="open", expires_at=expired_at)
    client, tables = _setup(monkeypatch, [game])

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    assert "g1" not in _ids(data["active_games"])
    assert tables["games"][0]["status"] == "finished"


# ═══════════════════════════════════════════════════════════════
# 9. Empty state
# ═══════════════════════════════════════════════════════════════


def test_empty_state_returns_empty_sections(monkeypatch):
    client, _ = _setup(monkeypatch, [])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    data = resp.json()
    assert data["active_games"] == []
    assert data["upcoming_games"] == []
    assert data["past_games"] == []
    assert data["cancelled_games"] == []


# ═══════════════════════════════════════════════════════════════
# 10. No duplication when user is both creator and participant
# ═══════════════════════════════════════════════════════════════


def test_no_duplication_when_creator_and_participant(monkeypatch):
    game = _game("g1", created_by="user-a", status="open")
    gp = {"id": "gp-1", "game_id": "g1", "user_id": "user-a"}
    client, _ = _setup(monkeypatch, [game], [gp])

    resp = client.get("/games/me", headers=_headers(USER_A))

    active = resp.json()["active_games"]
    assert len(active) == 1
    assert active[0]["id"] == "g1"


# ═══════════════════════════════════════════════════════════════
# 11. Mixed statuses across all sections
# ═══════════════════════════════════════════════════════════════


def test_mixed_statuses_in_correct_sections(monkeypatch):
    games = [
        _game("active-1", status="open"),
        _game("full-1", status="full"),
        _game("upcoming-1", status="open", scheduled_at=FUTURE),
        _game("past-1", status="finished"),
        _game("cancelled-1", status="cancelled", cancelled_at=NOW),
    ]
    client, _ = _setup(monkeypatch, games)

    resp = client.get("/games/me", headers=_headers(USER_A))

    data = resp.json()
    assert set(_ids(data["active_games"])) == {"active-1", "full-1"}
    assert _ids(data["upcoming_games"]) == ["upcoming-1"]
    assert _ids(data["past_games"]) == ["past-1"]
    assert _ids(data["cancelled_games"]) == ["cancelled-1"]


# ═══════════════════════════════════════════════════════════════
# 12. Batching / deduplication regression tests (PostgREST fix)
# ═══════════════════════════════════════════════════════════════


def test_many_participant_games_returned_correctly(monkeypatch):
    """Games fetched via batched .in_() are all returned."""
    count = 150
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(count)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(count)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    active = resp.json()["active_games"]
    assert len(active) == count


def test_200_participant_games_all_present(monkeypatch):
    """200 games exercising two full batches of 100."""
    count = 200
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(count)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(count)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == count


def test_101_games_crosses_batch_boundary(monkeypatch):
    """101 games = 1 full batch + 1 partial batch — both must return."""
    count = 101
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(count)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(count)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == count


def test_exactly_100_games_single_batch(monkeypatch):
    """Exactly one full batch — no off-by-one."""
    count = 100
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(count)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(count)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == count


def test_duplicate_game_player_rows_deduplicated(monkeypatch):
    """Multiple game_players rows for the same game produce one result."""
    game = _game("g1", created_by="user-b", status="open")
    gps = [
        {"id": "gp-1", "game_id": "g1", "user_id": "user-a"},
        {"id": "gp-2", "game_id": "g1", "user_id": "user-a"},
        {"id": "gp-3", "game_id": "g1", "user_id": "user-a"},
    ]
    client, _ = _setup(monkeypatch, [game], gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 1
    assert resp.json()["active_games"][0]["id"] == "g1"


def test_many_duplicates_across_batch_boundary(monkeypatch):
    """110 game_player rows pointing to 10 distinct games — dedup keeps count low."""
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(10)]
    gps = []
    for i in range(10):
        for dup in range(11):
            gps.append({"id": f"gp-{i}-{dup}", "game_id": f"g-{i}", "user_id": "user-a"})
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 10


def test_large_list_with_mixed_statuses(monkeypatch):
    """Large participant list with games spread across all four sections."""
    games = []
    gps = []
    for i in range(50):
        games.append(_game(f"active-{i}", created_by="user-b", status="open"))
        gps.append({"id": f"gp-a-{i}", "game_id": f"active-{i}", "user_id": "user-a"})
    for i in range(50):
        games.append(_game(f"upcoming-{i}", created_by="user-b", status="open", scheduled_at=FUTURE))
        gps.append({"id": f"gp-u-{i}", "game_id": f"upcoming-{i}", "user_id": "user-a"})
    for i in range(30):
        games.append(_game(f"past-{i}", created_by="user-b", status="finished"))
        gps.append({"id": f"gp-p-{i}", "game_id": f"past-{i}", "user_id": "user-a"})
    for i in range(20):
        games.append(_game(f"cancel-{i}", created_by="user-b", status="cancelled", cancelled_at=NOW))
        gps.append({"id": f"gp-c-{i}", "game_id": f"cancel-{i}", "user_id": "user-a"})
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["active_games"]) == 50
    assert len(data["upcoming_games"]) == 50
    assert len(data["past_games"]) == 30
    assert len(data["cancelled_games"]) == 20


def test_creator_and_participant_overlap_large_set(monkeypatch):
    """User created 50 games and joined 100 others — no duplicates, all returned."""
    games = []
    gps = []
    for i in range(50):
        games.append(_game(f"created-{i}", created_by="user-a", status="open"))
    for i in range(100):
        games.append(_game(f"joined-{i}", created_by="user-b", status="open"))
        gps.append({"id": f"gp-{i}", "game_id": f"joined-{i}", "user_id": "user-a"})
    for i in range(50):
        gps.append({"id": f"gp-own-{i}", "game_id": f"created-{i}", "user_id": "user-a"})
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 150


def test_zero_participant_games_still_returns_created(monkeypatch):
    """No game_players rows — only created games returned."""
    game = _game("g1", created_by="user-a", status="open")
    client, _ = _setup(monkeypatch, [game], [])

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 1


def test_single_participant_game(monkeypatch):
    """One game_player row — trivial batch of size 1."""
    game = _game("g1", created_by="user-b", status="open")
    gps = [{"id": "gp-1", "game_id": "g1", "user_id": "user-a"}]
    client, _ = _setup(monkeypatch, [game], gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 1


def test_99_games_under_batch_boundary(monkeypatch):
    """99 games — just under the batch size, single batch."""
    count = 99
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(count)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(count)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == count


def test_participant_game_ids_with_none_values_ignored(monkeypatch):
    """game_players rows with null game_id are silently skipped."""
    game = _game("g1", created_by="user-b", status="open")
    gps = [
        {"id": "gp-1", "game_id": "g1", "user_id": "user-a"},
        {"id": "gp-2", "game_id": None, "user_id": "user-a"},
    ]
    client, _ = _setup(monkeypatch, [game], gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 1


def test_participant_game_ids_with_empty_string_ignored(monkeypatch):
    """game_players rows with empty-string game_id are skipped."""
    game = _game("g1", created_by="user-b", status="open")
    gps = [
        {"id": "gp-1", "game_id": "g1", "user_id": "user-a"},
        {"id": "gp-2", "game_id": "", "user_id": "user-a"},
    ]
    client, _ = _setup(monkeypatch, [game], gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 1


def test_large_set_preserves_is_creator_flag(monkeypatch):
    """is_creator is correct across a large mixed set."""
    games = []
    gps = []
    for i in range(60):
        games.append(_game(f"own-{i}", created_by="user-a", status="open"))
    for i in range(60):
        games.append(_game(f"other-{i}", created_by="user-b", status="open"))
        gps.append({"id": f"gp-{i}", "game_id": f"other-{i}", "user_id": "user-a"})
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    active = resp.json()["active_games"]
    own_ids = {f"own-{i}" for i in range(60)}
    for g in active:
        if g["id"] in own_ids:
            assert g["is_creator"] is True, f"{g['id']} should be creator"
        else:
            assert g["is_creator"] is False, f"{g['id']} should not be creator"


def test_large_set_field_name_attached(monkeypatch):
    """field_name is enriched even for batched participant games."""
    count = 110
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(count)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(count)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    for g in resp.json()["active_games"]:
        assert g.get("field_name") == "Central Court"


def test_large_participant_past_games_sorted_descending(monkeypatch):
    """Past games from batched queries are still sorted by expires_at descending."""
    games = []
    gps = []
    for i in range(120):
        exp = NOW - timedelta(hours=i + 1)
        games.append(_game(f"past-{i}", created_by="user-b", status="finished", expires_at=exp))
        gps.append({"id": f"gp-{i}", "game_id": f"past-{i}", "user_id": "user-a"})
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    past = resp.json()["past_games"]
    assert len(past) == 120
    assert past[0]["id"] == "past-0"
    assert past[-1]["id"] == "past-119"


def test_batch_error_propagates_as_500(monkeypatch):
    """If the batched query raises, the endpoint returns 500 — not empty 200."""
    game = _game("g1", created_by="user-b", status="open")
    gps = [{"id": "gp-1", "game_id": "g1", "user_id": "user-a"}]
    client, _ = _setup(monkeypatch, [game], gps)

    def exploding_select(*_args, **_kwargs):
        raise RuntimeError("PostgREST request too large")

    monkeypatch.setattr("app.routers.games._select_with_in_batches", exploding_select)

    error_client = TestClient(app, raise_server_exceptions=False)
    resp = error_client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 500


def test_300_participant_games_three_batches(monkeypatch):
    """300 games = 3 full batches — all present in response."""
    count = 300
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(count)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(count)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == count


def test_duplicate_ids_not_double_counted_in_response(monkeypatch):
    """50 games with 5 duplicate game_players each — response has exactly 50 games."""
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(50)]
    gps = []
    for i in range(50):
        for d in range(5):
            gps.append({"id": f"gp-{i}-{d}", "game_id": f"g-{i}", "user_id": "user-a"})
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    assert len(resp.json()["active_games"]) == 50


def test_response_shape_unchanged_with_batching(monkeypatch):
    """Response still has all four section keys with batched queries."""
    games = [_game(f"g-{i}", created_by="user-b", status="open") for i in range(105)]
    gps = [{"id": f"gp-{i}", "game_id": f"g-{i}", "user_id": "user-a"} for i in range(105)]
    client, _ = _setup(monkeypatch, games, gps)

    resp = client.get("/games/me", headers=_headers(USER_A))

    assert resp.status_code == 200
    data = resp.json()
    assert "active_games" in data
    assert "upcoming_games" in data
    assert "past_games" in data
    assert "cancelled_games" in data
