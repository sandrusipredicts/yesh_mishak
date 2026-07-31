"""Bounded, fail-open runtime recording for approved security routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Literal
from uuid import UUID, uuid4

from app.db.supabase import get_supabase_service_role_client
from app.services.authentication_observability import safe_auth_log, safe_auth_monitor
from app.services.security_account_pseudonym import (
    SecurityAccountPseudonymError,
    canonicalize_account_uuid,
    derive_account_pseudonym,
)
from app.services.security_attribution_config import (
    SecurityAttributionConfigurationError,
    SecurityAttributionRuntimeConfiguration,
    get_security_attribution_runtime_configuration,
)


logger = logging.getLogger(__name__)

SecurityEventCategory = Literal[
    "session_security_change",
    "credential_method_change",
    "account_lifecycle_change",
]
SecurityRouteKey = Literal[
    "auth_logout",
    "auth_google_link",
    "auth_google_unlink",
    "auth_password_set",
    "auth_password_remove",
    "auth_account_delete",
]
SecurityHttpMethod = Literal["POST", "DELETE"]
SecurityOutcome = Literal["succeeded", "denied", "failed", "ambiguous"]
SecurityFailureCategory = Literal[
    "authorization_denied",
    "reauthentication_failed",
    "validation_rejected",
    "conflict",
    "not_found",
    "rate_limited",
    "dependency_unavailable",
    "outcome_unknown",
    "internal_error",
]
RecorderFailureCategory = Literal[
    "invalid_configuration",
    "pseudonym_derivation_failed",
    "ingestion_rpc_failed",
    "unexpected_rpc_response",
    "unexpected_failure",
]
RecorderStatus = Literal[
    "inserted",
    "already_recorded",
    "disabled",
    "failed",
]

SECURITY_ATTRIBUTION_RPC_TIMEOUT_SECONDS = 2.0
_APPROVED_ROUTE_REGISTRY = frozenset(
    {
        ("session_security_change", "auth_logout", "POST"),
        ("credential_method_change", "auth_google_link", "POST"),
        ("credential_method_change", "auth_google_unlink", "POST"),
        ("credential_method_change", "auth_password_set", "POST"),
        ("credential_method_change", "auth_password_remove", "POST"),
        ("account_lifecycle_change", "auth_account_delete", "DELETE"),
    }
)
_APPROVED_OUTCOME_FAILURES: dict[str, frozenset[str | None]] = {
    "succeeded": frozenset({None}),
    "denied": frozenset({"authorization_denied", "reauthentication_failed"}),
    "failed": frozenset(
        {
            "validation_rejected",
            "conflict",
            "not_found",
            "rate_limited",
            "dependency_unavailable",
            "internal_error",
        }
    ),
    "ambiguous": frozenset({"outcome_unknown"}),
}


class SecurityAttributionEventValidationError(ValueError):
    """An event is outside the initial closed application registry."""


class SecurityAttributionRecorderError(RuntimeError):
    """A bounded recorder failure safe for fail-open classification."""

    def __init__(
        self,
        failure_category: RecorderFailureCategory,
        *,
        environment: str = "unavailable",
    ) -> None:
        self.failure_category = failure_category
        self.environment = environment
        super().__init__("security attribution recording failed")


@dataclass(frozen=True, slots=True, repr=False)
class SecurityAttributionEventRequest:
    """One immutable request, including IDs and UTC time captured exactly once."""

    request_event_id: UUID
    occurred_at: datetime
    trusted_account_uuid: UUID
    event_category: SecurityEventCategory
    route_key: SecurityRouteKey
    http_method: SecurityHttpMethod
    outcome: SecurityOutcome
    failure_category: SecurityFailureCategory | None
    server_correlation_id: UUID | None

    def __repr__(self) -> str:
        return (
            "SecurityAttributionEventRequest("
            "request_event_id='[REDACTED]', "
            f"occurred_at={self.occurred_at!r}, "
            "trusted_account_uuid='[REDACTED]', "
            f"event_category={self.event_category!r}, "
            f"route_key={self.route_key!r}, "
            f"http_method={self.http_method!r}, "
            f"outcome={self.outcome!r}, "
            f"failure_category={self.failure_category!r}, "
            "server_correlation_id='[REDACTED]')"
        )


@dataclass(frozen=True, slots=True)
class SecurityAttributionRecordResult:
    status: RecorderStatus
    failure_category: RecorderFailureCategory | None = None

    def __post_init__(self) -> None:
        if (self.status == "failed") != (self.failure_category is not None):
            raise ValueError("security attribution recorder result is inconsistent")


def _nonzero_uuid(value: UUID | str, *, category: str) -> UUID:
    try:
        parsed = value if isinstance(value, UUID) else UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise SecurityAttributionEventValidationError(
            f"{category} is invalid"
        ) from None
    if parsed.int == 0:
        raise SecurityAttributionEventValidationError(f"{category} is invalid")
    return parsed


def _validate_event_request(event: SecurityAttributionEventRequest) -> None:
    if not isinstance(event, SecurityAttributionEventRequest):
        raise SecurityAttributionEventValidationError(
            "security attribution event request is invalid"
        )
    if not all(
        isinstance(value, str)
        for value in (event.event_category, event.route_key, event.http_method)
    ) or (
        event.event_category,
        event.route_key,
        event.http_method,
    ) not in _APPROVED_ROUTE_REGISTRY:
        raise SecurityAttributionEventValidationError(
            "security attribution route tuple is unsupported"
        )
    if (
        not isinstance(event.outcome, str)
        or event.outcome not in _APPROVED_OUTCOME_FAILURES
        or (
            event.failure_category is not None
            and not isinstance(event.failure_category, str)
        )
        or event.failure_category
        not in _APPROVED_OUTCOME_FAILURES[event.outcome]
    ):
        raise SecurityAttributionEventValidationError(
            "security attribution outcome is invalid"
        )
    if not isinstance(event.request_event_id, UUID) or event.request_event_id.int == 0:
        raise SecurityAttributionEventValidationError(
            "request event UUID is invalid"
        )
    if (
        not isinstance(event.trusted_account_uuid, UUID)
        or event.trusted_account_uuid.int == 0
    ):
        raise SecurityAttributionEventValidationError(
            "trusted account UUID is invalid"
        )
    if (
        not isinstance(event.occurred_at, datetime)
        or event.occurred_at.tzinfo is None
        or event.occurred_at.utcoffset() is None
    ):
        raise SecurityAttributionEventValidationError(
            "security attribution event time is invalid"
        )
    if event.server_correlation_id is not None and (
        not isinstance(event.server_correlation_id, UUID)
        or event.server_correlation_id.int == 0
    ):
        raise SecurityAttributionEventValidationError(
            "server correlation UUID is invalid"
        )


class SecurityAttributionRecorder:
    """Create and synchronously persist immutable attribution events."""

    def __init__(
        self,
        *,
        configuration_provider: Callable[
            [], SecurityAttributionRuntimeConfiguration
        ]
        | None = None,
        service_role_client_factory: Callable[[float], Any] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._configuration_provider = (
            configuration_provider or get_security_attribution_runtime_configuration
        )
        self._service_role_client_factory = service_role_client_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def create_event(
        self,
        *,
        trusted_account_uuid: UUID | str,
        route_key: SecurityRouteKey,
        event_category: SecurityEventCategory,
        http_method: SecurityHttpMethod,
        outcome: SecurityOutcome,
        failure_category: SecurityFailureCategory | None = None,
        server_correlation_id: UUID | str | None = None,
        request_event_id: UUID | None = None,
    ) -> SecurityAttributionEventRequest:
        """Capture one server time and one event ID after a bounded outcome exists."""

        if (event_category, route_key, http_method) not in _APPROVED_ROUTE_REGISTRY:
            raise SecurityAttributionEventValidationError(
                "security attribution route tuple is unsupported"
            )
        if (
            outcome not in _APPROVED_OUTCOME_FAILURES
            or failure_category not in _APPROVED_OUTCOME_FAILURES[outcome]
        ):
            raise SecurityAttributionEventValidationError(
                "security attribution outcome is invalid"
            )

        try:
            account_uuid = UUID(canonicalize_account_uuid(trusted_account_uuid))
        except SecurityAccountPseudonymError:
            raise SecurityAttributionEventValidationError(
                "trusted account UUID is invalid"
            ) from None

        event_id = request_event_id or uuid4()
        if event_id.int == 0:
            raise SecurityAttributionEventValidationError(
                "request event UUID is invalid"
            )

        captured_at = self._clock()
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise SecurityAttributionEventValidationError(
                "security attribution event time is invalid"
            )
        captured_at = captured_at.astimezone(timezone.utc)

        correlation_uuid = (
            _nonzero_uuid(server_correlation_id, category="server correlation UUID")
            if server_correlation_id is not None
            else None
        )

        return SecurityAttributionEventRequest(
            request_event_id=event_id,
            occurred_at=captured_at,
            trusted_account_uuid=account_uuid,
            event_category=event_category,
            route_key=route_key,
            http_method=http_method,
            outcome=outcome,
            failure_category=failure_category,
            server_correlation_id=correlation_uuid,
        )

    def _service_role_client(self) -> Any:
        if self._service_role_client_factory is not None:
            return self._service_role_client_factory(
                SECURITY_ATTRIBUTION_RPC_TIMEOUT_SECONDS
            )
        return get_supabase_service_role_client(
            postgrest_timeout_seconds=SECURITY_ATTRIBUTION_RPC_TIMEOUT_SECONDS
        )

    def record(
        self,
        event: SecurityAttributionEventRequest,
    ) -> SecurityAttributionRecordResult:
        """Persist only through the ingestion RPC using one captured config snapshot."""

        _validate_event_request(event)

        try:
            runtime_configuration = self._configuration_provider()
        except SecurityAttributionConfigurationError:
            raise SecurityAttributionRecorderError("invalid_configuration") from None
        except Exception:
            raise SecurityAttributionRecorderError("invalid_configuration") from None

        if not runtime_configuration.enabled:
            return SecurityAttributionRecordResult(status="disabled")

        active_configuration = runtime_configuration.active
        if active_configuration is None:
            raise SecurityAttributionRecorderError("invalid_configuration")
        environment = (
            active_configuration.environment
            if active_configuration.environment
            in {"development", "staging", "production"}
            else "unavailable"
        )

        event_epoch = event.occurred_at.astimezone(timezone.utc).strftime("%Y-%m")
        if event_epoch != active_configuration.epoch:
            raise SecurityAttributionRecorderError(
                "invalid_configuration",
                environment=environment,
            )

        try:
            derived = derive_account_pseudonym(
                event.trusted_account_uuid,
                environment=active_configuration.environment,
                epoch=active_configuration.epoch,
                key_version=active_configuration.key_version,
                key_material=active_configuration.key_material,
            )
        except SecurityAccountPseudonymError:
            raise SecurityAttributionRecorderError(
                "pseudonym_derivation_failed",
                environment=environment,
            ) from None

        params = {
            "p_request_event_id": str(event.request_event_id),
            "p_occurred_at": event.occurred_at.isoformat(),
            "p_account_pseudonym": derived.pseudonym,
            "p_pseudonym_epoch": active_configuration.epoch,
            "p_pseudonym_key_version": active_configuration.key_version,
            "p_environment": active_configuration.environment,
            "p_event_category": event.event_category,
            "p_route_key": event.route_key,
            "p_http_method": event.http_method,
            "p_outcome": event.outcome,
            "p_failure_category": event.failure_category,
            "p_server_correlation_id": (
                str(event.server_correlation_id)
                if event.server_correlation_id is not None
                else None
            ),
        }

        try:
            response = (
                self._service_role_client()
                .rpc("record_security_request_attribution_event", params)
                .execute()
            )
        except Exception:
            raise SecurityAttributionRecorderError(
                "ingestion_rpc_failed",
                environment=environment,
            ) from None

        try:
            rpc_result = response.data
            if isinstance(rpc_result, list):
                if len(rpc_result) != 1:
                    raise ValueError
                rpc_result = rpc_result[0]
            if rpc_result not in ("inserted", "already_recorded"):
                raise ValueError
        except Exception:
            raise SecurityAttributionRecorderError(
                "unexpected_rpc_response",
                environment=environment,
            ) from None

        return SecurityAttributionRecordResult(status=rpc_result)


def _warn_recording_failure(
    *,
    failure_category: RecorderFailureCategory,
    route_key: SecurityRouteKey,
    event_category: SecurityEventCategory,
    http_method: SecurityHttpMethod,
    environment: str,
) -> None:
    warning_fields = {
        "recorder_failure_category": failure_category,
        "route_key": route_key,
        "event_category": event_category,
        "http_method": http_method,
        "environment": environment,
    }
    safe_auth_log(
        logger,
        "warning",
        "security attribution recording failed; business response is unchanged",
        extra=warning_fields,
    )
    safe_auth_monitor(
        "Security attribution recording failed",
        level="warning",
        **warning_fields,
    )


def record_authenticated_security_event(
    *,
    trusted_account_uuid: UUID | str,
    route_key: SecurityRouteKey,
    event_category: SecurityEventCategory,
    http_method: SecurityHttpMethod,
    outcome: SecurityOutcome,
    failure_category: SecurityFailureCategory | None = None,
    server_correlation_id: UUID | str | None = None,
) -> SecurityAttributionRecordResult:
    """Fail-open route helper requiring every approved bounded event field."""

    recorder = SecurityAttributionRecorder()
    try:
        event = recorder.create_event(
            trusted_account_uuid=trusted_account_uuid,
            route_key=route_key,
            event_category=event_category,
            http_method=http_method,
            outcome=outcome,
            failure_category=failure_category,
            server_correlation_id=server_correlation_id,
        )
        return recorder.record(event)
    except SecurityAttributionRecorderError as exc:
        recorder_failure_category = exc.failure_category
        environment = exc.environment
    except Exception:
        recorder_failure_category = "unexpected_failure"
        environment = "unavailable"

    _warn_recording_failure(
        failure_category=recorder_failure_category,
        route_key=route_key,
        event_category=event_category,
        http_method=http_method,
        environment=environment,
    )
    return SecurityAttributionRecordResult(
        status="failed",
        failure_category=recorder_failure_category,
    )
