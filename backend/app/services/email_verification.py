from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import html
import secrets
import smtplib
from email.message import EmailMessage
from urllib.parse import quote

from app.core.config import get_settings
from app.db.supabase import get_supabase_service_role_client


GENERIC_RESEND_MESSAGE = "If the account exists and needs verification, a new email will be sent."


class VerificationDeliveryError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _verification_url(token: str) -> str:
    base = get_settings().public_app_url.rstrip("/")
    return f"{base}/verify-email?token={quote(token, safe='')}"


def _send_email(recipient: str, verification_url: str) -> None:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_address:
        raise VerificationDeliveryError("Email delivery is not configured")

    message = EmailMessage()
    message["Subject"] = "Verify your yesh_mishak email"
    message["From"] = settings.smtp_from_address
    message["To"] = recipient
    message.set_content(
        "Verify your yesh_mishak email by opening this link:\n\n"
        f"{verification_url}\n\n"
        "If you did not create this account, you can ignore this message."
    )
    safe_url = html.escape(verification_url, quote=True)
    message.add_alternative(
        f'<p>Verify your yesh_mishak email:</p><p><a href="{safe_url}">Verify email</a></p>'
        "<p>If you did not create this account, you can ignore this message.</p>",
        subtype="html",
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password or "")
            server.send_message(message)
    except Exception as exc:
        raise VerificationDeliveryError("Email delivery failed") from exc


def issue_verification_email(user_id: str, email: str) -> None:
    settings = get_settings()
    client = get_supabase_service_role_client()
    now = _now()
    cooldown_since = now - timedelta(seconds=settings.email_verification_resend_cooldown_seconds)
    recent = (
        client.table("email_verification_tokens")
        .select("created_at")
        .eq("user_id", user_id)
        .is_("used_at", "null")
        .gte("created_at", cooldown_since.isoformat())
        .limit(1)
        .execute()
    )
    if recent.data:
        raise ValueError("VERIFICATION_COOLDOWN")

    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    expires_at = now + timedelta(minutes=settings.email_verification_ttl_minutes)
    client.table("email_verification_tokens").update({"used_at": now.isoformat()}).eq(
        "user_id", user_id
    ).is_("used_at", "null").execute()
    client.table("email_verification_tokens").insert(
        {
            "user_id": user_id,
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
        }
    ).execute()
    _send_email(email, _verification_url(raw_token))


def verify_email_token(token: str) -> str:
    result = get_supabase_service_role_client().rpc(
        "verify_email_token", {"p_token_hash": _hash_token(token)}
    ).execute()
    if isinstance(result.data, str):
        return result.data
    if isinstance(result.data, list) and result.data:
        value = result.data[0]
        return value if isinstance(value, str) else str(value)
    return "invalid"
