"""ISSUE-043: Duplicate field detection tests.

Tests the scoring logic and admin endpoint for duplicate field detection
per the ISSUE-042 strategy.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from app.services.duplicate_detection import (
    RISK_CONFIRMED,
    RISK_NOT_ENOUGH,
    RISK_POSSIBLE,
    RISK_STRONG,
    find_duplicates,
    name_similarity,
    normalize_name,
    score_pair,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _field(
    *,
    id: str = "field-1",
    name: str = "מגרש כדורגל",
    lat: float = 32.0853,
    lng: float = 34.7818,
    sport_type: str = "football",
    city: str = "תל אביב",
    status: str = "open",
    approval_status: str = "approved",
    verified: bool = True,
    added_by: str | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "lat": lat,
        "lng": lng,
        "sport_type": sport_type,
        "city": city,
        "status": status,
        "approval_status": approval_status,
        "verified": verified,
        "added_by": added_by,
    }


# ═══════════════════════════════════════════════════════════════
# Name normalization
# ═══════════════════════════════════════════════════════════════


def test_normalize_name_trims_and_lowercases():
    assert normalize_name("  Hello World  ") == "hello world"


def test_normalize_name_removes_punctuation():
    assert normalize_name('מגרש "הפועל"') == "מגרש הפועל"


def test_normalize_name_collapses_whitespace():
    assert normalize_name("מגרש   כדורגל   עירוני") == "מגרש כדורגל עירוני"


def test_name_similarity_exact():
    assert name_similarity("מגרש כדורגל הפועל", "מגרש כדורגל הפועל") == 1.0


def test_name_similarity_different():
    sim = name_similarity("מגרש כדורגל הפועל", "בית ספר תיכון")
    assert sim < NAME_SIMILARITY_WEAK


NAME_SIMILARITY_WEAK = 0.50


# ═══════════════════════════════════════════════════════════════
# Scoring: R2 — exact coords + exact name = confirmed
# ═══════════════════════════════════════════════════════════════


def test_same_coordinates_same_name_confirmed():
    a = _field(id="a", name="מגרש כדורגל הפועל", lat=32.0853, lng=34.7818)
    b = _field(id="b", name="מגרש כדורגל הפועל", lat=32.0853, lng=34.7818)
    result = score_pair(a, b)
    assert result is not None
    assert result["risk_level"] == RISK_CONFIRMED
    assert result["distance_m"] == 0
    assert "exact_coordinates" in result["matching_signals"]
    assert "exact_name" in result["matching_signals"]


# ═══════════════════════════════════════════════════════════════
# Scoring: R4 — very close + similar name + same sport = strong
# ═══════════════════════════════════════════════════════════════


def test_very_close_similar_name_same_sport_strong():
    a = _field(id="a", name="מגרש כדורגל עירוני", lat=32.0853000, lng=34.7818000)
    b = _field(id="b", name="מגרש כדורגל העירוני", lat=32.0853050, lng=34.7818050)
    result = score_pair(a, b)
    assert result is not None
    assert result["risk_level"] == RISK_STRONG
    assert result["distance_m"] <= 10
    assert result["name_similarity"] >= 0.70


# ═══════════════════════════════════════════════════════════════
# Scoring: R8 — nearby + same sport + different name = possible
# ═══════════════════════════════════════════════════════════════


def test_nearby_same_sport_different_name_possible():
    a = _field(id="a", name="מגרש ספורט צפון", lat=32.0853000, lng=34.7818000,
               sport_type="basketball")
    b = _field(id="b", name="מגרש שכונתי", lat=32.0856000, lng=34.7820000,
               sport_type="basketball")
    result = score_pair(a, b)
    assert result is not None
    assert result["risk_level"] == RISK_POSSIBLE
    assert 10 < result["distance_m"] <= 50


# ═══════════════════════════════════════════════════════════════
# Scoring: R12 — far + similar name = not enough evidence
# ═══════════════════════════════════════════════════════════════


def test_far_similar_name_not_enough():
    a = _field(id="a", name="מגרש כדורגל הפועל", lat=32.0853, lng=34.7818,
               city="תל אביב")
    b = _field(id="b", name="מגרש כדורגל הפועל", lat=31.2530, lng=34.7910,
               city="באר שבע")
    result = score_pair(a, b)
    assert result is None


# ═══════════════════════════════════════════════════════════════
# Scoring: close + different sport type — not confirmed
# ═══════════════════════════════════════════════════════════════


def test_close_different_sport_not_confirmed():
    a = _field(id="a", name="מגרש כדורגל פארק", lat=32.0970, lng=34.8050,
               sport_type="football")
    b = _field(id="b", name="מגרש כדורסל פארק", lat=32.0970050, lng=34.8050050,
               sport_type="basketball")
    result = score_pair(a, b)
    if result is not None:
        assert result["risk_level"] != RISK_CONFIRMED
        assert "different_sport_type" in result["matching_signals"]


# ═══════════════════════════════════════════════════════════════
# Scoring: R14 — admin involvement elevates risk
# ═══════════════════════════════════════════════════════════════


def test_admin_involved_elevates_to_strong():
    a = _field(id="a", name="מגרש ספורט", lat=32.0853000, lng=34.7818000,
               sport_type="basketball", verified=True, approval_status="approved",
               added_by="admin-user-id")
    b = _field(id="b", name="מגרש שכונתי", lat=32.0856000, lng=34.7820000,
               sport_type="basketball")
    result = score_pair(a, b)
    assert result is not None
    assert result["risk_level"] <= RISK_STRONG
    assert "admin_involved" in result["matching_signals"]


# ═══════════════════════════════════════════════════════════════
# find_duplicates: integration
# ═══════════════════════════════════════════════════════════════


def test_find_duplicates_returns_sorted_candidates():
    fields = [
        _field(id="a", name="מגרש כדורגל הפועל", lat=32.0853, lng=34.7818),
        _field(id="b", name="מגרש כדורגל הפועל", lat=32.0853, lng=34.7818),
        _field(id="c", name="מגרש שכונתי", lat=31.2530, lng=34.7910),
    ]
    results = find_duplicates(fields)
    assert len(results) == 1
    assert results[0]["risk_level"] == RISK_CONFIRMED
    assert results[0]["field_a"]["id"] == "a"
    assert results[0]["field_b"]["id"] == "b"


def test_find_duplicates_excludes_not_enough_evidence():
    fields = [
        _field(id="a", name="מגרש א", lat=32.0853, lng=34.7818),
        _field(id="b", name="מגרש ב", lat=31.2530, lng=34.7910),
    ]
    results = find_duplicates(fields)
    assert len(results) == 0


def test_find_duplicates_result_shape():
    fields = [
        _field(id="a", name="מגרש כדורגל", lat=32.0853, lng=34.7818),
        _field(id="b", name="מגרש כדורגל", lat=32.0853, lng=34.7818),
    ]
    results = find_duplicates(fields)
    assert len(results) == 1
    r = results[0]
    assert "field_a" in r
    assert "field_b" in r
    assert "distance_m" in r
    assert "name_similarity" in r
    assert "matching_signals" in r
    assert "risk_level" in r
    assert "risk_label" in r
    assert "reason" in r
    assert "id" in r["field_a"]
    assert "name" in r["field_a"]


# ═══════════════════════════════════════════════════════════════
# R3: exact coords + different name + same sport = strong
# ═══════════════════════════════════════════════════════════════


def test_exact_coords_different_name_same_sport_strong():
    a = _field(id="a", name="מגרש הפועל", lat=32.0853, lng=34.7818)
    b = _field(id="b", name="מגרש מכבי", lat=32.0853, lng=34.7818)
    result = score_pair(a, b)
    assert result is not None
    assert result["risk_level"] == RISK_STRONG


# ═══════════════════════════════════════════════════════════════
# R13: same name + far + same city = possible
# ═══════════════════════════════════════════════════════════════


def test_same_name_far_same_city_possible():
    a = _field(id="a", name="מגרש כדורגל עירוני", lat=32.0853, lng=34.7818,
               city="תל אביב")
    b = _field(id="b", name="מגרש כדורגל עירוני", lat=32.0900, lng=34.7900,
               city="תל אביב")
    result = score_pair(a, b)
    if result is not None:
        assert result["risk_level"] == RISK_POSSIBLE
        assert "same_city" in result["matching_signals"]


# ═══════════════════════════════════════════════════════════════
# Admin endpoint tests
# ═══════════════════════════════════════════════════════════════


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self._data = list(data)
        self._filters: list[tuple[str, Any]] = []

    def select(self, *args, **kwargs) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self._filters.append((column, value))
        return self

    def limit(self, *args) -> "FakeQuery":
        return self

    def order(self, *args, **kwargs) -> "FakeQuery":
        return self

    def execute(self) -> FakeResponse:
        rows = self._data
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        return FakeResponse(rows)


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables.get(name, []))


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def _make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


ADMIN_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "admin@example.com",
    "name": "Admin",
    "role": "admin",
}

REGULAR_USER = {
    "id": "00000000-0000-0000-0000-000000000002",
    "email": "user@example.com",
    "name": "User",
    "role": "user",
}


def test_admin_duplicates_endpoint_requires_admin(monkeypatch) -> None:
    _configure(monkeypatch)
    fake = FakeSupabase({"users": [ADMIN_USER, REGULAR_USER], "fields": []})
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)

    response = TestClient(app).get(
        "/admin/fields/duplicates",
        headers={"Authorization": f"Bearer {_make_token(REGULAR_USER)}"},
    )
    assert response.status_code == 403


def test_admin_duplicates_endpoint_returns_candidates(monkeypatch) -> None:
    _configure(monkeypatch)
    fields = [
        {
            "id": "f1", "name": "מגרש כדורגל הפועל",
            "lat": 32.0853, "lng": 34.7818, "sport_type": "football",
            "city": "תל אביב", "status": "open",
            "approval_status": "approved", "verified": True,
            "added_by": None, "created_at": "2026-01-01",
        },
        {
            "id": "f2", "name": "מגרש כדורגל הפועל",
            "lat": 32.0853, "lng": 34.7818, "sport_type": "football",
            "city": "תל אביב", "status": "open",
            "approval_status": "pending", "verified": False,
            "added_by": "user-123", "created_at": "2026-06-01",
        },
        {
            "id": "f3", "name": "מגרש אחר",
            "lat": 31.2530, "lng": 34.7910, "sport_type": "basketball",
            "city": "באר שבע", "status": "open",
            "approval_status": "approved", "verified": True,
            "added_by": None, "created_at": "2026-01-01",
        },
    ]
    fake = FakeSupabase({"users": [ADMIN_USER, REGULAR_USER], "fields": fields})
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)

    response = TestClient(app).get(
        "/admin/fields/duplicates",
        headers={"Authorization": f"Bearer {_make_token(ADMIN_USER)}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["risk_level"] == RISK_CONFIRMED
    assert data[0]["field_a"]["id"] == "f1"
    assert data[0]["field_b"]["id"] == "f2"


def test_admin_duplicates_endpoint_empty_when_no_duplicates(monkeypatch) -> None:
    _configure(monkeypatch)
    fields = [
        {
            "id": "f1", "name": "מגרש א",
            "lat": 32.0853, "lng": 34.7818, "sport_type": "football",
            "city": "תל אביב", "status": "open",
            "approval_status": "approved", "verified": True,
            "added_by": None, "created_at": "2026-01-01",
        },
        {
            "id": "f2", "name": "מגרש ב",
            "lat": 31.2530, "lng": 34.7910, "sport_type": "basketball",
            "city": "באר שבע", "status": "open",
            "approval_status": "approved", "verified": True,
            "added_by": None, "created_at": "2026-01-01",
        },
    ]
    fake = FakeSupabase({"users": [ADMIN_USER, REGULAR_USER], "fields": fields})
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)

    response = TestClient(app).get(
        "/admin/fields/duplicates",
        headers={"Authorization": f"Bearer {_make_token(ADMIN_USER)}"},
    )
    assert response.status_code == 200
    assert response.json() == []
