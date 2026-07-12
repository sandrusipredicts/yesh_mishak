from __future__ import annotations

from dataclasses import dataclass
import logging

import httpx

from app.core.config import get_settings


logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    def __init__(self, reason: str, *, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class EmailDeliveryResult:
    accepted: bool
    provider_message_id: str | None = None
    reason: str | None = None


def _send_resend_email(
    *,
    recipient: str,
    sender: str,
    subject: str,
    text_body: str,
    html_body: str,
    idempotency_key: str | None = None,
) -> str:
    """Send through Resend HTTPS without logging secrets or retrying automatically."""
    settings = get_settings()
    api_key = settings.resend_api_key or settings.smtp_password
    if not api_key or not sender:
        raise EmailDeliveryError("not_configured")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    timeout = httpx.Timeout(15.0, connect=5.0, read=15.0, write=10.0, pool=5.0)
    try:
        response = httpx.post(
            settings.resend_api_url,
            headers=headers,
            json={
                "from": sender,
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


def send_email(
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
) -> str:
    settings = get_settings()
    return _send_resend_email(
        recipient=recipient,
        sender=settings.email_from_address or "",
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )


class ResendEmailDelivery:
    """Compatibility adapter for the existing password-reset service contract."""

    def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
        idempotency_key: str | None = None,
    ) -> EmailDeliveryResult:
        settings = get_settings()
        from_header = settings.password_reset_from_email or ""
        if from_header and settings.password_reset_from_name:
            from_header = f"{settings.password_reset_from_name} <{from_header}>"

        try:
            email_id = _send_resend_email(
                recipient=to_email,
                sender=from_header,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                idempotency_key=idempotency_key,
            )
        except EmailDeliveryError as exc:
            return EmailDeliveryResult(accepted=False, reason=exc.reason)
        return EmailDeliveryResult(accepted=True, provider_message_id=email_id)
