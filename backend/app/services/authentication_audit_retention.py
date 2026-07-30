from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.supabase import get_supabase_service_role_client


AUTHENTICATION_AUDIT_RETENTION_DAYS = 180

MIN_BATCH_SIZE = 1
DEFAULT_BATCH_SIZE = 1_000
MAX_BATCH_SIZE = 1_000

MIN_MAX_BATCHES = 1
DEFAULT_MAX_BATCHES = 50
MAX_MAX_BATCHES = 100


class UnexpectedAuthenticationAuditCleanupResponse(RuntimeError):
    """The cleanup RPC returned a value that cannot be trusted as a row count."""


class AuthenticationAuditCleanupRpcError(RuntimeError):
    """The cleanup RPC failed without exposing the database exception."""


def _validate_bounded_integer(
    value: int,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")


def _utc_reference_time(now: datetime | None) -> datetime:
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return reference.astimezone(timezone.utc)


def _validated_deleted_count(data: Any, *, batch_size: int) -> int:
    if isinstance(data, list):
        if len(data) != 1:
            raise UnexpectedAuthenticationAuditCleanupResponse(
                "cleanup RPC returned an unexpected response",
            )
        data = data[0]

    if isinstance(data, bool) or not isinstance(data, int):
        raise UnexpectedAuthenticationAuditCleanupResponse(
            "cleanup RPC returned an unexpected response",
        )
    if data < 0 or data > batch_size:
        raise UnexpectedAuthenticationAuditCleanupResponse(
            "cleanup RPC returned an out-of-bounds row count",
        )
    return data


def cleanup_authentication_audit_events(
    *,
    supabase: Any | None = None,
    now: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = DEFAULT_MAX_BATCHES,
) -> dict[str, int | bool]:
    """Delete expired audit rows in bounded, retry-safe RPC transactions."""
    _validate_bounded_integer(
        batch_size,
        name="batch_size",
        minimum=MIN_BATCH_SIZE,
        maximum=MAX_BATCH_SIZE,
    )
    _validate_bounded_integer(
        max_batches,
        name="max_batches",
        minimum=MIN_MAX_BATCHES,
        maximum=MAX_MAX_BATCHES,
    )

    cutoff = _utc_reference_time(now) - timedelta(
        days=AUTHENTICATION_AUDIT_RETENTION_DAYS,
    )
    cutoff_value = cutoff.isoformat()
    service_supabase = supabase or get_supabase_service_role_client()
    deleted_count = 0
    batch_count = 0
    reached_max_batches = False

    while batch_count < max_batches:
        rpc_failed = False
        response_data: Any = None
        try:
            response = (
                service_supabase.rpc(
                    "cleanup_authentication_audit_events",
                    {
                        "p_cutoff": cutoff_value,
                        "p_batch_limit": batch_size,
                    },
                )
                .execute()
            )
            response_data = response.data
        except Exception:
            # Raise outside the exception context so callers cannot traverse
            # an exception chain containing raw database response details.
            rpc_failed = True
        if rpc_failed:
            raise AuthenticationAuditCleanupRpcError("cleanup_rpc_failure")

        batch_deleted_count = _validated_deleted_count(
            response_data,
            batch_size=batch_size,
        )
        batch_count += 1
        deleted_count += batch_deleted_count

        if batch_deleted_count == 0:
            break
    else:
        reached_max_batches = True

    return {
        "processed_count": deleted_count,
        "deleted_count": deleted_count,
        "batch_count": batch_count,
        "reached_max_batches": reached_max_batches,
        "retention_days": AUTHENTICATION_AUDIT_RETENTION_DAYS,
        "batch_size": batch_size,
        "max_batches": max_batches,
    }
