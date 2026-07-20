import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_active_user
from app.errors import raise_api_error
from app.rate_limit import check_rate_limit_by_user
from app.schemas.analytics_events import AnalyticsEventBatch, AnalyticsEventIn
from app.services.analytics_events import record_analytics_events

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


@router.post("/events", status_code=status.HTTP_202_ACCEPTED)
async def create_analytics_events(
    batch: AnalyticsEventBatch,
    request: Request,
    current_user: dict[str, Any] = Depends(require_active_user),
) -> dict[str, Any]:
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]),
        "analytics_events_create",
        [(30, 60), (200, 3600)],
    )
    if rate_limit_hit:
        return rate_limit_hit

    accepted: list[AnalyticsEventIn] = []
    rejected = 0
    for item in batch.events:
        try:
            accepted.append(AnalyticsEventIn.model_validate(item))
        except ValidationError:
            rejected += 1

    if rejected:
        # Counts only -- rejected payload contents are never logged.
        logger.warning(
            "rejected malformed analytics events",
            extra={
                "event": "analytics_events.validation.rejected",
                "endpoint": _endpoint_path(request),
                "accepted_count": len(accepted),
                "rejected_count": rejected,
                "result": "partial_rejection",
            },
        )

    if accepted:
        try:
            await run_in_threadpool(record_analytics_events, accepted)
        except Exception as exc:
            logger.warning(
                "failed to persist analytics events",
                extra={
                    "event": "analytics_events.persist.failure",
                    "endpoint": _endpoint_path(request),
                    "accepted_count": len(accepted),
                    "rejected_count": rejected,
                    "exception_type": exc.__class__.__name__,
                    "result": "failure",
                },
                exc_info=True,
            )
            raise_api_error(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="ANALYTICS_UNAVAILABLE",
                message="Analytics ingestion is temporarily unavailable",
            )

    return {"accepted": len(accepted), "rejected": rejected}


def _endpoint_path(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "/analytics/events"
