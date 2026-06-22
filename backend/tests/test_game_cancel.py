import copy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient, FakeTableQuery


def configure(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


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
PARTICIPANT = {
    "id": "participant-1",
    "email": "participant@example.com",
    "name": "Participant",
    "role": "user",
    "status": "active",
}
PARTICIPANT_2 = {
    "id": "participant-2",
    "email": "participant2@example.com",
    "name": "Participant Two",
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


def make_scheduled_game(
    game_id: str = "game-1",
    scheduled_at: datetime = FUTURE,
    status: str = "open",
    created_by: str = CREATOR["id"],
    field_id: str = FIELD["id"],
) -> dict[str, Any]:
    return {
        "id": game_id,
        "field_id": field_id,
        "created_by": created_by,
        "sport_type": "football",
        "players_present": 2,
        "max_players": 10,
        "status": status,
        "scheduled_at": scheduled_at.isoformat(),
        "started_at": scheduled_at.isoformat(),
        "expires_at": (scheduled_at + timedelta(hours=2)).isoformat(),
    }


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def auth_headers(user: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user)}"}


def make_tables(game: dict[str, Any], participants: list[dict[str, Any]] | None = None):
    game_players = [
        {"game_id": game["id"], "user_id": game["created_by"]},
    ]
    if participants:
        for p in participants:
            game_players.append({"game_id": game["id"], "user_id": p["id"]})

    all_users = [CREATOR, PARTICIPANT, PARTICIPANT_2, ADMIN]
    return {
        "users": copy.deepcopy(all_users),
        "fields": [copy.deepcopy(FIELD)],
        "games": [copy.deepcopy(game)],
        "game_players": game_players,
        "notifications": [],
        "notification_preferences": [],
    }


def make_client(monkeypatch, tables: dict[str, list[dict[str, Any]]]):
    fake = FakeSupabaseClient(tables)
    configure(monkeypatch)
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
    return TestClient(app), fake


# ── 1. Creator can cancel their own future scheduled game ──


def test_creator_can_cancel_own_future_scheduled_game(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Game cancelled"
    assert data["game"]["status"] == "cancelled"
    assert data["game"]["cancelled_by"] == CREATOR["id"]
    assert data["game"]["cancelled_by_role"] == "creator"
    assert data["game"]["cancelled_at"] is not None


# ── 2. Admin can cancel any future scheduled game ──


def test_admin_can_cancel_any_future_scheduled_game(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/admin/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(ADMIN),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Game cancelled"
    assert data["game"]["status"] == "cancelled"
    assert data["game"]["cancelled_by"] == ADMIN["id"]
    assert data["game"]["cancelled_by_role"] == "admin"


# ── 3. Regular participant cannot cancel ──


def test_participant_cannot_cancel_game(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(PARTICIPANT),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the organizer can cancel game"


# ── 4. Cannot cancel a non-scheduled active game ──


def test_cannot_cancel_non_scheduled_game(monkeypatch):
    game = make_scheduled_game()
    game["scheduled_at"] = None
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only scheduled games can be cancelled"


# ── 5. Cannot cancel after scheduled_at has passed ──


def test_cannot_cancel_after_scheduled_at_passed(monkeypatch):
    game = make_scheduled_game(scheduled_at=PAST)
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot cancel a game after its scheduled start time"


# ── 6. Cancelled game is persisted ──


def test_cancelled_game_persisted(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    client.post(
        f"/games/{game['id']}/cancel",
        json={"reason": "Weather"},
        headers=auth_headers(CREATOR),
    )

    persisted = tables["games"][0]
    assert persisted["status"] == "cancelled"
    assert persisted["cancelled_by"] == CREATOR["id"]
    assert persisted["cancel_reason"] == "Weather"


# ── 7. Cancelled game excluded from active games ──


def test_cancelled_game_excluded_from_active_games(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    response = client.get("/games/active")
    assert response.status_code == 200
    assert len(response.json()) == 0


# ── 8. Cancelled game excluded from upcoming games ──


def test_cancelled_game_excluded_from_upcoming_games(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    response = client.get("/games/upcoming")
    assert response.status_code == 200
    assert len(response.json()) == 0


# ── 9. Cancelled game excluded from field details upcoming games ──


def test_cancelled_game_excluded_from_field_details(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    response = client.get(f"/fields/{FIELD['id']}")
    assert response.status_code == 200
    field_data = response.json()
    assert field_data.get("upcoming_games") == []
    assert field_data.get("active_game") is None


# ── 10. Participants receive scheduled_game_cancelled notification ──


def test_participants_receive_cancelled_notification(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    notifications = tables["notifications"]
    cancelled_notifications = [
        n for n in notifications if n.get("type") == "scheduled_game_cancelled"
    ]
    assert len(cancelled_notifications) == 1
    assert cancelled_notifications[0]["user_id"] == PARTICIPANT["id"]
    assert cancelled_notifications[0]["game_id"] == game["id"]
    assert cancelled_notifications[0]["data"]["cancelled_by_role"] == "creator"


# ── 11. Creator is NOT notified when creator cancels ──


def test_creator_not_notified_when_creator_cancels(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    notifications = tables["notifications"]
    cancelled_notifications = [
        n for n in notifications if n.get("type") == "scheduled_game_cancelled"
    ]
    recipient_ids = [n["user_id"] for n in cancelled_notifications]
    assert CREATOR["id"] not in recipient_ids


# ── 12. Creator IS notified when admin cancels ──


def test_creator_notified_when_admin_cancels(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    client.post(
        f"/admin/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(ADMIN),
    )

    notifications = tables["notifications"]
    cancelled_notifications = [
        n for n in notifications if n.get("type") == "scheduled_game_cancelled"
    ]
    recipient_ids = [n["user_id"] for n in cancelled_notifications]
    assert CREATOR["id"] in recipient_ids
    assert PARTICIPANT["id"] in recipient_ids
    assert len(cancelled_notifications) == 2


# ── Additional edge cases ──


def test_cancellation_with_no_participants_succeeds(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    tables["game_players"] = []
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 200
    assert tables["notifications"] == []


def test_cannot_cancel_already_finished_game(monkeypatch):
    game = make_scheduled_game(status="finished")
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"


def test_cannot_cancel_already_cancelled_game(monkeypatch):
    game = make_scheduled_game(status="cancelled")
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Game is not active"


def test_admin_cancel_non_scheduled_game_rejected(monkeypatch):
    game = make_scheduled_game()
    game["scheduled_at"] = None
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/admin/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(ADMIN),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only scheduled games can be cancelled"


def test_admin_cancel_past_scheduled_game_rejected(monkeypatch):
    game = make_scheduled_game(scheduled_at=PAST)
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/admin/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(ADMIN),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot cancel a game after its scheduled start time"


def test_non_admin_cannot_use_admin_cancel(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/admin/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 403


def test_cancel_reason_is_optional_and_persisted(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={"reason": "Rain expected"},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 200
    assert response.json()["game"]["cancel_reason"] == "Rain expected"


def test_cancel_with_empty_reason_stores_null(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game)
    client, _ = make_client(monkeypatch, tables)

    response = client.post(
        f"/games/{game['id']}/cancel",
        json={"reason": "  "},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 200
    assert response.json()["game"]["cancel_reason"] is None


# ── Regression: service-role client is used for game update ──


def test_creator_cancel_uses_service_role_for_game_update(monkeypatch):
    """The games.update() call must go through service-role, not the regular client."""
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])

    regular_fake = FakeSupabaseClient(copy.deepcopy(tables))
    service_fake = FakeSupabaseClient(tables)

    configure(monkeypatch)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: regular_fake)
    monkeypatch.setattr("app.routers.games.get_supabase_service_role_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: service_fake)

    client = TestClient(app)
    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 200
    assert service_fake.tables["games"][0]["status"] == "cancelled"
    assert regular_fake.tables["games"][0]["status"] == "open"


def test_creator_cancel_notifications_use_service_role(monkeypatch):
    """Notification inserts must go through service-role, not the regular client."""
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])

    regular_tables = copy.deepcopy(tables)
    regular_fake = FakeSupabaseClient(regular_tables)
    service_fake = FakeSupabaseClient(tables)

    configure(monkeypatch)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: regular_fake)
    monkeypatch.setattr("app.routers.games.get_supabase_service_role_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_client", lambda: regular_fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: service_fake)

    client = TestClient(app)
    response = client.post(
        f"/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(CREATOR),
    )

    assert response.status_code == 200
    service_notifications = [
        n for n in tables["notifications"]
        if n.get("type") == "scheduled_game_cancelled"
    ]
    regular_notifications = [
        n for n in regular_tables["notifications"]
        if n.get("type") == "scheduled_game_cancelled"
    ]
    assert len(service_notifications) == 1
    assert len(regular_notifications) == 0


# ── ISSUE-018: Notification copy and multi-participant coverage ──


def test_multiple_participants_all_receive_cancelled_notification(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT, PARTICIPANT_2])
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    notifications = [
        n for n in tables["notifications"]
        if n.get("type") == "scheduled_game_cancelled"
    ]
    recipient_ids = {n["user_id"] for n in notifications}
    assert len(notifications) == 2
    assert PARTICIPANT["id"] in recipient_ids
    assert PARTICIPANT_2["id"] in recipient_ids
    assert CREATOR["id"] not in recipient_ids


def test_cancelled_notification_title_is_correct_hebrew(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    notifications = [
        n for n in tables["notifications"]
        if n.get("type") == "scheduled_game_cancelled"
    ]
    assert len(notifications) == 1
    assert notifications[0]["title"] == "המשחק בוטל"


def test_cancelled_notification_body_creator(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    notifications = [
        n for n in tables["notifications"]
        if n.get("type") == "scheduled_game_cancelled"
    ]
    assert len(notifications) == 1
    assert notifications[0]["body"] == f"המשחק במגרש {FIELD['name']} בוטל על ידי המארגן"


def test_cancelled_notification_body_admin(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT])
    client, _ = make_client(monkeypatch, tables)

    client.post(
        f"/admin/games/{game['id']}/cancel",
        json={},
        headers=auth_headers(ADMIN),
    )

    notifications = [
        n for n in tables["notifications"]
        if n.get("type") == "scheduled_game_cancelled"
    ]
    creator_notification = next(n for n in notifications if n["user_id"] == CREATOR["id"])
    assert creator_notification["body"] == f"המשחק במגרש {FIELD['name']} בוטל על ידי מנהל"


def test_cancelled_notification_includes_game_id_and_field_id(monkeypatch):
    game = make_scheduled_game()
    tables = make_tables(game, participants=[PARTICIPANT, PARTICIPANT_2])
    client, _ = make_client(monkeypatch, tables)

    client.post(f"/games/{game['id']}/cancel", json={}, headers=auth_headers(CREATOR))

    notifications = [
        n for n in tables["notifications"]
        if n.get("type") == "scheduled_game_cancelled"
    ]
    for notification in notifications:
        assert notification["game_id"] == game["id"]
        assert notification["field_id"] == FIELD["id"]
