"""Pure derivation of monthly, environment-bound security account pseudonyms."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import re
from uuid import UUID


CANONICAL_INPUT_VERSION = "yesh_mishak.security-account-pseudonym:v1"
HMAC_KEY_BYTES = 32
MAX_KEY_VERSION = 32_767
PSEUDONYM_LENGTH = 43
SUPPORTED_ENVIRONMENTS = frozenset({"development", "staging", "production"})

_EPOCH_PATTERN = re.compile(r"[0-9]{4}-(?:0[1-9]|1[0-2])")
_PSEUDONYM_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
_KNOWN_PLACEHOLDER_FRAGMENTS = (
    b"change-me",
    b"changeme",
    b"example",
    b"placeholder",
    b"replace-me",
    b"replace-with",
)
_MINIMUM_DISTINCT_KEY_BYTES = 16
_NIL_UUID = UUID(int=0)


class SecurityAccountPseudonymError(ValueError):
    """Base class for bounded pseudonym validation failures."""


class AccountUuidValidationError(SecurityAccountPseudonymError):
    """The account identifier is not a canonical, non-nil UUID."""


class PseudonymEpochValidationError(SecurityAccountPseudonymError):
    """The pseudonym epoch is not an exact UTC calendar month."""


class PseudonymEnvironmentValidationError(SecurityAccountPseudonymError):
    """The source environment is outside the closed environment set."""


class PseudonymKeyVersionValidationError(SecurityAccountPseudonymError):
    """The key version is outside the database-compatible positive range."""


class PseudonymKeyValidationError(SecurityAccountPseudonymError):
    """The HMAC key is missing, malformed, or structurally weak."""


class AccountPseudonymValidationError(SecurityAccountPseudonymError):
    """A pseudonym does not match the full HMAC-SHA-256 output contract."""


@dataclass(frozen=True, slots=True, repr=False)
class DerivedAccountPseudonym:
    """Bounded derivation result without raw identity, key, or message bytes."""

    pseudonym: str
    epoch: str
    key_version: int
    environment: str

    def __repr__(self) -> str:
        return (
            "DerivedAccountPseudonym("
            "pseudonym='[REDACTED]', "
            f"epoch={self.epoch!r}, "
            f"key_version={self.key_version!r}, "
            f"environment={self.environment!r})"
        )

    __str__ = __repr__


def canonicalize_account_uuid(account_uuid: UUID | str) -> str:
    """Return canonical lowercase UUID text, rejecting alternate string forms."""

    if isinstance(account_uuid, UUID):
        parsed = account_uuid
    elif isinstance(account_uuid, str):
        try:
            parsed = UUID(account_uuid)
        except (AttributeError, TypeError, ValueError):
            raise AccountUuidValidationError("account UUID is invalid") from None
        if account_uuid != str(parsed):
            raise AccountUuidValidationError(
                "account UUID must use canonical lowercase text"
            )
    else:
        raise AccountUuidValidationError("account UUID is invalid")

    if parsed == _NIL_UUID:
        raise AccountUuidValidationError("account UUID is invalid")
    return str(parsed)


def validate_pseudonym_epoch(epoch: str) -> str:
    """Validate an exact UTC ``YYYY-MM`` calendar-month label."""

    if not isinstance(epoch, str) or _EPOCH_PATTERN.fullmatch(epoch) is None:
        raise PseudonymEpochValidationError("pseudonym epoch is invalid")
    if epoch.startswith("0000-"):
        raise PseudonymEpochValidationError("pseudonym epoch is invalid")
    return epoch


def validate_pseudonym_environment(environment: str) -> str:
    """Validate the closed deployment environment label."""

    if not isinstance(environment, str) or environment not in SUPPORTED_ENVIRONMENTS:
        raise PseudonymEnvironmentValidationError(
            "pseudonym environment is unsupported"
        )
    return environment


def validate_pseudonym_key_version(key_version: int) -> int:
    """Validate a positive key version compatible with PostgreSQL ``smallint``."""

    if (
        isinstance(key_version, bool)
        or not isinstance(key_version, int)
        or not 1 <= key_version <= MAX_KEY_VERSION
    ):
        raise PseudonymKeyVersionValidationError(
            "pseudonym key version is invalid"
        )
    return key_version


def _validate_hmac_key(key_material: bytes | None) -> bytes:
    if key_material is None or key_material == b"":
        raise PseudonymKeyValidationError("HMAC key is missing")
    if not isinstance(key_material, bytes):
        raise PseudonymKeyValidationError("HMAC key type is invalid")
    if len(key_material) != HMAC_KEY_BYTES:
        raise PseudonymKeyValidationError("HMAC key length is invalid")

    lowered_key = key_material.lower()
    if (
        len(set(key_material)) < _MINIMUM_DISTINCT_KEY_BYTES
        or any(fragment in lowered_key for fragment in _KNOWN_PLACEHOLDER_FRAGMENTS)
    ):
        raise PseudonymKeyValidationError("HMAC key is not permitted")
    return key_material


def decode_base64_hmac_key(encoded_key: str) -> bytes:
    """Decode one canonical standard-Base64, 32-byte active epoch key."""

    if encoded_key is None or encoded_key == "":
        raise PseudonymKeyValidationError("HMAC key is missing")
    if not isinstance(encoded_key, str):
        raise PseudonymKeyValidationError("HMAC key encoding is invalid")

    try:
        decoded_key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, ValueError):
        raise PseudonymKeyValidationError("HMAC key encoding is invalid") from None

    canonical_encoding = base64.b64encode(decoded_key).decode("ascii")
    if not hmac.compare_digest(canonical_encoding, encoded_key):
        raise PseudonymKeyValidationError("HMAC key encoding is invalid")
    return _validate_hmac_key(decoded_key)


def validate_account_pseudonym(pseudonym: str) -> str:
    """Validate an unpadded Base64url-encoded, full SHA-256 HMAC digest."""

    if (
        not isinstance(pseudonym, str)
        or len(pseudonym) != PSEUDONYM_LENGTH
        or _PSEUDONYM_PATTERN.fullmatch(pseudonym) is None
    ):
        raise AccountPseudonymValidationError("account pseudonym is invalid")

    try:
        decoded = base64.b64decode(
            pseudonym + "=",
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        raise AccountPseudonymValidationError(
            "account pseudonym is invalid"
        ) from None
    if len(decoded) != hashlib.sha256().digest_size:
        raise AccountPseudonymValidationError("account pseudonym is invalid")
    return pseudonym


def derive_account_pseudonym(
    account_uuid: UUID | str,
    *,
    environment: str,
    epoch: str,
    key_version: int,
    key_material: bytes,
) -> DerivedAccountPseudonym:
    """Derive one deterministic pseudonym from explicit, validated inputs."""

    canonical_uuid = canonicalize_account_uuid(account_uuid)
    validated_environment = validate_pseudonym_environment(environment)
    validated_epoch = validate_pseudonym_epoch(epoch)
    validated_key_version = validate_pseudonym_key_version(key_version)
    validated_key = _validate_hmac_key(key_material)

    canonical_message = (
        f"{CANONICAL_INPUT_VERSION}\n"
        f"environment={validated_environment}\n"
        f"epoch={validated_epoch}\n"
        f"account_uuid={canonical_uuid}"
    ).encode("utf-8")
    digest = hmac.new(
        validated_key,
        canonical_message,
        hashlib.sha256,
    ).digest()
    pseudonym = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    validate_account_pseudonym(pseudonym)

    return DerivedAccountPseudonym(
        pseudonym=pseudonym,
        epoch=validated_epoch,
        key_version=validated_key_version,
        environment=validated_environment,
    )
