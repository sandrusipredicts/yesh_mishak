from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.supabase import get_supabase_service_role_client


AUTHENTICATION_AUDIT_RETENTION_DAYS = 180
SECURITY_EVIDENCE_RETENTION_DAYS = AUTHENTICATION_AUDIT_RETENTION_DAYS

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


class SecurityEvidenceCleanupError(RuntimeError):
    """One or more security-evidence cleanup targets failed safely."""

    def __init__(
        self,
        failure_category: str,
        *,
        partial_result: dict[str, int | bool],
    ) -> None:
        super().__init__(failure_category)
        self.failure_category = failure_category
        self.partial_result = partial_result


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


def _cleanup_rpc_in_bounded_batches(
    *,
    supabase: Any,
    rpc_name: str,
    cutoff_value: str,
    batch_size: int,
    max_batches: int,
) -> dict[str, int | bool]:
    deleted_count = 0
    batch_count = 0
    reached_max_batches = False

    while batch_count < max_batches:
        rpc_failed = False
        response_data: Any = None
        try:
            response = (
                supabase.rpc(
                    rpc_name,
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
        "retention_days": SECURITY_EVIDENCE_RETENTION_DAYS,
        "batch_size": batch_size,
        "max_batches": max_batches,
    }


def _validate_cleanup_controls(
    *,
    batch_size: int,
    max_batches: int,
) -> None:
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


def cleanup_authentication_audit_events(
    *,
    supabase: Any | None = None,
    now: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = DEFAULT_MAX_BATCHES,
) -> dict[str, int | bool]:
    """Delete expired authentication audit rows in bounded RPC transactions."""
    _validate_cleanup_controls(
        batch_size=batch_size,
        max_batches=max_batches,
    )
    cutoff = _utc_reference_time(now) - timedelta(
        days=SECURITY_EVIDENCE_RETENTION_DAYS,
    )
    service_supabase = supabase or get_supabase_service_role_client()
    return _cleanup_rpc_in_bounded_batches(
        supabase=service_supabase,
        rpc_name="cleanup_authentication_audit_events",
        cutoff_value=cutoff.isoformat(),
        batch_size=batch_size,
        max_batches=max_batches,
    )


def cleanup_security_evidence_events(
    *,
    supabase: Any | None = None,
    now: datetime | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int = DEFAULT_MAX_BATCHES,
) -> dict[str, int | bool]:
    """Clean all security-evidence tables through independent bounded RPCs."""
    _validate_cleanup_controls(
        batch_size=batch_size,
        max_batches=max_batches,
    )
    cutoff = _utc_reference_time(now) - timedelta(
        days=SECURITY_EVIDENCE_RETENTION_DAYS,
    )
    cutoff_value = cutoff.isoformat()
    service_supabase = supabase or get_supabase_service_role_client()
    targets = (
        (
            "authentication_audit",
            "cleanup_authentication_audit_events",
        ),
        (
            "security_attribution",
            "cleanup_security_request_attribution_events",
        ),
        (
            "investigation_access",
            "cleanup_security_investigation_access_events",
        ),
    )
    result: dict[str, int | bool] = {
        "processed_count": 0,
        "deleted_count": 0,
        "batch_count": 0,
        "reached_max_batches": False,
        "retention_days": SECURITY_EVIDENCE_RETENTION_DAYS,
        "batch_size": batch_size,
        "max_batches": max_batches,
        "target_count": len(targets),
        "failed_target_count": 0,
    }
    failure_categories: list[str] = []

    for target_key, rpc_name in targets:
        try:
            target_result = _cleanup_rpc_in_bounded_batches(
                supabase=service_supabase,
                rpc_name=rpc_name,
                cutoff_value=cutoff_value,
                batch_size=batch_size,
                max_batches=max_batches,
            )
        except UnexpectedAuthenticationAuditCleanupResponse:
            failure_categories.append("unexpected_response")
            result["failed_target_count"] = (
                int(result["failed_target_count"]) + 1
            )
            continue
        except AuthenticationAuditCleanupRpcError:
            failure_categories.append("cleanup_rpc_failure")
            result["failed_target_count"] = (
                int(result["failed_target_count"]) + 1
            )
            continue

        target_deleted = int(target_result["deleted_count"])
        target_batches = int(target_result["batch_count"])
        result[f"{target_key}_deleted_count"] = target_deleted
        result[f"{target_key}_batch_count"] = target_batches
        result["processed_count"] = (
            int(result["processed_count"]) + target_deleted
        )
        result["deleted_count"] = (
            int(result["deleted_count"]) + target_deleted
        )
        result["batch_count"] = (
            int(result["batch_count"]) + target_batches
        )
        result["reached_max_batches"] = bool(
            result["reached_max_batches"]
        ) or bool(target_result["reached_max_batches"])

    if failure_categories:
        failure_category = (
            "unexpected_response"
            if "unexpected_response" in failure_categories
            else "cleanup_rpc_failure"
        )
        raise SecurityEvidenceCleanupError(
            failure_category,
            partial_result=result,
        )

    return result
