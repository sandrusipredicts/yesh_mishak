from datetime import datetime, timezone
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
