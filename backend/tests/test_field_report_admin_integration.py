from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app


@dataclass
class FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


class FakeQuery:
    def __init__(self, database: "FakeSupabase", table_name: str) -> None:
        self.database = database
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list[Any]]] = []
        self.selected_columns: list[str] | None = None
        self.update_payload: dict[str, Any] | None = None
        self.insert_payload: dict[str, Any] | None = None
        self.order_column: str | None = None
        self.order_desc: bool = False
        self.limit_count: int | None = None
        self._fail_insert = False

    def select(self, columns: str = "*", count: str | None = None) -> "FakeQuery":
        self.selected_columns = [c.strip() for c in columns.split(",")]
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.in_filters.append((column, values))
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        self.order_column = column
        self.order_desc = desc
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            if self.database.fail_notification_insert and self.table_name == "notifications":
                raise RuntimeError("notification insert failed")
            row = dict(self.insert_payload)
            row.setdefault("id", f"{self.table_name}-{len(self.database.tables.get(self.table_name, [])) + 1}")
            self.database.tables.setdefault(self.table_name, []).append(row)
            return FakeResponse([dict(row)])

        if self.update_payload is not None:
            if self.database.fail_field_report_update and self.table_name == "field_reports":
                raise RuntimeError("field report update failed")
            if self.database.malformed_field_report_update and self.table_name == "field_reports":
                return FakeResponse({"bad": "shape"})  # type: ignore[arg-type]
            if self.database.zero_row_field_report_update and self.table_name == "field_reports":
                return FakeResponse([])
            rows = self._filtered_rows()
            for row in rows:
                row.update(self.update_payload)
            return FakeResponse([dict(row) for row in rows])

        rows = self._filtered_rows()
        if self.limit_count is not None:
            rows = rows[: self.limit_count]
        return FakeResponse(
            [{c: r.get(c) for c in self.selected_columns} for r in rows]
            if self.selected_columns and "*" not in self.selected_columns
            else [dict(r) for r in rows]
        )

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self.database.tables.get(self.table_name, []))
        for column, value in self.filters:
            rows = [r for r in rows if r.get(column) == value]
        for column, values in self.in_filters:
            rows = [r for r in rows if r.get(column) in values]
        return rows


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.fail_notification_insert = False
        self.fail_field_report_update = False
        self.zero_row_field_report_update = False
        self.malformed_field_report_update = False

    def table(self, table_name: str) -> FakeQuery:
        self.tables.setdefault(table_name, [])
        return FakeQuery(self, table_name)


ADMIN_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000002"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000003"
FIELD_ID = "00000000-0000-0000-0000-000000000101"
REPORT_ID = "00000000-0000-0000-0000-000000000201"


def make_admin():
    return {"id": ADMIN_ID, "email": "admin@example.com", "name": "Admin", "role": "admin", "status": "active"}


def make_user(user_id=USER_ID):
    return {"id": user_id, "email": f"{user_id}@example.com", "name": "User", "role": "user", "status": "active"}


def make_report(report_id=REPORT_ID, user_id=USER_ID, status="open", admin_note=None):
    return {
        "id": report_id,
        "field_id": FIELD_ID,
        "user_id": user_id,
        "category": "wrong_location",
        "description": "Test report",
        "status": status,
        "admin_note": admin_note,
        "created_at": "2026-06-21T12:00:00+00:00",
        "reviewed_at": None,
        "reviewed_by": None,
    }


def auth_headers(user):
    token = create_access_token(subject=user["id"], email=user["email"])
    return {"Authorization": f"Bearer {token}"}


def configure(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def setup_client(monkeypatch, admin, users, reports, notifications=None):
    configure(monkeypatch)
    tables = {
        "users": [admin] + users,
        "fields": [{"id": FIELD_ID, "name": "Central Court"}],
        "field_reports": reports,
        "notifications": notifications or [],
        "push_subscriptions": [],
    }
    fake = FakeSupabase(tables)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: fake)
    return TestClient(app), fake


# --- Gap 1: Admin endpoint integration tests ---


def test_admin_can_update_status_and_set_admin_note(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved", "admin_note": "Fixed the location."},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["report"]["status"] == "resolved"
    assert data["report"]["admin_note"] == "Fixed the location."
    assert data["report"]["reviewed_by"] == ADMIN_ID


def test_status_update_uses_service_role_client_for_field_report_write(monkeypatch):
    configure(monkeypatch)
    admin = make_admin()
    user = make_user()
    report = make_report()
    anon_fake = FakeSupabase(
        {
            "users": [admin],
            "fields": [],
            "field_reports": [],
            "notifications": [],
            "push_subscriptions": [],
        }
    )
    service_fake = FakeSupabase(
        {
            "users": [admin, user],
            "fields": [{"id": FIELD_ID, "name": "Central Court"}],
            "field_reports": [report],
            "notifications": [],
            "push_subscriptions": [],
        }
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: anon_fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: anon_fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: service_fake)
    client = TestClient(app)

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "in_review"},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert service_fake.tables["field_reports"][0]["status"] == "in_review"
    assert anon_fake.tables["field_reports"] == []


def test_non_admin_receives_403(monkeypatch):
    admin = make_admin()
    user = make_user()
    report = make_report()
    client, _ = setup_client(monkeypatch, admin, [user], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved"},
        headers=auth_headers(user),
    )

    assert resp.status_code == 403


def test_unauthenticated_receives_401(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved"},
    )

    assert resp.status_code == 401


def test_missing_report_returns_404(monkeypatch):
    admin = make_admin()
    client, _ = setup_client(monkeypatch, admin, [make_user()], [])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved"},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "REPORT_NOT_FOUND"


def test_note_longer_than_1000_rejected(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved", "admin_note": "x" * 1001},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 422


def test_whitespace_only_note_normalized_to_null(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved", "admin_note": "   "},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] is None


def test_status_update_succeeds_when_notification_fails(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])
    fake.fail_notification_insert = True

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved"},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["status"] == "resolved"


def test_reporter_receives_notification_not_admin(monkeypatch):
    admin = make_admin()
    user = make_user()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [user], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "in_review"},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    notifications = fake.tables.get("notifications", [])
    assert len(notifications) == 1
    assert notifications[0]["user_id"] == USER_ID
    assert notifications[0]["user_id"] != ADMIN_ID


# --- Gap 3: admin_note update semantics ---


def test_admin_note_omitted_preserves_existing(monkeypatch):
    """Property omitted → preserves current note."""
    admin = make_admin()
    report = make_report(admin_note="Original note")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved"},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] == "Original note"


def test_admin_note_explicit_null_clears(monkeypatch):
    """Explicit null → clears note."""
    admin = make_admin()
    report = make_report(admin_note="Original note")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved", "admin_note": None},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] is None


def test_admin_note_empty_string_clears(monkeypatch):
    """Empty string → validator normalizes to None → clears note."""
    admin = make_admin()
    report = make_report(admin_note="Original note")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved", "admin_note": ""},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] is None


def test_admin_note_whitespace_only_clears(monkeypatch):
    """Whitespace-only string → validator normalizes to None → clears note."""
    admin = make_admin()
    report = make_report(admin_note="Original note")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved", "admin_note": "   \t  "},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] is None


def test_admin_note_nonempty_replaces(monkeypatch):
    """Non-empty string → replaces note (stripped)."""
    admin = make_admin()
    report = make_report(admin_note="Original note")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/status",
        json={"status": "resolved", "admin_note": "  New feedback.  "},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] == "New feedback."


def test_admin_can_resolve_open_report(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={"admin_note": "Fixed the location."},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Field report resolved"
    assert data["report"]["status"] == "resolved"
    assert data["report"]["admin_note"] == "Fixed the location."
    assert data["report"]["reviewed_by"] == ADMIN_ID
    assert data["report"]["reviewed_at"]
    assert fake.tables["field_reports"][0]["status"] == "resolved"
    assert fake.tables["field_reports"][0]["reviewed_by"] == ADMIN_ID


def test_resolve_uses_service_role_client_for_field_report_write(monkeypatch):
    configure(monkeypatch)
    admin = make_admin()
    user = make_user()
    report = make_report()
    anon_fake = FakeSupabase(
        {
            "users": [admin],
            "fields": [],
            "field_reports": [],
            "notifications": [],
            "push_subscriptions": [],
        }
    )
    service_fake = FakeSupabase(
        {
            "users": [admin, user],
            "fields": [{"id": FIELD_ID, "name": "Central Court"}],
            "field_reports": [report],
            "notifications": [],
            "push_subscriptions": [],
        }
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: anon_fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: anon_fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: service_fake)
    monkeypatch.setattr("app.routers.notifications.get_supabase_service_role_client", lambda: service_fake)
    client = TestClient(app)

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert service_fake.tables["field_reports"][0]["status"] == "resolved"
    assert anon_fake.tables["field_reports"] == []


def test_admin_can_resolve_in_review_report(monkeypatch):
    admin = make_admin()
    report = make_report(status="in_review")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["status"] == "resolved"


def test_resolve_preserves_admin_note_when_omitted(monkeypatch):
    admin = make_admin()
    report = make_report(admin_note="Existing note")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] == "Existing note"


def test_resolve_whitespace_note_normalized_to_null(monkeypatch):
    admin = make_admin()
    report = make_report(admin_note="Existing note")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={"admin_note": "   "},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert resp.json()["report"]["admin_note"] is None


def test_non_admin_cannot_resolve_report(monkeypatch):
    admin = make_admin()
    user = make_user()
    report = make_report()
    client, _ = setup_client(monkeypatch, admin, [user], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(user),
    )

    assert resp.status_code == 403


def test_unauthenticated_cannot_resolve_report(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
    )

    assert resp.status_code == 401


def test_resolve_missing_report_returns_404(monkeypatch):
    admin = make_admin()
    client, _ = setup_client(monkeypatch, admin, [make_user()], [])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "REPORT_NOT_FOUND"


def test_resolve_already_resolved_report_returns_409(monkeypatch):
    admin = make_admin()
    report = make_report(status="resolved")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "REPORT_ALREADY_RESOLVED"


def test_resolve_rejected_report_returns_409(monkeypatch):
    admin = make_admin()
    report = make_report(status="rejected")
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "REPORT_NOT_RESOLVABLE"


def test_resolve_invalid_payload_rejected(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={"status": "resolved"},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 422


def test_resolve_long_note_rejected(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, _ = setup_client(monkeypatch, admin, [make_user()], [report])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={"admin_note": "x" * 1001},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 422


def test_resolve_database_failure_does_not_return_success(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])
    fake.fail_field_report_update = True

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 500
    assert resp.json()["code"] == "DATABASE_ERROR"
    assert fake.tables["field_reports"][0]["status"] == "open"


def test_resolve_zero_row_update_does_not_return_success(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])
    fake.zero_row_field_report_update = True

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 500
    assert resp.json()["code"] == "DATABASE_ERROR"
    assert fake.tables["field_reports"][0]["status"] == "open"


def test_resolve_malformed_update_response_does_not_return_success(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])
    fake.malformed_field_report_update = True

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 500
    assert resp.json()["code"] == "INTERNAL_SERVER_ERROR"


def test_resolve_does_not_modify_related_field(monkeypatch):
    admin = make_admin()
    report = make_report()
    client, fake = setup_client(monkeypatch, admin, [make_user()], [report])
    original_field = dict(fake.tables["fields"][0])

    resp = client.patch(
        f"/admin/field-reports/{REPORT_ID}/resolve",
        json={},
        headers=auth_headers(admin),
    )

    assert resp.status_code == 200
    assert fake.tables["fields"][0] == original_field
