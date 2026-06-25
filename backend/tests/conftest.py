import pytest

from app.rate_limit import get_limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter_state():
    limiter = get_limiter()
    limiter.reset()
    limiter.reset_clock()
    yield
    limiter.reset()
    limiter.reset_clock()
