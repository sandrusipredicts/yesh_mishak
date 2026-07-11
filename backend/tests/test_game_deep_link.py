from datetime import datetime, timedelta, timezone
from typing import Any

from tests.test_game_close import (
    FakeSupabaseClient,
    configure_test_settings,
    freeze_game_time,
    make_client,
)


def make_game(
    game_id: str = "game-1",
    field_id: str = "field-1",
    status: str = "open",
    **overrides: Any,
) -> dict[str, Any]:
    game = {
        "id": game_id,
        "field_id": field_id,
        "created_by": "creator-1",
        "sport_type": "football",
        "players_present": 4,
        "max_players": 10,
        "status": status,
        "scheduled_at": None,
        "started_at": "2026-07-11T10:00:00+00:00",
        "expires_at": "2026-07-11T12:00:00+00:00",
    }
    game.update(overrides)
    return game


def test_get_existing_open_game_returns_current_state(monkeypatch):
    configure_test_settings(monkeypatch)
    game = make_game(status="open")
    tables = {"games": [game], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)
    freeze_game_time(monkeypatch, datetime(2026, 7, 11, 11, 0, tzinfo=timezone.utc))

    response = client.get("/games/game-1")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "game-1"
    assert body["status"] == "open"
    assert body["field_id"] == "field-1"
    assert body["participants"] == []


def test_get_finished_game_returns_terminal_status_not_error(monkeypatch):
    configure_test_settings(monkeypatch)
    game = make_game(status="finished")
    tables = {"games": [game], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)
    freeze_game_time(monkeypatch, datetime(2026, 7, 11, 11, 0, tzinfo=timezone.utc))

    response = client.get("/games/game-1")

    assert response.status_code == 200
    assert response.json()["status"] == "finished"


def test_get_game_past_expiry_is_lazily_marked_finished(monkeypatch):
    configure_test_settings(monkeypatch)
    game = make_game(status="open")
    tables = {"games": [game], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)
    # expires_at is 2026-07-11T12:00:00Z; ask "now" after that.
    freeze_game_time(monkeypatch, datetime(2026, 7, 11, 13, 0, tzinfo=timezone.utc))

    response = client.get("/games/game-1")

    assert response.status_code == 200
    assert response.json()["status"] == "finished"
    # The lazy transition must also persist to the backing store.
    assert tables["games"][0]["status"] == "finished"


def test_get_cancelled_game_returns_terminal_status(monkeypatch):
    configure_test_settings(monkeypatch)
    game = make_game(status="cancelled", cancelled_at="2026-07-10T09:00:00+00:00")
    tables = {"games": [game], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)

    response = client.get("/games/game-1")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_cancelled_game_with_past_expires_at_stays_cancelled(monkeypatch):
    """Regression: a cancelled game's expires_at (set at creation time) is
    often already in the past by the time someone views it. The lazy expiry
    check must only apply to still-active (open/full) games, or it silently
    overwrites the real terminal status with "finished"."""
    configure_test_settings(monkeypatch)
    game = make_game(
        status="cancelled",
        cancelled_at="2026-07-10T09:00:00+00:00",
        expires_at="2020-01-01T00:00:00+00:00",
    )
    tables = {"games": [game], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)

    response = client.get("/games/game-1")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert tables["games"][0]["status"] == "cancelled"


def test_get_missing_game_returns_404_not_found(monkeypatch):
    configure_test_settings(monkeypatch)
    tables = {"games": [], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)

    response = client.get("/games/game-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "GAME_NOT_FOUND"
    # The response must not leak internal error detail beyond the standard shape.
    assert set(body.keys()) == {"error", "code", "message"}


def test_get_game_with_malformed_id_returns_400_invalid_id(monkeypatch):
    configure_test_settings(monkeypatch)
    tables = {"games": [], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)
    monkeypatch.delenv("ALLOW_TEST_MOCK_IDS", raising=False)

    response = client.get("/games/not-a-uuid")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_ID"


def test_get_game_attaches_participants(monkeypatch):
    configure_test_settings(monkeypatch)
    game = make_game(status="open")
    tables = {
        "games": [game],
        "game_players": [{"id": "gp-1", "game_id": "game-1", "user_id": "user-1"}],
        "users": [{"id": "user-1", "username": "player_one", "name": "Player One"}],
    }
    client = make_client(monkeypatch, tables)
    freeze_game_time(monkeypatch, datetime(2026, 7, 11, 11, 0, tzinfo=timezone.utc))

    response = client.get("/games/game-1")

    assert response.status_code == 200
    participants = response.json()["participants"]
    assert len(participants) == 1
    assert participants[0]["user_id"] == "user-1"
    assert participants[0]["name"] == "player_one"


def test_get_game_does_not_require_authentication(monkeypatch):
    configure_test_settings(monkeypatch)
    game = make_game(status="open")
    tables = {"games": [game], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)
    freeze_game_time(monkeypatch, datetime(2026, 7, 11, 11, 0, tzinfo=timezone.utc))

    # No Authorization header supplied.
    response = client.get("/games/game-1")

    assert response.status_code == 200


def test_existing_active_upcoming_me_routes_still_resolve(monkeypatch):
    """Regression: the new /{game_id} route must not shadow /active, /upcoming, /me."""
    configure_test_settings(monkeypatch)
    tables = {"games": [], "game_players": [], "users": []}
    client = make_client(monkeypatch, tables)

    active_response = client.get("/games/active")
    upcoming_response = client.get("/games/upcoming")
    me_response = client.get("/games/me")

    assert active_response.status_code == 200
    assert upcoming_response.status_code == 200
    # /me requires auth; it must still hit the auth dependency, not become a
    # game_id lookup for the literal string "me".
    assert me_response.status_code in (401, 403)
