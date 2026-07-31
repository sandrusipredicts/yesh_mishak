from __future__ import annotations

import base64
from dataclasses import FrozenInstanceError
import re
from uuid import UUID

import pytest

from app.services.security_account_pseudonym import (
    AccountPseudonymValidationError,
    AccountUuidValidationError,
    DerivedAccountPseudonym,
    PseudonymEnvironmentValidationError,
    PseudonymEpochValidationError,
    PseudonymKeyValidationError,
    PseudonymKeyVersionValidationError,
    canonicalize_account_uuid,
    decode_base64_hmac_key,
    derive_account_pseudonym,
    validate_account_pseudonym,
    validate_pseudonym_epoch,
)


# Public, deterministic test material only. This is not an environment secret.
TEST_ACCOUNT_UUID = "00000000-0000-4000-8000-000000000001"
SECOND_ACCOUNT_UUID = "00000000-0000-4000-8000-000000000002"
TEST_KEY = bytes(range(32))
SECOND_TEST_KEY = bytes(range(32, 64))
TEST_KEY_BASE64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
FIXED_TEST_VECTOR_PSEUDONYM = "yXFDc5fbHJ_5UKP5B6AC3mJspD7YWmec18R0PtMmO8w"


def derive(
    account_uuid: UUID | str = TEST_ACCOUNT_UUID,
    *,
    environment: str = "development",
    epoch: str = "2026-07",
    key_version: int = 1,
    key_material: bytes = TEST_KEY,
) -> DerivedAccountPseudonym:
    return derive_account_pseudonym(
        account_uuid,
        environment=environment,
        epoch=epoch,
        key_version=key_version,
        key_material=key_material,
    )


def test_fixed_public_vector_and_result_contract() -> None:
    result = derive()

    assert result == DerivedAccountPseudonym(
        pseudonym=FIXED_TEST_VECTOR_PSEUDONYM,
        epoch="2026-07",
        key_version=1,
        environment="development",
    )


def test_same_inputs_produce_same_pseudonym() -> None:
    assert derive().pseudonym == derive().pseudonym


def test_different_accounts_produce_different_pseudonyms() -> None:
    assert derive(TEST_ACCOUNT_UUID).pseudonym != derive(SECOND_ACCOUNT_UUID).pseudonym


def test_different_epochs_produce_different_pseudonyms() -> None:
    assert derive(epoch="2026-07").pseudonym != derive(epoch="2026-08").pseudonym


def test_different_environments_and_independent_keys_produce_different_pseudonyms() -> None:
    development = derive(environment="development", key_material=TEST_KEY)
    production = derive(environment="production", key_material=SECOND_TEST_KEY)

    assert development.pseudonym != production.pseudonym


def test_environment_binding_changes_output_even_if_a_key_is_misconfigured_twice() -> None:
    development = derive(environment="development", key_material=TEST_KEY)
    production = derive(environment="production", key_material=TEST_KEY)

    assert development.pseudonym != production.pseudonym


def test_emergency_key_version_and_key_change_produce_different_pseudonyms() -> None:
    first = derive(key_version=1, key_material=TEST_KEY)
    replacement = derive(key_version=2, key_material=SECOND_TEST_KEY)

    assert first.pseudonym != replacement.pseudonym
    assert replacement.key_version == 2


def test_key_version_metadata_does_not_replace_required_key_rotation() -> None:
    first = derive(key_version=1, key_material=TEST_KEY)
    version_only_change = derive(key_version=2, key_material=TEST_KEY)

    assert first.pseudonym == version_only_change.pseudonym
    assert first.key_version != version_only_change.key_version


def test_output_is_43_character_unpadded_base64url_with_full_digest() -> None:
    pseudonym = derive().pseudonym

    assert len(pseudonym) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", pseudonym)
    assert "=" not in pseudonym
    assert len(base64.urlsafe_b64decode(pseudonym + "=")) == 32


def test_uuid_object_and_canonical_lowercase_text_are_deterministic() -> None:
    uuid_object = UUID(TEST_ACCOUNT_UUID)

    assert canonicalize_account_uuid(uuid_object) == TEST_ACCOUNT_UUID
    assert canonicalize_account_uuid(TEST_ACCOUNT_UUID) == TEST_ACCOUNT_UUID
    assert derive(uuid_object).pseudonym == derive(TEST_ACCOUNT_UUID).pseudonym


@pytest.mark.parametrize(
    "invalid_uuid",
    [
        "not-a-uuid",
        "00000000-0000-4000-8000-00000000000A",
        "{00000000-0000-4000-8000-000000000001}",
        "00000000000040008000000000000001",
        " 00000000-0000-4000-8000-000000000001",
        "00000000-0000-0000-0000-000000000000",
        "",
        None,
        1,
    ],
)
def test_invalid_or_noncanonical_uuid_is_rejected(invalid_uuid: object) -> None:
    with pytest.raises(AccountUuidValidationError):
        derive_account_pseudonym(
            invalid_uuid,  # type: ignore[arg-type]
            environment="development",
            epoch="2026-07",
            key_version=1,
            key_material=TEST_KEY,
        )


@pytest.mark.parametrize(
    "invalid_epoch",
    [
        "2026-7",
        "2026-00",
        "2026-13",
        "0000-01",
        "2026-07-01",
        " 2026-07",
        "2026-07 ",
        "",
        None,
    ],
)
def test_invalid_epoch_is_rejected(invalid_epoch: object) -> None:
    with pytest.raises(PseudonymEpochValidationError):
        validate_pseudonym_epoch(invalid_epoch)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "invalid_environment",
    [
        "dev",
        "local",
        "Development",
        "development ",
        "",
        None,
    ],
)
def test_invalid_environment_is_rejected(invalid_environment: object) -> None:
    with pytest.raises(PseudonymEnvironmentValidationError):
        derive(environment=invalid_environment)  # type: ignore[arg-type]


@pytest.mark.parametrize("invalid_version", [0, -1, 32_768, True, "1", None])
def test_invalid_key_version_is_rejected(invalid_version: object) -> None:
    with pytest.raises(PseudonymKeyVersionValidationError):
        derive(key_version=invalid_version)  # type: ignore[arg-type]


@pytest.mark.parametrize("missing_key", [b"", None])
def test_missing_key_is_rejected(missing_key: object) -> None:
    with pytest.raises(PseudonymKeyValidationError, match=r"^HMAC key is missing$"):
        derive(key_material=missing_key)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "weak_or_invalid_key",
    [
        b"x" * 31,
        b"x" * 33,
        b"\x00" * 32,
        b"x" * 32,
        b"replace-with-placeholder-key!!!",
        "not-bytes",
    ],
)
def test_short_long_placeholder_or_structurally_weak_key_is_rejected(
    weak_or_invalid_key: object,
) -> None:
    with pytest.raises(PseudonymKeyValidationError):
        derive(key_material=weak_or_invalid_key)  # type: ignore[arg-type]


def test_canonical_base64_key_decoding_succeeds() -> None:
    assert decode_base64_hmac_key(TEST_KEY_BASE64) == TEST_KEY


@pytest.mark.parametrize(
    "malformed_key",
    [
        "",
        None,
        123,
        "not-base64!",
        TEST_KEY_BASE64.rstrip("="),
        f" {TEST_KEY_BASE64}",
        base64.b64encode(b"x" * 31).decode("ascii"),
        base64.b64encode(b"x" * 32).decode("ascii"),
    ],
)
def test_malformed_or_weak_encoded_key_is_rejected(malformed_key: object) -> None:
    with pytest.raises(PseudonymKeyValidationError):
        decode_base64_hmac_key(malformed_key)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "invalid_pseudonym",
    [
        FIXED_TEST_VECTOR_PSEUDONYM + "=",
        FIXED_TEST_VECTOR_PSEUDONYM[:-1],
        FIXED_TEST_VECTOR_PSEUDONYM[:-1] + "+",
        "",
        None,
    ],
)
def test_padded_or_malformed_pseudonym_is_rejected(invalid_pseudonym: object) -> None:
    with pytest.raises(AccountPseudonymValidationError):
        validate_account_pseudonym(invalid_pseudonym)  # type: ignore[arg-type]


def test_exceptions_do_not_expose_account_or_key_material() -> None:
    sensitive_account = "00000000-0000-4000-8000-00000000000A"
    sensitive_key = "account-secret-key-material-that-is-invalid"

    with pytest.raises(AccountUuidValidationError) as uuid_error:
        derive(sensitive_account)
    with pytest.raises(PseudonymKeyValidationError) as key_error:
        decode_base64_hmac_key(sensitive_key)

    combined_errors = (
        f"{uuid_error.value!s} {uuid_error.value!r} "
        f"{key_error.value!s} {key_error.value!r}"
    )
    assert sensitive_account not in combined_errors
    assert sensitive_key not in combined_errors
    assert TEST_KEY_BASE64 not in combined_errors
    assert uuid_error.value.__cause__ is None
    assert key_error.value.__cause__ is None


def test_result_repr_and_string_hide_identity_key_and_pseudonym() -> None:
    result = derive()

    rendered = f"{result!r} {result}"
    assert TEST_ACCOUNT_UUID not in rendered
    assert TEST_KEY_BASE64 not in rendered
    assert FIXED_TEST_VECTOR_PSEUDONYM not in rendered
    assert "[REDACTED]" in rendered


def test_result_is_immutable() -> None:
    result = derive()

    with pytest.raises(FrozenInstanceError):
        result.epoch = "2026-08"  # type: ignore[misc]


def test_environment_variables_and_process_state_do_not_affect_derivation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = derive()
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
    monkeypatch.setenv("SECURITY_ATTRIBUTION_HMAC_KEY", "untrusted-global-value")
    monkeypatch.setenv("TZ", "Pacific/Kiritimati")

    assert derive() == before
