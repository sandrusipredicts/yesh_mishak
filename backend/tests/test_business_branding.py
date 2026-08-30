from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.auth.dependencies import require_admin
from app.main import app
from app.core.config import get_settings
from test_manual_auth import configure_test_settings


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]


class FakeTableQuery:
    def __init__(self, tables: dict[str, list[dict[str, Any]]], table_name: str):
        self.tables = tables
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.select_columns: list[str] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.insert_payload: dict[str, Any] | None = None

    def select(self, columns: str) -> "FakeTableQuery":
        self.select_columns = [column.strip() for column in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeTableQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _: int) -> "FakeTableQuery":
        return self

    def update(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.update_payload = payload
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeTableQuery":
        self.insert_payload = payload
        return self

    def execute(self) -> FakeResponse:
        rows = self.tables.setdefault(self.table_name, [])

        if self.insert_payload is not None:
            inserted = dict(self.insert_payload)
            rows.append(inserted)
            return FakeResponse(data=[inserted])

        filtered_rows = self._filter_rows(rows)

        if self.update_payload is not None:
            for row in filtered_rows:
                row.update(self.update_payload)
            return FakeResponse(data=[dict(row) for row in filtered_rows])

        if self.select_columns is None or "*" in self.select_columns:
            return FakeResponse(data=[dict(row) for row in filtered_rows])

        return FakeResponse(
            data=[
                {column: row.get(column) for column in self.select_columns}
                for row in filtered_rows
            ]
        )

    def _filter_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered = rows
        for column, value in self.filters:
            filtered = [row for row in filtered if row.get(column) == value]
        return filtered


class FakeSupabaseClient:
    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, table_name: str) -> FakeTableQuery:
        return FakeTableQuery(self.tables, table_name)


def _override_admin() -> dict[str, Any]:
    return {
        "id": "00000000-0000-0000-0000-000000000111",
        "email": "admin@example.com",
        "name": "Admin",
        "role": "admin",
    }


def test_business_branding_update_is_persisted_and_exposed(monkeypatch):
    configure_test_settings(monkeypatch)
    fake = FakeSupabaseClient()

    monkeypatch.setattr("app.services.business_branding.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.services.business_branding.get_supabase_service_role_client", lambda: fake)

    app.dependency_overrides[require_admin] = _override_admin
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/admin/settings/business-branding",
                json={"business_name": "Ofir's Barbershop"},
            )
            assert response.status_code == 200
            assert response.json()["business_name"] == "Ofir's Barbershop"

            response = client.patch(
                "/admin/settings/business-branding",
                json={"business_name": "ZOHAR"},
            )
            assert response.status_code == 200
            assert response.json()["business_name"] == "ZOHAR"

            public_response = client.get("/branding")
            assert public_response.status_code == 200
            assert public_response.json() == {
                "business_name": "ZOHAR",
                "source": "persisted",
            }

            admin_response = client.get("/admin/settings/business-branding")
            assert admin_response.status_code == 200
            assert admin_response.json()["business_name"] == "ZOHAR"
    finally:
        app.dependency_overrides.pop(require_admin, None)
        get_settings.cache_clear()


def test_business_branding_uses_default_then_generic_fallback(monkeypatch):
    configure_test_settings(monkeypatch)
    fake = FakeSupabaseClient()

    monkeypatch.setenv("DEFAULT_BUSINESS_NAME", "Tenant Default")
    monkeypatch.setenv("FALLBACK_BUSINESS_NAME", "")
    get_settings.cache_clear()

    monkeypatch.setattr("app.services.business_branding.get_supabase_client", lambda: fake)

    with TestClient(app) as client:
        response = client.get("/branding")
        assert response.status_code == 200
        assert response.json() == {
            "business_name": "Tenant Default",
            "source": "default",
        }

    monkeypatch.setenv("DEFAULT_BUSINESS_NAME", "")
    monkeypatch.setenv("FALLBACK_BUSINESS_NAME", "")
    get_settings.cache_clear()

    with TestClient(app) as client:
        response = client.get("/branding")
        assert response.status_code == 200
        assert response.json() == {
            "business_name": "Business",
            "source": "default",
        }
