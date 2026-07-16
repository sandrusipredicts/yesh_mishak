import logging
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from starlette.concurrency import run_in_threadpool

from app.auth.dependencies import require_active_user
from app.errors import raise_api_error
from app.rate_limit import check_rate_limit_by_user
from app.schemas.share_events import ShareEventCreate
from app.services.share_events import record_share_event

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


@router.post("/share-events", status_code=status.HTTP_202_ACCEPTED)
async def create_share_event(
    event: ShareEventCreate,
    request: Request,
    current_user: dict[str, Any] = Depends(require_active_user),
) -> dict[str, str]:
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]),
        "share_events_create",
        [(60, 60), (300, 3600)],
    )
    if rate_limit_hit:
        return rate_limit_hit

    try:
        await run_in_threadpool(record_share_event, event)
    except Exception as exc:
        logger.warning(
            "failed to persist share analytics event",
            extra={
                "event": "share_events.persist.failure",
                "endpoint": request.scope.get("route").path if request.scope.get("route") else "/analytics/share-events",
                "event_name": event.event_name,
                "entity_type": event.entity_type,
                "platform": event.platform,
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

    return {"status": "accepted"}
