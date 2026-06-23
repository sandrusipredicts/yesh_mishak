"""ISSUE-038: Notification stress test execution.

Executes the stress test plan from ISSUE-037 using the existing FakeSupabase
test infrastructure. All tests use synthetic data and mocked push delivery.

Scenarios covered:
1. Bulk game_created fan-out (100 / 1,000 recipients)
2. Repeated game creation with dedup verification
3. Unread counter under many notifications
4. Large inbox retrieval
5. Scheduled reminder batch stress
6. Retention cleanup stress
7. Duplicate prevention for all protected event types
"""

from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from app.routers.notifications import (
    create_game_closed_notifications,
    create_game_created_notifications,
    create_game_extended_notifications,
    create_scheduled_game_cancelled_notifications,
    generate_scheduled_game_reminders,
)
from tests.test_notifications import FakeSupabase

NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)
CUTOFF_90 = NOW - timedelta(days=90)

FIELD = {
    "id": "stress-field-001",
    "name": "Stress Court",
    "lat": 31.0,
    "lng": 34.9,
    "city": "stress-city",
    "sport_type": "both",
    "verified": True,
    "approval_status": "approved",
}

ORGANIZER = {
    "id": "stress-organizer",
    "email": "organizer@stress.test",
    "name": "Organizer",
    "role": "user",
    "status": "active",
}

ADMIN = {
    "id": "stress-admin",
    "email": "admin@stress.test",
    "name": "Admin",
    "role": "admin",
    "status": "active",
}


def _make_users(n: int, prefix: str = "stress-user") -> list[dict[str, Any]]:
    return [
        {
            "id": f"{prefix}-{i:04d}",
            "email": f"{prefix}-{i:04d}@stress.test",
            "name": f"User {i}",
            "role": "user",
            "status": "active",
        }
        for i in range(n)
    ]


def _make_radius_prefs(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"pref-{user['id']}",
            "user_id": user["id"],
            "enabled": True,
            "sport_type": "both",
            "notification_type": "radius",
            "radius_km": 50,
            "lat": 31.0,
            "lng": 34.9,
            "city": None,
            "field_id": None,
        }
        for user in users
    ]


def _make_game(game_id: str = "stress-game-001", **overrides: Any) -> dict[str, Any]:
    defaults = {
        "id": game_id,
        "field_id": FIELD["id"],
        "sport_type": "football",
        "created_by": ORGANIZER["id"],
        "status": "open",
        "max_players": 999,
        "players_present": 1,
        "scheduled_at": (NOW + timedelta(minutes=30)).isoformat(),
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
        "scheduled_reminder_processed_at": None,
    }
    defaults.update(overrides)
    return defaults


def _make_notification(
    notif_id: str,
    user_id: str,
    *,
    notif_type: str = "game_created",
    created_at: str | None = None,
    read_at: str | None = None,
    game_id: str | None = "stress-game-001",
) -> dict[str, Any]:
    return {
        "id": notif_id,
        "user_id": user_id,
        "type": notif_type,
        "title": "Stress test",
        "body": "Stress test body",
        "game_id": game_id,
        "field_id": FIELD["id"],
        "data": None,
        "read_at": read_at,
        "created_at": created_at or NOW.isoformat(),
    }


def _setup(
    monkeypatch,
    tables: dict[str, list[dict[str, Any]]],
    mock_push: bool = True,
) -> tuple[TestClient, FakeSupabase]:
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

    if mock_push:
        monkeypatch.setattr(
            "app.routers.notifications.send_fcm_notification",
            lambda token, title, body, data=None: {"ok": True},
        )

    return TestClient(app), fake


def _auth(user: dict[str, Any]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def _count_notifs(fake: FakeSupabase, **filters: Any) -> int:
    rows = fake.tables.get("notifications", [])
    for k, v in filters.items():
        rows = [r for r in rows if r.get(k) == v]
    return len(rows)


def _find_duplicates(fake: FakeSupabase, group_keys: list[str]) -> list[tuple]:
    from collections import Counter
    rows = fake.tables.get("notifications", [])
    keys = [tuple(r.get(k) for k in group_keys) for r in rows]
    return [(k, c) for k, c in Counter(keys).items() if c > 1]


# ═══════════════════════════════════════════════════════════════
# SCENARIO 1: Bulk game_created fan-out
# ═══════════════════════════════════════════════════════════════


class TestBulkGameCreatedFanout:

    @pytest.mark.parametrize("recipient_count", [100, 1000])
    def test_fanout_creates_correct_notification_count(
        self, monkeypatch, recipient_count: int,
    ):
        users = _make_users(recipient_count)
        prefs = _make_radius_prefs(users)
        game = _make_game()

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [],
            "notifications": [],
            "notification_preferences": [deepcopy(p) for p in prefs],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        t0 = time.perf_counter()
        result = create_game_created_notifications(fake, game, FIELD, ORGANIZER["id"])
        elapsed = time.perf_counter() - t0

        assert len(result) == recipient_count
        assert _count_notifs(fake, type="game_created") == recipient_count

        duplicates = _find_duplicates(fake, ["user_id", "type", "game_id"])
        assert duplicates == [], f"Duplicates found: {duplicates}"

        print(f"\n  [STRESS] fan-out {recipient_count} recipients: "
              f"{len(result)} notifications, {elapsed:.3f}s")

    def test_fanout_push_failure_does_not_block_creation(self, monkeypatch):
        users = _make_users(100)
        prefs = _make_radius_prefs(users)
        game = _make_game()
        push_tokens = [
            {"id": f"tok-{u['id']}", "user_id": u["id"], "token": f"fcm-{u['id']}"}
            for u in users
        ]

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [],
            "notifications": [],
            "notification_preferences": [deepcopy(p) for p in prefs],
            "push_tokens": [deepcopy(t) for t in push_tokens],
        }
        _, fake = _setup(monkeypatch, tables, mock_push=False)
        monkeypatch.setattr(
            "app.routers.notifications.send_fcm_notification",
            lambda token, title, body, data=None: (_ for _ in ()).throw(Exception("FCM down")),
        )

        result = create_game_created_notifications(fake, game, FIELD, ORGANIZER["id"])

        assert len(result) == 100
        assert _count_notifs(fake, type="game_created") == 100


# ═══════════════════════════════════════════════════════════════
# SCENARIO 2: Repeated game creation — dedup verification
# ═══════════════════════════════════════════════════════════════


class TestRepeatedGameCreationDedup:

    def test_second_call_for_same_game_creates_no_duplicates(self, monkeypatch):
        users = _make_users(50)
        prefs = _make_radius_prefs(users)
        game = _make_game()

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [],
            "notifications": [],
            "notification_preferences": [deepcopy(p) for p in prefs],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        result1 = create_game_created_notifications(fake, game, FIELD, ORGANIZER["id"])
        result2 = create_game_created_notifications(fake, game, FIELD, ORGANIZER["id"])

        assert len(result1) == 50
        assert len(result2) == 0
        assert _count_notifs(fake, type="game_created") == 50
        assert _find_duplicates(fake, ["user_id", "type", "game_id"]) == []

    def test_multiple_games_each_get_their_own_notifications(self, monkeypatch):
        users = _make_users(50)
        prefs = _make_radius_prefs(users)

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [],
            "notification_preferences": [deepcopy(p) for p in prefs],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        for i in range(10):
            game = _make_game(game_id=f"stress-game-{i:03d}")
            fake.tables["games"].append(deepcopy(game))
            result = create_game_created_notifications(fake, game, FIELD, ORGANIZER["id"])
            assert len(result) == 50

        assert _count_notifs(fake, type="game_created") == 500
        assert _find_duplicates(fake, ["user_id", "type", "game_id"]) == []


# ═══════════════════════════════════════════════════════════════
# SCENARIO 3: Unread counter under many notifications
# ═══════════════════════════════════════════════════════════════


class TestUnreadCounterStress:

    @pytest.mark.parametrize("notification_count", [100, 500, 1000])
    def test_unread_count_correct_for_many_notifications(
        self, monkeypatch, notification_count: int,
    ):
        user = _make_users(1, prefix="stress-unread")[0]
        notifications = [
            _make_notification(
                f"notif-{i:04d}", user["id"],
                game_id=f"game-{i:04d}",
                created_at=(NOW - timedelta(hours=i)).isoformat(),
            )
            for i in range(notification_count)
        ]

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN), deepcopy(user)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in notifications],
            "notification_preferences": [],
            "push_tokens": [],
        }
        client, fake = _setup(monkeypatch, tables)

        t0 = time.perf_counter()
        resp = client.get("/notifications/unread-count", headers=_auth(user))
        elapsed = time.perf_counter() - t0

        assert resp.status_code == 200
        assert resp.json()["unread_count"] == notification_count
        print(f"\n  [STRESS] unread-count with {notification_count} notifications: "
              f"{elapsed:.3f}s")

    def test_mark_single_read_decreases_count(self, monkeypatch):
        user = _make_users(1, prefix="stress-read")[0]
        notifications = [
            _make_notification(f"notif-{i}", user["id"], game_id=f"game-{i}")
            for i in range(100)
        ]
        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN), deepcopy(user)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in notifications],
            "notification_preferences": [],
            "push_tokens": [],
        }
        client, fake = _setup(monkeypatch, tables)

        resp = client.patch(f"/notifications/notif-0/read", headers=_auth(user))
        assert resp.status_code == 200

        resp = client.get("/notifications/unread-count", headers=_auth(user))
        assert resp.json()["unread_count"] == 99

    def test_mark_all_read_sets_count_to_zero(self, monkeypatch):
        user = _make_users(1, prefix="stress-readall")[0]
        notifications = [
            _make_notification(f"notif-{i}", user["id"], game_id=f"game-{i}")
            for i in range(200)
        ]
        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN), deepcopy(user)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in notifications],
            "notification_preferences": [],
            "push_tokens": [],
        }
        client, fake = _setup(monkeypatch, tables)

        resp = client.patch("/notifications/read-all", headers=_auth(user))
        assert resp.status_code == 200

        resp = client.get("/notifications/unread-count", headers=_auth(user))
        assert resp.json()["unread_count"] == 0

    def test_no_cross_user_contamination(self, monkeypatch):
        user_a = {"id": "stress-a", "email": "a@stress.test", "name": "A", "role": "user", "status": "active"}
        user_b = {"id": "stress-b", "email": "b@stress.test", "name": "B", "role": "user", "status": "active"}
        notifs_a = [_make_notification(f"a-{i}", user_a["id"], game_id=f"ga-{i}") for i in range(50)]
        notifs_b = [_make_notification(f"b-{i}", user_b["id"], game_id=f"gb-{i}") for i in range(50)]

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN), deepcopy(user_a), deepcopy(user_b)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in notifs_a + notifs_b],
            "notification_preferences": [],
            "push_tokens": [],
        }
        client, fake = _setup(monkeypatch, tables)

        client.patch("/notifications/read-all", headers=_auth(user_a))

        resp_a = client.get("/notifications/unread-count", headers=_auth(user_a))
        resp_b = client.get("/notifications/unread-count", headers=_auth(user_b))
        assert resp_a.json()["unread_count"] == 0
        assert resp_b.json()["unread_count"] == 50


# ═══════════════════════════════════════════════════════════════
# SCENARIO 4: Large inbox retrieval
# ═══════════════════════════════════════════════════════════════


class TestLargeInboxRetrieval:

    @pytest.mark.parametrize("notification_count", [100, 500, 1000])
    def test_get_notifications_returns_all_for_user(
        self, monkeypatch, notification_count: int,
    ):
        user = _make_users(1, prefix="stress-inbox")[0]
        notifications = [
            _make_notification(
                f"inbox-{i:04d}", user["id"],
                game_id=f"game-{i:04d}",
                created_at=(NOW - timedelta(minutes=i)).isoformat(),
            )
            for i in range(notification_count)
        ]

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN), deepcopy(user)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in notifications],
            "notification_preferences": [],
            "push_tokens": [],
        }
        client, fake = _setup(monkeypatch, tables)

        t0 = time.perf_counter()
        resp = client.get("/notifications", headers=_auth(user))
        elapsed = time.perf_counter() - t0

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == notification_count

        assert data[0]["id"] == "inbox-0000"

        print(f"\n  [STRESS] inbox retrieval {notification_count} rows: "
              f"{elapsed:.3f}s, payload {len(resp.content)} bytes")

    def test_other_users_notifications_not_returned(self, monkeypatch):
        user = _make_users(1, prefix="stress-inbox-own")[0]
        other = _make_users(1, prefix="stress-inbox-other")[0]
        own_notifs = [_make_notification(f"own-{i}", user["id"], game_id=f"g-{i}") for i in range(100)]
        other_notifs = [_make_notification(f"oth-{i}", other["id"], game_id=f"go-{i}") for i in range(100)]

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN), deepcopy(user), deepcopy(other)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in own_notifs + other_notifs],
            "notification_preferences": [],
            "push_tokens": [],
        }
        client, _ = _setup(monkeypatch, tables)

        resp = client.get("/notifications", headers=_auth(user))
        assert resp.status_code == 200
        assert len(resp.json()) == 100
        assert all(n["user_id"] == user["id"] for n in resp.json())


# ═══════════════════════════════════════════════════════════════
# SCENARIO 5: Scheduled reminder batch stress
# ═══════════════════════════════════════════════════════════════


class TestScheduledReminderBatchStress:

    @pytest.mark.parametrize("game_count", [50, 200])
    def test_reminder_batch_creates_correct_notifications(
        self, monkeypatch, game_count: int,
    ):
        participants_per_game = 10
        users = _make_users(participants_per_game, prefix="stress-reminder-user")
        games = []
        game_players = []
        for g in range(game_count):
            game = _make_game(
                game_id=f"reminder-game-{g:04d}",
                scheduled_at=(NOW + timedelta(minutes=30)).isoformat(),
            )
            games.append(game)
            for u in users:
                game_players.append({"game_id": game["id"], "user_id": u["id"]})

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(g) for g in games],
            "game_players": [deepcopy(gp) for gp in game_players],
            "notifications": [],
            "notification_preferences": [],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        t0 = time.perf_counter()
        result = generate_scheduled_game_reminders(supabase=fake, now=NOW)
        elapsed = time.perf_counter() - t0

        expected = game_count * participants_per_game
        assert result["notifications_created"] == expected
        assert len(result["processed_game_ids"]) == game_count
        assert _count_notifs(fake, type="scheduled_game_reminder") == expected
        assert _find_duplicates(fake, ["user_id", "type", "game_id"]) == []

        print(f"\n  [STRESS] reminder batch {game_count} games × "
              f"{participants_per_game} players: {expected} notifications, {elapsed:.3f}s")

    def test_reminder_rerun_is_idempotent(self, monkeypatch):
        users = _make_users(10, prefix="stress-rerun-user")
        game = _make_game(
            game_id="rerun-game",
            scheduled_at=(NOW + timedelta(minutes=30)).isoformat(),
        )
        game_players = [{"game_id": game["id"], "user_id": u["id"]} for u in users]

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [deepcopy(gp) for gp in game_players],
            "notifications": [],
            "notification_preferences": [],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        result1 = generate_scheduled_game_reminders(supabase=fake, now=NOW)
        result2 = generate_scheduled_game_reminders(supabase=fake, now=NOW)

        assert result1["notifications_created"] == 10
        assert result2["notifications_created"] == 0
        assert _count_notifs(fake, type="scheduled_game_reminder") == 10


# ═══════════════════════════════════════════════════════════════
# SCENARIO 6: Retention cleanup stress
# ═══════════════════════════════════════════════════════════════


class TestRetentionCleanupStress:

    @pytest.mark.parametrize(
        "old_count,fresh_count",
        [(1000, 1000), (5000, 5000)],
    )
    def test_cleanup_deletes_only_old_notifications(
        self, monkeypatch, old_count: int, fresh_count: int,
    ):
        old_date = (CUTOFF_90 - timedelta(days=1)).isoformat()
        fresh_date = (CUTOFF_90 + timedelta(days=1)).isoformat()

        old_notifs = [
            _make_notification(f"old-{i}", "stress-user-0000", created_at=old_date, game_id=f"og-{i}")
            for i in range(old_count)
        ]
        fresh_notifs = [
            _make_notification(f"fresh-{i}", "stress-user-0000", created_at=fresh_date, game_id=f"fg-{i}")
            for i in range(fresh_count)
        ]
        prefs = [{"id": "pref-1", "user_id": "stress-user-0000", "enabled": True}]
        tokens = [{"id": "tok-1", "user_id": "stress-user-0000", "token": "fcm-tok"}]

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in old_notifs + fresh_notifs],
            "notification_preferences": [deepcopy(p) for p in prefs],
            "push_tokens": [deepcopy(t) for t in tokens],
        }
        client, fake = _setup(monkeypatch, tables)

        t0 = time.perf_counter()
        resp = client.post("/admin/notifications/cleanup", headers=_auth(ADMIN))
        elapsed = time.perf_counter() - t0

        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_count"] == old_count
        assert data["retention_days"] == 90
        assert len(fake.tables["notifications"]) == fresh_count
        assert len(fake.tables["notification_preferences"]) == 1
        assert len(fake.tables["push_tokens"]) == 1

        print(f"\n  [STRESS] cleanup {old_count} old + {fresh_count} fresh: "
              f"deleted {data['deleted_count']}, {elapsed:.3f}s")

    def test_cleanup_rerun_is_idempotent(self, monkeypatch):
        old_date = (CUTOFF_90 - timedelta(days=1)).isoformat()
        old_notifs = [
            _make_notification(f"old-{i}", "stress-user-0000", created_at=old_date, game_id=f"og-{i}")
            for i in range(100)
        ]
        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN)],
            "fields": [deepcopy(FIELD)],
            "games": [],
            "game_players": [],
            "notifications": [deepcopy(n) for n in old_notifs],
            "notification_preferences": [],
            "push_tokens": [],
        }
        client, fake = _setup(monkeypatch, tables)

        resp1 = client.post("/admin/notifications/cleanup", headers=_auth(ADMIN))
        assert resp1.json()["deleted_count"] == 100

        resp2 = client.post("/admin/notifications/cleanup", headers=_auth(ADMIN))
        assert resp2.json()["deleted_count"] == 0
        assert len(fake.tables["notifications"]) == 0


# ═══════════════════════════════════════════════════════════════
# SCENARIO 7: Duplicate prevention for all protected event types
# ═══════════════════════════════════════════════════════════════


class TestDuplicatePreventionStress:

    def test_game_created_dedup_under_repeated_calls(self, monkeypatch):
        users = _make_users(100)
        prefs = _make_radius_prefs(users)
        game = _make_game()

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [],
            "notifications": [],
            "notification_preferences": [deepcopy(p) for p in prefs],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        for _ in range(5):
            create_game_created_notifications(fake, game, FIELD, ORGANIZER["id"])

        assert _count_notifs(fake, type="game_created") == 100
        assert _find_duplicates(fake, ["user_id", "type", "game_id"]) == []

    def test_game_closed_dedup_under_repeated_calls(self, monkeypatch):
        users = _make_users(20)
        game = _make_game()
        game_players = [{"game_id": game["id"], "user_id": u["id"]} for u in users]

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [deepcopy(gp) for gp in game_players],
            "notifications": [],
            "notification_preferences": [],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        for _ in range(5):
            create_game_closed_notifications(fake, game, ORGANIZER["id"])

        assert _count_notifs(fake, type="game_closed") == 20
        assert _find_duplicates(fake, ["user_id", "type", "game_id"]) == []

    def test_game_extended_dedup_same_end_time(self, monkeypatch):
        users = _make_users(20)
        game = _make_game()
        game_players = [{"game_id": game["id"], "user_id": u["id"]} for u in users]
        new_end = NOW + timedelta(hours=3)

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [deepcopy(gp) for gp in game_players],
            "notifications": [],
            "notification_preferences": [],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        for _ in range(5):
            create_game_extended_notifications(fake, game, new_end, ORGANIZER["id"])

        assert _count_notifs(fake, type="game_extended") == 20
        assert _find_duplicates(fake, ["user_id", "type", "game_id"]) == []

    def test_game_extended_different_end_times_create_separate_notifications(self, monkeypatch):
        users = _make_users(10)
        game = _make_game()
        game_players = [{"game_id": game["id"], "user_id": u["id"]} for u in users]

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [deepcopy(gp) for gp in game_players],
            "notifications": [],
            "notification_preferences": [],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        for i in range(3):
            new_end = NOW + timedelta(hours=3 + i)
            create_game_extended_notifications(fake, game, new_end, ORGANIZER["id"])

        assert _count_notifs(fake, type="game_extended") == 30

    def test_scheduled_game_reminder_dedup_under_repeated_batch(self, monkeypatch):
        users = _make_users(20, prefix="stress-dedup-reminder")
        game = _make_game(
            game_id="dedup-reminder-game",
            scheduled_at=(NOW + timedelta(minutes=30)).isoformat(),
        )
        game_players = [{"game_id": game["id"], "user_id": u["id"]} for u in users]

        tables = {
            "users": [deepcopy(ORGANIZER), deepcopy(ADMIN)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [deepcopy(gp) for gp in game_players],
            "notifications": [],
            "notification_preferences": [],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        for _ in range(5):
            generate_scheduled_game_reminders(supabase=fake, now=NOW)

        assert _count_notifs(fake, type="scheduled_game_reminder") == 20
        assert _find_duplicates(fake, ["user_id", "type", "game_id"]) == []

    def test_scheduled_game_cancelled_known_no_dedup(self, monkeypatch):
        """Documents the known ISSUE-030 gap: scheduled_game_cancelled has no
        application-level or DB-level dedup. Repeated calls DO create duplicates.
        This test documents the behavior; it is not a failure."""
        users = _make_users(10)
        game = _make_game()
        game_players = [{"game_id": game["id"], "user_id": u["id"]} for u in users]

        tables = {
            "users": [deepcopy(ORGANIZER)] + [deepcopy(u) for u in users],
            "fields": [deepcopy(FIELD)],
            "games": [deepcopy(game)],
            "game_players": [deepcopy(gp) for gp in game_players],
            "notifications": [],
            "notification_preferences": [],
            "push_tokens": [],
        }
        _, fake = _setup(monkeypatch, tables)

        create_scheduled_game_cancelled_notifications(fake, game, ORGANIZER["id"], "creator")
        first_count = _count_notifs(fake, type="scheduled_game_cancelled")

        create_scheduled_game_cancelled_notifications(fake, game, ADMIN["id"], "admin")
        second_count = _count_notifs(fake, type="scheduled_game_cancelled")

        assert first_count == 10
        assert second_count > first_count, (
            "ISSUE-030 documents that scheduled_game_cancelled has no dedup — "
            "repeated calls create additional rows. This confirms the known gap."
        )
        duplicates = _find_duplicates(fake, ["user_id", "type", "game_id"])
        print(f"\n  [STRESS] scheduled_game_cancelled dedup gap confirmed: "
              f"{first_count} -> {second_count} rows, "
              f"{len(duplicates)} user(s) with duplicates (ISSUE-030 known)")
