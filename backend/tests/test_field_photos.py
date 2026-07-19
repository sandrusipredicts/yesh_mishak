from __future__ import annotations

import os
from typing import Any

from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-google-client")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.main import app
from tests.test_game_close import FakeSupabaseClient


USER = {
    "id": "user-1",
    "email": "user@example.com",
    "name": "Regular User",
    "role": "user",
    "status": "active",
}
ADMIN = {
    "id": "admin-1",
    "email": "admin@example.com",
    "name": "Admin",
    "role": "admin",
    "status": "active",
}


class FakeStorageBucket:
    def __init__(self, *, fail_upload: bool = False) -> None:
        self.fail_upload = fail_upload
        self.objects: dict[str, dict[str, Any]] = {}
        self.removed: list[str] = []

    def upload(self, path: str, content: bytes, options: dict[str, Any]) -> dict[str, Any]:
        if self.fail_upload:
            raise RuntimeError("upload failed")
        if path in self.objects:
            raise RuntimeError("duplicate object")
        self.objects[path] = {"content": content, "options": options}
        return {"path": path}

    def remove(self, paths: list[str]) -> dict[str, Any]:
        for path in paths:
            self.removed.append(path)
            self.objects.pop(path, None)
        return {}

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, str]:
        return {"signedURL": f"https://storage.example.test/{path}?expires={expires_in}"}


class FakeStorage:
    def __init__(self, bucket: FakeStorageBucket) -> None:
        self.bucket = bucket
        self.requested_buckets: list[str] = []

    def from_(self, bucket_name: str) -> FakeStorageBucket:
        self.requested_buckets.append(bucket_name)
        return self.bucket


class FakeStorageClient:
    def __init__(self, bucket: FakeStorageBucket) -> None:
        self.storage = FakeStorage(bucket)


def _configure(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def _token(user: dict[str, Any]) -> str:
    return create_access_token(subject=user["id"], email=user["email"])


def _headers(user: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


def _base_tables(*fields: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        "users": [USER, ADMIN],
        "fields": list(fields),
        "games": [],
        "game_players": [],
    }


def _make_client(monkeypatch, tables: dict[str, list], bucket: FakeStorageBucket) -> TestClient:
    fake = FakeSupabaseClient(tables)
    storage_client = FakeStorageClient(bucket)
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.fields.get_supabase_service_role_client", lambda: storage_client)
    monkeypatch.setattr("app.routers.games.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_payloads.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.game_lifecycle.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.api.admin.get_supabase_service_role_client", lambda: storage_client)
    return TestClient(app)


def _field_form(**overrides: Any) -> dict[str, str]:
    data = {
        "name": "Central Court",
        "lat": "32.0853",
        "lng": "34.7818",
        "sport_type": "football",
        "surface_type": "asphalt",
        "has_nets": "true",
        "has_water": "false",
        "opening_hours": "08:00-22:00",
        "city": "Tel Aviv",
        "notes": "Lit at night",
    }
    data.update({key: str(value) for key, value in overrides.items()})
    return data


def _jpeg(size: int = 32) -> bytes:
    return b"\xff\xd8\xff" + (b"x" * size)


def _post_with_photo(client: TestClient, data: dict[str, str] | None = None, content: bytes | None = None):
    return client.post(
        "/fields/with-photo",
        data=data or _field_form(),
        files={"photo": ("../../evil.jpg", content or _jpeg(), "image/jpeg")},
        headers=_headers(USER),
    )


def test_field_photo_upload_requires_authentication(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(), FakeStorageBucket())

    response = client.post(
        "/fields/with-photo",
        data=_field_form(),
        files={"photo": ("field.jpg", _jpeg(), "image/jpeg")},
    )

    assert response.status_code == 401


def test_valid_field_photo_creates_pending_field_and_safe_storage_path(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = _base_tables()
    bucket = FakeStorageBucket()
    client = _make_client(monkeypatch, tables, bucket)

    response = _post_with_photo(client)

    assert response.status_code == 200
    field = response.json()["field"]
    assert field["approval_status"] == "pending"
    assert field["added_by"] == USER["id"]
    assert field["image_url"].startswith(f"fields/{field['id']}/")
    assert "../" not in field["image_url"]
    assert field["image_url"] in bucket.objects
    assert bucket.objects[field["image_url"]]["options"]["content-type"] == "image/jpeg"


def test_field_photo_rejects_unsupported_content_even_if_filename_looks_valid(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(), FakeStorageBucket())

    response = _post_with_photo(client, content=b"not an image")

    assert response.status_code == 400
    assert response.json()["code"] == "FIELD_PHOTO_UNSUPPORTED_TYPE"


def test_field_photo_rejects_oversized_upload(monkeypatch) -> None:
    _configure(monkeypatch)
    client = _make_client(monkeypatch, _base_tables(), FakeStorageBucket())

    response = _post_with_photo(client, content=_jpeg(5 * 1024 * 1024))

    assert response.status_code == 413
    assert response.json()["code"] == "FIELD_PHOTO_TOO_LARGE"


def test_upload_failure_removes_new_pending_field(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = _base_tables()
    client = _make_client(monkeypatch, tables, FakeStorageBucket(fail_upload=True))

    response = _post_with_photo(client)

    assert response.status_code == 500
    assert response.json()["code"] == "FIELD_PHOTO_UPLOAD_FAILED"
    assert tables["fields"] == []


def test_reference_update_failure_removes_uploaded_object_and_pending_field(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = _base_tables()
    bucket = FakeStorageBucket()
    client = _make_client(monkeypatch, tables, bucket)

    def fail_reference_update(_field_id: str, _photo_path: str) -> dict[str, Any]:
        raise RuntimeError("db update failed")

    monkeypatch.setattr("app.routers.fields._update_field_photo_reference", fail_reference_update)

    response = _post_with_photo(client)

    assert response.status_code == 500
    assert response.json()["code"] == "FIELD_PHOTO_UPLOAD_FAILED"
    assert tables["fields"] == []
    assert bucket.objects == {}
    assert bucket.removed


def test_existing_json_field_submission_without_photo_still_works(monkeypatch) -> None:
    _configure(monkeypatch)
    tables = _base_tables()
    client = _make_client(monkeypatch, tables, FakeStorageBucket())

    response = client.post("/fields/", json={
        "name": "Central Court",
        "lat": 32.0853,
        "lng": 34.7818,
        "sport_type": "football",
        "surface_type": "asphalt",
        "has_nets": True,
        "has_water": False,
        "opening_hours": "08:00-22:00",
        "city": "Tel Aviv",
        "notes": "Lit at night",
    }, headers=_headers(USER))

    assert response.status_code == 200
    assert response.json()["field"].get("image_url") is None
    assert len(tables["fields"]) == 1


def test_admin_pending_fields_include_signed_photo_url(monkeypatch) -> None:
    _configure(monkeypatch)
    field = {
        "id": "field-1",
        "name": "Pending Court",
        "lat": 32.0,
        "lng": 34.0,
        "sport_type": "football",
        "surface_type": "asphalt",
        "has_nets": True,
        "has_water": False,
        "opening_hours": None,
        "city": "Tel Aviv",
        "notes": None,
        "status": "open",
        "approval_status": "pending",
        "verified": False,
        "added_by": USER["id"],
        "image_url": "fields/field-1/photo.jpg",
        "removed_at": None,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    client = _make_client(monkeypatch, _base_tables(field), FakeStorageBucket())

    response = client.get("/admin/fields/pending", headers=_headers(ADMIN))

    assert response.status_code == 200
    body = response.json()
    assert body[0]["image_url"] == "fields/field-1/photo.jpg"
    assert body[0]["photo_url"].startswith("https://storage.example.test/fields/field-1/photo.jpg")


def test_public_field_list_does_not_mint_pending_photo_url(monkeypatch) -> None:
    _configure(monkeypatch)
    field = {
        "id": "field-1",
        "name": "Pending Court",
        "lat": 32.0,
        "lng": 34.0,
        "sport_type": "football",
        "surface_type": "asphalt",
        "has_nets": True,
        "has_water": False,
        "opening_hours": None,
        "city": "Tel Aviv",
        "notes": None,
        "status": "open",
        "approval_status": "pending",
        "verified": False,
        "added_by": USER["id"],
        "image_url": "fields/field-1/photo.jpg",
        "removed_at": None,
    }
    client = _make_client(monkeypatch, _base_tables(field), FakeStorageBucket())

    response = client.get("/fields/")

    assert response.status_code == 200
    assert response.json() == []


def test_public_pending_field_detail_does_not_expose_photo_reference(monkeypatch) -> None:
    _configure(monkeypatch)
    field = {
        "id": "field-1",
        "name": "Pending Court",
        "lat": 32.0,
        "lng": 34.0,
        "sport_type": "football",
        "surface_type": "asphalt",
        "has_nets": True,
        "has_water": False,
        "opening_hours": None,
        "city": "Tel Aviv",
        "notes": None,
        "status": "open",
        "approval_status": "pending",
        "verified": False,
        "added_by": USER["id"],
        "image_url": "fields/field-1/private-photo.jpg",
        "removed_at": None,
    }
    client = _make_client(monkeypatch, _base_tables(field), FakeStorageBucket())

    response = client.get("/fields/field-1")

    assert response.status_code == 200
    assert response.json()["image_url"] is None
    assert "photo_url" not in response.json()
