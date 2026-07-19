"""Unit + integration tests for app/monitoring.py (E09-01)."""
import pytest

from app.monitoring import (
    LOCAL_ENVIRONMENT,
    is_monitoring_enabled,
    redact_deep,
    redact_event,
    resolve_environment,
    resolve_release,
)


# --- Pure resolution logic -------------------------------------------------

def test_resolve_environment_defaults_to_local_when_unset():
    assert resolve_environment(None) == LOCAL_ENVIRONMENT
    assert resolve_environment("") == LOCAL_ENVIRONMENT
    assert resolve_environment("   ") == LOCAL_ENVIRONMENT


def test_resolve_environment_uses_explicit_value_verbatim():
    assert resolve_environment("production") == "production"
    assert resolve_environment("branch-build") == "branch-build"


def test_resolve_release_never_fabricates_a_version():
    assert resolve_release(None) == "unknown"
    assert resolve_release("") == "unknown"


def test_resolve_release_uses_explicit_value():
    assert resolve_release("yesh-mishak@abc1234") == "yesh-mishak@abc1234"


def test_is_monitoring_enabled_false_without_dsn():
    assert is_monitoring_enabled(None, "production", True) is False
    assert is_monitoring_enabled("", "production", True) is False


def test_is_monitoring_enabled_local_disabled_by_default():
    assert is_monitoring_enabled("https://example.invalid/1", "local", None) is False
    assert is_monitoring_enabled("https://example.invalid/1", "local", False) is False


def test_is_monitoring_enabled_local_explicit_override():
    assert is_monitoring_enabled("https://example.invalid/1", "local", True) is True


def test_is_monitoring_enabled_deployed_environments_enabled_automatically():
    for env in ("development", "branch-build", "production"):
        assert is_monitoring_enabled("https://example.invalid/1", env, False) is True


# --- Redaction ---------------------------------------------------------

def test_redact_deep_redacts_sensitive_keys_at_any_depth():
    value = {"a": {"b": {"password": "hunter2", "safe": "ok"}}}
    result = redact_deep(value)
    assert result["a"]["b"]["password"] == "[Redacted]"
    assert result["a"]["b"]["safe"] == "ok"


def test_redact_deep_does_not_mutate_input():
    value = {"authorization": "Bearer abc", "nested": {"token": "xyz"}}
    import copy
    snapshot = copy.deepcopy(value)
    redact_deep(value)
    assert value == snapshot


def test_redact_deep_redacts_coordinate_keys():
    value = {"location": {"latitude": 31.5, "longitude": 34.7}}
    result = redact_deep(value)
    assert result["location"]["latitude"] == "[Redacted]"
    assert result["location"]["longitude"] == "[Redacted]"


def test_redact_event_scrubs_authorization_header():
    event = {
        "request": {
            "url": "https://api.example.com/games?token=abc",
            "headers": {"Authorization": "Bearer secret", "Content-Type": "application/json"},
        }
    }
    result = redact_event(event, {})
    assert result["request"]["headers"]["Authorization"] == "[Redacted]"
    assert result["request"]["headers"]["Content-Type"] == "application/json"
    assert result["request"]["url"] == "https://api.example.com/games"


def test_redact_event_scrubs_cookies():
    event = {"request": {"cookies": {"session": "abc123"}}}
    result = redact_event(event, {})
    assert "cookies" not in result["request"]


def test_redact_event_removes_request_body_by_default():
    event = {"request": {"data": {"password": "hunter2", "email": "a@example.com"}}}
    result = redact_event(event, {})
    assert "data" not in result["request"]


def test_redact_event_scrubs_password_and_token_fields_in_extra():
    event = {"extra": {"password": "x", "refresh_token": "y", "safe_field": "z"}}
    result = redact_event(event, {})
    assert result["extra"]["password"] == "[Redacted]"
    assert result["extra"]["refresh_token"] == "[Redacted]"
    assert result["extra"]["safe_field"] == "z"


def test_redact_event_keeps_only_internal_user_id():
    event = {"user": {"id": "user-1", "email": "a@example.com", "username": "alice"}}
    result = redact_event(event, {})
    assert result["user"] == {"id": "user-1"}


# --- FastAPI integration (capture wiring) -------------------------------
#
# app/main.py calls init_monitoring(get_settings()) once at import time,
# which sets app.monitoring._enabled based on the real (DSN-less) test
# settings. That import must happen -- and settle -- BEFORE these fixtures
# monkeypatch _enabled/sentry_sdk on top of it, or app.main's own
# module-level init call (triggered whenever it's first imported) would run
# afterward and silently clobber the patch. Importing app.main explicitly
# first, before patching, makes the ordering deterministic regardless of
# whether an earlier-collected test file already imported it.

@pytest.fixture
def enabled_monitoring(monkeypatch):
    """Force app.monitoring into the enabled state without a real DSN, and
    capture every sentry_sdk call made through it for assertions."""
    import app.main  # noqa: F401
    import app.monitoring as monitoring

    calls = {"capture_exception": [], "capture_message": [], "tags": []}

    class FakeScope:
        def set_tag(self, key, value):
            calls["tags"].append((key, value))

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    def fake_new_scope():
        return FakeScope()

    def fake_capture_exception(exc):
        calls["capture_exception"].append(exc)
        return "fake-event-id"

    def fake_capture_message(message, level=None):
        calls["capture_message"].append((message, level))
        return "fake-event-id"

    monkeypatch.setattr(monitoring, "_enabled", True)
    monkeypatch.setattr(monitoring.sentry_sdk, "new_scope", fake_new_scope)
    monkeypatch.setattr(monitoring.sentry_sdk, "capture_exception", fake_capture_exception)
    monkeypatch.setattr(monitoring.sentry_sdk, "capture_message", fake_capture_message)
    yield calls


def _register_temp_test_routes(app):
    if getattr(app.state, "monitoring_test_routes_registered", False):
        return

    from app.errors import raise_api_error

    def unhandled():
        raise RuntimeError("boom")

    def internal_500():
        raise_api_error(500, "TEST_DATABASE_ERROR", "simulated internal failure")

    app.add_api_route("/__test_monitoring/unhandled", unhandled, methods=["GET"])
    app.add_api_route("/__test_monitoring/internal-500", internal_500, methods=["GET"])
    app.state.monitoring_test_routes_registered = True


def test_unhandled_exception_is_captured_exactly_once(enabled_monitoring):
    from fastapi.testclient import TestClient
    from app.main import app

    _register_temp_test_routes(app)
    response = TestClient(app, raise_server_exceptions=False).get("/__test_monitoring/unhandled")

    assert response.status_code == 500
    assert len(enabled_monitoring["capture_exception"]) == 1


def test_internal_500_raised_via_raise_api_error_is_captured(enabled_monitoring):
    from fastapi.testclient import TestClient
    from app.main import app

    _register_temp_test_routes(app)
    response = TestClient(app, raise_server_exceptions=False).get("/__test_monitoring/internal-500")

    assert response.status_code == 500
    assert response.json()["code"] == "TEST_DATABASE_ERROR"
    assert len(enabled_monitoring["capture_exception"]) == 1


def test_expected_http_exception_is_not_captured(enabled_monitoring):
    from fastapi.testclient import TestClient
    from app.main import app

    # /admin/monitoring requires auth -> a normal 401, an expected outcome.
    response = TestClient(app, raise_server_exceptions=False).get("/admin/monitoring")

    assert response.status_code == 401
    assert enabled_monitoring["capture_exception"] == []


def test_validation_error_is_not_captured(enabled_monitoring):
    from fastapi.testclient import TestClient
    from app.main import app

    # Missing required auth header on a route that also validates a path
    # param still resolves through the auth dependency first (401), which is
    # itself an expected-error case; this asserts no capture happens for it.
    response = TestClient(app, raise_server_exceptions=False).post("/auth/login", json={})

    assert response.status_code in (400, 401, 422)
    assert enabled_monitoring["capture_exception"] == []


def test_monitoring_outage_does_not_break_the_api(monkeypatch):
    import app.main  # noqa: F401 -- see note above enabled_monitoring
    import app.monitoring as monitoring
    from fastapi.testclient import TestClient
    from app.main import app

    def broken_new_scope():
        raise RuntimeError("sentry transport unavailable")

    monkeypatch.setattr(monitoring, "_enabled", True)
    monkeypatch.setattr(monitoring.sentry_sdk, "new_scope", broken_new_scope)

    _register_temp_test_routes(app)
    response = TestClient(app, raise_server_exceptions=False).get("/__test_monitoring/unhandled")

    # The API must still return its normal error response even though the
    # monitoring call itself failed.
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"


def test_release_and_environment_are_attached_at_init(monkeypatch):
    import app.monitoring as monitoring
    from app.core.config import Settings

    captured = {}

    def fake_init(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(monitoring.sentry_sdk, "init", fake_init)

    settings = Settings(
        SUPABASE_URL="http://example.test",
        SUPABASE_KEY="k",
        GOOGLE_CLIENT_ID="c",
        JWT_SECRET="s",
        SENTRY_DSN="https://example.invalid/1",
        SENTRY_ENVIRONMENT="production",
        SENTRY_RELEASE="yesh-mishak@abc1234",
    )
    monitoring.init_monitoring(settings)

    assert captured["environment"] == "production"
    assert captured["release"] == "yesh-mishak@abc1234"
    assert captured["send_default_pii"] is False
    assert captured["traces_sample_rate"] == 0

    monkeypatch.setattr(monitoring, "_enabled", False)


def test_init_monitoring_disabled_without_dsn():
    import app.monitoring as monitoring
    from app.core.config import Settings

    settings = Settings(
        SUPABASE_URL="http://example.test",
        SUPABASE_KEY="k",
        GOOGLE_CLIENT_ID="c",
        JWT_SECRET="s",
    )
    monitoring.init_monitoring(settings)

    assert monitoring.is_monitoring_active() is False


def test_init_monitoring_failure_does_not_raise(monkeypatch):
    import app.monitoring as monitoring
    from app.core.config import Settings

    def broken_init(**kwargs):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(monitoring.sentry_sdk, "init", broken_init)

    settings = Settings(
        SUPABASE_URL="http://example.test",
        SUPABASE_KEY="k",
        GOOGLE_CLIENT_ID="c",
        JWT_SECRET="s",
        SENTRY_DSN="https://example.invalid/1",
        SENTRY_ENVIRONMENT="production",
    )

    monitoring.init_monitoring(settings)  # must not raise
    assert monitoring.is_monitoring_active() is False
