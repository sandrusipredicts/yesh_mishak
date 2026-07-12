from dataclasses import dataclass
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailDeliveryResult:
    accepted: bool
    provider_message_id: str | None = None
    reason: str | None = None


class ResendEmailDelivery:
    endpoint = "https://api.resend.com/emails"

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
        if not settings.resend_api_key or not settings.password_reset_from_email:
            logger.warning(
                "password reset email configuration missing",
                extra={"event": "auth.password_reset.email_config_missing"},
            )
            return EmailDeliveryResult(accepted=False, reason="configuration_missing")

        from_header = settings.password_reset_from_email
        if settings.password_reset_from_name:
            from_header = f"{settings.password_reset_from_name} <{settings.password_reset_from_email}>"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                        **({"Idempotency-Key": idempotency_key} if idempotency_key else {}),
                    },
                    json={
                        "from": from_header,
                        "to": [to_email],
                        "subject": subject,
                        "html": html_body,
                        "text": text_body,
                    },
                )
        except httpx.TimeoutException:
            logger.warning(
                "password reset email provider timed out",
                extra={"event": "auth.password_reset.email_timeout"},
            )
            return EmailDeliveryResult(accepted=False, reason="timeout")
        except httpx.HTTPError as exc:
            logger.warning(
                "password reset email provider request failed",
                extra={
                    "event": "auth.password_reset.email_http_error",
                    "exception_type": exc.__class__.__name__,
                },
            )
            return EmailDeliveryResult(accepted=False, reason="http_error")

        if 200 <= response.status_code < 300:
            try:
                data = response.json()
            except ValueError:
                data = {}
            return EmailDeliveryResult(
                accepted=True,
                provider_message_id=data.get("id") if isinstance(data, dict) else None,
            )

        logger.warning(
            "password reset email provider rejected request",
            extra={
                "event": "auth.password_reset.email_rejected",
                "status_code": response.status_code,
            },
        )
        return EmailDeliveryResult(accepted=False, reason="provider_rejected")
