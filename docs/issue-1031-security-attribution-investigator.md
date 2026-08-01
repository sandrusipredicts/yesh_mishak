# Issue #1031 item 3, PR 4: bounded security-attribution investigator

## Scope and status

This document describes implementation PR 4 only. It adds a narrow,
server-side investigator capability boundary and the typed contract for
querying existing pseudonymous security-attribution evidence. It does not add
a dashboard, resolver, historical keys, new route instrumentation, schema or
grant changes, direct table access, database-owner credentials, deployment,
Railway configuration, production activation, or identity fields in general
request metrics.

The merged database query RPC is owner-only. The application has no approved
named database principal, role-assumption provider, owner connection, or
independent provider audit adapter. Consequently this PR deliberately ships an
unavailable database gateway. The endpoint can validate authentication,
authorization, configuration, and request shape, but the runtime cannot return
evidence until a separate reviewed database-capability change satisfies the
activation gate below.

The approved architecture remains
`docs/issue-1031-authenticated-request-correlation-design.md`. The merged
schema, HMAC, runtime, and account-route contracts remain documented in the
other `issue-1031-security-attribution-*.md` files and are not rewritten here.

## Verified foundations

The branch starts from `dev` commit
`dc3a09095963d77beff2f246cb14428629bcb155`, which contains PRs #1039 through
#1042.

The merged database function exactly matches the schema document:

```text
public.query_security_request_attribution_events(
    uuid, text, timestamptz, timestamptz, integer
)
```

It accepts only incident UUID, closed environment, half-open time window, and
bounded result limit. It orders evidence by `(occurred_at, id)`, returns only
approved pseudonymous fields, and atomically writes succeeded, rejected, or
failed investigation-access evidence. An access-audit persistence failure
raises a fixed error and returns no evidence.

The function grants `EXECUTE` only to its owner. `service_role` has no execute
grant on the query RPC and no direct privilege on either evidence table. The
application contains no PostgreSQL owner connection setting or named database
principal mechanism. Using the existing service-role Supabase client would
therefore be unauthorized; embedding an owner password would violate the
approved design and this task.

## Authorization model

The logical capability is:

```text
security_attribution_investigate
```

The repository has an existing two-stage server-side authorization boundary:
`require_active_user` and `require_admin`. It has no independent named
capability framework. This PR therefore adds the permitted minimal allowlist
adapter on top of `require_admin`:

1. the bearer token must resolve through the existing verified authentication
   dependency;
2. the current database user must be active;
3. the current database role must be `admin`;
4. investigation must be explicitly enabled; and
5. the authenticated internal canonical UUID must appear in the immutable
   investigator allowlist snapshot.

Default is deny. Ordinary admins do not inherit the capability. No identity is
read from the body, query string, header, email domain, or frontend state. The
dependency returns only a redacted internal-principal value to the endpoint,
not the authenticated user's email or profile.

Disabled, invalid, non-admin, and non-allowlisted access uses the existing
bounded `403 FORBIDDEN` response shape. Anonymous access uses the existing
`401 AUTH_REQUIRED` behavior.

## Configuration

Two uppercase aliased settings follow the repository convention:

| Variable | Contract |
| --- | --- |
| `SECURITY_ATTRIBUTION_INVESTIGATION_ENABLED` | Exact lowercase `true` or `false`; defaults to `false`. |
| `SECURITY_ATTRIBUTION_INVESTIGATOR_PRINCIPALS` | When enabled, a comma-separated list of unique lowercase canonical nonzero internal UUIDs, with no whitespace or empty item. |

The principal setting is a Pydantic `SecretStr`. Settings, active
configuration, principal, query, and gateway-response representations redact
principal/evidence values. Parsing errors use constant text and never echo the
rejected list. Enabled plus missing, empty, duplicated, noncanonical, nil, or
malformed principals fails closed during startup. Disabled mode starts without
the principal setting.

No real principal is present in `.env.example`. There is no owner DSN,
database password, historical-key variable, production secret, or adapter
activation flag.

## Endpoint contract

```text
POST /admin/security-attribution/investigate
```

The request accepts exactly:

```json
{
  "incident_id": "UUID",
  "environment": "development | staging | production",
  "window_start": "timezone-aware timestamp",
  "window_end": "timezone-aware timestamp",
  "limit": 1
}
```

Validation requires:

- a canonical nonzero incident UUID;
- a closed environment value;
- timezone-aware start and end timestamps;
- start strictly before end;
- a window no longer than 31 days; and
- an integer limit from 1 through 10,000.

Extra fields are forbidden. The model has no SQL, account UUID, email,
username, phone, pseudonym filter, category list, route list, metadata, sort,
page size, URL, token, IP, user agent, body, or header field. Invalid input is
rejected; it is never widened, normalized into a broader query, or passed to a
database adapter.

The typed success response contains only:

- incident ID;
- environment;
- requested start/end;
- result count; and
- approved pseudonymous evidence rows.

Public evidence rows contain `occurred_at`, `account_pseudonym`,
`pseudonym_epoch`, `pseudonym_key_version`, environment, event category, route
key, HTTP method, outcome, bounded failure category, and optional server
correlation ID. The RPC's internal request-event UUID is validated but omitted
from the API response. Ordering is preserved exactly; the application does not
sort or broaden results.

## Database RPC boundary and activation blocker

`SecurityAttributionInvestigationGateway` has one operation corresponding to
the exact approved RPC. Its query value exposes the exact name and five
parameters and keeps the authenticated principal redacted and outside the RPC
payload.

The production dependency returns
`UnavailableSecurityAttributionInvestigationGateway`. It creates no Supabase
client, exposes no `.table()` or `.rpc()` API, constructs no SQL, and always
raises the bounded `disabled` category. The endpoint therefore returns
`503 SECURITY_ATTRIBUTION_INVESTIGATION_UNAVAILABLE` with no evidence after an
otherwise valid admitted request.

A future adapter is blocked until a separate reviewed database change:

1. provisions the approved no-login `security_evidence_reader` capability;
2. selects named, MFA-backed principal/role assumption;
3. provides independent provider audit evidence mapping the named application
   investigator to the database invocation;
4. grants only query-RPC execution, never direct table access;
5. keeps `service_role`, `anon`, and `authenticated` unable to query; and
6. proves application runtime needs neither an owner credential nor a direct
   table grant.

This PR does not partially activate or simulate that database path.

## Access-audit fail-closed invariant

The existing RPC owns query execution and access-audit persistence in one
transaction. The application gateway contract returns an
`AuditedSecurityAttributionRpcResponse` only after that atomic call completes.

The service applies these gates in order:

1. call the single audited-query gateway;
2. require the explicit `access_audit_persisted=true` contract result;
3. strictly validate the complete RPC row shape and closed taxonomies;
4. reject mixed, malformed, out-of-window, cross-environment, oversized, or
   out-of-order responses;
5. map RPC `rejected` and `failed` statuses to bounded errors; and
6. construct public evidence only after every prior check succeeds.

If audit persistence is false or unavailable, even a payload containing valid
evidence is discarded and the API returns no evidence. Raw gateway exceptions
are replaced with a bounded failure. The unavailable production gateway makes
the same invariant fail closed before any query.

Application validation happens before database admission, so malformed HTTP
requests cannot currently create a database rejection audit. The merged RPC
already persists bounded rejection rows for owner-admitted invalid windows and
limits. Exercising that path from the application remains blocked with the
owner-only invocation mechanism.

## Logging and monitoring

The endpoint emits only constant text plus:

- event `security_attribution.investigation`;
- route key `admin_security_attribution_investigate`;
- closed failure category;
- closed environment;
- result count; and
- the existing bounded request correlation ID.

The closed application failure categories are `disabled`,
`authorization_denied`, `validation_rejected`, `query_failed`,
`unexpected_response`, `access_audit_failed`, and `unexpected_failure`.

Logs and monitoring never receive the evidence rows, pseudonyms, account UUID,
investigator UUID/email, token, request body, SQL, raw RPC payload/response,
HMAC key, or exception text. Expected authentication/authorization denial
retains the existing response behavior and reveals no evidence existence or
count.

## Privacy restrictions

- No raw account identity is accepted or returned.
- No email, username, phone, token, IP, user agent, request content, header,
  query, raw URL, key, SQL, or free-form metadata is accepted.
- No pseudonym-to-account or cross-epoch resolver exists.
- No historical key is loaded or stored.
- No identity or pseudonym is added to general request metrics, analytics, or
  middleware.
- No direct evidence-table access is present.
- No existing RLS, ACL, retention, authentication, account-route
  instrumentation, frontend, Android, or iOS behavior changes.

## Test evidence

Initial focused implementation run:

```text
pytest -q tests/test_security_attribution_investigator.py -p no:cacheprovider
55 passed, 0 failed, 0 skipped
```

It covers disabled/default configuration, strict allowlisting and redaction,
anonymous/user/admin/investigator authorization, request-controlled identity,
all request bounds and forbidden filters, exact RPC name/parameters, no table
API, strict response validation, deterministic ordering, bounded rejection and
query failure, access-audit failure with an evidence payload, raw exception
redaction, response privacy, and the unavailable production gateway.

The preservation batch was:

```text
pytest -q \
  tests/test_security_attribution_investigator.py \
  tests/test_admin_me.py \
  tests/test_security_attribution_config.py \
  tests/test_security_request_attribution.py \
  tests/test_security_account_pseudonym.py \
  tests/test_security_attribution_account_routes.py \
  tests/test_authentication_audit_events.py \
  tests/test_authentication_audit_revocation_phase_2.py \
  tests/test_authentication_audit_retention.py

507 passed, 0 failed, 0 skipped
```

The full backend suite with the repository's coverage gate was:

```text
pytest tests/ --cov=app --cov-fail-under=89 --cov-report=term-missing \
  --cov-report=xml -p no:cacheprovider

1,709 passed, 0 failed, 152 skipped
91.09% coverage (89% required)
```

The 152 skips are explicit environment gates, not hidden test failures:

- 5 analytics migration tests: `ANALYTICS_EVENTS_DATABASE_URL` absent;
- 76 authentication-audit event migration tests:
  `AUTHENTICATION_AUDIT_DATABASE_URL` absent;
- 16 authentication-audit retention migration tests: the same disposable
  authentication-audit database absent;
- 43 security-attribution migration tests:
  `SECURITY_ATTRIBUTION_DATABASE_URL` absent; and
- 12 password-reset PostgreSQL tests: `PASSWORD_RESET_DATABASE_URL` absent.

The disabled-mode application import and changed-file Python compilation pass.
Final diff, secret, and committed-scope checks are recorded in the Draft PR
and task handoff. The repository configures no standalone Python formatter,
linter, or static type-check command; Black, Ruff, and mypy are not installed
in the backend test environment and are not claimed as run.

## Hosted development rollout (not executed)

Production remains disabled. No Railway or hosted database change is part of
this PR.

After the named-principal database capability and independent audit mechanism
are separately approved and implemented:

1. add one synthetic investigator's canonical internal UUID to Railway dev;
2. keep production investigation disabled;
3. deploy the feature branch to Railway dev;
4. authenticate as that active admin/investigator principal;
5. query one known synthetic incident and window no longer than 31 days;
6. verify only pseudonymous approved evidence is returned in RPC order;
7. verify an anonymous, user, and ordinary admin receive no data or count;
8. reconcile the successful RPC access row with the named provider audit;
9. force access-audit persistence failure in an isolated transaction and prove
   the endpoint returns no evidence;
10. verify `service_role`, clients, and the application still have no direct
    evidence-table privilege; and
11. remove the synthetic investigator after sanitized evidence capture.

Until that prerequisite PR exists, a dev deployment may verify default deny,
authorization, validation, and bounded unavailability only. It must not claim
successful evidence-query activation.

## Rollback

Set `SECURITY_ATTRIBUTION_INVESTIGATION_ENABLED=false` and redeploy. Disabled
mode denies every investigator request and needs no principal configuration.
If source rollback is needed, revert this application commit. There is no
database migration or data rollback. Preserve existing attribution and access
evidence under the merged 180-day retention policy; do not delete tables,
change grants, weaken RLS, or remove HMAC keys through this rollback.

## Explicit non-goals and remaining risks

- Historical identity resolution remains out of scope.
- Cross-epoch linking remains out of scope.
- The application endpoint is not a dashboard or general database explorer.
- Owner-only query activation remains blocked.
- The database access table records bounded capability, not the application
  principal UUID. Named attribution requires the separately approved provider
  role-assumption audit; this PR does not add a schema field.
- An enabled allowlist alone cannot return evidence because the production
  gateway remains unavailable.
- Existing attribution recording remains fail-open for business requests;
  investigator evidence access remains fail-closed.
- Production remains disabled and unverified.
