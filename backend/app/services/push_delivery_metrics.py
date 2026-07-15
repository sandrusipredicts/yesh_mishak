from datetime import datetime
from typing import Any

from app.db.supabase import get_supabase_service_role_client


def get_push_delivery_metrics(
    *,
    window_started_at: datetime,
    window_ended_at: datetime,
    supabase: Any | None = None,
) -> dict[str, int | float]:
    client = supabase or get_supabase_service_role_client()
    response = (
        client.rpc(
            "get_push_delivery_metrics",
            {
                "window_start": window_started_at.isoformat(),
                "window_end": window_ended_at.isoformat(),
            },
        )
        .execute()
    )
    row = _first_rpc_row(response.data)
    attempted = max(0, _safe_int(row.get("attempted_count")))
    accepted = max(0, _safe_int(row.get("accepted_count")))
    failed = max(0, _safe_int(row.get("failed_count")))
    invalid_token = max(0, _safe_int(row.get("invalid_token_count")))
    acceptance_rate = accepted / attempted if attempted > 0 else 0.0
    return {
        "attempted_count": attempted,
        "accepted_count": accepted,
        "failed_count": failed,
        "invalid_token_count": invalid_token,
        "acceptance_rate": round(acceptance_rate, 4),
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
