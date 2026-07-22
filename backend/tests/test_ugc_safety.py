from fastapi.testclient import TestClient

from app.auth.jwt import create_access_token
from app.core.config import get_settings
from app.main import app
from tests.test_game_close import FakeSupabaseClient

REPORTER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
GAME_ID = "33333333-3333-4333-8333-333333333333"


def _make_client(monkeypatch) -> tuple[TestClient, FakeSupabaseClient, str]:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()

    fake = FakeSupabaseClient(
        {
            "users": [
                {
                    "id": REPORTER_ID,
                    "email": "reporter@example.com",
                    "name": "Reporter",
                    "role": "user",
                    "status": "active",
                    "tokens_valid_after": None,
                },
                {
                    "id": OTHER_USER_ID,
                    "email": "other@example.com",
                    "name": "Other User",
                    "role": "user",
                    "status": "active",
                    "tokens_valid_after": None,
                },
            ],
            "games": [{"id": GAME_ID, "created_by": OTHER_USER_ID}],
            "content_reports": [],
            "user_blocks": [],
        }
    )
    monkeypatch.setattr("app.auth.dependencies.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.moderation.get_supabase_client", lambda: fake)
    monkeypatch.setattr("app.routers.moderation.get_supabase_service_role_client", lambda: fake)
    token = create_access_token(subject=REPORTER_ID, email="reporter@example.com")
    return TestClient(app), fake, token


def test_user_can_report_a_game_for_moderation(monkeypatch):
    client, fake, token = _make_client(monkeypatch)

    response = client.post(
        "/moderation/reports",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "target_type": "game",
            "target_id": GAME_ID,
            "reason": "inappropriate",
            "description": "Please review this game.",
        },
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Report submitted"
    assert fake.tables["content_reports"][0]["reporter_user_id"] == REPORTER_ID
    assert fake.tables["content_reports"][0]["target_id"] == GAME_ID


def test_duplicate_open_report_is_rejected(monkeypatch):
    client, _, token = _make_client(monkeypatch)
    payload = {
        "target_type": "game",
        "target_id": GAME_ID,
        "reason": "spam",
    }

    assert client.post(
        "/moderation/reports",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    ).status_code == 201
    duplicate = client.post(
        "/moderation/reports",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "REPORT_ALREADY_OPEN"


def test_user_can_block_list_and_unblock_another_user(monkeypatch):
    client, fake, token = _make_client(monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    blocked = client.post(f"/moderation/blocks/{OTHER_USER_ID}", headers=headers)
    assert blocked.status_code == 201
    assert fake.tables["user_blocks"] == [
        {
            "id": "inserted-1",
            "blocker_user_id": REPORTER_ID,
            "blocked_user_id": OTHER_USER_ID,
        }
    ]

    listed = client.get("/moderation/blocks", headers=headers)
    assert listed.status_code == 200
    assert listed.json() == {"blocked_user_ids": [OTHER_USER_ID]}

    unblocked = client.delete(f"/moderation/blocks/{OTHER_USER_ID}", headers=headers)
    assert unblocked.status_code == 200
    assert fake.tables["user_blocks"] == []


def test_user_cannot_report_or_block_self(monkeypatch):
    client, _, token = _make_client(monkeypatch)
    headers = {"Authorization": f"Bearer {token}"}

    report = client.post(
        "/moderation/reports",
        headers=headers,
        json={"target_type": "user", "target_id": REPORTER_ID, "reason": "other"},
    )
    blocked = client.post(f"/moderation/blocks/{REPORTER_ID}", headers=headers)

    assert report.status_code == 400
    assert blocked.status_code == 400
