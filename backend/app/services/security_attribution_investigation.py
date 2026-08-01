"""Fail-closed application boundary for security-attribution investigations.

The merged query RPC is owner-only. This module deliberately provides no
database implementation until a separately reviewed named-principal database
capability can invoke that RPC without an owner credential in application
runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Literal, Protocol

from pydantic import TypeAdapter, ValidationError

from app.schemas.security_attribution_investigation import (
    SecurityAttributionEvidenceRow,
    SecurityAttributionInvestigationRequest,
    SecurityAttributionInvestigationResponse,
    SecurityAttributionInvestigationRpcRow,
)
from app.services.security_attribution_investigation_config import (
    SECURITY_ATTRIBUTION_INVESTIGATION_CAPABILITY,
    SecurityAttributionInvestigatorPrincipal,
)


SECURITY_ATTRIBUTION_INVESTIGATION_RPC = (
    "query_security_request_attribution_events"
)

InvestigationFailureCategory = Literal[
    "disabled",
    "authorization_denied",
    "validation_rejected",
    "query_failed",
    "unexpected_response",
    "access_audit_failed",
    "unexpected_failure",
]


class SecurityAttributionInvestigationError(RuntimeError):
    """A bounded failure that never includes evidence or exception text."""

    def __init__(self, failure_category: InvestigationFailureCategory) -> None:
        self.failure_category = failure_category
        super().__init__("security attribution investigation failed")


@dataclass(frozen=True, slots=True, repr=False)
class BoundedSecurityAttributionInvestigationQuery:
    """Exact RPC parameters plus a redacted named application principal."""

    request: SecurityAttributionInvestigationRequest
    investigator_principal: SecurityAttributionInvestigatorPrincipal

    @property
    def rpc_name(self) -> str:
        return SECURITY_ATTRIBUTION_INVESTIGATION_RPC

    @property
    def capability(self) -> str:
        return SECURITY_ATTRIBUTION_INVESTIGATION_CAPABILITY

    @property
    def rpc_parameters(self) -> dict[str, object]:
        return {
            "p_incident_id": str(self.request.incident_id),
            "p_environment": self.request.environment,
            "p_window_start": self.request.window_start.isoformat(),
            "p_window_end": self.request.window_end.isoformat(),
            "p_result_limit": self.request.limit,
        }

    def __repr__(self) -> str:
        return (
            "BoundedSecurityAttributionInvestigationQuery("
            f"rpc_name={self.rpc_name!r}, "
            "request='[REDACTED]', investigator_principal='[REDACTED]')"
        )


@dataclass(frozen=True, slots=True, repr=False)
class AuditedSecurityAttributionRpcResponse:
    """Result returned only after the RPC's access audit commits atomically."""

    rows: object
    access_audit_persisted: bool

    def __repr__(self) -> str:
        return (
            "AuditedSecurityAttributionRpcResponse("
            "rows='[REDACTED]', "
            f"access_audit_persisted={self.access_audit_persisted!r})"
        )


class SecurityAttributionInvestigationGateway(Protocol):
    """Future named-principal adapter for the one atomic owner-approved RPC."""

    def query_audited_security_attribution(
        self,
        query: BoundedSecurityAttributionInvestigationQuery,
    ) -> AuditedSecurityAttributionRpcResponse:
        """Execute only ``query.rpc_name`` through a reviewed trusted path."""
        ...


class UnavailableSecurityAttributionInvestigationGateway:
    """Production default while the named database capability is unapproved."""

    def query_audited_security_attribution(
        self,
        query: BoundedSecurityAttributionInvestigationQuery,
    ) -> AuditedSecurityAttributionRpcResponse:
        del query
        raise SecurityAttributionInvestigationError("disabled")


_RPC_ROWS = TypeAdapter(list[SecurityAttributionInvestigationRpcRow])
_UNAVAILABLE_GATEWAY = UnavailableSecurityAttributionInvestigationGateway()


def get_security_attribution_investigation_gateway(
) -> SecurityAttributionInvestigationGateway:
    """Return the deliberately unavailable runtime adapter."""

    return _UNAVAILABLE_GATEWAY


def _validate_succeeded_rows(
    request: SecurityAttributionInvestigationRequest,
    rows: list[SecurityAttributionInvestigationRpcRow],
) -> list[SecurityAttributionEvidenceRow]:
    if len(rows) > request.limit:
        raise SecurityAttributionInvestigationError("unexpected_response")

    evidence: list[SecurityAttributionEvidenceRow] = []
    previous_occurred_at = None
    for row in rows:
        if row.query_status != "succeeded":
            raise SecurityAttributionInvestigationError("unexpected_response")
        occurred_at = row.occurred_at
        if occurred_at is None:
            raise SecurityAttributionInvestigationError("unexpected_response")
        if not (request.window_start <= occurred_at < request.window_end):
            raise SecurityAttributionInvestigationError("unexpected_response")
        if row.environment != request.environment:
            raise SecurityAttributionInvestigationError("unexpected_response")
        if row.pseudonym_epoch != occurred_at.astimezone(timezone.utc).strftime(
            "%Y-%m"
        ):
            raise SecurityAttributionInvestigationError("unexpected_response")
        if previous_occurred_at is not None and occurred_at < previous_occurred_at:
            raise SecurityAttributionInvestigationError("unexpected_response")
        previous_occurred_at = occurred_at
        evidence.append(SecurityAttributionEvidenceRow.from_rpc_row(row))
    return evidence


def investigate_security_attribution(
    request: SecurityAttributionInvestigationRequest,
    *,
    investigator_principal: SecurityAttributionInvestigatorPrincipal,
    gateway: SecurityAttributionInvestigationGateway,
) -> SecurityAttributionInvestigationResponse:
    """Return evidence only after the gateway proves the atomic audit boundary."""

    query = BoundedSecurityAttributionInvestigationQuery(
        request=request,
        investigator_principal=investigator_principal,
    )
    try:
        rpc_response = gateway.query_audited_security_attribution(query)
    except SecurityAttributionInvestigationError:
        raise
    except Exception:
        raise SecurityAttributionInvestigationError("unexpected_failure") from None

    if (
        not isinstance(rpc_response, AuditedSecurityAttributionRpcResponse)
        or rpc_response.access_audit_persisted is not True
    ):
        raise SecurityAttributionInvestigationError("access_audit_failed")

    try:
        rows = _RPC_ROWS.validate_python(rpc_response.rows)
    except (TypeError, ValidationError, ValueError):
        raise SecurityAttributionInvestigationError("unexpected_response") from None

    statuses = {row.query_status for row in rows}
    if statuses == {"rejected"} and len(rows) == 1:
        raise SecurityAttributionInvestigationError("validation_rejected")
    if statuses == {"failed"} and len(rows) == 1:
        raise SecurityAttributionInvestigationError("query_failed")
    if statuses and statuses != {"succeeded"}:
        raise SecurityAttributionInvestigationError("unexpected_response")

    evidence = _validate_succeeded_rows(request, rows)
    return SecurityAttributionInvestigationResponse(
        incident_id=request.incident_id,
        environment=request.environment,
        window_start=request.window_start,
        window_end=request.window_end,
        result_count=len(evidence),
        evidence=evidence,
    )
