import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable

from fastapi import Request

FAILED_LOGIN_WINDOW_SECONDS = 15 * 60
MAX_PROGRESSIVE_DELAY_SECONDS = 30


@dataclass
class _FailureWindow:
    count: int
    window_start: float


class BruteForceProtector:
    def __init__(self) -> None:
        self._lock = Lock()
        self._failures: dict[str, _FailureWindow] = {}
        self._clock = time.monotonic
        self._sleep = time.sleep

    def set_clock(self, clock_fn: Callable[[], float]) -> None:
        self._clock = clock_fn

    def reset_clock(self) -> None:
        self._clock = time.monotonic

    def set_sleep(self, sleep_fn: Callable[[float], None]) -> None:
        self._sleep = sleep_fn

    def reset_sleep(self) -> None:
        self._sleep = time.sleep

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()

    def record_failure(self, keys: list[str]) -> int:
        now = self._clock()
        counts: list[int] = []

        with self._lock:
            for key in keys:
                window = self._failures.get(key)
                if window is None or now - window.window_start >= FAILED_LOGIN_WINDOW_SECONDS:
                    window = _FailureWindow(count=0, window_start=now)
                    self._failures[key] = window

                window.count += 1
                counts.append(window.count)

        return _delay_for_failure_count(max(counts, default=0))

    def reset_keys(self, keys: list[str]) -> None:
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)

    def apply_delay(self, delay_seconds: int) -> None:
        if delay_seconds > 0:
            self._sleep(delay_seconds)


_global_protector = BruteForceProtector()


def get_brute_force_protector() -> BruteForceProtector:
    return _global_protector


def get_client_ip(request: Request) -> str:
    client = request.client
    if client:
        return client.host
    return "unknown"


def normalize_login_identifier(identifier: str) -> str:
    return identifier.strip().lower()


def login_tracking_keys(request: Request, identifier: str) -> list[str]:
    client_ip = get_client_ip(request)
    normalized_identifier = normalize_login_identifier(identifier)
    return [
        f"ip:{client_ip}",
        f"identifier:{normalized_identifier}",
        f"ip_identifier:{client_ip}:{normalized_identifier}",
    ]


def record_failed_login_and_delay(request: Request, identifier: str) -> int:
    protector = get_brute_force_protector()
    delay_seconds = protector.record_failure(login_tracking_keys(request, identifier))
    protector.apply_delay(delay_seconds)
    return delay_seconds


def reset_failed_login_state(request: Request, identifier: str) -> None:
    get_brute_force_protector().reset_keys(login_tracking_keys(request, identifier))


def _delay_for_failure_count(failure_count: int) -> int:
    if failure_count <= 5:
        return 0
    if failure_count == 6:
        return 2
    if failure_count == 7:
        return 5
    if failure_count == 8:
        return 10
    return MAX_PROGRESSIVE_DELAY_SECONDS
