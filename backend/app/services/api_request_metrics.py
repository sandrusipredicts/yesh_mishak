from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.db.supabase import get_supabase_service_role_client

API_REQUEST_METRICS_TABLE = "api_request_metrics"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def record_api_request_metric(
    *,
    method: str,
    normalized_path: str,
    status_code: int,
    duration_ms: int,
    recorded_at: datetime | None = None,
) -> None:
    """Persist a completed API request outcome without sensitive request data."""
    timestamp = recorded_at or utc_now()
    get_supabase_service_role_client().table(API_REQUEST_METRICS_TABLE).insert(
        {
            "recorded_at": timestamp.isoformat(),
            "method": method.upper(),
            "normalized_path": normalized_path,
            "status_code": status_code,
            "duration_ms": max(0, duration_ms),
            "is_error": 500 <= status_code <= 599,
        }
    ).execute()


def count_api_request_metrics(
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
    is_error: bool | None = None,
    supabase: Any | None = None,
) -> int:
    client = supabase or get_supabase_service_role_client()
    query = (
        client.table(API_REQUEST_METRICS_TABLE)
        .select("id", count="exact")
        .gte("recorded_at", window_started_at.isoformat())
        .lt("recorded_at", window_ended_at.isoformat())
    )

    if is_error is not None:
        query = query.eq("is_error", is_error)

    response = query.execute()
    count = getattr(response, "count", None)
    if count is not None:
        return int(count)
    return len(response.data or [])


def get_api_response_time_metrics(
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
    supabase: Any | None = None,
) -> dict[str, int | float]:
    client = supabase or get_supabase_service_role_client()
    response = (
        client.rpc(
            "get_api_response_time_metrics",
            {
                "window_start": window_started_at.isoformat(),
                "window_end": window_ended_at.isoformat(),
            },
        )
        .execute()
    )
    row = _first_rpc_row(response.data)
    return {
        "sample_count": max(0, _safe_int(row.get("sample_count"))),
        "average_ms": _safe_metric_float(row.get("average_ms")),
        "p50_ms": _safe_metric_float(row.get("p50_ms")),
        "p95_ms": _safe_metric_float(row.get("p95_ms")),
        "max_ms": _safe_metric_float(row.get("max_ms")),
    }


def _first_rpc_row(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        first = data[0] if data else {}
        return first if isinstance(first, dict) else {}
    return data if isinstance(data, dict) else {}


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_metric_float(value: Any) -> float:
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return 0.0
    if numeric.is_nan() or numeric < 0:
        return 0.0
    return float(round(numeric, 2))
