import os
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client")
os.environ.setdefault("JWT_SECRET", "test-secret-with-at-least-32-characters")

import app.api.admin as admin
from app.auth.dependencies import require_admin
from app.main import app
from app.middleware.request_metrics import should_record_request_metric


ADMIN_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "admin@example.com",
    "name": "Admin User",
    "role": "admin",
    "status": "active",
}


@pytest.fixture(autouse=True)
def disable_existing_request_metric_side_effect(monkeypatch):
    monkeypatch.setattr(
        "app.middleware.request_metrics.record_api_request_metric",
        lambda **_: None,
    )


@pytest.fixture
def admin_client():
    app.dependency_overrides[require_admin] = lambda: ADMIN_USER
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_admin, None)


def test_engagement_returns_backend_derived_existing_rpc_metrics(
    monkeypatch,
    admin_client: TestClient,
) -> None:
    fixed_now = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)
    calls: dict[str, dict[str, datetime]] = {}

    def analytics_metrics(**kwargs: datetime) -> list[dict[str, Any]]:
        calls["analytics"] = kwargs
        return [
            {
                "event_day": "2026-07-19",
                "event_name": "app_open",
                "platform": "android",
                "event_count": 3,
            },
            {
                "event_day": "2026-07-20",
                "event_name": "app_open",
                "platform": "web",
                "event_count": 2,
            },
            {
                "event_day": "2026-07-20",
                "event_name": "screen_view",
                "platform": "android",
                "event_count": 4,
            },
            {
                "event_day": "2026-07-20",
                "event_name": "screen_view",
                "platform": "web",
                "event_count": 1,
            },
        ]

    def share_metrics(**kwargs: datetime) -> list[dict[str, Any]]:
        calls["shares"] = kwargs
        return [
            {
                "event_name": "share_action",
                "entity_type": "game",
                "platform": "android",
                "mechanism": "native_share",
                "outcome": "shared",
                "error_category": None,
                "event_count": 2,
            },
            {
                "event_name": "share_action",
                "entity_type": "field",
                "platform": "web",
                "mechanism": "copy_link",
                "outcome": "copied",
                "error_category": None,
                "event_count": 1,
            },
            {
                "event_name": "share_action",
                "entity_type": "game",
                "platform": "web",
                "mechanism": "native_share",
                "outcome": "failed",
                "error_category": "share_failed",
                "event_count": 2,
            },
            {
                "event_name": "link_open",
                "entity_type": "game",
                "platform": "web",
                "mechanism": None,
                "outcome": "valid",
                "error_category": None,
                "event_count": 20,
            },
        ]

    monkeypatch.setattr(admin, "get_now", lambda: fixed_now)
    monkeypatch.setattr(admin, "get_analytics_event_metrics", analytics_metrics)
    monkeypatch.setattr(admin, "get_share_event_metrics", share_metrics)
    monkeypatch.setattr(
        admin,
        "get_supabase_client",
        lambda: pytest.fail("engagement must not select raw rows"),
    )

    response = admin_client.get("/admin/engagement?window_days=7")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["window_days"] == 7
    assert data["window_started_at"] == (fixed_now - timedelta(days=7)).isoformat()
    assert data["window_ended_at"] == fixed_now.isoformat()
    assert data["analytics_events"] == {
        "source_available": True,
        "source": "database",
        "semantics": "anonymous_first_party_events",
        "app_opens": 5,
        "screen_views": 5,
        "daily": [
            {
                "event_day": "2026-07-19",
                "app_opens": 3,
                "screen_views": 0,
            },
            {
                "event_day": "2026-07-20",
                "app_opens": 2,
                "screen_views": 5,
            },
        ],
        "platform_breakdown": [
            {
                "platform": "web",
                "app_opens": 2,
                "screen_views": 1,
                "total_events": 3,
            },
            {
                "platform": "android",
                "app_opens": 3,
                "screen_views": 4,
                "total_events": 7,
            },
            {
                "platform": "ios",
                "app_opens": 0,
                "screen_views": 0,
                "total_events": 0,
            },
        ],
    }
    assert data["share_events"]["total_actions"] == 5
    assert data["share_events"]["successful_actions"] == 3
    assert data["share_events"]["success_rate"] == 0.6
    assert data["share_events"]["outcome_breakdown"] == [
        {"outcome": "shared", "event_count": 2},
        {"outcome": "copied", "event_count": 1},
        {"outcome": "cancelled", "event_count": 0},
        {"outcome": "unavailable", "event_count": 0},
        {"outcome": "failed", "event_count": 2},
    ]
    assert calls["analytics"] == calls["shares"]
    assert calls["analytics"] == {
        "window_started_at": fixed_now - timedelta(days=7),
        "window_ended_at": fixed_now,
    }


def test_engagement_keeps_available_source_when_other_rpc_fails(
    monkeypatch,
    admin_client: TestClient,
) -> None:
    def fail_analytics(**_: Any) -> None:
        raise RuntimeError("analytics unavailable")

    monkeypatch.setattr(admin, "get_analytics_event_metrics", fail_analytics)
    monkeypatch.setattr(admin, "get_share_event_metrics", lambda **_: [])

    response = admin_client.get("/admin/engagement")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "partial"
    assert data["analytics_events"]["source_available"] is False
    assert "analytics unavailable" not in data["analytics_events"]["reason"]
    assert data["share_events"]["source_available"] is True
    assert data["share_events"]["total_actions"] == 0
    assert data["share_events"]["success_rate"] == 0.0


@pytest.mark.parametrize("window_days", [1, 8, 91])
def test_engagement_rejects_unsupported_windows(
    monkeypatch,
    admin_client: TestClient,
    window_days: int,
) -> None:
    monkeypatch.setattr(
        admin,
        "get_analytics_event_metrics",
        lambda **_: pytest.fail("invalid windows must be rejected before querying"),
    )

    response = admin_client.get(
        "/admin/engagement",
        params={"window_days": window_days},
    )

    assert response.status_code == 422


def test_engagement_route_is_get_only() -> None:
    route = next(route for route in app.routes if route.path == "/admin/engagement")

    assert route.methods == {"GET"}


def test_engagement_is_excluded_from_request_metric_inserts() -> None:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/admin/engagement",
            "raw_path": b"/admin/engagement",
            "query_string": b"window_days=30",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        },
    )

    assert should_record_request_metric(request) is False


def test_engagement_requires_authentication() -> None:
    app.dependency_overrides.pop(require_admin, None)

    response = TestClient(app).get("/admin/engagement")

    assert response.status_code == 401


def test_engagement_rejects_non_admin() -> None:
    def reject_non_admin() -> None:
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[require_admin] = reject_non_admin
    try:
        response = TestClient(app).get("/admin/engagement")
    finally:
        app.dependency_overrides.pop(require_admin, None)

    assert response.status_code == 403
