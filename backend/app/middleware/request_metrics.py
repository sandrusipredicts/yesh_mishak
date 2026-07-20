import logging
from time import perf_counter
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.concurrency import run_in_threadpool

from app.services.api_request_metrics import record_api_request_metric

logger = logging.getLogger(__name__)

EXCLUDED_METRIC_PATHS = {
    "/",
    "/admin/engagement",
    "/admin/monitoring",
    "/health",
    "/healthz",
    "/ready",
    "/readiness",
    "/live",
    "/liveness",
}


def should_record_request_metric(request: Request) -> bool:
    if request.method.upper() == "OPTIONS":
        return False
    path = request.url.path
    return path not in EXCLUDED_METRIC_PATHS


def get_normalized_path(request: Request) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return "__unmatched__"


async def request_metrics_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    start = perf_counter()
    should_record = should_record_request_metric(request)

    try:
        response = await call_next(request)
    except Exception:
        if should_record:
            await _record_metric_safely(
                request=request,
                status_code=500,
                duration_ms=_duration_ms(start),
            )
        raise

    if should_record:
        await _record_metric_safely(
            request=request,
            status_code=response.status_code,
            duration_ms=_duration_ms(start),
        )
    return response


def _duration_ms(start: float) -> int:
    return max(0, round((perf_counter() - start) * 1000))


async def _record_metric_safely(
    *,
    request: Request,
    status_code: int,
    duration_ms: int,
) -> None:
    normalized_path = get_normalized_path(request)
    try:
        await run_in_threadpool(
            record_api_request_metric,
            method=request.method,
            normalized_path=normalized_path,
            status_code=status_code,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        logger.warning(
            "failed to persist api request metric",
            extra={
                "event": "api_request_metrics.persist.failure",
                "method": request.method,
                "normalized_path": normalized_path,
                "status_code": status_code,
                "exception_type": exc.__class__.__name__,
                "result": "partial_failure",
            },
            exc_info=True,
        )
