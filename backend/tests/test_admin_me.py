from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class FakeRpcQuery:
    def __init__(self, data: Any) -> None:
        self.data = data

    def execute(self) -> FakeResponse:
        return FakeResponse(data=self.data)


class FakeUsersQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.user_id: str | None = None
        self.selected_columns: list[str] | None = None
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.update_payload: dict[str, Any] | None = None
        self.exact_count = False
        self.order_column: str | None = None
        self.order_desc = False

    def select(self, columns: str, count: str | None = None) -> "FakeUsersQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        self.exact_count = count == "exact"
        return self

    def eq(self, column: str, value: str) -> "FakeUsersQuery":
        if column == "id":
            self.user_id = value
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeUsersQuery":
        self.in_filters.append((column, values))
        return self

    def gte(self, column: str, value: Any) -> "FakeUsersQuery":
        self.filters.append(("__gte", (column, value)))
        return self

    def lt(self, column: str, value: Any) -> "FakeUsersQuery":
        self.filters.append(("__lt", (column, value)))
        return self

    def is_(self, column: str, value: str) -> "FakeUsersQuery":
        self.filters.append(("__is_null", (column, value)))
        return self

    def limit(self, _: int) -> "FakeUsersQuery":
        return self

    def order(self, column: str, desc: bool = False) -> "FakeUsersQuery":
        self.order_column = column
        self.order_desc = desc
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeUsersQuery":
        self.rows.append(dict(payload))
        self._insert_data = [dict(payload)]
        return self

    def update(self, payload: dict[str, Any]) -> "FakeUsersQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if hasattr(self, "_insert_data"):
            return FakeResponse(data=self._insert_data)

        if self.update_payload is not None:
            rows = self._filtered_rows()
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse(data=[dict(row) for row in rows])

        rows = self._filtered_rows()
        if self.order_column:
            rows = sorted(
                rows,
                key=lambda row: row.get(self.order_column) or "",
                reverse=self.order_desc,
            )
        data = [self._select_columns(row) for row in rows]
        return FakeResponse(data=data, count=len(rows) if self.exact_count else None)

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = self.rows
        for column, value in self.filters:
            if column == "__gte":
                col, threshold = value
                rows = [row for row in rows if (row.get(col) or "") >= threshold]
            elif column == "__lt":
                col, threshold = value
                rows = [row for row in rows if (row.get(col) or "") < threshold]
            elif column == "__is_null":
                col, _ = value
                rows = [row for row in rows if row.get(col) is None]
            else:
                rows = [row for row in rows if row.get(column) == value]
        for column, values in self.in_filters:
            rows = [row for row in rows if row.get(column) in values]
        return rows

    def _select_columns(self, user: dict[str, Any]) -> dict[str, Any]:
        if self.selected_columns is None:
            return user

        if "*" in self.selected_columns:
            return user

        return {column: user.get(column) for column in self.selected_columns}


class FakeSupabaseClient:
    def __init__(
        self,
        users_by_id: dict[str, dict[str, Any]],
        tables: dict[str, list[dict[str, Any]]] | None = None,
        rpc_responses: dict[str, Any] | None = None,
    ) -> None:
        self.tables = tables or {}
        self.tables.setdefault("users", list(users_by_id.values()))
        self.rpc_responses = rpc_responses or {}
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []

    def table(self, table_name: str) -> FakeUsersQuery:
        assert table_name in self.tables
        return FakeUsersQuery(self.tables[table_name])

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpcQuery:
        self.rpc_calls.append((name, dict(params)))
        if name in self.rpc_responses:
            response = self.rpc_responses[name]
            if isinstance(response, BaseException):
                raise response
            return FakeRpcQuery(response)
        if name == "get_api_response_time_metrics":
            return FakeRpcQuery([_calculate_response_time_rpc(self.tables.get("api_request_metrics", []), params)])
        raise AssertionError(f"Unexpected RPC call: {name}")


def _calculate_response_time_rpc(rows: list[dict[str, Any]], params: dict[str, Any]) -> dict[str, Any]:
    window_start = params["window_start"]
    window_end = params["window_end"]
    durations = sorted(
        row["duration_ms"]
        for row in rows
        if window_start <= (row.get("recorded_at") or "") < window_end
    )
    if not durations:
        return {
            "sample_count": 0,
            "average_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "max_ms": 0.0,
        }
    return {
        "sample_count": len(durations),
        "average_ms": round(sum(durations) / len(durations), 2),
        "p50_ms": _percentile_cont(durations, 0.50),
        "p95_ms": _percentile_cont(durations, 0.95),
        "max_ms": float(max(durations)),
    }


def _percentile_cont(sorted_values: list[int], percentile: float) -> float:
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = percentile * (len(sorted_values) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index
    value = sorted_values[lower_index] + (
        sorted_values[upper_index] - sorted_values[lower_index]
    ) * fraction
    return round(value, 2)


def _response_time_rpc_calls(fake_client: FakeSupabaseClient) -> list[dict[str, Any]]:
    return [
        params
        for name, params in fake_client.rpc_calls
        if name == "get_api_response_time_metrics"
    ]


def make_token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def configure_test_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


ADMIN_ENDPOINTS = [
    "/admin/me",
    "/admin/fields",
    "/admin/fields/duplicates",
    "/admin/field-reports",
    "/admin/games",
    "/admin/users",
    "/admin/stats",
    "/admin/monitoring",
]


def make_admin_matrix_client(
    admin_user: dict[str, Any],
    regular_user: dict[str, Any],
) -> FakeSupabaseClient:
    return FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, regular_user],
            "fields": [
                {
                    "id": "00000000-0000-0000-0000-000000000101",
                    "name": "Central Field",
                    "verified": True,
                    "approval_status": "approved",
                },
                {
                    "id": "00000000-0000-0000-0000-000000000102",
                    "name": "Pending Field",
                    "verified": False,
                    "approval_status": "pending",
                },
            ],
            "games": [
                {
                    "id": "00000000-0000-0000-0000-000000000201",
                    "field_id": "00000000-0000-0000-0000-000000000101",
                    "status": "open",
                    "started_at": "2026-06-15T09:00:00+00:00",
                },
                {
                    "id": "00000000-0000-0000-0000-000000000202",
                    "field_id": "00000000-0000-0000-0000-000000000101",
                    "status": "finished",
                    "started_at": "2026-06-14T09:00:00+00:00",
                },
            ],
            "game_players": [],
            "field_reports": [
                {
                    "id": "00000000-0000-0000-0000-000000000301",
                    "field_id": "00000000-0000-0000-0000-000000000101",
                    "user_id": regular_user["id"],
                    "category": "wrong_information",
                    "description": "Missing lighting details.",
                    "status": "open",
                    "created_at": "2026-06-15T09:00:00+00:00",
                    "reviewed_at": None,
                    "reviewed_by": None,
                },
            ],
            "notifications": [],
            "api_request_metrics": [],
        },
    )


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_admin_endpoints_allow_admin_user(monkeypatch, endpoint: str) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    fake_client = make_admin_matrix_client(admin_user, regular_user)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: fake_client,
    )
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        endpoint,
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_admin_endpoints_reject_regular_user(monkeypatch, endpoint: str) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    fake_client = make_admin_matrix_client(admin_user, regular_user)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        endpoint,
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_admin_endpoints_require_token(endpoint: str) -> None:
    response = TestClient(app).get(endpoint)

    assert response.status_code == 401


def test_admin_me_returns_current_admin(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({admin_user["id"]: admin_user}),
    )

    response = TestClient(app).get(
        "/admin/me",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert response.json() == admin_user


def test_admin_me_rejects_regular_user(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({regular_user["id"]: regular_user}),
    )

    response = TestClient(app).get(
        "/admin/me",
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403


def test_admin_me_requires_token() -> None:
    response = TestClient(app).get("/admin/me")

    assert response.status_code == 401


def test_admin_users_returns_required_fields_only(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
        "status": "active",
    }
    listed_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "username": "regular-user",
        "email": "user@example.com",
        "name": "Regular User",
        "phone_number": None,
        "created_at": "2026-06-15T09:00:00+00:00",
        "last_active": None,
        "role": "user",
        "status": "active",
        "restriction_reason": None,
        "restricted_at": None,
        "google_sub": "private-provider-id",
        "picture": "https://example.com/private.png",
    }
    fake_client = FakeSupabaseClient(
        {
            admin_user["id"]: admin_user,
            listed_user["id"]: listed_user,
        }
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        "/admin/users",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": listed_user["id"],
            "username": listed_user["username"],
            "name": listed_user["name"],
            "email": listed_user["email"],
            "phone_number": None,
            "created_at": listed_user["created_at"],
            "last_active": None,
            "role": listed_user["role"],
            "status": "active",
            "restriction_reason": None,
            "restricted_at": None,
        },
        {
            "id": admin_user["id"],
            "username": None,
            "name": admin_user["name"],
            "email": admin_user["email"],
            "phone_number": None,
            "created_at": None,
            "last_active": None,
            "role": admin_user["role"],
            "status": "active",
            "restriction_reason": None,
            "restricted_at": None,
        },
    ]


def test_admin_users_rejects_regular_user(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({regular_user["id"]: regular_user}),
    )

    response = TestClient(app).get(
        "/admin/users",
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403


def test_admin_field_reports_returns_enriched_reports_newest_first(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    reporter = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "reporter@example.com",
        "name": "Reporter User",
        "role": "user",
    }
    field = {
        "id": "00000000-0000-0000-0000-000000000101",
        "name": "Central Court",
    }
    reports = [
        {
            "id": f"00000000-0000-0000-0000-0000000003{index:02d}",
            "field_id": field["id"],
            "user_id": reporter["id"],
            "category": "wrong_information",
            "description": f"Report {index}",
            "status": "open" if index % 2 == 0 else "resolved",
            "created_at": f"2026-06-{index:02d}T09:00:00+00:00",
            "reviewed_at": None,
            "reviewed_by": None,
        }
        for index in range(1, 21)
    ]
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, reporter],
            "fields": [field],
            "field_reports": reports,
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        "/admin/field-reports",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 20
    assert data[0]["id"] == "00000000-0000-0000-0000-000000000320"
    assert data[0]["field_name"] == field["name"]
    assert data[0]["reporter_name"] == reporter["name"]
    assert data[0]["reporter_email"] == reporter["email"]
    assert data[0]["description"] == "Report 20"
    assert data[-1]["id"] == "00000000-0000-0000-0000-000000000301"


def test_admin_field_reports_supports_status_filter(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    reporter = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "reporter@example.com",
        "name": "Reporter User",
        "role": "user",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, reporter],
            "fields": [{"id": "field-1", "name": "Central Court"}],
            "field_reports": [
                {
                    "id": "report-open",
                    "field_id": "field-1",
                    "user_id": reporter["id"],
                    "category": "field_closed",
                    "description": None,
                    "status": "open",
                    "created_at": "2026-06-20T09:00:00+00:00",
                    "reviewed_at": None,
                    "reviewed_by": None,
                },
                {
                    "id": "report-resolved",
                    "field_id": "field-1",
                    "user_id": reporter["id"],
                    "category": "wrong_location",
                    "description": None,
                    "status": "resolved",
                    "created_at": "2026-06-21T09:00:00+00:00",
                    "reviewed_at": "2026-06-21T10:00:00+00:00",
                    "reviewed_by": admin_user["id"],
                },
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        "/admin/field-reports?status=open",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert [report["id"] for report in response.json()] == ["report-open"]


def test_admin_can_move_open_field_report_to_in_review(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    reporter = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "reporter@example.com",
        "name": "Reporter User",
        "role": "user",
    }
    report = {
        "id": "report-open",
        "field_id": "field-1",
        "user_id": reporter["id"],
        "category": "field_closed",
        "description": None,
        "status": "open",
        "created_at": "2026-06-20T09:00:00+00:00",
        "reviewed_at": None,
        "reviewed_by": None,
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, reporter],
            "field_reports": [report],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).patch(
        "/admin/field-reports/report-open/status",
        json={"status": "in_review"},
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    updated_report = response.json()["report"]
    assert updated_report["status"] == "in_review"
    assert fake_client.tables["field_reports"][0]["status"] == "in_review"


@pytest.mark.parametrize("review_status", ["resolved", "rejected"])
def test_admin_can_mark_field_report_terminal_status(monkeypatch, review_status: str) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    reporter = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "reporter@example.com",
        "name": "Reporter User",
        "role": "user",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, reporter],
            "field_reports": [
                {
                    "id": "report-in-review",
                    "field_id": "field-1",
                    "user_id": reporter["id"],
                    "category": "wrong_information",
                    "description": "Needs review.",
                    "status": "in_review",
                    "created_at": "2026-06-20T09:00:00+00:00",
                    "reviewed_at": None,
                    "reviewed_by": None,
                }
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).patch(
        "/admin/field-reports/report-in-review/status",
        json={"status": review_status},
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert response.json()["report"]["status"] == review_status
    assert fake_client.tables["field_reports"][0]["status"] == review_status


def test_admin_field_report_status_rejects_invalid_status(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user],
            "field_reports": [
                {
                    "id": "report-open",
                    "status": "open",
                    "reviewed_at": None,
                    "reviewed_by": None,
                }
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).patch(
        "/admin/field-reports/report-open/status",
        json={"status": "open"},
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "status must be in_review, resolved, or rejected"
    assert response.json()["error"] is True
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert fake_client.tables["field_reports"][0]["status"] == "open"
    assert fake_client.tables["field_reports"][0]["reviewed_at"] is None
    assert fake_client.tables["field_reports"][0]["reviewed_by"] is None


def test_admin_field_report_status_rejects_regular_user(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [regular_user],
            "field_reports": [
                {
                    "id": "report-open",
                    "status": "open",
                    "reviewed_at": None,
                    "reviewed_by": None,
                }
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).patch(
        "/admin/field-reports/report-open/status",
        json={"status": "in_review"},
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403
    assert fake_client.tables["field_reports"][0]["status"] == "open"
    assert fake_client.tables["field_reports"][0]["reviewed_at"] is None
    assert fake_client.tables["field_reports"][0]["reviewed_by"] is None


def test_admin_field_report_status_saves_review_metadata(monkeypatch) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    reporter = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "reporter@example.com",
        "name": "Reporter User",
        "role": "user",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, reporter],
            "field_reports": [
                {
                    "id": "report-open",
                    "field_id": "field-1",
                    "user_id": reporter["id"],
                    "category": "wrong_location",
                    "description": None,
                    "status": "open",
                    "created_at": "2026-06-20T09:00:00+00:00",
                    "reviewed_at": None,
                    "reviewed_by": None,
                }
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).patch(
        "/admin/field-reports/report-open/status",
        json={"status": "in_review"},
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    updated_report = response.json()["report"]
    assert updated_report["reviewed_by"] == admin_user["id"]
    assert updated_report["reviewed_at"] is not None
    assert fake_client.tables["field_reports"][0]["reviewed_by"] == admin_user["id"]
    assert fake_client.tables["field_reports"][0]["reviewed_at"] == updated_report["reviewed_at"]


def test_admin_stats_returns_counts_only(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, regular_user],
            "fields": [
                {"id": "field-1", "verified": True, "approval_status": "approved"},
                {"id": "field-2", "verified": True, "approval_status": "approved"},
                {"id": "field-3", "verified": False, "approval_status": "approved"},
                {"id": "field-4", "verified": False, "approval_status": "pending"},
                {"id": "field-5", "verified": False, "approval_status": "rejected"},
            ],
            "games": [
                {"id": "game-1", "status": "open"},
                {"id": "game-2", "status": "full"},
                {"id": "game-3", "status": "finished"},
                {"id": "game-4", "status": "cancelled"},
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    response = TestClient(app).get(
        "/admin/stats",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "verified_fields": 2,
        "pending_fields": 1,
        "active_games": 2,
        "total_users": 2,
        "rejected_fields": 1,
        "finished_games": 2,
    }
    assert all(isinstance(value, int) for value in response.json().values())


def test_admin_stats_rejects_regular_user(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
    }
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({regular_user["id"]: regular_user}),
    )

    response = TestClient(app).get(
        "/admin/stats",
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("endpoint", "expected_event", "expected_status", "expected_verified"),
    [
        ("/admin/fields/field-1/approve", "fields.moderation.approve", "approved", True),
        ("/admin/fields/field-1/reject", "fields.moderation.reject", "rejected", False),
    ],
)
def test_admin_field_moderation_logs_decision(
    monkeypatch,
    caplog,
    endpoint: str,
    expected_event: str,
    expected_status: str,
    expected_verified: bool,
) -> None:
    configure_test_settings(monkeypatch)

    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user],
            "fields": [
                {
                    "id": "field-1",
                    "verified": False,
                    "approval_status": "pending",
                }
            ],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)

    with caplog.at_level(logging.INFO, logger="app.api.admin"):
        response = TestClient(app).post(
            endpoint,
            headers={"Authorization": f"Bearer {make_token(admin_user)}"},
        )

    assert response.status_code == 200
    assert response.json()["approval_status"] == expected_status
    assert response.json()["verified"] is expected_verified
    moderation_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == expected_event
    ]
    assert moderation_records
    assert moderation_records[-1].actor_user_id == admin_user["id"]
    assert moderation_records[-1].field_id == "field-1"
    assert moderation_records[-1].approval_status == expected_status


# ---------------------------------------------------------------------------
# /admin/monitoring
# ---------------------------------------------------------------------------

SENSITIVE_STRINGS = [
    "example.com",
    "test-key",
    "test-secret",
    "test-google-client",
    "Bearer",
    "password",
    "push-token",
]


def _make_monitoring_client(monkeypatch, *, admin_user=None, regular_user=None):
    configure_test_settings(monkeypatch)

    if admin_user is None:
        admin_user = {
            "id": "00000000-0000-0000-0000-000000000001",
            "email": "admin@example.com",
            "name": "Admin User",
            "role": "admin",
            "status": "active",
            "last_login": "2026-06-24T10:00:00+00:00",
        }
    if regular_user is None:
        regular_user = {
            "id": "00000000-0000-0000-0000-000000000002",
            "email": "user@example.com",
            "name": "Regular User",
            "role": "user",
            "status": "active",
            "last_login": "2026-06-24T08:00:00+00:00",
        }

    stale_user = {
        "id": "00000000-0000-0000-0000-000000000003",
        "email": "stale@example.com",
        "name": "Stale User",
        "role": "user",
        "status": "active",
        "last_login": "2026-01-01T00:00:00+00:00",
    }

    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user, regular_user, stale_user],
            "fields": [
                {"id": "field-1", "verified": True, "approval_status": "approved"},
                {"id": "field-2", "verified": False, "approval_status": "pending"},
                {"id": "field-3", "verified": False, "approval_status": "pending"},
            ],
            "games": [
                {"id": "game-1", "status": "open"},
                {"id": "game-2", "status": "full"},
                {"id": "game-3", "status": "finished"},
            ],
            "notifications": [
                {
                    "id": "notif-1",
                    "user_id": regular_user["id"],
                    "created_at": "2026-06-24T09:00:00+00:00",
                    "read_at": None,
                },
                {
                    "id": "notif-2",
                    "user_id": regular_user["id"],
                    "created_at": "2026-06-24T07:00:00+00:00",
                    "read_at": "2026-06-24T08:00:00+00:00",
                },
                {
                    "id": "notif-3",
                    "user_id": regular_user["id"],
                    "created_at": "2026-06-01T00:00:00+00:00",
                    "read_at": None,
                },
            ],
            "api_request_metrics": [],
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: fake_client,
    )
    return admin_user, regular_user, fake_client


def test_monitoring_rejects_unauthenticated(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    response = TestClient(app).get("/admin/monitoring")
    assert response.status_code in (401, 403)


def test_monitoring_rejects_regular_user(monkeypatch) -> None:
    regular_user = {
        "id": "00000000-0000-0000-0000-000000000002",
        "email": "user@example.com",
        "name": "Regular User",
        "role": "user",
        "status": "active",
    }
    configure_test_settings(monkeypatch)
    monkeypatch.setattr(
        "app.auth.dependencies.get_supabase_client",
        lambda: FakeSupabaseClient({regular_user["id"]: regular_user}),
    )
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(regular_user)}"},
    )
    assert response.status_code == 403


def test_monitoring_admin_succeeds(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    assert response.status_code == 200
    data = response.json()

    expected_keys = {
        "status",
        "generated_at",
        "runtime",
        "active_games",
        "active_users",
        "notifications",
        "moderation",
        "database",
        "api_errors",
        "response_time",
        "scheduled_jobs",
        "push_notifications",
    }
    assert set(data.keys()) == expected_keys


def test_monitoring_active_games_count(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    data = response.json()
    assert data["active_games"]["count"] == 2
    assert data["active_games"]["source"] == "database"


def test_monitoring_active_users_count(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    data = response.json()
    assert data["active_users"]["total_registered"] == 3
    assert data["active_users"]["source"] == "database"
    assert isinstance(data["active_users"]["last_24h"], int)
    assert isinstance(data["active_users"]["last_7d"], int)
    assert data["active_users"]["last_7d"] >= data["active_users"]["last_24h"]


def test_monitoring_notifications(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    data = response.json()
    assert isinstance(data["notifications"]["created_last_24h"], int)
    assert isinstance(data["notifications"]["unread_total"], int)
    assert data["notifications"]["unread_total"] == 2
    assert data["notifications"]["source"] == "database"


def test_monitoring_pending_moderation(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    data = response.json()
    assert data["moderation"]["pending_fields"] == 2


def test_monitoring_database_health(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    data = response.json()
    assert data["database"]["healthy"] is True
    assert data["database"]["error_type"] is None


def test_monitoring_unavailable_metrics_marked(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    data = response.json()

    assert data["api_errors"]["source_available"] is True
    assert data["api_errors"]["source"] == "database"
    assert data["response_time"]["source_available"] is True
    assert data["response_time"]["source"] == "database"

    for key in ("scheduled_jobs", "push_notifications"):
        assert data[key]["source_available"] is False
        assert "reason" in data[key]
        assert isinstance(data[key]["reason"], str)
        assert len(data[key]["reason"]) > 10


def test_monitoring_scheduled_jobs_returns_recent_runs(monkeypatch) -> None:
    admin_user, _, fake_client = _make_monitoring_client(monkeypatch)
    fake_client.tables["job_runs"] = [
        {
            "id": "run-old",
            "job_name": "game_expiry_reconciliation",
            "status": "succeeded",
            "started_at": "2026-07-14T10:00:00+00:00",
            "finished_at": "2026-07-14T10:00:01+00:00",
            "duration_ms": 1000,
            "processed_count": 0,
            "scanned_count": 0,
            "reconciled_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "batch_count": 1,
            "reached_max_batches": False,
            "error_type": None,
            "error_message": None,
            "metadata": {"batch_size": 100, "max_batches": 50},
            "created_at": "2026-07-14T10:00:00+00:00",
            "updated_at": "2026-07-14T10:00:01+00:00",
        },
        {
            "id": "run-new",
            "job_name": "game_expiry_reconciliation",
            "status": "failed",
            "started_at": "2026-07-14T11:00:00+00:00",
            "finished_at": "2026-07-14T11:00:02+00:00",
            "duration_ms": 2000,
            "processed_count": None,
            "scanned_count": None,
            "reconciled_count": None,
            "skipped_count": None,
            "failed_count": None,
            "batch_count": None,
            "reached_max_batches": None,
            "error_type": "RuntimeError",
            "error_message": "database unavailable",
            "metadata": {"batch_size": 100, "max_batches": 50},
            "created_at": "2026-07-14T11:00:00+00:00",
            "updated_at": "2026-07-14T11:00:02+00:00",
        },
    ]
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: fake_client)

    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )

    assert response.status_code == 200
    scheduled_jobs = response.json()["scheduled_jobs"]
    assert scheduled_jobs["source_available"] is True
    assert scheduled_jobs["source"] == "database"
    assert scheduled_jobs["job_name"] == "game_expiry_reconciliation"
    assert scheduled_jobs["latest_status"] == "failed"
    assert [run["id"] for run in scheduled_jobs["recent_runs"]] == ["run-new", "run-old"]


def test_monitoring_no_sensitive_data(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    raw = response.text

    for sensitive in SENSITIVE_STRINGS:
        assert sensitive.lower() not in raw.lower(), (
            f"Sensitive string '{sensitive}' found in monitoring response"
        )

    assert "admin@" not in raw
    assert "user@" not in raw
    assert "stale@" not in raw
    assert "phone" not in raw.lower() or "phone_is_null" in raw.lower() or "phone_number" not in raw
    assert "token" not in raw.lower() or "push_token" not in raw.lower()


def test_monitoring_status_and_generated_at(monkeypatch) -> None:
    admin_user, _, _ = _make_monitoring_client(monkeypatch)
    response = TestClient(app).get(
        "/admin/monitoring",
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )
    data = response.json()
    assert data["status"] in ("ok", "degraded")
    assert "generated_at" in data
    assert "T" in data["generated_at"]


def _ensure_metric_test_routes() -> None:
    if getattr(app.state, "metric_test_routes_registered", False):
        return

    def metric_success():
        return {"ok": True}

    def metric_http_error(code: int):
        raise HTTPException(status_code=code, detail=f"test {code}")

    def metric_unhandled_error():
        raise RuntimeError("test unhandled failure")

    app.add_api_route("/__test_metrics/success", metric_success, methods=["GET"])
    app.add_api_route("/__test_metrics/http/{code}", metric_http_error, methods=["GET"])
    app.add_api_route("/__test_metrics/unhandled", metric_unhandled_error, methods=["GET"])
    app.state.metric_test_routes_registered = True


def _metric_row(
    *,
    minutes_ago: int = 1,
    status_code: int = 200,
    method: str = "GET",
    normalized_path: str = "/__seeded__",
    duration_ms: int = 12,
) -> dict[str, Any]:
    recorded_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {
        "id": f"metric-{minutes_ago}-{status_code}-{normalized_path}",
        "recorded_at": recorded_at.isoformat(),
        "method": method,
        "normalized_path": normalized_path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "is_error": 500 <= status_code <= 599,
    }


def _make_metric_monitoring_client(monkeypatch, metrics_rows=None) -> tuple[dict[str, Any], FakeSupabaseClient]:
    configure_test_settings(monkeypatch)
    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
        "status": "active",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user],
            "fields": [],
            "games": [],
            "notifications": [],
            "job_runs": [],
            "api_request_metrics": list(metrics_rows or []),
        },
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: fake_client,
    )
    return admin_user, fake_client


def _get_admin_monitoring(admin_user: dict[str, Any], *, window_minutes: int | None = None):
    params = {"window_minutes": window_minutes} if window_minutes is not None else None
    return TestClient(app).get(
        "/admin/monitoring",
        params=params,
        headers={"Authorization": f"Bearer {make_token(admin_user)}"},
    )


def test_monitoring_api_errors_default_window_zero_requests(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(monkeypatch)

    response = _get_admin_monitoring(admin_user)

    assert response.status_code == 200
    api_errors = response.json()["api_errors"]
    assert api_errors["window_minutes"] == 60
    assert api_errors["total_requests"] == 0
    assert api_errors["failed_requests"] == 0
    assert api_errors["error_rate"] == 0.0
    response_time = response.json()["response_time"]
    assert response_time["window_minutes"] == 60
    assert response_time["sample_count"] == 0
    assert response_time["average_ms"] == 0.0
    assert response_time["p50_ms"] == 0.0
    assert response_time["p95_ms"] == 0.0
    assert response_time["max_ms"] == 0.0


def test_monitoring_api_errors_custom_valid_window(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [
            _metric_row(minutes_ago=10, status_code=200),
            _metric_row(minutes_ago=70, status_code=200),
        ],
    )

    one_hour = _get_admin_monitoring(admin_user, window_minutes=60).json()["api_errors"]
    two_hours = _get_admin_monitoring(admin_user, window_minutes=120).json()["api_errors"]

    assert one_hour["window_minutes"] == 60
    assert one_hour["total_requests"] == 1
    assert two_hours["window_minutes"] == 120
    assert two_hours["total_requests"] == 2


def test_monitoring_response_time_custom_valid_window(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [
            _metric_row(minutes_ago=10, status_code=200, duration_ms=100),
            _metric_row(minutes_ago=70, status_code=200, duration_ms=300),
        ],
    )

    one_hour = _get_admin_monitoring(admin_user, window_minutes=60).json()["response_time"]
    two_hours = _get_admin_monitoring(admin_user, window_minutes=120).json()["response_time"]

    assert one_hour["window_minutes"] == 60
    assert one_hour["sample_count"] == 1
    assert one_hour["average_ms"] == 100.0
    assert two_hours["window_minutes"] == 120
    assert two_hours["sample_count"] == 2
    assert two_hours["average_ms"] == 200.0


@pytest.mark.parametrize("window_minutes", [4, 1441])
def test_monitoring_rejects_invalid_window_minutes(monkeypatch, window_minutes: int) -> None:
    admin_user, _ = _make_metric_monitoring_client(monkeypatch)

    response = _get_admin_monitoring(admin_user, window_minutes=window_minutes)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_monitoring_api_error_rate_counts_5xx_only(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [
            _metric_row(minutes_ago=1, status_code=200),
            _metric_row(minutes_ago=2, status_code=204),
            _metric_row(minutes_ago=3, status_code=400),
            _metric_row(minutes_ago=4, status_code=401),
            _metric_row(minutes_ago=5, status_code=403),
            _metric_row(minutes_ago=6, status_code=404),
            _metric_row(minutes_ago=7, status_code=409),
            _metric_row(minutes_ago=8, status_code=422),
            _metric_row(minutes_ago=9, status_code=500),
            _metric_row(minutes_ago=10, status_code=503),
        ],
    )

    response = _get_admin_monitoring(admin_user)

    assert response.status_code == 200
    api_errors = response.json()["api_errors"]
    assert api_errors["total_requests"] == 10
    assert api_errors["failed_requests"] == 2
    assert api_errors["error_rate"] == 0.2


def test_monitoring_response_time_one_sample(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [_metric_row(minutes_ago=1, status_code=200, duration_ms=37)],
    )

    response_time = _get_admin_monitoring(admin_user).json()["response_time"]

    assert response_time["sample_count"] == 1
    assert response_time["average_ms"] == 37.0
    assert response_time["p50_ms"] == 37.0
    assert response_time["p95_ms"] == 37.0
    assert response_time["max_ms"] == 37.0


def test_monitoring_response_time_average_percentiles_and_max(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [
            _metric_row(minutes_ago=1, duration_ms=0),
            _metric_row(minutes_ago=2, duration_ms=100),
            _metric_row(minutes_ago=3, duration_ms=200),
            _metric_row(minutes_ago=4, duration_ms=1000),
        ],
    )

    response_time = _get_admin_monitoring(admin_user).json()["response_time"]

    assert response_time["sample_count"] == 4
    assert response_time["average_ms"] == 325.0
    assert response_time["p50_ms"] == 150.0
    assert response_time["p95_ms"] == 880.0
    assert response_time["max_ms"] == 1000.0


def test_monitoring_response_time_identical_and_odd_sample_counts(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [
            _metric_row(minutes_ago=1, duration_ms=42),
            _metric_row(minutes_ago=2, duration_ms=42),
            _metric_row(minutes_ago=3, duration_ms=42),
        ],
    )

    response_time = _get_admin_monitoring(admin_user).json()["response_time"]

    assert response_time["sample_count"] == 3
    assert response_time["average_ms"] == 42.0
    assert response_time["p50_ms"] == 42.0
    assert response_time["p95_ms"] == 42.0
    assert response_time["max_ms"] == 42.0


def test_monitoring_response_time_includes_mixed_statuses_and_5xx(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [
            _metric_row(minutes_ago=1, status_code=200, duration_ms=10),
            _metric_row(minutes_ago=2, status_code=404, duration_ms=20),
            _metric_row(minutes_ago=3, status_code=422, duration_ms=30),
            _metric_row(minutes_ago=4, status_code=500, duration_ms=900),
        ],
    )

    data = _get_admin_monitoring(admin_user).json()

    assert data["api_errors"]["total_requests"] == 4
    assert data["api_errors"]["failed_requests"] == 1
    assert data["response_time"]["sample_count"] == 4
    assert data["response_time"]["max_ms"] == 900.0


def test_monitoring_response_time_uses_same_window_boundaries_as_api_errors(monkeypatch) -> None:
    admin_user, fake_client = _make_metric_monitoring_client(
        monkeypatch,
        [_metric_row(minutes_ago=1, status_code=200, duration_ms=15)],
    )

    data = _get_admin_monitoring(admin_user).json()
    response_time_calls = _response_time_rpc_calls(fake_client)

    assert len(response_time_calls) == 1
    assert response_time_calls[0]["window_start"] == data["api_errors"]["window_started_at"]
    assert response_time_calls[0]["window_end"] == data["api_errors"]["window_ended_at"]
    assert data["response_time"]["window_started_at"] == data["api_errors"]["window_started_at"]
    assert data["response_time"]["window_ended_at"] == data["api_errors"]["window_ended_at"]


def test_monitoring_response_time_boundaries_include_start_exclude_end(monkeypatch) -> None:
    fixed_now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    window_start = fixed_now - timedelta(minutes=60)
    monkeypatch.setattr("app.api.admin.get_now", lambda: fixed_now)
    admin_user, _ = _make_metric_monitoring_client(
        monkeypatch,
        [
            {
                **_metric_row(duration_ms=10),
                "recorded_at": window_start.isoformat(),
            },
            {
                **_metric_row(duration_ms=20),
                "recorded_at": fixed_now.isoformat(),
            },
        ],
    )

    response_time = _get_admin_monitoring(admin_user).json()["response_time"]

    assert response_time["sample_count"] == 1
    assert response_time["max_ms"] == 10.0


def test_monitoring_response_timestamps_are_utc(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(monkeypatch)

    data = _get_admin_monitoring(admin_user).json()
    api_errors = data["api_errors"]
    response_time = data["response_time"]

    started = datetime.fromisoformat(api_errors["window_started_at"])
    ended = datetime.fromisoformat(api_errors["window_ended_at"])
    assert started.tzinfo is not None
    assert ended.tzinfo is not None
    assert started.utcoffset() == timedelta(0)
    assert ended.utcoffset() == timedelta(0)
    assert response_time["window_started_at"] == api_errors["window_started_at"]
    assert response_time["window_ended_at"] == api_errors["window_ended_at"]


def test_monitoring_response_time_stub_removed(monkeypatch) -> None:
    admin_user, _ = _make_metric_monitoring_client(monkeypatch)

    response = _get_admin_monitoring(admin_user)

    assert response.status_code == 200
    raw = response.text
    assert "Response-time middleware not implemented yet" not in raw
    assert "reason" not in response.json()["response_time"]
    assert response.json()["response_time"]["source_available"] is True


def test_monitoring_response_time_rpc_failure_returns_unavailable_source(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
        "status": "active",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user],
            "fields": [],
            "games": [],
            "notifications": [],
            "api_request_metrics": [_metric_row(minutes_ago=1, status_code=200)],
        },
        rpc_responses={"get_api_response_time_metrics": RuntimeError("rpc unavailable")},
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: fake_client,
    )

    response = _get_admin_monitoring(admin_user)

    assert response.status_code == 200
    data = response.json()
    assert data["api_errors"]["source_available"] is True
    assert data["api_errors"]["total_requests"] == 1
    assert data["response_time"]["source_available"] is False
    assert "reason" in data["response_time"]
    assert "rpc unavailable" not in data["response_time"]["reason"]


def test_request_metrics_middleware_records_success_and_excludes_monitoring(monkeypatch) -> None:
    _ensure_metric_test_routes()
    admin_user, fake_client = _make_metric_monitoring_client(monkeypatch)

    success_response = TestClient(app).get("/__test_metrics/success?token=secret")
    monitoring_response = _get_admin_monitoring(admin_user)

    assert success_response.status_code == 200
    assert monitoring_response.status_code == 200
    rows = fake_client.tables["api_request_metrics"]
    assert len(rows) == 1
    assert rows[0]["method"] == "GET"
    assert rows[0]["normalized_path"] == "/__test_metrics/success"
    assert rows[0]["status_code"] == 200
    assert rows[0]["is_error"] is False
    assert "token" not in str(rows[0]).lower()
    assert "secret" not in str(rows[0]).lower()


def test_request_metrics_middleware_records_5xx_and_4xx_correctly(monkeypatch) -> None:
    _ensure_metric_test_routes()
    _, fake_client = _make_metric_monitoring_client(monkeypatch)
    client = TestClient(app, raise_server_exceptions=False)

    client.get("/__test_metrics/http/404")
    client.get("/__test_metrics/http/500")
    client.get("/__test_metrics/unhandled")

    rows = fake_client.tables["api_request_metrics"]
    statuses = [row["status_code"] for row in rows]
    assert statuses == [404, 500, 500]
    assert [row["is_error"] for row in rows] == [False, True, True]
    assert rows[0]["normalized_path"] == "/__test_metrics/http/{code}"
    assert rows[2]["normalized_path"] == "/__test_metrics/unhandled"


def test_request_metrics_middleware_excludes_health_and_options(monkeypatch) -> None:
    _ensure_metric_test_routes()
    _, fake_client = _make_metric_monitoring_client(monkeypatch)

    TestClient(app).get("/")
    TestClient(app).options("/__test_metrics/success")

    assert fake_client.tables["api_request_metrics"] == []


def test_request_metric_write_failure_does_not_break_response(monkeypatch, caplog) -> None:
    _ensure_metric_test_routes()
    configure_test_settings(monkeypatch)

    class BrokenInsertQuery(FakeUsersQuery):
        def insert(self, payload: dict[str, Any]) -> "FakeUsersQuery":
            raise RuntimeError("metrics table unavailable")

    class BrokenInsertClient(FakeSupabaseClient):
        def table(self, table_name: str) -> FakeUsersQuery:
            if table_name == "api_request_metrics":
                return BrokenInsertQuery([])
            return super().table(table_name)

    broken_client = BrokenInsertClient({}, tables={"users": [], "api_request_metrics": []})
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: broken_client,
    )

    with caplog.at_level(logging.WARNING, logger="app.middleware.request_metrics"):
        response = TestClient(app).get("/__test_metrics/success")

    assert response.status_code == 200
    assert any(
        getattr(record, "event", None) == "api_request_metrics.persist.failure"
        for record in caplog.records
    )


def test_monitoring_metric_read_failure_returns_unavailable(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    admin_user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "email": "admin@example.com",
        "name": "Admin User",
        "role": "admin",
        "status": "active",
    }
    fake_client = FakeSupabaseClient(
        {},
        tables={
            "users": [admin_user],
            "fields": [],
            "games": [],
            "notifications": [],
        },
    )

    class BrokenReadClient(FakeSupabaseClient):
        def table(self, table_name: str) -> FakeUsersQuery:
            raise RuntimeError("metrics read unavailable")

    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake_client)
    monkeypatch.setattr(
        "app.services.api_request_metrics.get_supabase_service_role_client",
        lambda: BrokenReadClient({}, tables={}),
    )

    response = _get_admin_monitoring(admin_user)

    assert response.status_code == 503
    assert response.json()["code"] == "MONITORING_UNAVAILABLE"
