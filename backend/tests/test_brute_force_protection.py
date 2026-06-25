from __future__ import annotations

import logging
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.brute_force import (
    get_brute_force_protector,
    login_tracking_keys,
    record_failed_login_and_delay,
)
from app.main import app

from test_manual_auth import FakeSupabaseClient, configure_test_settings


def _patch_supabase(monkeypatch, fake_client: FakeSupabaseClient) -> None:
    monkeypatch.setattr("app.api.auth.get_supabase_client", lambda: fake_client)


def _user(username: str = "manual-user") -> dict[str, str]:
    return {
        "id": "00000000-0000-0000-0000-000000000101",
        "email": "manual@example.com",
        "name": "Manual User",
        "username": username,
        "phone_number": "0501234567",
        "password_hash": "not-used-in-tests",
    }


def _client_with_user(monkeypatch, username: str = "manual-user") -> TestClient:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient([_user(username)]))
    monkeypatch.setattr("app.api.auth.verify_password", lambda password, password_hash: False)
    return TestClient(app)


def _sleep_calls() -> list[float]:
    calls: list[float] = []
    get_brute_force_protector().set_sleep(calls.append)
    return calls


def _failed_login(client: TestClient, username: str = "manual-user"):
    return client.post(
        "/auth/login",
        json={"username": username, "password": "wrongpass123"},
    )


def test_repeated_failed_login_attempts_increase_progressive_delay(monkeypatch) -> None:
    client = _client_with_user(monkeypatch)
    sleep_calls = _sleep_calls()

    for _ in range(5):
        response = _failed_login(client)
        assert response.status_code == 401

    assert sleep_calls == []

    assert _failed_login(client).status_code == 401
    assert _failed_login(client).status_code == 401
    assert _failed_login(client).status_code == 401
    assert _failed_login(client).status_code == 401

    assert sleep_calls == [2, 5, 10, 30]


def test_delay_starts_only_after_configured_threshold(monkeypatch) -> None:
    client = _client_with_user(monkeypatch)
    sleep_calls = _sleep_calls()

    for _ in range(5):
        assert _failed_login(client).status_code == 401

    assert sleep_calls == []

    assert _failed_login(client).status_code == 401
    assert sleep_calls == [2]


def test_delay_is_capped_at_30_seconds(monkeypatch) -> None:
    client = _client_with_user(monkeypatch)
    sleep_calls = _sleep_calls()

    for _ in range(9):
        assert _failed_login(client).status_code == 401

    assert sleep_calls[-1] == 30
    assert max(sleep_calls) == 30


def test_successful_login_resets_failure_state(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    _patch_supabase(monkeypatch, FakeSupabaseClient([_user()]))
    monkeypatch.setattr(
        "app.api.auth.verify_password",
        lambda password, password_hash: password == "strongpass123",
    )
    client = TestClient(app)
    sleep_calls = _sleep_calls()

    for _ in range(6):
        assert _failed_login(client).status_code == 401
    assert sleep_calls == [2]

    response = client.post(
        "/auth/login",
        json={"username": "manual-user", "password": "strongpass123"},
    )
    assert response.status_code == 200

    assert _failed_login(client).status_code == 401
    assert sleep_calls == [2]


def test_unknown_and_known_usernames_use_same_generic_failure_response(monkeypatch) -> None:
    client = _client_with_user(monkeypatch)

    known_response = _failed_login(client, "manual-user")
    unknown_response = _failed_login(client, "unknown-user")

    assert known_response.status_code == 401
    assert unknown_response.status_code == 401
    assert known_response.json() == unknown_response.json()


def test_unknown_username_failures_contribute_to_tracking(monkeypatch) -> None:
    configure_test_settings(monkeypatch)
    fake_client = FakeSupabaseClient()
    _patch_supabase(monkeypatch, fake_client)
    client = TestClient(app)
    sleep_calls = _sleep_calls()

    for _ in range(5):
        assert _failed_login(client, "future-user").status_code == 401

    fake_client.users.append(_user("future-user"))
    monkeypatch.setattr("app.api.auth.verify_password", lambda password, password_hash: False)

    assert _failed_login(client, "future-user").status_code == 401
    assert sleep_calls == [2]


def test_ip_based_failures_affect_later_attempts_from_same_ip() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})
    sleep_calls = _sleep_calls()

    for index in range(5):
        assert record_failed_login_and_delay(request, f"user-{index}") == 0

    assert record_failed_login_and_delay(request, "different-user") == 2
    assert sleep_calls == [2]


def test_identifier_based_failures_affect_same_normalized_identifier() -> None:
    request_a = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})
    request_b = SimpleNamespace(client=SimpleNamespace(host="5.6.7.8"), headers={})
    sleep_calls = _sleep_calls()

    for _ in range(5):
        assert record_failed_login_and_delay(request_a, "Manual-User") == 0

    assert record_failed_login_and_delay(request_b, " manual-user ") == 2
    assert sleep_calls == [2]


def test_different_identifiers_do_not_share_identifier_specific_counters() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})
    protector = get_brute_force_protector()

    first_identifier_key = login_tracking_keys(request, "first-user")[1]
    second_identifier_key = login_tracking_keys(request, "second-user")[1]

    for _ in range(5):
        protector.record_failure([first_identifier_key])

    assert protector.record_failure([second_identifier_key]) == 0


def test_different_ips_do_not_share_ip_specific_counters() -> None:
    protector = get_brute_force_protector()

    for _ in range(5):
        protector.record_failure(["ip:1.2.3.4"])

    assert protector.record_failure(["ip:5.6.7.8"]) == 0


def test_issue_099_rate_limiting_still_returns_429(monkeypatch) -> None:
    client = _client_with_user(monkeypatch)
    _sleep_calls()

    for _ in range(10):
        _failed_login(client)

    response = _failed_login(client)

    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"


def test_progressive_delay_does_not_bypass_rate_limiting(monkeypatch) -> None:
    client = _client_with_user(monkeypatch)
    sleep_calls = _sleep_calls()

    for _ in range(10):
        _failed_login(client)

    response = _failed_login(client)

    assert response.status_code == 429
    assert sleep_calls == [2, 5, 10, 30, 30]


def test_no_hard_lockout_after_many_failures() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})
    protector = get_brute_force_protector()

    for _ in range(25):
        delay = protector.record_failure(login_tracking_keys(request, "manual-user"))

    assert delay == 30

    protector.reset_keys(login_tracking_keys(request, "manual-user"))
    assert protector.record_failure(login_tracking_keys(request, "manual-user")) == 0


def test_delay_uses_mocked_sleep_not_real_sleep(monkeypatch) -> None:
    client = _client_with_user(monkeypatch)
    sleep_calls = _sleep_calls()

    for _ in range(6):
        assert _failed_login(client).status_code == 401

    assert sleep_calls == [2]


def test_new_brute_force_logging_does_not_include_plaintext_credentials(monkeypatch, caplog) -> None:
    client = _client_with_user(monkeypatch)
    _sleep_calls()

    with caplog.at_level(logging.WARNING, logger="app.api.auth"):
        for _ in range(6):
            _failed_login(client, "manual-user")

    assert "wrongpass123" not in caplog.text
    assert "manual-user" not in caplog.text
    delay_records = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "auth.login.progressive_delay"
    ]
    assert delay_records
    assert delay_records[-1].delay_seconds == 2
