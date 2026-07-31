# Issue #1031 item 3: security-attribution HMAC implementation

## Scope

This document covers implementation PR 2 only: a pure Python library for
deriving the monthly, environment-bound account pseudonym approved in the
[authenticated request-correlation design](issue-1031-authenticated-request-correlation-design.md).

The library does not read settings, load deployment secrets, inspect requests,
call Supabase, write evidence, instrument routes, resolve pseudonyms, schedule
rotation, or deploy configuration. General request metrics and anonymous
analytics remain unchanged.

The implementation is
[`security_account_pseudonym.py`](../backend/app/services/security_account_pseudonym.py).

## Canonical input

The HMAC message has this exact four-line form:

```text
yesh_mishak.security-account-pseudonym:v1
environment=<development|staging|production>
epoch=<YYYY-MM>
account_uuid=<lowercase-canonical-uuid>
```

The message is encoded as UTF-8. Literal LF bytes (`0x0A`) separate adjacent
lines. There is no leading whitespace, trailing whitespace, or trailing
newline. Labels, punctuation, order, and version text are immutable parts of
the version 1 contract.

String account identifiers must already be lowercase, hyphenated canonical
UUID text. A `uuid.UUID` object is accepted and rendered canonically. Nil,
uppercase, compact, braced, padded, and malformed UUID values fail closed.
There is no normalization of strings, so a future caller cannot silently
change the input bytes.

The only accepted environments are `development`, `staging`, and
`production`, matching the database foundation from PR #1039. Epoch is an
exact, nonzero-year UTC calendar month in `YYYY-MM` form.

Key version is deliberately not part of the canonical message approved in the
design. It identifies the independently generated key used for the event.
Emergency rotation must change both the positive key version and the key.
Changing the version while reusing a key is not a cryptographic rotation.

## Cryptographic primitive and output

The implementation uses the Python standard library implementation of
HMAC-SHA-256:

```text
digest = HMAC-SHA-256(active_epoch_key, canonical_input_bytes)
pseudonym = Base64url(digest), without "=" padding
```

All 32 digest bytes are retained. The output is exactly 43 ASCII characters
matching `^[A-Za-z0-9_-]{43}$`. It is validated again before being returned.
No digest truncation or custom cryptographic construction is used.

HMAC is required instead of a plain UUID hash because a database or user-list
exposure would make an unkeyed UUID dictionary enumerable. HMAC resistance to
that attack depends on the active key remaining secret. Pseudonymization is
not anonymization.

## Key contract

`derive_account_pseudonym(...)` accepts key material only as exactly 32 bytes.
There is no default, runtime generation, root-key derivation, historical key
store, or global settings lookup.

`decode_base64_hmac_key(...)` is the narrow adapter for a future secret
loader. Its input must be canonical standard Base64 for exactly 32 decoded
bytes. For 32 bytes this is a 44-character encoding with one trailing `=`.
Whitespace, Base64url substitutions, missing padding, noncanonical encodings,
short/long values, repeated-byte keys, and known placeholder fragments are
rejected with bounded errors.

Structural validation cannot prove that an arbitrary 32-byte value was
generated randomly. The approved custodian must generate each key with a
cryptographically secure random generator and provide independent keys for
every environment, month, and emergency version. The library's weak-key
checks are a fail-closed guard against obvious configuration mistakes, not an
entropy certification.

No real key or usable default is committed. No configuration variable is
added in this PR.

## API and result contract

The public API is:

```python
canonicalize_account_uuid(account_uuid: UUID | str) -> str
validate_pseudonym_epoch(epoch: str) -> str
validate_pseudonym_environment(environment: str) -> str
validate_pseudonym_key_version(key_version: int) -> int
decode_base64_hmac_key(encoded_key: str) -> bytes
validate_account_pseudonym(pseudonym: str) -> str
derive_account_pseudonym(
    account_uuid: UUID | str,
    *,
    environment: str,
    epoch: str,
    key_version: int,
    key_material: bytes,
) -> DerivedAccountPseudonym
```

`DerivedAccountPseudonym` is frozen and contains only:

- `pseudonym`;
- `epoch`;
- `key_version`; and
- `environment`.

It contains no account UUID, key, canonical message, or digest bytes. Its
`repr` and string form redact even the pseudonym to discourage accidental
diagnostic disclosure.

The derivation function is pure for explicit inputs. It does not use process
environment, clocks, locale, settings caches, logging, monitoring, database
clients, or mutable module state.

## Validation and error model

Validation failures use subclasses of
`SecurityAccountPseudonymError(ValueError)`:

- `AccountUuidValidationError`;
- `PseudonymEpochValidationError`;
- `PseudonymEnvironmentValidationError`;
- `PseudonymKeyVersionValidationError`;
- `PseudonymKeyValidationError`; and
- `AccountPseudonymValidationError`.

Messages are stable categories such as `account UUID is invalid`,
`pseudonym epoch is invalid`, and `HMAC key encoding is invalid`. They never
interpolate the rejected identity, key, encoded secret, or derived
pseudonym. Key version is restricted to `1..32767`, matching the PostgreSQL
`smallint` column.

## Fixed public test vector

This vector is synthetic, deterministic, and test-only. Its key is public and
must never be used by any environment.

```text
account UUID: 00000000-0000-4000-8000-000000000001
environment: development
epoch: 2026-07
key version: 1
key bytes: 000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f
key Base64: AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
canonical UTF-8 byte length: 129
expected pseudonym: yXFDc5fbHJ_5UKP5B6AC3mJspD7YWmec18R0PtMmO8w
```

The canonical input bytes are:

```text
yesh_mishak.security-account-pseudonym:v1
environment=development
epoch=2026-07
account_uuid=00000000-0000-4000-8000-000000000001
```

The test vector detects changes to prefix, labels, ordering, separators,
encoding, digest length, or output encoding.

## Threat model

- A telemetry-database compromise reveals pseudonymous within-epoch groups,
  not the raw account UUID or key.
- An application compromise that obtains the current key and candidate account
  UUIDs can enumerate current-epoch pseudonyms and forge events. Rotate the
  affected environment/month key through a separately approved process.
- A key compromise permits dictionary attacks for its environment, epoch, and
  version. It does not expose independently keyed months or environments.
- Monthly unlinkability depends on independently random monthly keys. The
  epoch in the canonical message is defense in depth, not permission to reuse a
  key.
- Environment isolation depends on independently random environment keys. The
  environment label in the canonical message also prevents identical output
  if a key is accidentally duplicated, but duplicated keys still violate
  custody policy.
- The runtime should eventually receive only the active key. Any narrowly
  approved prior-key retry grace, historical-key storage, resolution, and key
  destruction are outside this PR.
- The library does not log. Callers must not put account identity, key,
  canonical bytes, digest, pseudonym, or raw exception context into logs or
  monitoring.
- Account deletion and the fixed 180-day evidence retention remain governed
  by the approved design and database foundation. This library stores nothing.

## Integration contract for implementation PR 3

Future security-route instrumentation must provide:

1. a trusted internal account UUID from the existing verified
   authentication dependency;
2. one closed environment label;
3. the UTC `YYYY-MM` epoch captured from the event's server timestamp;
4. the positive active key version; and
5. the active 32-byte environment/epoch key supplied by an approved secret
   adapter.

It receives a `DerivedAccountPseudonym` containing the 43-character
pseudonym, epoch, key version, and environment. It must pass those bounded
values to the already approved ingestion boundary without copying the raw
account UUID into an RPC payload, general metric, log, warning, or event.

The instrumentation adapter must prove that its captured event timestamp
belongs to the configured active epoch before derivation. This library accepts
one explicit epoch and one active key; it has no clock or historical-key
selection behavior. A future prior-key retry, if separately approved, must
retain the original timestamp, epoch, version, key, and immutable event
payload.

No database write occurs in this PR.

## Rotation expectations and activation gates

Normal rotation creates an independent key at 00:00 UTC on the first day of a
month and increments or initializes its positive version according to the
approved key inventory. An emergency rotation creates a new independent key
and increments the version immediately.

Before any runtime activation, owners must still approve and verify:

- the managed secret system and named key custodian;
- independent key generation and access-audit evidence;
- exact deployment-to-environment mapping;
- atomic epoch/key/version configuration rollover;
- current-key-only application access and any separately reviewed retry grace;
- no key reuse across environments, epochs, or emergency versions; and
- bounded diagnostics for configuration/derivation failures.

Historical-key storage, resolver access, investigator capabilities, and
destruction evidence remain later scopes.

## Rollout and rollback

This PR's rollout is limited to merging an unused pure module after unit and
security review. It provisions no variable and changes no runtime path.

The later instrumentation rollout must:

1. provision an independent non-production active key outside source control;
2. decode and validate it through a small fail-closed configuration adapter;
3. verify environment, UTC epoch, key version, and fixed-vector compatibility;
4. exercise synthetic same/different account, environment, and month cases;
5. confirm no sensitive value reaches logs, monitoring, RPC errors, or general
   request metrics; and
6. enable only the minimal approved route allowlist in a separate PR.

Rollback before instrumentation is a source revert with no data or
environment effect. After later instrumentation, disable the caller first and
preserve already-recorded evidence under the 180-day policy. Remove active key
access through the approved secret process. Do not assume already recorded
pseudonymous evidence can be made unseen.
