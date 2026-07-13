"""E02-01: Field edit endpoint tests.

Covers PATCH /admin/fields/{field_id} — the admin-only edit contract
(allowlisted fields, validation, duplicate detection, moderation,
concurrency/last-write-wins) per the Maps & Fields roadmap task.
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
BANNED_ADMIN = {
    "id": "admin-2",
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
    has_nets: bool = True,
    has_water: bool = False,
    opening_hours: str | None = "08:00-22:00",
    city: str | None = "Tel Aviv",
    notes: str | None = "Great field",
    status: str = "open",
    approval_status: str = "approved",
    verified: bool = True,
    added_by: str | None = "creator-1",
) -> dict[str, Any]:
    return {
        "id": field_id,
        "name": name,
        "lat": lat,
        "lng": lng,
        "sport_type": sport_type,
        "surface_type": surface_type,
        "has_nets": has_nets,
        "has_water": has_water,
        "opening_hours": opening_hours,
        "city": city,
        "notes": notes,
        "status": status,
        "approval_status": approval_status,
        "verified": verified,
        "added_by": added_by,
        "created_at": "2026-01-01T00:00:00+00:00",
        "image_url": None,
        "updated_at": None,
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


def _base_tables(*fields: dict[str, Any], users: list[dict[str, Any]] | None = None) -> dict[str, list]:
    return {
        "users": users if users is not None else [ADMIN, BANNED_ADMIN, REGULAR_USER, CREATOR],
        "fields": list(fields),
        "games": [],
        "game_players": [],
    }


PATCH_PATH = "/admin/fields/{}"


# ═══════════════════════════════════════════════════════════════
# Auth / authorization
# ═══════════════════════════════════════════════════════════════


def test_edit_requires_authentication(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(PATCH_PATH.format("field-1"), json={"name": "New Name"})

    assert response.status_code == 401


def test_edit_forbidden_for_regular_user(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "New Name"}, headers=_headers(REGULAR_USER)
    )

    assert response.status_code == 403


def test_edit_forbidden_for_field_creator_without_admin_role(monkeypatch) -> None:
    """added_by is attribution only — no owner-edit bypass exists in this model."""
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field(added_by="creator-1")))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "New Name"}, headers=_headers(CREATOR)
    )

    assert response.status_code == 403


def test_edit_rejects_banned_admin(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "New Name"}, headers=_headers(BANNED_ADMIN)
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_RESTRICTED"


def test_edit_missing_field_returns_404(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field(field_id="other-field")))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "New Name"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 404
    assert response.json()["code"] == "FIELD_NOT_FOUND"


# ═══════════════════════════════════════════════════════════════
# Payload shape / mass assignment / allowlist
# ═══════════════════════════════════════════════════════════════


def test_edit_rejects_empty_payload(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(PATCH_PATH.format("field-1"), json={}, headers=_headers(ADMIN))

    assert response.status_code == 400
    assert response.json()["code"] == "FIELD_EDIT_EMPTY"


@pytest.mark.parametrize(
    "forbidden_key,value",
    [
        ("id", "some-other-id"),
        ("added_by", "user-1"),
        ("approval_status", "approved"),
        ("verified", True),
        ("status", "closed"),
        ("created_at", "2020-01-01T00:00:00Z"),
        ("random_field", "hack"),
    ],
)
def test_edit_rejects_disallowed_fields(monkeypatch, forbidden_key, value) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"),
        json={"name": "New Name", forbidden_key: value},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 422


def test_edit_does_not_change_immutable_or_admin_only_fields_via_allowed_payload(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field(approval_status="pending", verified=False, added_by="creator-1")
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "Updated notes"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    updated = response.json()["field"]
    assert updated["approval_status"] == "pending"
    assert updated["verified"] is False
    assert updated["added_by"] == "creator-1"
    assert updated["id"] == "field-1"


# ═══════════════════════════════════════════════════════════════
# Partial update semantics
# ═══════════════════════════════════════════════════════════════


def test_edit_single_field_leaves_others_untouched(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field()
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"city": "Haifa"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    updated = response.json()["field"]
    assert updated["city"] == "Haifa"
    assert updated["name"] == "Central Court"
    assert updated["surface_type"] == "grass"
    assert updated["notes"] == "Great field"


def test_edit_multiple_fields_at_once(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field()
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.patch(
        PATCH_PATH.format("field-1"),
        json={"name": "Renamed Court", "has_nets": False, "notes": "Renovated"},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200
    updated = response.json()["field"]
    assert updated["name"] == "Renamed Court"
    assert updated["has_nets"] is False
    assert updated["notes"] == "Renovated"
    assert updated["city"] == "Tel Aviv"


def test_edit_same_value_as_existing_succeeds(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field()
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "Central Court"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    assert response.json()["field"]["name"] == "Central Court"


def test_edit_sets_updated_at(monkeypatch) -> None:
    _configure(monkeypatch)
    field = _field()
    client = _make_client(monkeypatch, _base_tables(field))
    assert field["updated_at"] is None

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "New notes"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    assert response.json()["field"]["updated_at"] is not None


def test_edit_last_write_wins_on_sequential_edits(monkeypatch) -> None:
    """No optimistic-concurrency infra exists yet — documents last-write-wins."""
    _configure(monkeypatch)
    field = _field()
    client = _make_client(monkeypatch, _base_tables(field))

    first = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "First edit"}, headers=_headers(ADMIN)
    )
    second = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "Second edit"}, headers=_headers(ADMIN)
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["field"]["notes"] == "Second edit"


# ═══════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════


def test_edit_rejects_empty_name(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "   "}, headers=_headers(ADMIN)
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_edit_rejects_null_name(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": None}, headers=_headers(ADMIN)
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_edit_rejects_name_too_long(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "x" * 201}, headers=_headers(ADMIN)
    )

    assert response.status_code == 422


def test_edit_rejects_notes_too_long(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "x" * 1001}, headers=_headers(ADMIN)
    )

    assert response.status_code == 422


def test_edit_rejects_fake_test_name(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"name": "test"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 400
    assert response.json()["code"] == "CONTENT_REJECTED"


def test_edit_does_not_revalidate_unchanged_legacy_name(monkeypatch) -> None:
    """A legacy field with a name that would now fail moderation must not
    block edits to unrelated fields (e.g. city only)."""
    _configure(monkeypatch)
    field = _field(name="test")  # would fail moderation if re-validated today
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"city": "Haifa"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    assert response.json()["field"]["name"] == "test"
    assert response.json()["field"]["city"] == "Haifa"


@pytest.mark.parametrize(
    "payload",
    [
        {"lat": 91},
        {"lat": -91},
        {"lng": 181},
        {"lng": -181},
    ],
)
def test_edit_rejects_out_of_range_coordinates(monkeypatch, payload) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(PATCH_PATH.format("field-1"), json=payload, headers=_headers(ADMIN))

    assert response.status_code == 422


def test_edit_rejects_non_finite_coordinates(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"lat": float("nan")}, headers=_headers(ADMIN)
    )

    assert response.status_code == 422


def test_edit_rejects_string_coordinates_that_are_not_numeric(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"lat": "not-a-number"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 422


def test_edit_rejects_invalid_sport_type_enum(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"sport_type": "tennis"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 422


def test_edit_accepts_valid_coordinate_and_moves_field(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    response = client.patch(
        PATCH_PATH.format("field-1"),
        json={"lat": 31.0, "lng": 35.0},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200
    updated = response.json()["field"]
    assert updated["lat"] == 31.0
    assert updated["lng"] == 35.0


# ═══════════════════════════════════════════════════════════════
# Duplicate detection
# ═══════════════════════════════════════════════════════════════


def test_edit_blocks_confirmed_duplicate_after_move(monkeypatch) -> None:
    _configure(monkeypatch)
    field_a = _field(field_id="field-a", name="Shared Name", lat=32.0, lng=34.0)
    field_b = _field(field_id="field-b", name="Different Name", lat=31.0, lng=35.0)
    client = _make_client(monkeypatch, _base_tables(field_a, field_b))

    response = client.patch(
        PATCH_PATH.format("field-b"),
        json={"name": "Shared Name", "lat": 32.0, "lng": 34.0},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "FIELD_DUPLICATE"


def test_edit_field_is_not_a_duplicate_of_itself(monkeypatch) -> None:
    """A single field being edited must never be compared against itself."""
    _configure(monkeypatch)
    field = _field(field_id="field-1", name="Only Field", lat=32.0, lng=34.0)
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.patch(
        PATCH_PATH.format("field-1"),
        json={"name": "Only Field", "lat": 32.0, "lng": 34.0},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200


def test_edit_does_not_run_duplicate_check_when_unrelated_field_changes(monkeypatch) -> None:
    """Editing surface_type/notes/etc. (no name/lat/lng/city) never triggers
    duplicate detection, even if another exact duplicate already exists."""
    _configure(monkeypatch)
    field_a = _field(field_id="field-a", name="Same Name", lat=32.0, lng=34.0)
    field_b = _field(field_id="field-b", name="Same Name", lat=32.0, lng=34.0)
    client = _make_client(monkeypatch, _base_tables(field_a, field_b))

    response = client.patch(
        PATCH_PATH.format("field-b"), json={"surface_type": "asphalt"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    assert response.json()["field"]["surface_type"] == "asphalt"


def test_edit_allows_possible_duplicate_without_blocking(monkeypatch) -> None:
    """Only RISK_CONFIRMED blocks — weaker signals stay advisory, matching
    create_field's existing (unenforced) duplicate-detection behavior."""
    _configure(monkeypatch)
    field_a = _field(field_id="field-a", name="מגרש ספורט צפון", lat=32.0853000, lng=34.7818000, sport_type="basketball")
    field_b = _field(field_id="field-b", name="מגרש שכונתי", lat=32.0800, lng=34.7800, sport_type="basketball")
    client = _make_client(monkeypatch, _base_tables(field_a, field_b))

    response = client.patch(
        PATCH_PATH.format("field-b"),
        json={"lat": 32.0856000, "lng": 34.7820000},
        headers=_headers(ADMIN),
    )

    assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════
# Moderation status independence
# ═══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "approval_status,verified",
    [("pending", False), ("approved", True), ("rejected", False)],
)
def test_edit_works_regardless_of_approval_status(monkeypatch, approval_status, verified) -> None:
    _configure(monkeypatch)
    field = _field(approval_status=approval_status, verified=verified)
    client = _make_client(monkeypatch, _base_tables(field))

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "Reviewed"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 200
    assert response.json()["field"]["approval_status"] == approval_status
    assert response.json()["field"]["verified"] == verified


# ═══════════════════════════════════════════════════════════════
# DB failure handling
# ═══════════════════════════════════════════════════════════════


def test_edit_database_failure_returns_clean_500(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(_field()))

    def failing_update(self, payload):
        self.update_payload = payload

        def fail_execute():
            raise RuntimeError("update failed")

        self.execute = fail_execute
        return self

    monkeypatch.setattr(FakeTableQuery, "update", failing_update)

    response = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "New notes"}, headers=_headers(ADMIN)
    )

    assert response.status_code == 500
    err = response.json()
    assert err["error"] is True
    assert err["code"] == "DATABASE_ERROR"


# ═══════════════════════════════════════════════════════════════
# Regression: games linked to an edited field stay intact
# ═══════════════════════════════════════════════════════════════


def test_edit_does_not_break_active_game_relationship(monkeypatch) -> None:
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
    tables = _base_tables(field)
    tables["games"] = [game]
    tables["game_players"] = []
    client = _make_client(monkeypatch, tables)

    edit_response = client.patch(
        PATCH_PATH.format("field-1"), json={"notes": "Edited during active game"}, headers=_headers(ADMIN)
    )
    assert edit_response.status_code == 200

    field_response = client.get("/fields/field-1")
    assert field_response.status_code == 200
    body = field_response.json()
    assert body["notes"] == "Edited during active game"
    assert body["active_game"] is not None
    assert body["active_game"]["id"] == "game-1"
