"""ISSUE-048: Inactive field lifecycle tests.

Validates that field status (open/closed/renovation) is correctly enforced
across game creation, public listing, and admin workflows per ISSUE-047 policy.
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient, FakeTableQuery


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

NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def _token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def _headers(user: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def _field(
    *,
    field_id: str = "field-1",
    status: str = "open",
    approval_status: str = "approved",
    verified: bool = True,
    sport_type: str = "football",
) -> dict[str, Any]:
    return {
        "id": field_id,
        "name": "Test Field",
        "lat": 32.0853,
        "lng": 34.7818,
        "sport_type": sport_type,
        "city": "Tel Aviv",
        "surface_type": "grass",
        "verified": verified,
        "approval_status": approval_status,
        "status": status,
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _make_client(monkeypatch, tables: dict[str, list]) -> TestClient:
    fake = FakeSupabaseClient(tables)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    return TestClient(app)


def _game_payload(field_id: str = "field-1") -> dict[str, Any]:
    return {
        "field_id": field_id,
        "sport_type": "football",
        "players_present": 2,
        "max_players": 10,
    }


# ═══════════════════════════════════════════════════════════════
# Game creation: field status enforcement
# ═══════════════════════════════════════════════════════════════


def test_game_creation_succeeds_on_approved_open_field(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    tables = {
        "users": [CREATOR],
        "fields": [_field(status="open", approval_status="approved")],
        "games": [],
        "game_players": [],
        "notification_preferences": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.post("/games/", json=_game_payload(), headers=_headers(CREATOR))

    assert response.status_code == 200


def test_game_creation_blocked_on_closed_field(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    tables = {
        "users": [CREATOR],
        "fields": [_field(status="closed", approval_status="approved")],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.post("/games/", json=_game_payload(), headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Field is not open"


def test_game_creation_blocked_on_renovation_field(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    tables = {
        "users": [CREATOR],
        "fields": [_field(status="renovation", approval_status="approved")],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.post("/games/", json=_game_payload(), headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Field is not open"


def test_game_creation_blocked_on_pending_field(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    tables = {
        "users": [CREATOR],
        "fields": [_field(approval_status="pending", verified=False)],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.post("/games/", json=_game_payload(), headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Field not approved"


def test_game_creation_blocked_on_rejected_field(monkeypatch) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    tables = {
        "users": [CREATOR],
        "fields": [_field(approval_status="rejected", verified=False)],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.post("/games/", json=_game_payload(), headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Field not approved"


def test_game_creation_blocked_on_approved_closed_returns_correct_error(monkeypatch) -> None:
    """Approved + closed must return 'Field is not open', not 'Field not approved'."""
    _configure(monkeypatch)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    tables = {
        "users": [CREATOR],
        "fields": [_field(status="closed", approval_status="approved", verified=True)],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.post("/games/", json=_game_payload(), headers=_headers(CREATOR))

    assert response.status_code == 400
    assert response.json()["detail"] == "Field is not open"


# ═══════════════════════════════════════════════════════════════
# Public listing: status filter
# ═══════════════════════════════════════════════════════════════


def test_public_listing_returns_only_open_approved_fields(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [],
        "fields": [
            _field(field_id="open-approved", status="open", approval_status="approved"),
            _field(field_id="closed-approved", status="closed", approval_status="approved"),
            _field(field_id="renovation-approved", status="renovation", approval_status="approved"),
            _field(field_id="open-pending", status="open", approval_status="pending", verified=False),
            _field(field_id="open-rejected", status="open", approval_status="rejected", verified=False),
        ],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.get("/fields/")

    assert response.status_code == 200
    field_ids = [f["id"] for f in response.json()]
    assert field_ids == ["open-approved"]


def test_public_listing_excludes_closed_fields(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [],
        "fields": [
            _field(field_id="f1", status="open", approval_status="approved"),
            _field(field_id="f2", status="closed", approval_status="approved"),
        ],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.get("/fields/")

    assert response.status_code == 200
    field_ids = [f["id"] for f in response.json()]
    assert "f1" in field_ids
    assert "f2" not in field_ids


def test_public_listing_excludes_renovation_fields(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [],
        "fields": [
            _field(field_id="f1", status="open", approval_status="approved"),
            _field(field_id="f2", status="renovation", approval_status="approved"),
        ],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.get("/fields/")

    assert response.status_code == 200
    field_ids = [f["id"] for f in response.json()]
    assert "f1" in field_ids
    assert "f2" not in field_ids


# ═══════════════════════════════════════════════════════════════
# Direct field lookup: no status filter (known MVP gap)
# ═══════════════════════════════════════════════════════════════


def test_direct_lookup_returns_closed_field(monkeypatch) -> None:
    """GET /fields/{id} returns closed fields — known MVP gap per ISSUE-044/047."""
    _configure(monkeypatch)
    tables = {
        "users": [],
        "fields": [_field(field_id="closed-1", status="closed")],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.get("/fields/closed-1")

    assert response.status_code == 200
    assert response.json()["status"] == "closed"


def test_direct_lookup_returns_renovation_field(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [],
        "fields": [_field(field_id="reno-1", status="renovation")],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.get("/fields/reno-1")

    assert response.status_code == 200
    assert response.json()["status"] == "renovation"


# ═══════════════════════════════════════════════════════════════
# Admin: field status changes still work
# ═══════════════════════════════════════════════════════════════


def test_admin_can_set_field_status_to_closed(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [ADMIN],
        "fields": [_field(status="open")],
    }
    client = _make_client(monkeypatch, tables)

    response = client.patch(
        "/admin/fields/field-1/status",
        json={"status": "closed"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["field"]["status"] == "closed"


def test_admin_can_set_field_status_to_renovation(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [ADMIN],
        "fields": [_field(status="open")],
    }
    client = _make_client(monkeypatch, tables)

    response = client.patch(
        "/admin/fields/field-1/status",
        json={"status": "renovation"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["field"]["status"] == "renovation"


def test_admin_can_reopen_closed_field(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [ADMIN],
        "fields": [_field(status="closed")],
    }
    client = _make_client(monkeypatch, tables)

    response = client.patch(
        "/admin/fields/field-1/status",
        json={"status": "open"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["field"]["status"] == "open"


def test_admin_can_reopen_renovation_field(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [ADMIN],
        "fields": [_field(status="renovation")],
    }
    client = _make_client(monkeypatch, tables)

    response = client.patch(
        "/admin/fields/field-1/status",
        json={"status": "open"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200
    assert response.json()["field"]["status"] == "open"


def test_admin_status_change_rejects_invalid_status(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [ADMIN],
        "fields": [_field(status="open")],
    }
    client = _make_client(monkeypatch, tables)

    response = client.patch(
        "/admin/fields/field-1/status",
        json={"status": "demolished"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 400


def test_regular_user_cannot_change_field_status(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [CREATOR],
        "fields": [_field(status="open")],
    }
    client = _make_client(monkeypatch, tables)

    response = client.patch(
        "/admin/fields/field-1/status",
        json={"status": "closed"},
        headers=_headers(CREATOR),
    )

    assert response.status_code == 403


# ═══════════════════════════════════════════════════════════════
# Admin listing: all fields visible regardless of status
# ═══════════════════════════════════════════════════════════════


def test_admin_listing_includes_all_statuses(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = {
        "users": [ADMIN],
        "fields": [
            _field(field_id="f-open", status="open"),
            _field(field_id="f-closed", status="closed"),
            _field(field_id="f-reno", status="renovation"),
        ],
        "games": [],
        "game_players": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.get("/admin/fields", headers=_headers(ADMIN))

    assert response.status_code == 200
    field_ids = {f["id"] for f in response.json()}
    assert field_ids == {"f-open", "f-closed", "f-reno"}


# ═══════════════════════════════════════════════════════════════
# Combined approval_status + status matrix
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "approval_status,verified,field_status,expected_code,expected_detail",
    [
        ("approved", True, "open", 200, None),
        ("approved", True, "closed", 400, "Field is not open"),
        ("approved", True, "renovation", 400, "Field is not open"),
        ("pending", False, "open", 400, "Field not approved"),
        ("rejected", False, "open", 400, "Field not approved"),
    ],
    ids=[
        "approved+open",
        "approved+closed",
        "approved+renovation",
        "pending+open",
        "rejected+open",
    ],
)
def test_game_creation_matrix(
    monkeypatch,
    approval_status: str,
    verified: bool,
    field_status: str,
    expected_code: int,
    expected_detail: str | None,
) -> None:
    _configure(monkeypatch)
    monkeypatch.setattr("app.routers.games.get_now", lambda: NOW)
    monkeypatch.setattr("app.routers.game_lifecycle.get_now", lambda: NOW)
    tables = {
        "users": [CREATOR],
        "fields": [
            _field(
                status=field_status,
                approval_status=approval_status,
                verified=verified,
            )
        ],
        "games": [],
        "game_players": [],
        "notification_preferences": [],
    }
    client = _make_client(monkeypatch, tables)

    response = client.post("/games/", json=_game_payload(), headers=_headers(CREATOR))

    assert response.status_code == expected_code
    if expected_detail is not None:
        assert response.json()["detail"] == expected_detail
