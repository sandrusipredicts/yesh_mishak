from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import re
from typing import Any, Literal

from postgrest.exceptions import APIError

from app.services.authentication_audit_events import (
    AuthMethod,
    FailureCategory,
    RevocationReason,
)
from app.services.authentication_observability import safe_auth_log, safe_auth_monitor

MutationExecutionState = Literal[
    "confirmed_succeeded",
    "confirmed_failed",
    "outcome_ambiguous",
]

_POSTGRES_SQLSTATE = re.compile(r"^[0-9A-Z]{5}$")
_POSTGREST_ERROR_CODE = re.compile(r"^PGRST[0-9]{3}$")
_SERVICE_UNAVAILABLE_SQLSTATE_CLASSES = frozenset({"08", "53"})
_SERVICE_UNAVAILABLE_SQLSTATES = frozenset({"57P01", "57P02", "57P03"})
_SERVICE_UNAVAILABLE_POSTGREST_CODES = frozenset(
    {"PGRST000", "PGRST001", "PGRST002", "PGRST003"}
)
_INVALID_STATE_CODES = frozenset(
    {
        "42501",  # insufficient_privilege
        "42704",  # undefined_object
        "42883",  # undefined_function
        "42P01",  # undefined_table
        "PGRST202",  # function absent from the schema cache
        "PGRST203",  # overloaded function ambiguity
        "PGRST204",  # referenced column absent from the schema cache
    }
)


@dataclass(frozen=True)
class MutationExecution:
    state: MutationExecutionState
    response: Any | None = None
    failure_category: FailureCategory | None = None
    ambiguity_reason: Literal[
        "transport_failure",
        "response_processing_failure",
    ] | None = None


def _structured_postgrest_error_code(exc: APIError) -> str | None:
    code = exc.code
    if not isinstance(code, str):
        return None
    normalized = code.strip().upper()
    if _POSTGRES_SQLSTATE.fullmatch(normalized):
        return normalized
    if _POSTGREST_ERROR_CODE.fullmatch(normalized):
        return normalized
    return None


def _failure_category(code: str) -> FailureCategory:
    if (
        code[:2] in _SERVICE_UNAVAILABLE_SQLSTATE_CLASSES
        or code in _SERVICE_UNAVAILABLE_SQLSTATES
        or code in _SERVICE_UNAVAILABLE_POSTGREST_CODES
    ):
        return "service_unavailable"
    if code in _INVALID_STATE_CODES:
        return "invalid_state"
    return "internal_error"


def execute_postgrest_mutation(
    operation: Callable[[], Any],
    *,
    validate_response: Callable[[Any], Any | None],
) -> MutationExecution:
    """Execute one transactional RPC without inferring outcome from type alone.

    The postgrest-py 0.18 RPC builder resolves through
    ``SyncSingleRequestBuilder.execute``. It raises a direct ``APIError`` for a
    decoded non-success HTTP response, and the same type *with exception
    context* when response validation or decoding fails. Only the former, with
    a structured PostgREST/SQLSTATE code, is sufficient evidence of rollback.
    A successful HTTP response is not confirmed until the operation-specific
    validator accepts its bounded response shape.
    """

    try:
        response = operation()
    except APIError as exc:
        # A cause or context means response processing itself failed. That can
        # happen after an HTTP success and therefore cannot prove rollback.
        if exc.__cause__ is not None or exc.__context__ is not None:
            return MutationExecution(
                state="outcome_ambiguous",
                ambiguity_reason="response_processing_failure",
            )
        code = _structured_postgrest_error_code(exc)
        if code is None:
            return MutationExecution(
                state="outcome_ambiguous",
                ambiguity_reason="response_processing_failure",
            )
        return MutationExecution(
            state="confirmed_failed",
            failure_category=_failure_category(code),
        )
    except Exception:  # noqa: BLE001 - transport/client outcome is unknowable
        return MutationExecution(
            state="outcome_ambiguous",
            ambiguity_reason="transport_failure",
        )

    try:
        validated_response = validate_response(response)
    except Exception:  # noqa: BLE001 - response diagnostics are never exposed
        validated_response = None
    if validated_response is None:
        return MutationExecution(
            state="outcome_ambiguous",
            ambiguity_reason="response_processing_failure",
        )
    return MutationExecution(
        state="confirmed_succeeded",
        response=validated_response,
    )


def observe_ambiguous_mutation(
    logger: logging.Logger,
    *,
    auth_method: AuthMethod,
    revocation_reason: RevocationReason,
    user_id_present: bool,
    ambiguity_reason: str | None,
) -> None:
    """Emit bounded, non-throwing telemetry for an unknowable commit state."""

    bounded_reason = (
        ambiguity_reason
        if ambiguity_reason
        in {"transport_failure", "response_processing_failure"}
        else "response_processing_failure"
    )
    context = {
        "event": "auth.token_revocation.outcome_ambiguous",
        "auth_method": auth_method,
        "revocation_reason": revocation_reason,
        "user_id_present": user_id_present,
        "ambiguity_reason": bounded_reason,
    }
    safe_auth_log(
        logger,
        "warning",
        "authentication mutation outcome is ambiguous",
        extra=context,
    )
    safe_auth_monitor(
        "Authentication mutation outcome is ambiguous",
        level="warning",
        **context,
    )
