"""Tests proving the CORS middleware accepts the production origin and rejects untrusted ones."""

import os

# Required env vars so Settings can instantiate without a .env file.
os.environ.setdefault("SUPABASE_URL", "https://fake.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "fake-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "fake-google-id")
os.environ.setdefault("JWT_SECRET", "test-secret")

import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Production origin — https://yesh-mishak.com
# ---------------------------------------------------------------------------

class TestProductionOriginPreflight:
    """OPTIONS preflight from the canonical production origin."""

    ORIGIN = "https://yesh-mishak.com"

    def test_options_auth_google_returns_cors_headers(self, client: TestClient):
        resp = client.options(
            "/auth/google",
            headers={
                "Origin": self.ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == self.ORIGIN
        assert "POST" in resp.headers.get("access-control-allow-methods", "").upper()
        assert "content-type" in resp.headers.get("access-control-allow-headers", "").lower()

    def test_post_auth_google_includes_allow_origin(self, client: TestClient):
        """A credentialed POST must echo the origin, not '*'."""
        resp = client.post(
            "/auth/google",
            headers={"Origin": self.ORIGIN},
            json={"credential": "fake"},
        )
        assert resp.headers.get("access-control-allow-origin") == self.ORIGIN


# ---------------------------------------------------------------------------
# Untrusted origin — must be rejected
# ---------------------------------------------------------------------------

class TestUntrustedOriginRejected:
    """An origin that is not in the allowlist must not receive CORS headers."""

    ORIGIN = "https://evil-site.example.com"

    def test_options_auth_google_no_allow_origin(self, client: TestClient):
        resp = client.options(
            "/auth/google",
            headers={
                "Origin": self.ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # Starlette's CORSMiddleware returns 400 for disallowed origins
        assert resp.headers.get("access-control-allow-origin") is None

    def test_post_auth_google_no_allow_origin(self, client: TestClient):
        resp = client.post(
            "/auth/google",
            headers={"Origin": self.ORIGIN},
            json={"credential": "fake"},
        )
        assert resp.headers.get("access-control-allow-origin") is None


# ---------------------------------------------------------------------------
# Existing legitimate origins still work
# ---------------------------------------------------------------------------

class TestExistingOriginsPreserved:
    """Localhost dev origins and Capacitor origin must remain allowed."""

    @pytest.mark.parametrize(
        "origin",
        [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
            "https://localhost",  # Capacitor
        ],
    )
    def test_options_allowed(self, client: TestClient, origin: str):
        resp = client.options(
            "/auth/google",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == origin
