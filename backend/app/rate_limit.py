import math
import time
from threading import Lock
from typing import Callable

from fastapi import Request, status
from fastapi.responses import JSONResponse


class _RateLimitWindow:
    __slots__ = ("count", "window_start")

    def __init__(self, window_start: float) -> None:
        self.count = 0
        self.window_start = window_start


class RateLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._windows: dict[str, _RateLimitWindow] = {}
        self._clock = time.monotonic

    def set_clock(self, clock_fn: Callable[[], float]) -> None:
        self._clock = clock_fn

    def reset_clock(self) -> None:
        self._clock = time.monotonic

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()

    def check(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        now = self._clock()
        bucket_key = f"{key}:{window_seconds}"

        with self._lock:
            window = self._windows.get(bucket_key)

            if window is None or now - window.window_start >= window_seconds:
                window = _RateLimitWindow(now)
                self._windows[bucket_key] = window

            window.count += 1

            if window.count > max_requests:
                elapsed = now - window.window_start
                retry_after = max(1, math.ceil(window_seconds - elapsed))
                return False, retry_after

        return True, 0


_global_limiter = RateLimiter()


def get_limiter() -> RateLimiter:
    return _global_limiter


def _get_client_ip(request: Request) -> str:
    client = request.client
    if client:
        return client.host
    return "unknown"


def _rate_limit_response(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": True,
            "code": "RATE_LIMITED",
            "message": "Too many requests. Please try again later.",
        },
        headers={"Retry-After": str(retry_after)},
    )


def check_rate_limit_by_ip(
    request: Request,
    endpoint_name: str,
    limits: list[tuple[int, int]],
) -> JSONResponse | None:
    ip = _get_client_ip(request)
    limiter = get_limiter()

    for max_requests, window_seconds in limits:
        allowed, retry_after = limiter.check(
            f"ip:{endpoint_name}:{ip}",
            max_requests,
            window_seconds,
        )
        if not allowed:
            return _rate_limit_response(retry_after)

    return None


def check_rate_limit_by_user(
    user_id: str,
    endpoint_name: str,
    limits: list[tuple[int, int]],
) -> JSONResponse | None:
    limiter = get_limiter()

    for max_requests, window_seconds in limits:
        allowed, retry_after = limiter.check(
            f"user:{endpoint_name}:{user_id}",
            max_requests,
            window_seconds,
        )
        if not allowed:
            return _rate_limit_response(retry_after)

    return None
