from __future__ import annotations

import hashlib
import logging
import random
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import requests

from app.monitoring import capture_unexpected_exception
from app.services.firebase_push import FirebaseConfigError, send_fcm_notification
from app.services.job_runs import sanitize_error_message, sanitize_error_type

logger = logging.getLogger(__name__)

UNKNOWN_ERROR_MAX_RETRIES = 2
DEFAULT_BASE_DELAY_SECONDS = 30.0
DEFAULT_MAX_DELAY_SECONDS = 1800.0
DEFAULT_LEASE_DURATION_SECONDS = 300


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def classify_push_error(exc: Exception) -> str:
    if isinstance(exc, FirebaseConfigError):
        return "config_error"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code in (429, 500, 502, 503):
            return "transient"
        if code == 401:
            return "config_error"
        return "permanent"
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return "transient"
    return "unknown"


def extract_retry_after_seconds(response: requests.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        retry_dt = parsedate_to_datetime(raw)
        delta = (retry_dt - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)
    except (ValueError, TypeError):
        return None


def calculate_next_retry_at(
    attempt_count: int,
    retry_after_seconds: float | None = None,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    max_delay_seconds: float = DEFAULT_MAX_DELAY_SECONDS,
    now_fn: Callable[[], datetime] | None = None,
    jitter_fn: Callable[[float, float], float] | None = None,
) -> datetime:
    _now = (now_fn or _utc_now)()
    _jitter = jitter_fn or random.uniform

    if retry_after_seconds is not None:
        delay = min(retry_after_seconds, max_delay_seconds)
    else:
        delay = min(base_delay_seconds * (2 ** (attempt_count - 1)), max_delay_seconds)
        delay += _jitter(0, base_delay_seconds)

    return _now + timedelta(seconds=delay)


def record_and_claim_initial_delivery(
    client: Any,
    notification_id: str,
    push_token_id: str,
    token: str,
    title: str,
    body: str,
    data: dict[str, Any] | None,
    max_attempts: int = 5,
) -> dict[str, Any] | None:
    response = client.rpc(
        "claim_initial_push_delivery",
        {
            "p_notification_id": notification_id,
            "p_push_token_id": push_token_id,
            "p_token_hash": _token_hash(token),
            "p_title": title,
            "p_body": body,
            "p_push_data": data,
            "p_max_attempts": max_attempts,
            "p_lease_duration_seconds": DEFAULT_LEASE_DURATION_SECONDS,
        },
    ).execute()
    rows = response.data or []
    if not rows:
        return None
    return rows[0]


def cas_update_attempt(client: Any, attempt_id: str, lease_id: str, **fields: Any) -> bool:
    fields["updated_at"] = _utc_now().isoformat()
    result = (
        client.table("push_delivery_attempts")
        .update(fields)
        .eq("id", attempt_id)
        .eq("status", "processing")
        .eq("lease_id", lease_id)
        .execute()
    )
    return bool(result.data)


def invalidate_sibling_attempts(client: Any, push_token_id: str) -> int:
    result = (
        client.table("push_delivery_attempts")
        .update({
            "status": "failed_permanent",
            "last_error_type": "TOKEN_INVALIDATED",
            "updated_at": _utc_now().isoformat(),
        })
        .eq("push_token_id", push_token_id)
        .eq("status", "failed_retryable")
        .execute()
    )
    return len(result.data or [])


def handle_attempt_result(
    client: Any,
    attempt_id: str,
    lease_id: str,
    push_token_id: str | None,
    token: str | None,
    fcm_result: dict[str, Any] | None,
    exc: Exception | None,
    attempt_count: int,
    max_attempts: int,
    delete_token_fn: Callable[[Any, str], None] | None = None,
) -> str:
    now = _utc_now()

    if exc is None and fcm_result is not None:
        if fcm_result.get("invalid_token"):
            if push_token_id and token:
                invalidate_sibling_attempts(client, push_token_id)
                if delete_token_fn:
                    delete_token_fn(client, token)
            cas_update_attempt(
                client, attempt_id, lease_id,
                status="failed_permanent",
                last_error_type="INVALID_TOKEN",
                last_http_status=fcm_result.get("status_code"),
                last_attempted_at=now.isoformat(),
            )
            return "failed_permanent"

        if fcm_result.get("ok"):
            cas_update_attempt(
                client, attempt_id, lease_id,
                status="delivered",
                delivered_at=now.isoformat(),
                last_attempted_at=now.isoformat(),
            )
            return "delivered"

    if exc is not None:
        classification = classify_push_error(exc)
        http_status = None
        retry_after = None

        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            http_status = exc.response.status_code
            if http_status in (429, 503):
                retry_after = extract_retry_after_seconds(exc.response)

        if classification in ("config_error", "permanent"):
            cas_update_attempt(
                client, attempt_id, lease_id,
                status="failed_permanent",
                last_error_type=sanitize_error_type(exc.__class__.__name__),
                last_error_message=sanitize_error_message(str(exc)),
                last_http_status=http_status,
                last_attempted_at=now.isoformat(),
            )
            return "failed_permanent"

        effective_max = max_attempts
        if classification == "unknown":
            effective_max = min(max_attempts, UNKNOWN_ERROR_MAX_RETRIES)
            logger.error(
                "unknown push delivery error",
                extra={
                    "event": "push_delivery.unknown_error",
                    "attempt_id": attempt_id,
                    "attempt_count": attempt_count,
                    "exception_type": exc.__class__.__name__,
                },
                exc_info=True,
            )
            # Config/transient/permanent push failures are expected and
            # already routed/retried appropriately above; an "unknown"
            # classification means classify_push_error() couldn't place it
            # in any of those known buckets, which is exactly the unexpected
            # case worth surfacing.
            capture_unexpected_exception(
                exc,
                code="PUSH_DELIVERY_UNKNOWN_ERROR",
            )

        if attempt_count >= effective_max:
            cas_update_attempt(
                client, attempt_id, lease_id,
                status="abandoned",
                last_error_type=sanitize_error_type(exc.__class__.__name__),
                last_error_message=sanitize_error_message(str(exc)),
                last_http_status=http_status,
                last_attempted_at=now.isoformat(),
            )
            return "abandoned"

        next_retry = calculate_next_retry_at(attempt_count, retry_after_seconds=retry_after)
        cas_update_attempt(
            client, attempt_id, lease_id,
            status="failed_retryable",
            last_error_type=sanitize_error_type(exc.__class__.__name__),
            last_error_message=sanitize_error_message(str(exc)),
            last_http_status=http_status,
            next_retry_at=next_retry.isoformat(),
            last_attempted_at=now.isoformat(),
        )
        return "failed_retryable"

    cas_update_attempt(
        client, attempt_id, lease_id,
        status="failed_permanent",
        last_error_type="UNEXPECTED_RESULT",
        last_attempted_at=now.isoformat(),
    )
    return "failed_permanent"


def _load_token_for_retry(client: Any, push_token_id: str | None) -> str | None:
    if not push_token_id:
        return None
    rows = (
        client.table("push_tokens")
        .select("token")
        .eq("id", push_token_id)
        .execute()
        .data or []
    )
    if not rows:
        return None
    return rows[0].get("token")


def process_retry_batch(
    client: Any,
    batch_size: int = 50,
    staleness_seconds: int = 7200,
    lease_duration_seconds: int = DEFAULT_LEASE_DURATION_SECONDS,
) -> dict[str, int]:
    response = client.rpc(
        "claim_push_delivery_retries",
        {
            "p_batch_size": batch_size,
            "p_staleness_cutoff_seconds": staleness_seconds,
            "p_lease_duration_seconds": lease_duration_seconds,
        },
    ).execute()

    claimed = response.data or []
    if not claimed:
        return {"claimed": 0, "delivered": 0, "failed_retryable": 0, "failed_permanent": 0, "abandoned": 0}

    counts = {"claimed": len(claimed), "delivered": 0, "failed_retryable": 0, "failed_permanent": 0, "abandoned": 0}

    for attempt in claimed:
        attempt_id = attempt["id"]
        lease_id = attempt["lease_id"]
        push_token_id = attempt.get("push_token_id")
        attempt_count = attempt["attempt_count"]
        max_attempts_val = attempt["max_attempts"]

        token = _load_token_for_retry(client, push_token_id)
        if not token:
            cas_update_attempt(
                client, attempt_id, lease_id,
                status="failed_permanent",
                last_error_type="TOKEN_DELETED",
                last_attempted_at=_utc_now().isoformat(),
            )
            counts["failed_permanent"] += 1
            continue

        fcm_result = None
        exc = None
        try:
            fcm_result = send_fcm_notification(
                token,
                attempt["title"],
                attempt["body"],
                attempt.get("push_data"),
            )
        except FirebaseConfigError:
            raise
        except Exception as send_exc:
            exc = send_exc

        status = handle_attempt_result(
            client, attempt_id, lease_id,
            push_token_id, token,
            fcm_result, exc,
            attempt_count, max_attempts_val,
        )
        counts[status] = counts.get(status, 0) + 1

    return counts
