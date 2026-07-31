# Issue #1031 item 3: minimal security-attribution runtime

## Scope and status

This document describes implementation PR 3A only. It adds the current-key
runtime adapter, a bounded service-role ingestion recorder, and explicit
instrumentation for one authenticated route. It does not add middleware,
expand general request metrics, instrument the other 47 database-approved
routes, expose investigator access, retain historical keys, deploy anything,
or enable production.

The approved architecture remains
`docs/issue-1031-authenticated-request-correlation-design.md`. The database
and HMAC contracts remain documented in
`docs/issue-1031-security-attribution-schema.md` and
`docs/issue-1031-security-attribution-hmac.md`.

## Initial exact route mapping

| Source file | Method | Route | Existing authentication | Trusted account UUID | Event category | Route key | Recorded business outcomes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `backend/app/api/auth.py` | `POST` | `/auth/logout` | `Depends(require_active_user)` | `current_user["id"]`, returned after verified JWT subject lookup, current database account lookup, revocation check, and active-status check | `session_security_change` | `auth_logout` | `succeeded` with null failure; `failed` with `dependency_unavailable` for a revocation dependency failure; `failed` with `internal_error` for an invalid revocation result |

The explicit helper runs only after logout's authoritative revocation outcome
is known. Authentication rejection occurs before handler entry and is not
attributed by this PR. The helper never parses an authorization header, JWT,
body, route parameter, email, username, or reset token.

## Runtime variables

The adapter follows the repository's uppercase aliased settings convention:

| Variable | Disabled mode | Enabled mode |
| --- | --- | --- |
| `SECURITY_ATTRIBUTION_ENABLED` | Defaults to `false` | Must be `true` deliberately |
| `SECURITY_ATTRIBUTION_ENVIRONMENT` | Not required | Exactly `development`, `staging`, or `production` |
| `SECURITY_ATTRIBUTION_ACTIVE_EPOCH` | Not required | Current UTC month in `YYYY-MM` |
| `SECURITY_ATTRIBUTION_KEY_VERSION` | Not required | Integer `1..32767` |
| `SECURITY_ATTRIBUTION_HMAC_KEY_BASE64` | Not required | Canonical standard Base64 encoding of an approved 32-byte key |

There is no default key, generated key, root key, prior key, or placeholder
accepted as key material. The encoded value is held as Pydantic `SecretStr`
until it is decoded through the merged HMAC library. The checked-in example is
disabled and contains no usable key.

## Immutable active snapshot and startup validation

`ActiveSecurityAttributionConfiguration` is a frozen, slotted value containing
exactly:

- environment;
- epoch;
- positive key version; and
- decoded 32-byte key material.

Its representation redacts key material. The process caches one
`SecurityAttributionRuntimeConfiguration` during application import. Enabled
configuration is validated before requests are accepted; invalid environment,
epoch, version, missing key, malformed Base64, weak key, or placeholder key
raises a bounded configuration error without echoing the secret. Disabled
mode initializes without any of the four active values.

Each recording call captures the active object once and uses that same object
for HMAC environment/epoch/version/key inputs and RPC environment/epoch/version
metadata. Environment variables are not reread during an event.

Changing only the key version is not rotation. Monthly or emergency rotation
must atomically replace epoch, key version, and independently generated key.
Every environment needs independently generated keys. The runtime receives
only the current active key; historical keys and rollover grace are outside
this PR.

## Recorder API and flow

The route helper requires explicit bounded inputs:

```python
record_authenticated_security_event(
    trusted_account_uuid=...,
    route_key="auth_logout",
    event_category="session_security_change",
    http_method="POST",
    outcome=...,
    failure_category=...,
    server_correlation_id=...,
)
```

The initial in-process registry contains only
`("session_security_change", "auth_logout", "POST")`. Unsupported tuples and
incompatible outcome/failure pairs fail before any client or RPC call.

`SecurityAttributionRecorder.create_event(...)` captures one UTC timestamp and
generates, or accepts for an immutable replay, one nonzero request-event UUID.
The resulting request object is frozen and redacts the account UUID and both
server identifiers from its representation. `record(...)` then:

1. captures one cached runtime snapshot;
2. returns a silent disabled result if attribution is off;
3. verifies the event UTC month equals the active epoch;
4. derives the pseudonym through `derive_account_pseudonym(...)`;
5. creates the existing service-role Supabase client with a two-second
   PostgREST timeout;
6. calls only `record_security_request_attribution_event`; and
7. accepts only `inserted` or `already_recorded`.

The same frozen event object retains the same timestamp, request-event UUID,
correlation UUID, outcome, tuple, and derived payload across a caller retry.
An exact replay is `already_recorded`. A database idempotency conflict is a
bounded `ingestion_rpc_failed` recorder result. There is no retry queue,
worker, or new background task.

## Exact RPC payload

The recorder sends only these function parameters:

| Parameter | Source |
| --- | --- |
| `p_request_event_id` | Server-generated immutable event UUID |
| `p_occurred_at` | One captured UTC event time |
| `p_account_pseudonym` | Full 43-character HMAC result |
| `p_pseudonym_epoch` | Captured active snapshot epoch |
| `p_pseudonym_key_version` | Captured active snapshot version |
| `p_environment` | Captured active snapshot environment |
| `p_event_category` | Closed initial registry |
| `p_route_key` | Closed initial registry |
| `p_http_method` | Closed initial registry |
| `p_outcome` | Database-approved bounded outcome |
| `p_failure_category` | Null or compatible database-approved category |
| `p_server_correlation_id` | Optional canonical UUID parsed from the existing server-generated auth correlation ID |

No direct table read or write exists in the runtime service.

## Fail-open behavior and diagnostics

Logout revocation remains authoritative. Recording occurs after success or a
confirmed handler failure. Recorder construction, configuration, derivation,
client, RPC, response-validation, logging, and monitoring failures do not
change the existing response or roll back a completed action.

A disabled recorder is a silent no-op. Other failures emit one constant-text
warning and one bounded monitoring message through the existing fail-safe auth
observability helpers. Their only structured fields are recorder failure
category, approved route key, approved event category, HTTP method, and
configured environment. Raw exception text is discarded.

The closed recorder failure categories are:

- `invalid_configuration`;
- `pseudonym_derivation_failed`;
- `ingestion_rpc_failed`;
- `unexpected_rpc_response`; and
- `unexpected_failure`.

`disabled` is a result state, not a noisy warning category. Database business
failure values remain the separately closed schema taxonomy.

## Privacy boundary

The raw account UUID exists only in trusted handler/recorder memory and is
used only as HMAC input. It is not included in the RPC payload. The recorder
does not accept or persist email, username, phone, IP, user agent, request
body, headers, cookie, token, query string, raw URL, target/resource ID, or
free-form metadata.

The key, encoded key, raw UUID, derived pseudonym, RPC payload, database
response, raw exception, and request-event UUID never enter recorder logs or
monitoring. General request metrics, product analytics, route middleware, and
authentication dependency behavior are unchanged.

Focused tests assert the exact RPC parameter set, absence of raw UUID and PII,
redacted representations/errors, sanitized logging and monitoring, service-
role-only RPC use, no table access, and registry rejection.

## Latency and durability tradeoff

The recorder is synchronous after the authoritative business outcome. It adds
one awaited PostgREST round trip in enabled mode and caps that new call at two
seconds. This avoids an untracked fire-and-forget task and allows `inserted` or
`already_recorded` to mean the RPC completed before the response returned.

Typical latency therefore increases by one database round trip. During an
outage, the response can be delayed by up to the attribution timeout, but the
business result remains unchanged. A process termination before completion,
timeout, or database failure can still lose this secondary evidence. This PR
does not claim durability for those cases and does not add an outbox or queue.

## Test evidence

The initial focused run was:

```text
pytest -q tests/test_security_attribution_config.py \
  tests/test_security_request_attribution.py \
  tests/test_jwt_lifecycle.py

84 passed, 0 failed, 0 skipped
```

The focused tests cover disabled/valid/invalid configuration, current-month
enforcement, secret redaction, one-snapshot derivation, exact RPC payload,
service-role usage, inserted/idempotent responses, unexpected response and
RPC failure mapping, privacy-bounded diagnostics, timestamp enforcement,
disabled no-op, unsupported tuples, successful and failed logout behavior,
and ordinary-route exclusion. Final regression evidence is recorded in the
Draft PR and implementation handoff.

The authentication/HMAC/retention regression batch completed with 479 passed,
0 failed, and 0 skipped. The full backend run, using a workspace-local pytest
base temp because the host default temp directory is inaccessible, completed
with 1,580 passed, 0 failed, and 152 environment-gated skips. The skips are:

- 5 analytics PostgreSQL tests: `ANALYTICS_EVENTS_DATABASE_URL` absent;
- 76 authentication-audit event PostgreSQL tests:
  `AUTHENTICATION_AUDIT_DATABASE_URL` absent;
- 16 authentication-audit retention PostgreSQL tests: the same disposable
  database variable absent;
- 43 security-attribution PostgreSQL tests:
  `SECURITY_ATTRIBUTION_DATABASE_URL` absent; and
- 12 password-reset PostgreSQL tests: `PASSWORD_RESET_DATABASE_URL` absent.

The first full-run attempt used pytest's default Windows temp parent and
reported 1,563 passed, 152 skipped, and 17 setup errors because that host path
returned `Access is denied`. The controlled rerun changed only pytest's temp
and cache locations and eliminated all 17 setup errors.

## Isolated-development rollout (not executed by this PR)

1. Generate a cryptographically random 32-byte development-only key outside
   source control.
2. Encode it as canonical standard Base64.
3. Set the five runtime variables in Railway dev only, atomically supplying
   environment `development`, current UTC epoch, version, and key.
4. Deploy this feature branch to Railway dev.
5. Perform controlled successful and failed logout flows with synthetic dev
   accounts.
6. Query evidence with owner-only SQL during the existing activation gate;
   do not grant investigator access.
7. Verify no raw UUID/PII, deterministic same-account/same-epoch pseudonym,
   correct route tuple/outcome, zero event for an uninstrumented route,
   unchanged business behavior under forced attribution RPC failure, and
   continuing bounded cleanup success.
8. Remove or rotate the development key after evidence is captured.
9. Keep production disabled.

No Railway variable, secret, deployment, or hosted database action is part of
this PR.

## Rollback

Set `SECURITY_ATTRIBUTION_ENABLED=false` and redeploy the previous or current
application configuration first. Disabled mode performs no derivation or RPC
call and needs no key variables. If code rollback is required, revert the
runtime/route commit while leaving the additive database foundation and
existing rows inert under the approved 180-day cleanup.

Do not directly delete evidence, remove schema objects, change ACLs, or destroy
keys needed by approved retained evidence as part of application rollback.
Already recorded evidence cannot be made unseen.

## Remaining 47 uninstrumented routes

The following database-approved tuples remain explicitly absent from the
application registry:

- account security/recovery: `GET /auth/account-methods`,
  `POST /auth/link/google`, `POST /auth/unlink/google`,
  `POST /auth/set-password`, `POST /auth/remove-password`,
  `POST /auth/password-reset/confirm`, `POST /auth/verify-email`, and
  `DELETE /auth/account`;
- private reads/settings: `GET /field-reports/mine`,
  `GET /moderation/blocks`, `POST /moderation/blocks/{blocked_user_id}`,
  `DELETE /moderation/blocks/{blocked_user_id}`, `GET /notifications`,
  `GET /notifications/preferences`, `PUT /notifications/preferences`,
  `POST /notifications/push-token`, and
  `DELETE /notifications/push-token`;
- privileged reads: `GET /admin/me`, `GET /admin/users`,
  `GET /admin/field-reports`, `GET /admin/stats`, `GET /admin/fields`,
  `GET /admin/fields/pending`, `GET /admin/fields/duplicates`,
  `GET /admin/games`, `GET /admin/engagement`, `GET /admin/monitoring`,
  `GET /admin/content-reports`, and `POST /notifications/candidates`; and
- privileged mutations: `POST /admin/users/{user_id}/ban`,
  `POST /admin/users/{user_id}/unban`,
  `POST /admin/users/{user_id}/suspend`,
  `POST /admin/users/{user_id}/unsuspend`,
  `PATCH /admin/field-reports/{report_id}/status`,
  `PATCH /admin/field-reports/{report_id}/resolve`,
  `POST /admin/fields/{field_id}/approve`,
  `POST /admin/fields/{field_id}/reject`,
  `PATCH /admin/fields/{field_id}/status`,
  `PATCH /admin/fields/{field_id}`, `DELETE /admin/fields/{field_id}`,
  `PATCH /fields/{field_id}/status`,
  `POST /admin/reminders/scheduled-games/run`,
  `POST /admin/notifications/cleanup`,
  `POST /admin/games/{game_id}/close`,
  `POST /admin/games/{game_id}/extend`,
  `POST /admin/games/{game_id}/cancel`, and
  `PATCH /admin/content-reports/{report_id}`.

Password-reset confirmation is deliberately excluded because its current
handler has no trusted authenticated internal account UUID; it accepts a
client-controlled recovery token. Email verification has the same one-time
token boundary. Neither may derive identity from its body in this PR.

## Remaining activation gates and risks

- Independent monthly key custody, generation, audit, atomic replacement, and
  destruction remain operational approval gates.
- The new evidence RPC is fail-open; a database outage can create an evidence
  gap without an independent durable outbox.
- Aggregate dev route volume and the new round-trip latency must be measured
  before any route expansion.
- Investigator role provisioning, named/MFA-backed principals, access audit,
  bounded query tooling, historical-key access, and resolution remain a
  separate reviewed implementation gate.
- No investigator PostgreSQL capability is granted by this PR.
- Production attribution remains disabled until isolated-dev evidence and
  explicit security/privacy approval are complete.
