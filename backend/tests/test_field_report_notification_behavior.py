"""Tests for create_field_report_status_notification behavior.

Tests the actual notification creation function, not just templates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.core.config import get_settings


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.selected_columns: list[str] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.limit_count: int | None = None

    def select(self, columns: str = "*") -> "FakeQuery":
        self.selected_columns = [c.strip() for c in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.in_filters.append((column, values))
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.insert_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            if self.database.fail_insert:
                raise RuntimeError("insert failed")
            row = dict(self.insert_payload)
            row.setdefault("id", f"notif-{len(self.database.tables.get(self.table_name, [])) + 1}")
            self.database.tables.setdefault(self.table_name, []).append(row)
            return FakeResponse([dict(row)])

        rows = list(self.database.tables.get(self.table_name, []))
        for column, value in self.filters:
            rows = [r for r in rows if r.get(column) == value]
        for column, values in self.in_filters:
            rows = [r for r in rows if r.get(column) in values]
        if self.limit_count is not None:
            rows = rows[:self.limit_count]
        if self.selected_columns and "*" not in self.selected_columns:
            return FakeResponse([{c: r.get(c) for c in self.selected_columns} for r in rows])
        return FakeResponse([dict(r) for r in rows])


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.fail_insert = False

    def table(self, table_name: str) -> FakeQuery:
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)


REPORTER_ID = "user-reporter"
OTHER_USER_ID = "user-other"
FIELD_ID = "field-1"
REPORT_ID = "report-1"
OTHER_REPORT_ID = "report-2"


def make_report(report_id=REPORT_ID, user_id=REPORTER_ID, field_id=FIELD_ID):
    return {
        "id": report_id,
        "field_id": field_id,
        "user_id": user_id,
        "category": "wrong_location",
        "status": "open",
    }


def configure(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def make_fake(notifications=None):
    return FakeSupabase({
        "fields": [{"id": FIELD_ID, "name": "Central Court"}],
        "notifications": notifications or [],
        "push_subscriptions": [],
    })


def call_create(monkeypatch, fake, report, new_status):
    monkeypatch.setattr(
        "app.routers.notifications.get_supabase_service_role_client", lambda: fake
    )
    from app.routers.notifications import create_field_report_status_notification
    return create_field_report_status_notification(report=report, new_status=new_status)


def test_open_to_in_review_creates_notification(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    result = call_create(monkeypatch, fake, make_report(), "in_review")

    assert len(result) == 1
    assert len(fake.tables["notifications"]) == 1


def test_open_to_resolved_creates_notification(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    result = call_create(monkeypatch, fake, make_report(), "resolved")

    assert len(result) == 1
    assert len(fake.tables["notifications"]) == 1


def test_open_to_rejected_creates_notification(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    result = call_create(monkeypatch, fake, make_report(), "rejected")

    assert len(result) == 1
    assert len(fake.tables["notifications"]) == 1


def test_same_status_twice_no_duplicate(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    call_create(monkeypatch, fake, make_report(), "resolved")
    result = call_create(monkeypatch, fake, make_report(), "resolved")

    assert result == []
    assert len(fake.tables["notifications"]) == 1


def test_different_status_creates_new_notification(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    call_create(monkeypatch, fake, make_report(), "in_review")
    result = call_create(monkeypatch, fake, make_report(), "resolved")

    assert len(result) == 1
    assert len(fake.tables["notifications"]) == 2


def test_other_report_does_not_block(monkeypatch):
    configure(monkeypatch)
    existing_notif = {
        "id": "existing-1",
        "user_id": REPORTER_ID,
        "type": "field_report_status_changed",
        "title": "t",
        "body": "b",
        "data": {
            "field_report_id": OTHER_REPORT_ID,
            "new_status": "resolved",
        },
    }
    fake = make_fake(notifications=[existing_notif])
    result = call_create(monkeypatch, fake, make_report(), "resolved")

    assert len(result) == 1
    assert len(fake.tables["notifications"]) == 2


def test_other_user_does_not_block(monkeypatch):
    configure(monkeypatch)
    existing_notif = {
        "id": "existing-1",
        "user_id": OTHER_USER_ID,
        "type": "field_report_status_changed",
        "title": "t",
        "body": "b",
        "data": {
            "field_report_id": REPORT_ID,
            "new_status": "resolved",
        },
    }
    fake = make_fake(notifications=[existing_notif])
    result = call_create(monkeypatch, fake, make_report(), "resolved")

    assert len(result) == 1


def test_insert_failure_raises(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    fake.fail_insert = True

    with pytest.raises(RuntimeError):
        call_create(monkeypatch, fake, make_report(), "resolved")


def test_notification_payload_correct(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    result = call_create(monkeypatch, fake, make_report(), "resolved")

    notif = result[0]
    assert notif["user_id"] == REPORTER_ID
    assert notif["type"] == "field_report_status_changed"
    assert notif["field_id"] == FIELD_ID

    data = notif["data"]
    assert data["field_report_id"] == REPORT_ID
    assert data["field_id"] == FIELD_ID
    assert data["new_status"] == "resolved"
    assert data["type"] == "field_report_status_changed"


def test_no_admin_identity_exposed(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    result = call_create(monkeypatch, fake, make_report(), "resolved")

    notif = result[0]
    notif_str = str(notif)
    assert "admin" not in notif_str.lower() or "admin_note" in notif_str.lower() or notif_str.lower().count("admin") == 0
    assert "reviewed_by" not in notif
    data = notif["data"]
    assert "reviewed_by" not in data
    assert "admin_id" not in data


def test_missing_reporter_returns_empty(monkeypatch):
    configure(monkeypatch)
    fake = make_fake()
    report = make_report()
    report["user_id"] = None
    result = call_create(monkeypatch, fake, report, "resolved")

    assert result == []
    assert len(fake.tables["notifications"]) == 0
