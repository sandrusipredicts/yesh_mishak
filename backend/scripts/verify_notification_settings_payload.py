from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.dependencies import get_current_user
from app.main import app
from app.routers import notifications


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeTable:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.rows = []

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def in_(self, *_args):
        return self

    def update(self, row):
        self.rows.append(dict(row, id="updated"))
        return self

    def insert(self, row):
        if isinstance(row, list):
            self.rows.extend(dict(item, id=f"inserted-{index}") for index, item in enumerate(row))
        else:
            self.rows.append(dict(row, id="inserted"))
        return self

    def delete(self):
        return self

    def execute(self):
        if self.table_name == "notification_preferences" and not self.rows:
            return FakeResult([])

        return FakeResult(self.rows)


class FakeSupabase:
    def table(self, table_name: str):
        return FakeTable(table_name)


def fake_current_user():
    return {"id": "user-1", "email": "user@example.com"}


def fake_supabase_client():
    return FakeSupabase()


def main() -> None:
    app.dependency_overrides[get_current_user] = fake_current_user
    original_get_supabase_client = notifications.get_supabase_client
    notifications.get_supabase_client = fake_supabase_client

    try:
        client = TestClient(app)
        response = client.put(
            "/notifications/preferences",
            json={
                "distance_enabled": True,
                "distance_radius_km": 5,
                "city_enabled": True,
                "city_name": "ירוחם",
                "specific_fields_enabled": True,
                "selected_field_ids": ["field-1"],
            },
        )

        assert response.status_code == 200, response.text
        assert "Radius preferences require radius_km, lat, and lng" not in response.text
        assert response.json()["message"] == "Preferences saved"
        print("notification settings payload route ok")
    finally:
        notifications.get_supabase_client = original_get_supabase_client
        app.dependency_overrides.clear()


if __name__ == "__main__":
    main()
