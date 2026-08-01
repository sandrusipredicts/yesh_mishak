# Issue #1031 item 3, PR 3B: security attribution for account-security mutation routes

## Scope and status

This document describes implementation PR 3B only. It extends the merged
runtime architecture (PRs #1039–#1041) to five authenticated account-security
mutation routes. It does not add middleware, schema or migrations, new RPCs,
direct table reads/writes, investigator tools or roles, historical keys,
resolver logic, admin instrumentation, private read instrumentation, production
deployment, production secrets, Railway changes, retry queue or outbox, or
general metrics identity.

The approved architecture remains
`docs/issue-1031-authenticated-request-correlation-design.md`. The database
and HMAC contracts remain documented in
`docs/issue-1031-security-attribution-schema.md` and
`docs/issue-1031-security-attribution-hmac.md`. The runtime adapter and
recorder remain documented in
`docs/issue-1031-security-attribution-runtime.md`.

## Newly instrumented routes

| Source file | Method | Route | Existing authentication | Trusted account UUID | Event category | Route key | Recorded business outcomes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `backend/app/api/auth.py` | `POST` | `/auth/link/google` | `Depends(require_active_user)` | `current_user["id"]` | `credential_method_change` | `auth_google_link` | `succeeded`; `denied`/`rate_limited`; failure mapped via `_security_attribution_failure` |
| `backend/app/api/auth.py` | `POST` | `/auth/unlink/google` | `Depends(require_active_user)` | `current_user["id"]` | `credential_method_change` | `auth_google_unlink` | `succeeded`; `denied`/`rate_limited`; failure mapped via `_security_attribution_failure` |
| `backend/app/api/auth.py` | `POST` | `/auth/set-password` | `Depends(require_active_user)` | `current_user["id"]` | `credential_method_change` | `auth_password_set` | `succeeded`; `denied`/`rate_limited`; failure mapped via `_security_attribution_failure` |
| `backend/app/api/auth.py` | `POST` | `/auth/remove-password` | `Depends(require_active_user)` | `current_user["id"]` | `credential_method_change` | `auth_password_remove` | `succeeded`; `denied`/`rate_limited`; failure mapped via `_security_attribution_failure` |
| `backend/app/api/auth.py` | `DELETE` | `/auth/account` | `Depends(require_active_user)` | `current_user["id"]` | `account_lifecycle_change` | `auth_account_delete` | `succeeded`; `denied`/`rate_limited`; failure mapped via `_security_attribution_failure` |

The existing `auth_logout` instrumentation from PR 3A is unchanged.

## Route qualification criteria

Each route was selected because it satisfies all four requirements:

1. **Already exists** — no new endpoints were created.
2. **Exposes a trusted internal account UUID** — `Depends(require_active_user)`
   provides `current_user["id"]` after verified JWT subject lookup, current
   database account lookup, revocation check, and active-status check.
3. **Matches a database-approved route/category/method tuple** — confirmed in
   `docs/issue-1031-security-attribution-schema.md`.
4. **Has bounded authoritative outcomes** — each service call returns a known
   success result or raises an `HTTPException` with a status code that maps
   deterministically to an approved outcome/failure category pair.

## Failure mapping helper

A shared `_security_attribution_failure(exc: HTTPException)` helper maps HTTP
status codes to database-approved `(outcome, failure_category)` pairs:

| HTTP status | Detail code | Outcome | Failure category |
| --- | --- | --- | --- |
| 429 | any | `denied` | `rate_limited` |
| 403 | `LAST_ADMIN` | `denied` | `authorization_denied` |
| 403 | other | `denied` | `reauthentication_failed` |
| 400 | any | `failed` | `validation_rejected` |
| 404 | any | `failed` | `not_found` |
| 409 | any | `failed` | `conflict` |
| other | any | `failed` | `internal_error` |

The helper inspects only the integer status code and the `code` field of a
`dict`-typed `detail`. It does not inspect the exception message, body, URL,
or any client-controlled field.

## Instrumentation pattern

Each route follows the same pattern:

1. Rate limit check — if denied, record `denied`/`rate_limited`, then return
   the rate-limit response unchanged.
2. Wrap the service call in `try/except HTTPException`.
3. On `HTTPException` — map via `_security_attribution_failure`, record
   attribution, re-raise the original exception unchanged.
4. On success — record `succeeded` with `failure_category=None`.

All calls use `str(current_user["id"])` as `trusted_account_uuid`. No body
field, header, URL parameter, or client-supplied identity is passed to
attribution.

## Registry extension

`_APPROVED_ROUTE_REGISTRY` grew from 1 entry (PR 3A) to 6 entries. The
`SecurityEventCategory` literal gained `credential_method_change` and
`account_lifecycle_change`. The `SecurityRouteKey` literal gained
`auth_google_link`, `auth_google_unlink`, `auth_password_set`,
`auth_password_remove`, and `auth_account_delete`. The `SecurityHttpMethod`
literal gained `DELETE`. The `_APPROVED_OUTCOME_FAILURES` map and the
`SecurityOutcome`/`SecurityFailureCategory` types are unchanged — all needed
outcome/failure values already existed in PR 3A.

## Privacy boundary

The same privacy boundary from PR 3A applies unchanged:

- Raw account UUIDs are never logged or persisted by the attribution runtime.
- Account identity is pseudonymized via HMAC-SHA-256 before RPC ingestion.
- No email, username, phone, token, body, URL, header, IP, user agent,
  pseudonym, key material, or raw exception text is passed to any attribution
  call.
- The `SecurityAttributionEventRequest.__repr__` redacts all identity fields.

## Fail-open guarantee

Attribution failure does not change any business operation:

- `record_authenticated_security_event` catches all recorder exceptions and
  returns a `SecurityAttributionRecordResult(status="failed")`.
- The instrumented route handler does not inspect the attribution result; the
  business response (success or error) is returned identically.
- When attribution is disabled (`SECURITY_ATTRIBUTION_ENABLED=false`), the
  recorder returns `disabled` without creating a service-role client or making
  any RPC call.

## Test coverage

`backend/tests/test_security_attribution_account_routes.py` covers:

1. Existing success behavior unchanged (×5 routes)
2. Existing failure behavior unchanged (×5 routes)
3. Correct route/category/method tuple (×5 routes)
4. Correct bounded outcome on success (×5 routes)
5. Correct bounded outcome on failure (×5 routes)
6. Trusted UUID from server context (×5 routes)
7. Client-controlled identity ignored (×5 routes)
8. Attribution failure preserves success response (×5 routes)
9. Attribution failure preserves error response (×5 routes)
10. Disabled mode produces no RPC
11. Unsupported tuples rejected before client creation
12. No PII in attribution calls (×5 routes)
13. auth_logout tuple still accepted
14. Uninstrumented route produces no attribution call
15. Failure-category mapping (×8 status/code combinations)
16. Rate-limited records denied (×5 routes)
17. All new tuples accepted by registry (×5 tuples)
18. Original logout tuple still in registry
19. Registry has exactly 6 entries

## Changed files

| File | Change |
| --- | --- |
| `backend/app/services/security_request_attribution.py` | Extended type literals and `_APPROVED_ROUTE_REGISTRY` from 1 to 6 entries |
| `backend/app/api/auth.py` | Added `_security_attribution_failure` helper; instrumented 5 account-security routes |
| `backend/tests/test_security_attribution_account_routes.py` | New comprehensive test file (738 lines) |

## Remaining work (out of scope for this PR)

42 approved routes remain uninstrumented. The full list is in
`docs/issue-1031-security-attribution-runtime.md`. Investigator tooling, admin
instrumentation, and production deployment are separate future PRs under
Issue #1031.
