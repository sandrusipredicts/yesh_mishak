"""E02-02: Field removal endpoint tests.

Covers DELETE /admin/fields/{field_id} — the admin-only, moderation-aware
soft-delete contract (reason validation, idempotency, public-listing
exclusion, game-creation blocking, historical-record preservation) per the
Maps & Fields roadmap task.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient, FakeTableQuery


ADMIN = {
    "id": "admin-1",
    "email": "admin@example.com",
    "name": "Admin",
    "role": "admin",
    "status": "active",
}
SECOND_ADMIN = {
    "id": "admin-2",
    "email": "admin2@example.com",
    "name": "Second Admin",
    "role": "admin",
    "status": "active",
}
BANNED_ADMIN = {
    "id": "admin-3",
    "email": "banned-admin@example.com",
    "name": "Banned Admin",
    "role": "admin",
    "status": "banned",
}
REGULAR_USER = {
    "id": "user-1",
    "email": "user@example.com",
    "name": "Regular User",
    "role": "user",
    "status": "active",
}
CREATOR = {
    "id": "creator-1",
    "email": "creator@example.com",
    "name": "Creator",
    "role": "user",
    "status": "active",
}


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def _token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def _headers(user: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


def _field(
    *,
    field_id: str = "field-1",
    name: str = "Central Court",
    lat: float = 32.0853,
    lng: float = 34.7818,
    sport_type: str = "football",
    surface_type: str = "grass",
    status: str = "open",
    approval_status: str = "approved",
    verified: bool = True,
    added_by: str | None = "creator-1",
    removed_at: str | None = None,
    removed_by: str | None = None,
    removal_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "id": field_id,
        "name": name,
        "lat": lat,
        "lng": lng,
        "sport_type": sport_type,
        "surface_type": surface_type,
        "has_nets": True,
        "has_water": False,
        "opening_hours": "08:00-22:00",
        "city": "Tel Aviv",
        "notes": None,
        "status": status,
        "approval_status": approval_status,
        "verified": verified,
        "added_by": added_by,
        "created_at": "2026-01-01T00:00:00+00:00",
        "image_url": None,
        "updated_at": None,
        "removed_at": removed_at,
        "removed_by": removed_by,
        "removal_reason": removal_reason,
    }


def _make_client(monkeypatch, tables: dict[str, list]) -> TestClient:
    fake = FakeSupabaseClient(tables)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    return TestClient(app)


def _base_tables(
    *fields: dict[str, Any],
    users: list[dict[str, Any]] | None = None,
    games: list[dict[str, Any]] | None = None,
) -> dict[str, list]:
    return {
        "users": users if users is not None else [ADMIN, SECOND_ADMIN, BANNED_ADMIN, REGULAR_USER, CREATOR],
        "fields": list(fields),
        "games": games if games is not None else [],
        "game_players": [],
    }


DELETE_PATH = "/admin/fields/{}"
VALID_BODY = {"reason": "duplicate_field"}


# ═══════════════════════════════════════════════════════════════
# Auth / authorization
# ═══════════════════════════════════════════════════════════════


def test_delete_requires_authentication(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request("DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY)

    assert response.status_code == 401


def test_delete_forbidden_for_regular_user(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(REGULAR_USER)
    )

    assert response.status_code == 403


def test_delete_forbidden_for_field_creator_without_admin_role(monkeypatch) -> None:
    """added_by is attribution only — no owner-delete bypass exists in this model."""
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field(added_by="creator-1")))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(CREATOR)
    )

    assert response.status_code == 403


def test_delete_rejects_banned_admin(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(BANNED_ADMIN)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_RESTRICTED"


def test_delete_missing_field_returns_404(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field(field_id="other-field")))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "FIELD_NOT_FOUND"


def test_delete_malformed_id_returns_400(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE", DELETE_PATH.format(""), json=VALID_BODY, headers=_headers(ADMIN)
    )

    assert response.status_code in (404, 405)


# ═══════════════════════════════════════════════════════════════
# Reason / payload validation
# ═══════════════════════════════════════════════════════════════


def test_delete_requires_reason(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json={}, headers=_headers(ADMIN)
    )

    assert response.status_code == 422


def test_delete_rejects_invalid_reason(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json={"reason": "not_a_real_reason"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 422


def test_delete_rejects_note_too_long(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json={"reason": "other", "note": "x" * 501},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 422


def test_delete_rejects_unknown_fields(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json={"reason": "other", "moderation_status": "removed"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 422


def test_delete_accepts_optional_note(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json={"reason": "safety_issue", "note": "Broken glass on the court"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200
    field = response.json()["field"]
    assert field["removal_reason"] == "safety_issue"


# ═══════════════════════════════════════════════════════════════
# Successful removal
# ═══════════════════════════════════════════════════════════════


def test_delete_succeeds_for_admin_and_sets_removal_fields(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    body = response.json()
    field = body["field"]
    assert field["id"] == "field-1"
    assert field["removed_at"] is not None
    assert field["removed_by"] == "admin-1"
    assert field["removal_reason"] == "duplicate_field"


@pytest.mark.parametrize(
    "approval_status,verified",
    [("pending", False), ("approved", True), ("rejected", False)],
)
def test_delete_works_regardless_of_approval_status(monkeypatch, approval_status, verified) -> None:
    """Mirrors the edit endpoint's E02-01 precedent: moderation removal is
    orthogonal to the approval workflow."""
    _configure(monkeypatch)
    field = _field(approval_status=approval_status, verified=verified)
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    assert response.json()["field"]["approval_status"] == approval_status


# ═══════════════════════════════════════════════════════════════
# Idempotency / repeated & concurrent deletion
# ═══════════════════════════════════════════════════════════════


def test_delete_already_removed_field_returns_409(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field(removed_at="2026-01-02T00:00:00+00:00", removed_by="admin-1", removal_reason="other")
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )

    assert response.status_code == 409
    assert response.json()["code"] == "FIELD_ALREADY_REMOVED"


def test_repeated_delete_requests_are_safe(monkeypatch) -> None:
    """Simulates two admins racing to remove the same field: the first
    request wins, the second sees a clean 409 rather than corrupting state
    (e.g. overwriting removed_by/removal_reason)."""
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    first = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json={"reason": "duplicate_field"}, headers=_headers(ADMIN)
    )
    second = client.request(
        "DELETE",
        DELETE_PATH.format("field-1"),
        json={"reason": "private_field"},
        headers=_headers(SECOND_ADMIN),
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert first.json()["field"]["removed_by"] == "admin-1"
    assert first.json()["field"]["removal_reason"] == "duplicate_field"


# ═══════════════════════════════════════════════════════════════
# Public listing / detail exclusion
# ═══════════════════════════════════════════════════════════════


def test_removed_field_excluded_from_public_list(monkeypatch) -> None:
    _configure(monkeypatch)
    visible = _field(field_id="field-visible", name="Visible Court")
    removed = _field(
        field_id="field-removed",
        name="Removed Court",
        removed_at="2026-01-02T00:00:00+00:00",
        removed_by="admin-1",
        removal_reason="other",
    )
    client = _make_client(monkeypatch, _base_tables(visible, removed))

    response = client.get("/fields/")

    assert response.status_code == 200
    ids = [f["id"] for f in response.json()]
    assert "field-visible" in ids
    assert "field-removed" not in ids


def test_removed_field_excluded_from_bounded_public_list(monkeypatch) -> None:
    _configure(monkeypatch)
    removed = _field(
        field_id="field-removed",
        lat=32.0853,
        lng=34.7818,
        removed_at="2026-01-02T00:00:00+00:00",
        removed_by="admin-1",
        removal_reason="other",
    )
    client = _make_client(monkeypatch, _base_tables(removed))

    response = client.get(
        "/fields/", params={"north": 33, "south": 31, "east": 35, "west": 34}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_removed_field_detail_returns_404(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field(removed_at="2026-01-02T00:00:00+00:00", removed_by="admin-1", removal_reason="other")
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.get("/fields/field-1")

    assert response.status_code == 404
    assert response.json()["code"] == "FIELD_NOT_FOUND"


def test_already_removed_field_excluded_from_admin_listing(monkeypatch) -> None:
    """A field removed before this request began must not appear in the
    default admin listing either — removal must survive a fresh GET, not
    just the acting session's local state. Regression test for a bug where
    GET /admin/fields had no removed_at filter, so a soft-deleted field
    would reappear after any page refresh even though the deletion had
    persisted correctly."""
    _configure(monkeypatch)
    field = _field(removed_at="2026-01-02T00:00:00+00:00", removed_by="admin-1", removal_reason="safety_issue")
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.get("/admin/fields", headers=_headers(ADMIN))

    assert response.status_code == 200
    assert response.json() == []


def test_delete_then_admin_listing_excludes_field_but_database_row_still_exists(monkeypatch) -> None:
    """End-to-end regression test for the refresh bug: remove a field
    through the real endpoint (not a pre-seeded removed row), then fetch
    the admin field list again in a separate request and confirm the field
    is gone from it — while the underlying database row is still present
    with removed_at/removed_by/removal_reason populated (soft delete, not
    a hard delete)."""
    _configure(monkeypatch)
    tables = _base_tables(_field())
    client = _make_client(monkeypatch, tables)

    delete_response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )
    assert delete_response.status_code == 200

    # Simulates a page refresh: a brand-new GET /admin/fields request,
    # independent of any client-side state from the DELETE response.
    listing_response = client.get("/admin/fields", headers=_headers(ADMIN))
    assert listing_response.status_code == 200
    assert listing_response.json() == []

    db_row = next(row for row in tables["fields"] if row["id"] == "field-1")
    assert db_row["removed_at"] is not None
    assert db_row["removed_by"] == "admin-1"
    assert db_row["removal_reason"] == "duplicate_field"


# ═══════════════════════════════════════════════════════════════
# Game creation blocked on removed fields
# ═══════════════════════════════════════════════════════════════


def test_cannot_create_game_on_removed_field(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field(removed_at="2026-01-02T00:00:00+00:00", removed_by="admin-1", removal_reason="other")
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.post(
        "/games/",
        json={
            "field_id": "field-1",
            "sport_type": "football",
            "players_present": 1,
            "max_players": 10,
        },
        headers=_headers(REGULAR_USER),
    )

    assert response.status_code == 400
    assert response.json()["code"] == "FIELD_NOT_OPEN"


# ═══════════════════════════════════════════════════════════════
# Historical / existing records remain intact
# ═══════════════════════════════════════════════════════════════


def test_existing_game_remains_valid_after_field_removed(monkeypatch) -> None:
    """Removal must not cascade to games — active games keep working exactly
    as before, mirroring the E02-01 edit-endpoint precedent."""
    _configure(monkeypatch)
    field = _field()
    game = {
        "id": "game-1",
        "field_id": "field-1",
        "created_by": "creator-1",
        "sport_type": "football",
        "players_present": 4,
        "max_players": 10,
        "status": "open",
        "started_at": "2099-06-01T10:00:00+00:00",
        "expires_at": "2099-06-01T12:00:00+00:00",
        "scheduled_at": None,
    }
    tables = _base_tables(field, games=[game])
    client = _make_client(monkeypatch, tables)

    delete_response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )
    assert delete_response.status_code == 200

    game_response = client.get("/games/game-1")
    assert game_response.status_code == 200
    assert game_response.json()["id"] == "game-1"
    assert game_response.json()["status"] == "open"


def test_finished_game_remains_intact_after_field_removed(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field()
    game = {
        "id": "game-2",
        "field_id": "field-1",
        "created_by": "creator-1",
        "sport_type": "football",
        "players_present": 10,
        "max_players": 10,
        "status": "finished",
        "started_at": "2020-01-01T10:00:00+00:00",
        "expires_at": "2020-01-01T12:00:00+00:00",
        "scheduled_at": None,
    }
    tables = _base_tables(field, games=[game])
    client = _make_client(monkeypatch, tables)

    delete_response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )
    assert delete_response.status_code == 200

    game_response = client.get("/games/game-2")
    assert game_response.status_code == 200
    assert game_response.json()["status"] == "finished"


# ═══════════════════════════════════════════════════════════════
# Duplicate-detection pool excludes removed fields
# ═══════════════════════════════════════════════════════════════


def test_edit_duplicate_check_ignores_removed_fields(monkeypatch) -> None:
    """A field that would otherwise be flagged as a confirmed duplicate of a
    *removed* field must not be blocked — the removed field no longer
    represents a live listing."""
    _configure(monkeypatch)
    removed = _field(
        field_id="field-removed",
        name="Shared Name",
        lat=32.0,
        lng=34.0,
        removed_at="2026-01-02T00:00:00+00:00",
        removed_by="admin-1",
        removal_reason="duplicate_field",
    )
    other = _field(field_id="field-other", name="Different Name", lat=31.0, lng=35.0)
    client = _make_client(monkeypatch, _base_tables(removed, other))

    response = client.patch(
        "/admin/fields/field-other",
        json={"name": "Shared Name", "lat": 32.0, "lng": 34.0},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════
# DB failure handling
# ═══════════════════════════════════════════════════════════════


def test_delete_database_failure_returns_clean_500(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    def failing_update(self, payload):
        self.update_payload = payload

        def fail_execute():
            raise RuntimeError("update failed")

        self.execute = fail_execute
        return self

    monkeypatch.setattr(FakeTableQuery, "update", failing_update)

    response = client.request(
        "DELETE", DELETE_PATH.format("field-1"), json=VALID_BODY, headers=_headers(ADMIN)
    )

    assert response.status_code == 500
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "DATABASE_ERROR"
