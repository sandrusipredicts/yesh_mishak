"""Fail-safe, privacy-bounded observability helpers for authentication flows."""

from __future__ import annotations

import logging
from typing import Any, Literal

from app.monitoring import capture_unexpected_exception, capture_unexpected_message


LogLevel = Literal["info", "warning", "error"]


def safe_auth_log(
    target_logger: logging.Logger,
    level: LogLevel,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> bool:
    """Emit an allowlisted auth log without ever changing authentication."""
    try:
        if level == "info":
            target_logger.info(message, extra=extra)
        elif level == "warning":
            target_logger.warning(message, extra=extra)
        else:
            target_logger.error(message, extra=extra)
        return True
    except Exception:  # noqa: BLE001 - observability is never authoritative
        # Never report an observability failure through the same logger.
        return False


def safe_auth_monitor(
    message: str,
    *,
    level: str = "warning",
    **safe_tags: Any,
) -> bool:
    """Send constant-text monitoring with caller-allowlisted, bounded tags."""
    try:
        capture_unexpected_message(message, level=level, **safe_tags)
        return True
    except Exception:  # noqa: BLE001 - monitoring is never authoritative
        # Avoid recursion when the monitoring transport itself is unavailable.
        return False


def safe_auth_exception(
    target_logger: logging.Logger,
    message: str,
    exc: BaseException,
    *,
    route: str | None,
    method: str | None,
    status_code: int,
    code: str | None,
) -> None:
    """Report a sanitized auth exception without changing its HTTP response.

    Authentication request identifiers are deliberately not accepted here:
    they are high-cardinality and must not become monitoring tags.
    """
    try:
        target_logger.exception(message)
    except Exception:  # noqa: BLE001 - never recurse through the failed logger
        pass

    try:
        capture_unexpected_exception(
            exc,
            route=route,
            method=method,
            status_code=status_code,
            code=code,
        )
    except Exception:  # noqa: BLE001 - monitoring is never authoritative
        # Do not invoke either observability channel again from this boundary.
        pass
