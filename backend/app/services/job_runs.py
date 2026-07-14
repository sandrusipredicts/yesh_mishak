import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.db.supabase import get_supabase_service_role_client


JOB_RUN_ERROR_MESSAGE_MAX_LENGTH = 500
JOB_RUN_ERROR_TYPE_MAX_LENGTH = 120

_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(password\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(secret\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(key\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(service_role\s*[=:]\s*)[^\s,;]+"),
]


@dataclass(frozen=True)
class JobRun:
    id: str
    job_name: str
    started_at: datetime
    start_monotonic: float


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_error_message(message: str, *, max_length: int = JOB_RUN_ERROR_MESSAGE_MAX_LENGTH) -> str:
    sanitized = " ".join(str(message).split())
    for pattern in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", sanitized)
    if len(sanitized) > max_length:
        return sanitized[: max_length - 3].rstrip() + "..."
    return sanitized


def sanitize_error_type(error_type: str) -> str:
    return sanitize_error_message(error_type, max_length=JOB_RUN_ERROR_TYPE_MAX_LENGTH)


def _duration_ms(start_monotonic: float) -> int:
    return max(0, round((time.perf_counter() - start_monotonic) * 1000))


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class JobRunRecorder:
    def __init__(self, supabase: Any | None = None) -> None:
        self._supabase = supabase

    @property
    def supabase(self) -> Any:
        if self._supabase is None:
            self._supabase = get_supabase_service_role_client()
        return self._supabase

    def start(self, *, job_name: str, metadata: dict[str, Any] | None = None) -> JobRun:
        started_at = utc_now()
        response = (
            self.supabase.table("job_runs")
            .insert(
                {
                    "job_name": job_name,
                    "status": "running",
                    "started_at": started_at.isoformat(),
                    "metadata": metadata or {},
                }
            )
            .execute()
        )
        data = response.data or []
        run_id = data[0].get("id") if data else None
        if not run_id:
            raise RuntimeError("job_runs insert did not return an id")
        return JobRun(
            id=str(run_id),
            job_name=job_name,
            started_at=started_at,
            start_monotonic=time.perf_counter(),
        )

    def mark_succeeded(self, job_run: JobRun, result: dict[str, Any]) -> None:
        finished_at = utc_now()
        reconciled_count = _safe_int(result.get("reconciled_count"))
        payload = {
            "status": "succeeded",
            "finished_at": finished_at.isoformat(),
            "duration_ms": _duration_ms(job_run.start_monotonic),
            "processed_count": reconciled_count,
            "scanned_count": _safe_int(result.get("scanned_count")),
            "reconciled_count": reconciled_count,
            "skipped_count": _safe_int(result.get("skipped_count")),
            "failed_count": _safe_int(result.get("failed_count")),
            "batch_count": _safe_int(result.get("batch_count")),
            "reached_max_batches": bool(result.get("reached_max_batches")),
            "updated_at": finished_at.isoformat(),
        }
        self._update(job_run, payload)

    def mark_failed(self, job_run: JobRun, exc: BaseException) -> None:
        finished_at = utc_now()
        payload = {
            "status": "failed",
            "finished_at": finished_at.isoformat(),
            "duration_ms": _duration_ms(job_run.start_monotonic),
            "error_type": sanitize_error_type(exc.__class__.__name__),
            "error_message": sanitize_error_message(str(exc)),
            "updated_at": finished_at.isoformat(),
        }
        self._update(job_run, payload)

    def _update(self, job_run: JobRun, payload: dict[str, Any]) -> None:
        self.supabase.table("job_runs").update(payload).eq("id", job_run.id).execute()
