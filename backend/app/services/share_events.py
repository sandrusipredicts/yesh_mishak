from datetime import datetime
from typing import Any

from app.db.supabase import get_supabase_service_role_client
from app.schemas.share_events import ShareEventCreate

SHARE_EVENTS_TABLE = "share_events"


def record_share_event(
    event: ShareEventCreate,
    *,
    supabase: Any | None = None,
) -> None:
    client = supabase or get_supabase_service_role_client()
    payload = event.model_dump(exclude_none=True)
    client.table(SHARE_EVENTS_TABLE).insert(payload).execute()


def get_share_event_metrics(
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
    supabase: Any | None = None,
) -> list[dict[str, Any]]:
    client = supabase or get_supabase_service_role_client()
    response = (
        client.rpc(
            "get_share_event_metrics",
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
            "event_name": str(row.get("event_name") or ""),
            "entity_type": str(row.get("entity_type") or ""),
            "platform": str(row.get("platform") or ""),
            "mechanism": row.get("mechanism"),
            "outcome": str(row.get("outcome") or ""),
            "error_category": row.get("error_category"),
            "event_count": max(0, _safe_int(row.get("event_count"))),
        }
        for row in rows
        if isinstance(row, dict)
    ]


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
