import os
os.environ["ALLOW_TEST_MOCK_IDS"] = "true"

import pytest

from app.brute_force import get_brute_force_protector
from app.rate_limit import get_limiter


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
