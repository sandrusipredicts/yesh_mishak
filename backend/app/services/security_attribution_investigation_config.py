"""Default-deny configuration for the security-attribution investigator."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

from app.core.config import Settings, get_settings


SECURITY_ATTRIBUTION_INVESTIGATION_CAPABILITY = (
    "security_attribution_investigate"
)


class SecurityAttributionInvestigationConfigurationError(RuntimeError):
    """Enabled investigator configuration is incomplete or invalid."""


@dataclass(frozen=True, slots=True, repr=False)
class SecurityAttributionInvestigatorPrincipal:
    """One authenticated internal principal, always redacted in diagnostics."""

    internal_id: UUID

    def __repr__(self) -> str:
        return "SecurityAttributionInvestigatorPrincipal(internal_id='[REDACTED]')"


@dataclass(frozen=True, slots=True, repr=False)
class ActiveSecurityAttributionInvestigationConfiguration:
    """One immutable allowlist snapshot; principal values remain redacted."""

    investigator_principals: frozenset[UUID]

    def __post_init__(self) -> None:
        if not self.investigator_principals:
            raise SecurityAttributionInvestigationConfigurationError(
                "security attribution investigation configuration is invalid"
            )

    def __repr__(self) -> str:
        return (
            "ActiveSecurityAttributionInvestigationConfiguration("
            "investigator_principals='[REDACTED]')"
        )

    def authorizes(self, principal: SecurityAttributionInvestigatorPrincipal) -> bool:
        return principal.internal_id in self.investigator_principals


@dataclass(frozen=True, slots=True, repr=False)
class SecurityAttributionInvestigationConfiguration:
    """Disabled state or one immutable, explicitly enabled allowlist."""

    enabled: bool
    active: ActiveSecurityAttributionInvestigationConfiguration | None

    def __post_init__(self) -> None:
        if self.enabled != (self.active is not None):
            raise SecurityAttributionInvestigationConfigurationError(
                "security attribution investigation configuration is inconsistent"
            )

    def __repr__(self) -> str:
        return (
            "SecurityAttributionInvestigationConfiguration("
            f"enabled={self.enabled!r}, active="
            f"{'[REDACTED]' if self.active is not None else None!r})"
        )


def _parse_investigator_principals(raw_value: str | None) -> frozenset[UUID]:
    if raw_value is None or not raw_value:
        raise SecurityAttributionInvestigationConfigurationError(
            "security attribution investigation configuration is invalid"
        )

    values = raw_value.split(",")
    if any(not value or value != value.strip() for value in values):
        raise SecurityAttributionInvestigationConfigurationError(
            "security attribution investigation configuration is invalid"
        )

    parsed: list[UUID] = []
    try:
        for value in values:
            principal_id = UUID(value)
            if principal_id.int == 0 or str(principal_id) != value:
                raise ValueError
            parsed.append(principal_id)
    except (AttributeError, TypeError, ValueError):
        raise SecurityAttributionInvestigationConfigurationError(
            "security attribution investigation configuration is invalid"
        ) from None

    if len(set(parsed)) != len(parsed):
        raise SecurityAttributionInvestigationConfigurationError(
            "security attribution investigation configuration is invalid"
        )

    return frozenset(parsed)


def load_security_attribution_investigation_configuration(
    settings: Settings,
) -> SecurityAttributionInvestigationConfiguration:
    """Load a redacted capability snapshot without enabling database access."""

    if not settings.security_attribution_investigation_enabled:
        return SecurityAttributionInvestigationConfiguration(
            enabled=False,
            active=None,
        )

    configured_principals = settings.security_attribution_investigator_principals
    principals = _parse_investigator_principals(
        configured_principals.get_secret_value()
        if configured_principals is not None
        else None
    )
    return SecurityAttributionInvestigationConfiguration(
        enabled=True,
        active=ActiveSecurityAttributionInvestigationConfiguration(
            investigator_principals=principals,
        ),
    )


def parse_authenticated_investigator_principal(
    value: object,
) -> SecurityAttributionInvestigatorPrincipal:
    """Accept only the canonical internal UUID returned by authentication."""

    try:
        if not isinstance(value, str):
            raise ValueError
        principal_id = UUID(value)
        if principal_id.int == 0 or str(principal_id) != value:
            raise ValueError
    except (AttributeError, TypeError, ValueError):
        raise SecurityAttributionInvestigationConfigurationError(
            "authenticated investigator principal is invalid"
        ) from None
    return SecurityAttributionInvestigatorPrincipal(internal_id=principal_id)


@lru_cache
def get_security_attribution_investigation_configuration(
) -> SecurityAttributionInvestigationConfiguration:
    """Return the process-lifetime investigator capability snapshot."""

    return load_security_attribution_investigation_configuration(get_settings())
