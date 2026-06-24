from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.selected_columns: list[str] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.limit_count: int | None = None

    def select(self, columns: str = "*") -> "FakeQuery":
        self.selected_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.insert_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            if self.database.fail_field_report_insert and self.table_name == "field_reports":
                raise RuntimeError("insert failed")

            row = dict(self.insert_payload)
            row.setdefault("id", f"{self.table_name}-{len(self.database.tables[self.table_name]) + 1}")
            if self.table_name == "field_reports":
                row.setdefault("status", "open")
                row.setdefault("created_at", "2026-06-21T12:00:00+00:00")
                row.setdefault("reviewed_at", None)
                row.setdefault("reviewed_by", None)
            self.database.tables[self.table_name].append(row)
            return FakeResponse([dict(row)])

        rows = self.database.tables.setdefault(self.table_name, [])
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return FakeResponse([self._select(row) for row in rows])

    def _select(self, row: dict[str, Any]) -> dict[str, Any]:
        if not self.selected_columns or "*" in self.selected_columns:
            return dict(row)
        return {column: row.get(column) for column in self.selected_columns}


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.fail_field_report_insert = False

    def table(self, table_name: str) -> FakeQuery:
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)


def configure_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def make_user(user_id: str = "user-1") -> dict[str, str]:
    return {
        "id": user_id,
        "email": f"{user_id}@example.com",
        "name": user_id,
        "role": "user",
    }


def auth_headers(user: dict[str, str]) -> dict[str, str]:
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def make_fake_supabase(user: dict[str, str]) -> FakeSupabase:
    return FakeSupabase(
        {
            "users": [user],
            "fields": [{"id": "field-1", "name": "Central Court"}],
            "field_reports": [],
        }
    )


def make_client(monkeypatch, fake_supabase: FakeSupabase) -> TestClient:
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake_supabase)
    monkeypatch.setattr("app.routers.field_reports.get_supabase_client", lambda: fake_supabase)
    return TestClient(app)


def test_authenticated_user_can_submit_field_report(monkeypatch, caplog) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake_supabase = make_fake_supabase(user)
    client = make_client(monkeypatch, fake_supabase)

    with caplog.at_level(logging.INFO, logger="app.routers.field_reports"):
        response = client.post(
            "/field-reports",
            json={
                "field_id": "field-1",
                "category": "wrong_location",
                "description": "The pin is on the wrong block.",
            },
            headers=auth_headers(user),
        )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["field_id"] == "field-1"
    assert report["user_id"] == user["id"]
    assert report["category"] == "wrong_location"
    assert report["description"] == "The pin is on the wrong block."
    assert report["status"] == "open"
    assert report["reviewed_at"] is None
    assert report["reviewed_by"] is None

    selected = (
        fake_supabase.table("field_reports")
        .select("*")
        .eq("id", report["id"])
        .limit(1)
        .execute()
        .data
    )
    assert selected == [report]
    success_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "field_reports.create.success"
    ]
    assert success_records
    assert success_records[-1].report_id == report["id"]
    assert success_records[-1].field_id == "field-1"
    assert success_records[-1].user_id == user["id"]
    assert "The pin is on the wrong block." not in caplog.text


def test_field_report_description_is_optional(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake_supabase = make_fake_supabase(user)
    client = make_client(monkeypatch, fake_supabase)

    response = client.post(
        "/field-reports",
        json={"field_id": "field-1", "category": "other"},
        headers=auth_headers(user),
    )

    assert response.status_code == 200
    assert response.json()["report"]["description"] is None


def test_field_report_rejects_invalid_category(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake_supabase = make_fake_supabase(user)
    client = make_client(monkeypatch, fake_supabase)

    response = client.post(
        "/field-reports",
        json={"field_id": "field-1", "category": "bad_category"},
        headers=auth_headers(user),
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Invalid field report category"
    assert response.json()["error"] is True
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert fake_supabase.tables["field_reports"] == []


def test_field_report_rejects_missing_field(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake_supabase = make_fake_supabase(user)
    client = make_client(monkeypatch, fake_supabase)

    response = client.post(
        "/field-reports",
        json={"field_id": "missing-field", "category": "wrong_information"},
        headers=auth_headers(user),
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Field not found"
    assert response.json()["error"] is True
    assert response.json()["code"] == "FIELD_NOT_FOUND"
    assert fake_supabase.tables["field_reports"] == []


def test_field_report_requires_authentication(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake_supabase = make_fake_supabase(user)
    client = make_client(monkeypatch, fake_supabase)

    response = client.post(
        "/field-reports",
        json={"field_id": "field-1", "category": "wrong_location"},
    )

    assert response.status_code == 401
    assert fake_supabase.tables["field_reports"] == []


def test_field_report_rejects_client_controlled_review_fields(monkeypatch) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake_supabase = make_fake_supabase(user)
    client = make_client(monkeypatch, fake_supabase)

    response = client.post(
        "/field-reports",
        json={
            "field_id": "field-1",
            "category": "wrong_location",
            "status": "resolved",
            "reviewed_at": "2026-06-21T12:00:00+00:00",
            "reviewed_by": "admin-1",
        },
        headers=auth_headers(user),
    )

    assert response.status_code == 422
    assert fake_supabase.tables["field_reports"] == []


def test_field_report_insert_failure_returns_clean_api_error(monkeypatch, caplog) -> None:
    configure_settings(monkeypatch)
    user = make_user()
    fake_supabase = make_fake_supabase(user)
    fake_supabase.fail_field_report_insert = True
    client = make_client(monkeypatch, fake_supabase)

    with caplog.at_level(logging.ERROR, logger="app.routers.field_reports"):
        response = client.post(
            "/field-reports",
            json={"field_id": "field-1", "category": "field_closed"},
            headers=auth_headers(user),
        )

    assert response.status_code == 500
    assert response.json()["message"] == "Failed to create field report"
    assert response.json()["error"] is True
    assert response.json()["code"] == "DATABASE_ERROR"
    failure_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "field_reports.create.failure"
    ]
    assert failure_records
    assert failure_records[-1].error_code == "DATABASE_ERROR"
    assert failure_records[-1].field_id == "field-1"
