from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.services.security_attribution_config import (
    SecurityAttributionConfigurationError,
    load_security_attribution_runtime_configuration,
)


NOW = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc)
VALID_KEY_BYTES = bytes(range(32))
VALID_KEY_BASE64 = base64.b64encode(VALID_KEY_BYTES).decode("ascii")


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_KEY": "public-test-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-test-key",
        "GOOGLE_CLIENT_ID": "google-test-client",
        "JWT_SECRET": "jwt-test-secret",
        "SECURITY_ATTRIBUTION_ENABLED": True,
        "SECURITY_ATTRIBUTION_ENVIRONMENT": "development",
        "SECURITY_ATTRIBUTION_ACTIVE_EPOCH": "2026-07",
        "SECURITY_ATTRIBUTION_KEY_VERSION": 1,
        "SECURITY_ATTRIBUTION_HMAC_KEY_BASE64": VALID_KEY_BASE64,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_disabled_mode_requires_no_attribution_key() -> None:
    configuration = load_security_attribution_runtime_configuration(
        make_settings(
            SECURITY_ATTRIBUTION_ENABLED=False,
            SECURITY_ATTRIBUTION_ENVIRONMENT=None,
            SECURITY_ATTRIBUTION_ACTIVE_EPOCH=None,
            SECURITY_ATTRIBUTION_KEY_VERSION=None,
            SECURITY_ATTRIBUTION_HMAC_KEY_BASE64=None,
        ),
        now=NOW,
    )

    assert configuration.enabled is False
    assert configuration.active is None


def test_enabled_valid_development_configuration_loads() -> None:
    configuration = load_security_attribution_runtime_configuration(
        make_settings(),
        now=NOW,
    )

    assert configuration.enabled is True
    assert configuration.active is not None
    assert configuration.active.environment == "development"
    assert configuration.active.epoch == "2026-07"
    assert configuration.active.key_version == 1
    assert configuration.active.key_material == VALID_KEY_BYTES


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(SecurityAttributionConfigurationError):
        load_security_attribution_runtime_configuration(
            make_settings(SECURITY_ATTRIBUTION_ENVIRONMENT="preview"),
            now=NOW,
        )


def test_epoch_must_equal_current_utc_month() -> None:
    with pytest.raises(
        SecurityAttributionConfigurationError,
        match=r"^security attribution active epoch is not the current UTC month$",
    ):
        load_security_attribution_runtime_configuration(
            make_settings(SECURITY_ATTRIBUTION_ACTIVE_EPOCH="2026-06"),
            now=NOW,
        )


@pytest.mark.parametrize("key_version", [0, -1, 32_768])
def test_invalid_key_version_is_rejected(key_version: int) -> None:
    with pytest.raises(SecurityAttributionConfigurationError):
        load_security_attribution_runtime_configuration(
            make_settings(SECURITY_ATTRIBUTION_KEY_VERSION=key_version),
            now=NOW,
        )


def test_missing_key_is_rejected_when_enabled() -> None:
    with pytest.raises(SecurityAttributionConfigurationError):
        load_security_attribution_runtime_configuration(
            make_settings(SECURITY_ATTRIBUTION_HMAC_KEY_BASE64=None),
            now=NOW,
        )


def test_malformed_base64_key_is_rejected() -> None:
    with pytest.raises(SecurityAttributionConfigurationError) as exc_info:
        load_security_attribution_runtime_configuration(
            make_settings(
                SECURITY_ATTRIBUTION_HMAC_KEY_BASE64="malformed-secret-value"
            ),
            now=NOW,
        )

    assert "malformed-secret-value" not in str(exc_info.value)


def test_weak_key_is_rejected() -> None:
    weak_key = base64.b64encode(b"A" * 32).decode("ascii")

    with pytest.raises(SecurityAttributionConfigurationError) as exc_info:
        load_security_attribution_runtime_configuration(
            make_settings(SECURITY_ATTRIBUTION_HMAC_KEY_BASE64=weak_key),
            now=NOW,
        )

    assert weak_key not in str(exc_info.value)


def test_configuration_repr_does_not_expose_key() -> None:
    settings = make_settings()
    configuration = load_security_attribution_runtime_configuration(
        settings,
        now=NOW,
    )

    representation = repr(configuration)
    assert "[REDACTED]" in representation
    assert VALID_KEY_BASE64 not in representation
    assert repr(VALID_KEY_BYTES) not in representation
    assert VALID_KEY_BASE64 not in repr(settings)


def test_configuration_errors_do_not_expose_secret_values() -> None:
    secret_value = base64.b64encode(b"B" * 32).decode("ascii")

    with pytest.raises(SecurityAttributionConfigurationError) as exc_info:
        load_security_attribution_runtime_configuration(
            make_settings(SECURITY_ATTRIBUTION_HMAC_KEY_BASE64=secret_value),
            now=NOW,
        )

    diagnostic = f"{exc_info.value!s} {exc_info.value!r}"
    assert secret_value not in diagnostic
    assert repr(b"B" * 32) not in diagnostic
