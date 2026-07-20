from datetime import datetime
from typing import Any, Sequence

from app.db.supabase import get_supabase_service_role_client
from app.schemas.analytics_events import AnalyticsEventIn

ANALYTICS_EVENTS_TABLE = "analytics_events"

DEFAULT_RETENTION_DAYS = 90


def record_analytics_events(
    events: Sequence[AnalyticsEventIn],
    *,
    supabase: Any | None = None,
) -> None:
    if not events:
        return

    client = supabase or get_supabase_service_role_client()
    payload = [_event_row(event) for event in events]
    client.table(ANALYTICS_EVENTS_TABLE).insert(payload).execute()


def _event_row(event: AnalyticsEventIn) -> dict[str, Any]:
    row: dict[str, Any] = {
        "event_name": event.event_name,
        "platform": event.platform,
        "properties": dict(event.properties),
    }
    if event.app_version is not None:
        row["app_version"] = event.app_version
    if event.occurred_at is not None:
        row["recorded_at"] = event.occurred_at.isoformat()
    return row


def get_analytics_event_metrics(
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
    supabase: Any | None = None,
) -> list[dict[str, Any]]:
    client = supabase or get_supabase_service_role_client()
    response = (
        client.rpc(
            "get_analytics_event_metrics",
            {
                "window_start": window_started_at.isoformat(),
                "window_end": window_ended_at.isoformat(),
            },
        )
        .execute()
    )

    rows = response.data if isinstance(response.data, list) else []
    return [
        {
            "event_day": str(row.get("event_day") or ""),
            "event_name": str(row.get("event_name") or ""),
            "platform": str(row.get("platform") or ""),
            "event_count": max(0, _safe_int(row.get("event_count"))),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def cleanup_analytics_events(
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    supabase: Any | None = None,
) -> int:
    if retention_days < 1 or retention_days > 365:
        raise ValueError("retention_days must be between 1 and 365")

    client = supabase or get_supabase_service_role_client()
    response = client.rpc(
        "cleanup_analytics_events",
        {"retention_days": retention_days},
    ).execute()

    return max(0, _safe_int(response.data))


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
