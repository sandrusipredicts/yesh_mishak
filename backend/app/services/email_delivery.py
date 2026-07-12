from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    def __init__(self, reason: str, *, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


def send_email(
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> str:
    """Send one email through Resend's HTTPS API without automatic retries.

    The caller owns idempotency. Provider response bodies, credentials,
    recipient addresses, and message content are deliberately never logged.
    """
    settings = get_settings()
    api_key = settings.resend_api_key or settings.smtp_password
    if not api_key or not settings.email_from_address:
        raise EmailDeliveryError("not_configured")

    timeout = httpx.Timeout(15.0, connect=5.0, read=15.0, write=10.0, pool=5.0)
    try:
        response = httpx.post(
            settings.resend_api_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": settings.email_from_address,
                "to": [recipient],
                "subject": subject,
                "text": text_body,
                "html": html_body,
            },
            timeout=timeout,
        )
    except httpx.TimeoutException as exc:
        raise EmailDeliveryError("timeout") from exc
    except httpx.RequestError as exc:
        raise EmailDeliveryError("network_error") from exc

    if response.status_code not in (200, 201):
        logger.warning(
            "email provider rejected request",
            extra={
                "event": "email.delivery.rejected",
                "provider": "resend",
                "status_code": response.status_code,
            },
        )
        raise EmailDeliveryError("provider_error", status_code=response.status_code)

    try:
        payload = response.json()
    except ValueError as exc:
        raise EmailDeliveryError("malformed_response", status_code=response.status_code) from exc

    email_id = payload.get("id") if isinstance(payload, dict) else None
    if not isinstance(email_id, str) or not email_id.strip():
        raise EmailDeliveryError("missing_email_id", status_code=response.status_code)

    logger.info(
        "email accepted by provider",
        extra={"event": "email.delivery.accepted", "provider": "resend"},
    )
    return email_id
