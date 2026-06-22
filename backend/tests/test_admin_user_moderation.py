from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_admin_me import FakeSupabaseClient


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def configure(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


ADMIN_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "admin@example.com",
    "name": "Admin User",
    "role": "admin",
    "status": "active",
}
REGULAR_USER = {
    "id": "00000000-0000-0000-0000-000000000002",
    "email": "user@example.com",
    "name": "Regular User",
    "role": "user",
    "status": "active",
}
ANOTHER_ADMIN = {
    "id": "00000000-0000-0000-0000-000000000003",
    "email": "admin2@example.com",
    "name": "Admin Two",
    "role": "admin",
    "status": "active",
}
BANNED_USER = {
    "id": "00000000-0000-0000-0000-000000000004",
    "email": "banned@example.com",
    "name": "Banned User",
    "role": "user",
    "status": "banned",
    "restriction_reason": "Spam",
    "restricted_at": "2026-06-20T10:00:00+00:00",
    "restricted_by": ADMIN_USER["id"],
}
SUSPENDED_USER = {
    "id": "00000000-0000-0000-0000-000000000005",
    "email": "suspended@example.com",
    "name": "Suspended User",
    "role": "user",
    "status": "suspended",
    "restriction_reason": "Abuse",
    "restricted_at": "2026-06-20T10:00:00+00:00",
    "restricted_by": ADMIN_USER["id"],
}


import copy


def make_client(monkeypatch, users=None):
    configure(monkeypatch)
    all_users = copy.deepcopy(users or [ADMIN_USER, REGULAR_USER, ANOTHER_ADMIN, BANNED_USER, SUSPENDED_USER])
    fake = FakeSupabaseClient(
        {},
        tables={
            "users": all_users,
            "user_moderation_audit": [],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: fake)
    return TestClient(app), fake


# ── admin can ban regular user ──


def test_admin_can_ban_regular_user(monkeypatch):
    client, fake = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/ban",
        json={"reason": "Spamming"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["status"] == "banned"
    assert data["user"]["restriction_reason"] == "Spamming"
    assert data["message"] == "User ban successful"


# ── admin can unban banned user ──


def test_admin_can_unban_banned_user(monkeypatch):
    client, fake = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{BANNED_USER['id']}/unban",
        json={},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["status"] == "active"
    assert data["user"]["restriction_reason"] is None
    assert data["message"] == "User unban successful"


# ── admin can suspend regular user ──


def test_admin_can_suspend_regular_user(monkeypatch):
    client, fake = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/suspend",
        json={"reason": "Abusive behavior"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["status"] == "suspended"
    assert data["user"]["restriction_reason"] == "Abusive behavior"
    assert data["message"] == "User suspend successful"


# ── admin can unsuspend suspended user ──


def test_admin_can_unsuspend_suspended_user(monkeypatch):
    client, fake = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{SUSPENDED_USER['id']}/unsuspend",
        json={},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["status"] == "active"
    assert data["user"]["restriction_reason"] is None
    assert data["message"] == "User unsuspend successful"


# ── reason required for ban/suspend ──


@pytest.mark.parametrize("action", ["ban", "suspend"])
def test_reason_required_for_ban_and_suspend(monkeypatch, action):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/{action}",
        json={"reason": ""},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Reason is required"


@pytest.mark.parametrize("action", ["ban", "suspend"])
def test_reason_required_for_ban_and_suspend_whitespace(monkeypatch, action):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/{action}",
        json={"reason": "   "},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Reason is required"


# ── audit row created for every successful action ──


@pytest.mark.parametrize(
    "action,target,expected_previous,expected_new",
    [
        ("ban", REGULAR_USER, "active", "banned"),
        ("unban", BANNED_USER, "banned", "active"),
        ("suspend", REGULAR_USER, "active", "suspended"),
        ("unsuspend", SUSPENDED_USER, "suspended", "active"),
    ],
)
def test_audit_row_created(monkeypatch, action, target, expected_previous, expected_new):
    client, fake = make_client(monkeypatch)
    body = {"reason": "Test reason"} if action in ("ban", "suspend") else {}

    response = client.post(
        f"/admin/users/{target['id']}/{action}",
        json=body,
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    audit_rows = fake.tables["user_moderation_audit"]
    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row["target_user_id"] == target["id"]
    assert row["actor_user_id"] == ADMIN_USER["id"]
    assert row["action_type"] == action
    assert row["previous_status"] == expected_previous
    assert row["new_status"] == expected_new


# ── non-admin cannot perform moderation ──


@pytest.mark.parametrize("action", ["ban", "unban", "suspend", "unsuspend"])
def test_non_admin_cannot_perform_moderation(monkeypatch, action):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/{action}",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {make_token(REGULAR_USER)}"},
    )

    assert response.status_code == 403


# ── admin target cannot be moderated ──


@pytest.mark.parametrize("action", ["ban", "suspend"])
def test_admin_target_cannot_be_moderated(monkeypatch, action):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{ANOTHER_ADMIN['id']}/{action}",
        json={"reason": "Test"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot moderate admin users"


# ── invalid transitions are rejected ──


def test_cannot_ban_already_banned_user(monkeypatch):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{BANNED_USER['id']}/ban",
        json={"reason": "double ban"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 400
    assert "not currently active" in response.json()["detail"]


def test_cannot_unban_active_user(monkeypatch):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/unban",
        json={},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 400
    assert "not currently banned" in response.json()["detail"]


def test_cannot_suspend_already_suspended_user(monkeypatch):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{SUSPENDED_USER['id']}/suspend",
        json={"reason": "double suspend"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 400
    assert "not currently active" in response.json()["detail"]


def test_cannot_unsuspend_active_user(monkeypatch):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/unsuspend",
        json={},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 400
    assert "not currently suspended" in response.json()["detail"]


# ── restricted users blocked from normal workflows ──


def test_banned_user_blocked_from_creating_game(monkeypatch):
    configure(monkeypatch)
    fake = FakeSupabaseClient(
        {},
        tables={"users": [BANNED_USER]},
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)

    response = TestClient(app).post(
        "/games",
        json={
            "field_id": "00000000-0000-0000-0000-000000000999",
            "sport_type": "football",
            "max_players": 10,
        },
        headers={"Authorization": f"Bearer {make_token(BANNED_USER)}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is banned"


def test_suspended_user_blocked_from_creating_game(monkeypatch):
    configure(monkeypatch)
    fake = FakeSupabaseClient(
        {},
        tables={"users": [SUSPENDED_USER]},
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)

    response = TestClient(app).post(
        "/games",
        json={
            "field_id": "00000000-0000-0000-0000-000000000999",
            "sport_type": "football",
            "max_players": 10,
        },
        headers={"Authorization": f"Bearer {make_token(SUSPENDED_USER)}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Account is suspended"


# ── promote/remove admin endpoints do not exist ──


@pytest.mark.parametrize("action", ["promote", "demote", "remove-admin"])
def test_promote_remove_admin_not_implemented(monkeypatch, action):
    client, _ = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{REGULAR_USER['id']}/{action}",
        json={},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code in (404, 405)


# ── GET /admin/users returns real status and restriction metadata ──


def test_admin_users_returns_status_and_restriction(monkeypatch):
    client, _ = make_client(monkeypatch)

    response = client.get(
        "/admin/users",
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    data = response.json()
    banned = next(u for u in data if u["id"] == BANNED_USER["id"])
    assert banned["status"] == "banned"
    assert banned["restriction_reason"] == "Spam"
    assert banned["restricted_at"] is not None

    active = next(u for u in data if u["id"] == REGULAR_USER["id"])
    assert active["status"] == "active"


# ── user not found ──


def test_moderation_on_nonexistent_user_returns_404(monkeypatch):
    client, _ = make_client(monkeypatch)

    response = client.post(
        "/admin/users/00000000-0000-0000-0000-000000099999/ban",
        json={"reason": "test"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "User not found"


# ── unban/unsuspend accept optional reason and still write audit ──


def test_unban_with_optional_reason_writes_audit(monkeypatch):
    client, fake = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{BANNED_USER['id']}/unban",
        json={"reason": "Reviewed and cleared"},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    audit_rows = fake.tables["user_moderation_audit"]
    assert len(audit_rows) == 1
    assert audit_rows[0]["reason"] == "Reviewed and cleared"


def test_unsuspend_without_reason_writes_audit(monkeypatch):
    client, fake = make_client(monkeypatch)

    response = client.post(
        f"/admin/users/{SUSPENDED_USER['id']}/unsuspend",
        json={},
        headers={"Authorization": f"Bearer {make_token(ADMIN_USER)}"},
    )

    assert response.status_code == 200
    audit_rows = fake.tables["user_moderation_audit"]
    assert len(audit_rows) == 1
    assert audit_rows[0]["reason"] is None
