from __future__ import annotations

import logging
import re
from typing import Literal
from uuid import uuid4

from app.core.config import get_settings
from app.db.supabase import get_supabase_service_role_client
from app.monitoring import resolve_environment
from app.services.authentication_observability import safe_auth_log, safe_auth_monitor

logger = logging.getLogger(__name__)

EventType = Literal["login", "logout", "token_revocation"]
Outcome = Literal["succeeded", "failed"]
AuthMethod = Literal["password", "google", "bearer", "recovery"]
FailureCategory = Literal[
    "invalid_credentials",
    "invalid_provider_credential",
    "email_not_verified",
    "account_link_required",
    "rate_limited",
    "identity_conflict",
    "service_unavailable",
    "invalid_state",
    "internal_error",
]
RevocationReason = Literal[
    "logout",
    "google_unlinked",
    "password_set",
    "password_removed",
    "password_reset",
    "account_deleted",
]

_UNSAFE_ENVIRONMENT_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]+")
_MULTIPLE_SEPARATORS = re.compile(r"-{2,}")
_ENVIRONMENT_MAX_LENGTH = 32


class UnexpectedAuthenticationAuditResponse(RuntimeError):
    """The audit RPC returned neither an insertion nor an idempotent replay."""


def _persistence_error_category(exc: Exception) -> str:
    if isinstance(exc, UnexpectedAuthenticationAuditResponse):
        return "unexpected_response"
    code = getattr(exc, "code", None)
    if code is None and exc.args and isinstance(exc.args[0], dict):
        code = exc.args[0].get("code")
    if str(code) == "23505":
        return "idempotency_conflict"
    return "persistence_error"


def new_audit_event_id() -> str:
    return str(uuid4())


def new_auth_correlation_id() -> str:
    return uuid4().hex


def source_environment() -> str:
    """Return a bounded database-safe deployment label from server settings."""
    resolved = resolve_environment(get_settings().sentry_environment)
    normalized = _UNSAFE_ENVIRONMENT_CHARACTERS.sub("-", resolved.strip().lower())
    normalized = _MULTIPLE_SEPARATORS.sub("-", normalized).strip("._-")
    return normalized[:_ENVIRONMENT_MAX_LENGTH].rstrip("._-") or "unknown"


def record_authentication_event(
    *,
    event_id: str,
    event_type: EventType,
    outcome: Outcome,
    auth_method: AuthMethod,
    correlation_id: str,
    user_id: str | None = None,
    failure_category: FailureCategory | None = None,
    revocation_reason: RevocationReason | None = None,
) -> bool:
    """Synchronously persist one event without changing auth behavior on failure."""
    environment = "unknown"
    try:
        environment = source_environment()
        params = {
            "p_event_id": event_id,
            "p_event_type": event_type,
            "p_outcome": outcome,
            "p_auth_method": auth_method,
            "p_user_id": user_id,
            "p_failure_category": failure_category,
            "p_revocation_reason": revocation_reason,
            "p_correlation_id": correlation_id,
            "p_source_environment": environment,
        }
        response = (
            get_supabase_service_role_client()
            .rpc("record_authentication_audit_event", params)
            .execute()
        )
        result = response.data
        if isinstance(result, list):
            if len(result) != 1 or not isinstance(result[0], bool):
                raise UnexpectedAuthenticationAuditResponse
            return result[0]
        if isinstance(result, bool):
            return result
        raise UnexpectedAuthenticationAuditResponse
    except Exception as exc:  # noqa: BLE001 - audit persistence is non-fatal
        error_category = _persistence_error_category(exc)
        warning_context = {
            "event": "auth.audit.persist.failure",
            "audit_event_type": event_type,
            "outcome": outcome,
            "auth_method": auth_method,
            "failure_category": failure_category,
            "revocation_reason": revocation_reason,
            "environment": environment,
            "user_id_present": user_id is not None,
            "audit_event_id": event_id,
            "correlation_id": correlation_id,
            "exception_type": exc.__class__.__name__,
            "error_category": error_category,
            "result": "partial_failure",
        }
        safe_auth_log(
            logger,
            "warning",
            "authentication audit persistence failed; authentication will continue",
            extra=warning_context,
        )

        # High-cardinality event, correlation, and user identifiers are
        # deliberately excluded from monitoring tags.
        safe_auth_monitor(
            "Authentication audit event persistence failed",
            level="warning",
            event="auth.audit.persist.failure",
            audit_event_type=event_type,
            outcome=outcome,
            auth_method=auth_method,
            failure_category=failure_category,
            revocation_reason=revocation_reason,
            environment=environment,
            user_id_present=user_id is not None,
            exception_type=exc.__class__.__name__,
            error_category=error_category,
        )
        return False


def record_token_revocation_event(
    *,
    outcome: Outcome,
    auth_method: AuthMethod,
    revocation_reason: RevocationReason,
    user_id: str | None,
    failure_category: FailureCategory | None = None,
) -> bool:
    """Persist one independently correlated revocation outcome.

    Event and correlation identifiers are generated exactly once per durable
    event. Failure observability contains only bounded taxonomy values; the
    high-cardinality identifiers remain confined to the persistence helper's
    structured log and are never monitoring tags.
    """
    try:
        event_id = new_audit_event_id()
        correlation_id = new_auth_correlation_id()
        persisted = record_authentication_event(
            event_id=event_id,
            event_type="token_revocation",
            outcome=outcome,
            auth_method=auth_method,
            correlation_id=correlation_id,
            user_id=user_id,
            failure_category=failure_category,
            revocation_reason=revocation_reason,
        )
    except Exception:  # noqa: BLE001 - every audit step is non-fatal
        safe_auth_log(
            logger,
            "warning",
            "authentication audit event construction failed; authentication will continue",
            extra={
                "event": "auth.audit.construct.failure",
                "audit_event_type": "token_revocation",
                "outcome": outcome,
                "auth_method": auth_method,
                "failure_category": failure_category,
                "revocation_reason": revocation_reason,
                "user_id_present": user_id is not None,
                "result": "partial_failure",
            },
        )
        safe_auth_monitor(
            "Authentication audit event construction failed",
            level="warning",
            event="auth.audit.construct.failure",
            audit_event_type="token_revocation",
            outcome=outcome,
            auth_method=auth_method,
            failure_category=failure_category,
            revocation_reason=revocation_reason,
            user_id_present=user_id is not None,
        )
        persisted = False
    if outcome == "failed":
        safe_auth_log(
            logger,
            "warning",
            "authoritative authentication token revocation failed",
            extra={
                "event": "auth.token_revocation.failure",
                "auth_method": auth_method,
                "failure_category": failure_category,
                "revocation_reason": revocation_reason,
                "user_id_present": user_id is not None,
            },
        )
        safe_auth_monitor(
            "Authoritative authentication token revocation failed",
            level="warning",
            event="auth.token_revocation.failure",
            auth_method=auth_method,
            failure_category=failure_category,
            revocation_reason=revocation_reason,
            user_id_present=user_id is not None,
        )
    return persisted
