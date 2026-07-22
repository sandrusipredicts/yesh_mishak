import os
os.environ["ALLOW_TEST_MOCK_IDS"] = "true"

import pytest

from app.brute_force import get_brute_force_protector
from app.rate_limit import get_limiter
from app.routers import fields, game_payloads


@pytest.fixture(autouse=True)
def reset_security_state():
    limiter = get_limiter()
    brute_force = get_brute_force_protector()
    limiter.reset()
    limiter.reset_clock()
    brute_force.reset()
    brute_force.reset_clock()
    brute_force.set_sleep(lambda _: None)
    yield
    limiter.reset()
    limiter.reset_clock()
    brute_force.reset()
    brute_force.reset_clock()
    brute_force.reset_sleep()


@pytest.fixture(autouse=True)
def route_fields_map_service_client_to_test_double(monkeypatch):
    """Keep legacy endpoint tests on their injected client, never live Supabase."""
    monkeypatch.setattr(
        game_payloads,
        "get_supabase_service_role_client",
        lambda: fields.get_supabase_client(),
    )
