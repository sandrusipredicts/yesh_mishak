"""ISSUE-021: Game participant limit validation tests.

Verifies that no game can exceed max_players through the join/leave API,
that status flips between open↔full correctly, and documents the
concurrency limitation of the current implementation.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient, FakeTableQuery


NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def _user(uid: str, role: str = "user") -> dict[str, Any]:
    return {
        "id": uid,
        "email": f"{uid}@example.com",
        "name": uid,
        "role": role,
        "status": "active",
    }


CREATOR = _user("creator")
USER_A = _user("user-a")
USER_B = _user("user-b")
USER_C = _user("user-c")
USER_D = _user("user-d")

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
    players_present: int = 1,
    max_players: int = 3,
    status: str = "open",
) -> dict[str, Any]:
    return {
        "id": "game-1",
        "field_id": FIELD["id"],
        "created_by": CREATOR["id"],
        "sport_type": "football",
        "players_present": players_present,
        "max_players": max_players,
        "status": status,
        "scheduled_at": None,
        "started_at": NOW.isoformat(),
        "expires_at": "2026-06-22T14:00:00+00:00",
    }


def _setup(monkeypatch, game: dict[str, Any], extra_players: list[dict[str, Any]] | None = None):
    game_players = [{"id": "gp-creator", "game_id": game["id"], "user_id": CREATOR["id"]}]
    if extra_players:
        for i, p in enumerate(extra_players):
            game_players.append({"id": f"gp-{i}", "game_id": game["id"], "user_id": p["id"]})

    tables = {
        "users": [CREATOR, USER_A, USER_B, USER_C, USER_D],
        "fields": [FIELD.copy()],
        "games": [game.copy()],
        "game_players": game_players,
        "notifications": [],
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
# 1. Last spot taken — game becomes full
# ═══════════════════════════════════════════════════════════════


def test_last_spot_sets_game_to_full(monkeypatch):
    """max_players=2, creator already in (players_present=1). USER_A takes the last spot."""
    game = _game(players_present=1, max_players=2)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/join", headers=_headers(USER_A))

    assert response.status_code == 200
    updated = response.json()["game"]
    assert updated["players_present"] == 2
    assert updated["status"] == "full"
    assert tables["games"][0]["status"] == "full"


def test_second_to_last_spot_keeps_game_open(monkeypatch):
    """max_players=3, creator already in (players_present=1). USER_A joins → still open."""
    game = _game(players_present=1, max_players=3)
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/join", headers=_headers(USER_A))

    assert response.status_code == 200
    updated = response.json()["game"]
    assert updated["players_present"] == 2
    assert updated["status"] == "open"


# ═══════════════════════════════════════════════════════════════
# 2. Joining a full game is rejected
# ═══════════════════════════════════════════════════════════════


def test_cannot_join_full_game(monkeypatch):
    """max_players=2, already full. USER_B cannot join."""
    game = _game(players_present=2, max_players=2, status="full")
    client, tables = _setup(monkeypatch, game, extra_players=[USER_A])

    response = client.post("/games/game-1/join", headers=_headers(USER_B))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is full"
    assert tables["games"][0]["players_present"] == 2
    assert tables["games"][0]["status"] == "full"


def test_cannot_join_when_players_present_equals_max(monkeypatch):
    """Edge: players_present == max_players but status still says open (inconsistent).
    The join check uses players_present, not status, so it should still block."""
    game = _game(players_present=3, max_players=3, status="open")
    client, tables = _setup(monkeypatch, game, extra_players=[USER_A, USER_B])

    response = client.post("/games/game-1/join", headers=_headers(USER_C))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is full"


# ═══════════════════════════════════════════════════════════════
# 3. Leave a full game → status reopens, another user can join
# ═══════════════════════════════════════════════════════════════


def test_leave_full_game_reopens_spot(monkeypatch):
    """max_players=2, game is full. USER_A leaves → status becomes open, players_present=1."""
    game = _game(players_present=2, max_players=2, status="full")
    client, tables = _setup(monkeypatch, game, extra_players=[USER_A])

    response = client.post("/games/game-1/leave", headers=_headers(USER_A))

    assert response.status_code == 200
    updated = response.json()["game"]
    assert updated["players_present"] == 1
    assert updated["status"] == "open"


def test_leave_then_join_cycle(monkeypatch):
    """Full game → USER_A leaves → USER_B joins → game is full again."""
    game = _game(players_present=2, max_players=2, status="full")
    client, tables = _setup(monkeypatch, game, extra_players=[USER_A])

    leave_response = client.post("/games/game-1/leave", headers=_headers(USER_A))
    assert leave_response.status_code == 200
    assert tables["games"][0]["status"] == "open"
    assert tables["games"][0]["players_present"] == 1

    join_response = client.post("/games/game-1/join", headers=_headers(USER_B))
    assert join_response.status_code == 200
    assert tables["games"][0]["status"] == "full"
    assert tables["games"][0]["players_present"] == 2


# ═══════════════════════════════════════════════════════════════
# 4. Sequential multi-join fills and then blocks
# ═══════════════════════════════════════════════════════════════


def test_sequential_joins_fill_game_then_block(monkeypatch):
    """max_players=3, creator already in. USER_A and USER_B join. USER_C is blocked."""
    game = _game(players_present=1, max_players=3)
    client, tables = _setup(monkeypatch, game)

    r1 = client.post("/games/game-1/join", headers=_headers(USER_A))
    assert r1.status_code == 200
    assert tables["games"][0]["players_present"] == 2
    assert tables["games"][0]["status"] == "open"

    r2 = client.post("/games/game-1/join", headers=_headers(USER_B))
    assert r2.status_code == 200
    assert tables["games"][0]["players_present"] == 3
    assert tables["games"][0]["status"] == "full"

    r3 = client.post("/games/game-1/join", headers=_headers(USER_C))
    assert r3.status_code == 400
    assert r3.json()["detail"] == "Game is full"
    assert tables["games"][0]["players_present"] == 3

    actual_players = [
        gp for gp in tables["game_players"] if gp["game_id"] == "game-1"
    ]
    assert len(actual_players) == 3


# ═══════════════════════════════════════════════════════════════
# 5. Duplicate join is rejected
# ═══════════════════════════════════════════════════════════════


def test_same_user_cannot_join_twice(monkeypatch):
    """USER_A joins, then tries to join again. Second attempt fails."""
    game = _game(players_present=1, max_players=3)
    client, tables = _setup(monkeypatch, game)

    r1 = client.post("/games/game-1/join", headers=_headers(USER_A))
    assert r1.status_code == 200

    r2 = client.post("/games/game-1/join", headers=_headers(USER_A))
    assert r2.status_code == 400
    assert r2.json()["detail"] == "User already joined"
    assert tables["games"][0]["players_present"] == 2


# ═══════════════════════════════════════════════════════════════
# 6. players_present consistency after join/leave cycles
# ═══════════════════════════════════════════════════════════════


def test_players_present_stays_consistent_through_join_leave_cycles(monkeypatch):
    """Join → leave → join cycle: players_present always matches actual game_players count."""
    game = _game(players_present=1, max_players=3)
    client, tables = _setup(monkeypatch, game)

    client.post("/games/game-1/join", headers=_headers(USER_A))
    assert tables["games"][0]["players_present"] == 2
    actual = len([gp for gp in tables["game_players"] if gp["game_id"] == "game-1"])
    assert actual == 2

    client.post("/games/game-1/leave", headers=_headers(USER_A))
    assert tables["games"][0]["players_present"] == 1
    actual = len([gp for gp in tables["game_players"] if gp["game_id"] == "game-1"])
    assert actual == 1

    client.post("/games/game-1/join", headers=_headers(USER_B))
    assert tables["games"][0]["players_present"] == 2
    actual = len([gp for gp in tables["game_players"] if gp["game_id"] == "game-1"])
    assert actual == 2


def test_players_present_never_goes_below_zero(monkeypatch):
    """Edge: players_present=0 and someone leaves (shouldn't happen but code uses max(0,...))."""
    game = _game(players_present=1, max_players=3)
    client, tables = _setup(monkeypatch, game)

    client.post("/games/game-1/join", headers=_headers(USER_A))

    tables["games"][0]["players_present"] = 0

    client.post("/games/game-1/leave", headers=_headers(USER_A))
    assert tables["games"][0]["players_present"] == 0


# ═══════════════════════════════════════════════════════════════
# 7. max_players=1 edge case
# ═══════════════════════════════════════════════════════════════


def test_max_players_one_game_is_full_at_creation(monkeypatch):
    """A game created with players_present=1, max_players=1 is immediately full."""
    game = _game(players_present=1, max_players=1, status="full")
    client, tables = _setup(monkeypatch, game)

    response = client.post("/games/game-1/join", headers=_headers(USER_A))

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is full"


# ═══════════════════════════════════════════════════════════════
# 8. Concurrent join simulation (sequential, documenting limitation)
# ═══════════════════════════════════════════════════════════════


def test_sequential_concurrent_join_simulation(monkeypatch):
    """Simulates the concurrent join scenario sequentially.

    Real-world race condition: two users read the same players_present,
    both pass the check, both insert. The FakeSupabaseClient is synchronous,
    so requests execute serially — the second request sees the updated
    players_present from the first and is correctly blocked.

    This test proves the app-level logic is correct for sequential execution.
    True concurrent protection requires a DB-level mechanism (e.g. SELECT
    FOR UPDATE, a Postgres function, or a CHECK constraint on
    players_present <= max_players). The unique(game_id, user_id) constraint
    on game_players prevents the same user from double-joining but does NOT
    prevent two different users from racing past the players_present check.

    See ISSUE-021 notes for the concurrency gap analysis.
    """
    game = _game(players_present=1, max_players=2)
    client, tables = _setup(monkeypatch, game)

    r1 = client.post("/games/game-1/join", headers=_headers(USER_A))
    assert r1.status_code == 200
    assert tables["games"][0]["players_present"] == 2
    assert tables["games"][0]["status"] == "full"

    r2 = client.post("/games/game-1/join", headers=_headers(USER_B))
    assert r2.status_code == 400
    assert r2.json()["detail"] == "Game is full"

    assert tables["games"][0]["players_present"] == 2
    actual_players = [gp for gp in tables["game_players"] if gp["game_id"] == "game-1"]
    assert len(actual_players) == 2
    assert tables["games"][0]["players_present"] <= tables["games"][0]["max_players"]


# ═══════════════════════════════════════════════════════════════
# 9. ISSUE-022: Duplicate join protection
# ═══════════════════════════════════════════════════════════════


def test_duplicate_join_does_not_increment_players_present(monkeypatch):
    """Second join by the same user must not change players_present or game_players."""
    game = _game(players_present=1, max_players=5)
    client, tables = _setup(monkeypatch, game)

    r1 = client.post("/games/game-1/join", headers=_headers(USER_A))
    assert r1.status_code == 200
    assert tables["games"][0]["players_present"] == 2

    r2 = client.post("/games/game-1/join", headers=_headers(USER_A))
    assert r2.status_code == 400
    assert r2.json()["detail"] == "User already joined"
    assert tables["games"][0]["players_present"] == 2

    actual_players = [gp for gp in tables["game_players"] if gp["game_id"] == "game-1"]
    assert len(actual_players) == 2  # creator + USER_A, no duplicate


def test_no_duplicate_game_players_rows_after_duplicate_join(monkeypatch):
    """game_players must contain exactly one row per (game_id, user_id) after a rejected duplicate."""
    game = _game(players_present=1, max_players=5)
    client, tables = _setup(monkeypatch, game)

    client.post("/games/game-1/join", headers=_headers(USER_A))
    client.post("/games/game-1/join", headers=_headers(USER_A))
    client.post("/games/game-1/join", headers=_headers(USER_A))

    user_a_rows = [
        gp for gp in tables["game_players"]
        if gp["game_id"] == "game-1" and gp["user_id"] == USER_A["id"]
    ]
    assert len(user_a_rows) == 1


def test_leave_then_rejoin_produces_single_game_players_row(monkeypatch):
    """After join → leave → rejoin, exactly one game_players row exists for that user."""
    game = _game(players_present=1, max_players=3)
    client, tables = _setup(monkeypatch, game)

    client.post("/games/game-1/join", headers=_headers(USER_A))
    assert len([gp for gp in tables["game_players"] if gp["user_id"] == USER_A["id"]]) == 1

    client.post("/games/game-1/leave", headers=_headers(USER_A))
    assert len([gp for gp in tables["game_players"] if gp["user_id"] == USER_A["id"]]) == 0

    client.post("/games/game-1/join", headers=_headers(USER_A))
    user_a_rows = [
        gp for gp in tables["game_players"]
        if gp["game_id"] == "game-1" and gp["user_id"] == USER_A["id"]
    ]
    assert len(user_a_rows) == 1
    assert tables["games"][0]["players_present"] == 2


def test_same_user_concurrent_join_simulation(monkeypatch):
    """Same user joining twice in rapid succession — second must fail without side effects.

    The FakeRpcQuery serializes calls, so this tests that the RPC's
    duplicate check correctly blocks the second attempt and leaves
    game state unchanged.
    """
    game = _game(players_present=1, max_players=5)
    client, tables = _setup(monkeypatch, game)

    r1 = client.post("/games/game-1/join", headers=_headers(USER_A))
    r2 = client.post("/games/game-1/join", headers=_headers(USER_A))

    assert r1.status_code == 200
    assert r2.status_code == 400
    assert r2.json()["detail"] == "User already joined"

    assert tables["games"][0]["players_present"] == 2
    all_user_a = [
        gp for gp in tables["game_players"]
        if gp["game_id"] == "game-1" and gp["user_id"] == USER_A["id"]
    ]
    assert len(all_user_a) == 1
