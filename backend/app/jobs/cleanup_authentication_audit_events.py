from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from app.services.authentication_audit_retention import (
    AUTHENTICATION_AUDIT_RETENTION_DAYS,
    AuthenticationAuditCleanupRpcError,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_BATCHES,
    MAX_BATCH_SIZE,
    MAX_MAX_BATCHES,
    MIN_BATCH_SIZE,
    MIN_MAX_BATCHES,
    UnexpectedAuthenticationAuditCleanupResponse,
    cleanup_authentication_audit_events,
)
from app.services.job_runs import JobRun, JobRunRecorder


logger = logging.getLogger(__name__)
JOB_NAME = "authentication_audit_retention_cleanup"
ENTRY_POINT = "app.jobs.cleanup_authentication_audit_events"


class AuthenticationAuditCleanupJobFailure(RuntimeError):
    """A bounded failure category safe for job-run persistence."""


def _bounded_integer(
    value: str,
    *,
    name: str,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise argparse.ArgumentTypeError(
            f"{name} must be between {minimum} and {maximum}",
        )
    return parsed


def _batch_size(value: str) -> int:
    return _bounded_integer(
        value,
        name="batch-size",
        minimum=MIN_BATCH_SIZE,
        maximum=MAX_BATCH_SIZE,
    )


def _max_batches(value: str) -> int:
    return _bounded_integer(
        value,
        name="max-batches",
        minimum=MIN_MAX_BATCHES,
        maximum=MAX_MAX_BATCHES,
    )


def _safe_warning(message: str, *, extra: dict[str, Any]) -> None:
    try:
        logger.warning(message, extra=extra)
    except Exception:
        # Cleanup and its exit status must not depend on the logger backend.
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Delete authentication audit events older than the fixed "
            f"{AUTHENTICATION_AUDIT_RETENTION_DAYS}-day retention window."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=_batch_size,
        default=DEFAULT_BATCH_SIZE,
    )
    parser.add_argument(
        "--max-batches",
        type=_max_batches,
        default=DEFAULT_MAX_BATCHES,
    )
    return parser


def _failure_category(exc: BaseException) -> str:
    if isinstance(exc, UnexpectedAuthenticationAuditCleanupResponse):
        return "unexpected_response"
    if isinstance(exc, AuthenticationAuditCleanupRpcError):
        return "cleanup_rpc_failure"
    return "cleanup_rpc_failure"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = build_parser().parse_args(argv)
    recorder = JobRunRecorder()
    job_run: JobRun | None = None

    try:
        job_run = recorder.start(
            job_name=JOB_NAME,
            metadata={
                "retention_days": AUTHENTICATION_AUDIT_RETENTION_DAYS,
                "batch_size": args.batch_size,
                "max_batches": args.max_batches,
                "entry_point": ENTRY_POINT,
            },
        )
    except Exception:
        _safe_warning(
            "authentication audit cleanup monitoring is unavailable",
            extra={
                "event": "jobs.authentication_audit_cleanup.monitoring_failure",
                "job_name": JOB_NAME,
                "monitoring_stage": "start",
                "failure_category": "job_run_record_failed",
                "result": "partial_failure",
            },
        )

    try:
        result = cleanup_authentication_audit_events(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
        )
    except Exception as exc:
        failure_category = _failure_category(exc)
        safe_failure = AuthenticationAuditCleanupJobFailure(failure_category)
        if job_run is not None:
            try:
                recorder.mark_failed(job_run, safe_failure)
            except Exception:
                _safe_warning(
                    "authentication audit cleanup failure monitoring is unavailable",
                    extra={
                        "event": (
                            "jobs.authentication_audit_cleanup.monitoring_failure"
                        ),
                        "job_name": JOB_NAME,
                        "monitoring_stage": "failure",
                        "failure_category": "job_run_record_failed",
                        "result": "partial_failure",
                    },
                )
        _safe_warning(
            "authentication audit cleanup failed; expired rows were retained for retry",
            extra={
                "event": "jobs.authentication_audit_cleanup.failure",
                "job_name": JOB_NAME,
                "failure_category": failure_category,
                "result": "failure",
            },
        )
        return 1

    if job_run is not None:
        try:
            recorder.mark_succeeded(job_run, result)
        except Exception:
            _safe_warning(
                "authentication audit cleanup success monitoring is unavailable",
                extra={
                    "event": "jobs.authentication_audit_cleanup.monitoring_failure",
                    "job_name": JOB_NAME,
                    "monitoring_stage": "success",
                    "failure_category": "job_run_record_failed",
                    "result": "partial_failure",
                },
            )

    if result["reached_max_batches"]:
        _safe_warning(
            "authentication audit cleanup reached its bounded work limit",
            extra={
                "event": "jobs.authentication_audit_cleanup.capacity_reached",
                "job_name": JOB_NAME,
                "processed_count": result["processed_count"],
                "batch_count": result["batch_count"],
                "reached_max_batches": True,
                "result": "partial_success",
            },
        )

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
