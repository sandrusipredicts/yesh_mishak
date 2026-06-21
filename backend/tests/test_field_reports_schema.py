from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_SQL = (BACKEND_DIR / "migrations" / "field_reports.sql").read_text()
SCHEMA_SQL = (BACKEND_DIR / "schema.sql").read_text()


def _field_reports_table_sql(sql: str) -> str:
    match = re.search(
        r"create table if not exists field_reports\s*\((.*?)\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match, "field_reports table was not found"
    return match.group(1)


def _extract_allowed_values(sql: str, column_name: str) -> set[str]:
    sql = _field_reports_table_sql(sql)
    pattern = rf"{column_name}\s+text\s+not\s+null.*?{column_name}\s+in\s*\((.*?)\)"
    match = re.search(pattern, sql, flags=re.IGNORECASE | re.DOTALL)
    assert match, f"{column_name} check constraint was not found"
    return set(re.findall(r"'([^']+)'", match.group(1)))


APPROVED_CATEGORIES = {
    "wrong_location",
    "field_does_not_exist",
    "field_closed",
    "under_renovation",
    "private_field",
    "duplicate_field",
    "wrong_information",
    "other",
}
APPROVED_STATUSES = {"open", "in_review", "resolved", "rejected"}


class FakeFieldReportsTable:
    def __init__(self, allowed_categories: set[str], allowed_statuses: set[str]) -> None:
        self.allowed_categories = allowed_categories
        self.allowed_statuses = allowed_statuses
        self.rows: list[dict[str, Any]] = []

    def insert(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = dict(payload)
        row.setdefault("id", f"report-{len(self.rows) + 1}")
        row.setdefault("status", "open")
        row.setdefault("created_at", "2026-06-21T00:00:00+00:00")
        row.setdefault("reviewed_at", None)
        row.setdefault("reviewed_by", None)

        required_columns = ("field_id", "user_id", "category", "status", "created_at")
        for column in required_columns:
            if row.get(column) is None:
                raise ValueError(f"{column} is required")

        if row["category"] not in self.allowed_categories:
            raise ValueError("Invalid field report category")
        if row["status"] not in self.allowed_statuses:
            raise ValueError("Invalid field report status")

        self.rows.append(row)
        return dict(row)

    def select(self, report_id: str) -> dict[str, Any] | None:
        return next((dict(row) for row in self.rows if row["id"] == report_id), None)


def make_field_reports_table() -> FakeFieldReportsTable:
    return FakeFieldReportsTable(
        allowed_categories=_extract_allowed_values(MIGRATION_SQL, "category"),
        allowed_statuses=_extract_allowed_values(MIGRATION_SQL, "status"),
    )


def test_field_reports_migration_defines_required_table_columns_and_constraints() -> None:
    assert "create table if not exists field_reports" in MIGRATION_SQL
    assert "id uuid primary key default gen_random_uuid()" in MIGRATION_SQL
    assert "field_id uuid not null references fields(id) on delete cascade" in MIGRATION_SQL
    assert "user_id uuid not null references users(id) on delete cascade" in MIGRATION_SQL
    assert "category text not null check" in MIGRATION_SQL
    assert "description text" in MIGRATION_SQL
    assert "status text not null default 'open' check" in MIGRATION_SQL
    assert "created_at timestamptz not null default now()" in MIGRATION_SQL
    assert "reviewed_at timestamptz" in MIGRATION_SQL
    assert "reviewed_by uuid references users(id) on delete set null" in MIGRATION_SQL
    assert _extract_allowed_values(MIGRATION_SQL, "category") == APPROVED_CATEGORIES
    assert _extract_allowed_values(MIGRATION_SQL, "status") == APPROVED_STATUSES


def test_field_reports_schema_sql_is_kept_in_sync_with_migration() -> None:
    assert "create table if not exists field_reports" in SCHEMA_SQL
    assert _extract_allowed_values(SCHEMA_SQL, "category") == APPROVED_CATEGORIES
    assert _extract_allowed_values(SCHEMA_SQL, "status") == APPROVED_STATUSES
    for index_name in (
        "idx_field_reports_field_id",
        "idx_field_reports_user_id",
        "idx_field_reports_status",
        "idx_field_reports_created_at",
        "idx_field_reports_field_id_status",
    ):
        assert index_name in MIGRATION_SQL
        assert index_name in SCHEMA_SQL


def test_valid_field_report_can_be_inserted_and_selected() -> None:
    table = make_field_reports_table()

    inserted = table.insert(
        {
            "field_id": "field-1",
            "user_id": "user-1",
            "category": "wrong_location",
            "description": "The marker is across the street.",
        }
    )

    assert inserted["status"] == "open"
    assert inserted["reviewed_at"] is None
    assert inserted["reviewed_by"] is None
    assert table.select(inserted["id"]) == inserted


def test_invalid_field_report_category_is_rejected() -> None:
    table = make_field_reports_table()

    with pytest.raises(ValueError, match="Invalid field report category"):
        table.insert(
            {
                "field_id": "field-1",
                "user_id": "user-1",
                "category": "bad_category",
            }
        )


def test_invalid_field_report_status_is_rejected() -> None:
    table = make_field_reports_table()

    with pytest.raises(ValueError, match="Invalid field report status"):
        table.insert(
            {
                "field_id": "field-1",
                "user_id": "user-1",
                "category": "field_closed",
                "status": "done",
            }
        )


def test_reviewed_fields_can_be_stored_when_provided() -> None:
    table = make_field_reports_table()

    inserted = table.insert(
        {
            "field_id": "field-1",
            "user_id": "user-1",
            "category": "other",
            "status": "resolved",
            "reviewed_at": "2026-06-21T12:00:00+00:00",
            "reviewed_by": "admin-1",
        }
    )

    assert inserted["status"] == "resolved"
    assert inserted["reviewed_at"] == "2026-06-21T12:00:00+00:00"
    assert inserted["reviewed_by"] == "admin-1"
