"""Fail-closed loading of the current security-attribution key snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal

from app.core.config import Settings, get_settings
from app.services.security_account_pseudonym import (
    SecurityAccountPseudonymError,
    decode_base64_hmac_key,
    validate_pseudonym_environment,
    validate_pseudonym_epoch,
    validate_pseudonym_key_version,
)


SecurityAttributionEnvironment = Literal["development", "staging", "production"]


class SecurityAttributionConfigurationError(RuntimeError):
    """Enabled attribution configuration is incomplete or invalid."""


@dataclass(frozen=True, slots=True, repr=False)
class ActiveSecurityAttributionConfiguration:
    """One atomic current-key snapshot; key material is always redacted."""

    environment: SecurityAttributionEnvironment
    epoch: str
    key_version: int
    key_material: bytes

    def __repr__(self) -> str:
        return (
            "ActiveSecurityAttributionConfiguration("
            f"environment={self.environment!r}, "
            f"epoch={self.epoch!r}, "
            f"key_version={self.key_version!r}, "
            "key_material='[REDACTED]')"
        )


@dataclass(frozen=True, slots=True)
class SecurityAttributionRuntimeConfiguration:
    """Disabled state or one immutable active configuration snapshot."""

    enabled: bool
    active: ActiveSecurityAttributionConfiguration | None

    def __post_init__(self) -> None:
        if self.enabled != (self.active is not None):
            raise SecurityAttributionConfigurationError(
                "security attribution runtime configuration is inconsistent"
            )


def _current_utc_epoch(now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise SecurityAttributionConfigurationError(
            "security attribution runtime clock is invalid"
        )
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def load_security_attribution_runtime_configuration(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> SecurityAttributionRuntimeConfiguration:
    """Validate settings once without ever exposing encoded or decoded key data."""

    if not settings.security_attribution_enabled:
        return SecurityAttributionRuntimeConfiguration(enabled=False, active=None)

    try:
        environment = validate_pseudonym_environment(
            settings.security_attribution_environment
        )
        epoch = validate_pseudonym_epoch(settings.security_attribution_active_epoch)
        key_version = validate_pseudonym_key_version(
            settings.security_attribution_key_version
        )
        encoded_key = settings.security_attribution_hmac_key_base64
        key_material = decode_base64_hmac_key(
            encoded_key.get_secret_value() if encoded_key is not None else None
        )
        if epoch != _current_utc_epoch(now or datetime.now(timezone.utc)):
            raise SecurityAttributionConfigurationError(
                "security attribution active epoch is not the current UTC month"
            )
    except SecurityAttributionConfigurationError:
        raise
    except SecurityAccountPseudonymError:
        raise SecurityAttributionConfigurationError(
            "security attribution active configuration is invalid"
        ) from None

    return SecurityAttributionRuntimeConfiguration(
        enabled=True,
        active=ActiveSecurityAttributionConfiguration(
            environment=environment,
            epoch=epoch,
            key_version=key_version,
            key_material=key_material,
        ),
    )


@lru_cache
def get_security_attribution_runtime_configuration(
) -> SecurityAttributionRuntimeConfiguration:
    """Return the process-lifetime snapshot initialized during application startup."""

    return load_security_attribution_runtime_configuration(get_settings())
