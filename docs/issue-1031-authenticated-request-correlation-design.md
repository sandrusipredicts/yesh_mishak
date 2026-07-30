# Issue #1031 item 3: authenticated request correlation design

## Decision status

This document is the privacy design decision for Issue #1031 item 3. It does
not implement the design.

**Recommendation:** keep general request metrics and product analytics
anonymous. In a separate security-evidence store, record one minimal
attribution event only for an exact allowlist of security-relevant requests.
Identify the acting account with an environment-bound, monthly rotating
HMAC-SHA-256 pseudonym. Do not create a persistent pseudonym-to-account
mapping. Permit cross-epoch grouping or account resolution only through a
separately authorized, audited resolver while the relevant epoch keys and
account record still exist.

The recommendation is not yet implementation authorization. The product
owner/security owner must approve the endpoint allowlist, key custodian,
investigator role, resolution policy, account-deletion semantics, and the
fail-open application boundary in [R. Open decisions](#r-open-decisions).

## A. Current gap

The exposure-window audit could account for aggregate request volume and
exclude unexpected writes, but it could not prove whether an exposed dev
credential was used for read-only access. The evidence records three causes:

- `api_request_metrics` has no account identifier by deliberate design;
- general request logs do not durably associate a trusted account with a
  request; and
- the relevant platform logs had rolled out of the searchable window.

See
[the exposure-window audit](evidence/dev-backend-performance-2026-07-26/exposure-window-audit-2026-07-26.md)
and [Issue #1031](https://github.com/sandrusipredicts/yesh_mishak/issues/1031).

Items 1, 2, and 4 have repaired `last_login`, added durable authentication
audit events, and enforced 180-day bounded retention for those events.
`public.authentication_audit_events` now answers credential-lifecycle
questions about login, logout, and token revocation. It does not represent
every security-relevant authenticated request, and its correlation identifier
groups authentication operations rather than attributing the rest of the
request surface.

The remaining question is:

> For a given incident window, which security-relevant authenticated requests
> originated from the same account?

The answer must not make ordinary gameplay, product analytics, or general
request-performance telemetry into an account activity history.

## B. Current system map

### B.1 Identity and telemetry flow

| Stage | Repository behavior | Identity status |
| --- | --- | --- |
| Request context | [`request_context.py`](../backend/app/middleware/request_context.py) accepts a bounded `X-Request-Id` or generates a UUID and stores only that value on `request.state`. | Deliberately independent of credentials and account identity. |
| General request metrics | [`request_metrics.py`](../backend/app/middleware/request_metrics.py) records after `call_next`; [`api_request_metrics.py`](../backend/app/services/api_request_metrics.py) persists time, normalized route, method, status, duration, and error boolean. | No account field is accepted or stored. |
| JWT verification | [`jwt.py`](../backend/app/auth/jwt.py) verifies signature, issuer, audience, expiry, and then exposes the `sub` claim to the authentication dependency. | A token subject is available, but is not yet a trusted active account. |
| Account resolution | [`get_current_user`](../backend/app/auth/dependencies.py) looks up the subject using the service-role client and refreshes status, role, and token-revocation fields even on cache hits. | This is the first point at which a request has a trusted internal account ID. |
| Authorization | `require_active_user` rejects banned/suspended accounts; `require_admin` additionally requires the database-backed `admin` role. | The dependency has the trusted ID even when an active/admin authorization check later denies the request. |
| Handler | Authenticated handlers receive `current_user`, use its `id` for ownership, rate limiting, and mutations, and sometimes write endpoint-specific logs. | Identity is handler-local; it is not copied to general request middleware or metrics. |
| Anonymous analytics | [`analytics_events.py`](../backend/app/routers/analytics_events.py) authenticates and rate-limits ingestion, but [`analytics_events.py`](../backend/app/services/analytics_events.py) deliberately discards the account before persistence. The registry permits only closed, coarse properties. | Authentication protects ingestion; stored product events remain anonymous. |
| Authentication audit | [`authentication_audit_events.sql`](../backend/migrations/authentication_audit_events.sql) stores a restricted raw `user_id` when known for login, logout, and revocation events. | Separate security store, not general request telemetry. |
| Retention | [`authentication_audit_retention.sql`](../backend/migrations/authentication_audit_retention.sql) and the [retention runbook](issue-1031-authentication-audit-retention.md) delete expired authentication audit rows in bounded oldest-first batches. | Fixed 180-day security evidence window with observable cleanup. |
| Admin/domain audit | Admin authorization is application-level. `user_moderation_audit` records raw actor and target IDs for four account-moderation actions. Other admin handlers are inconsistently represented by domain rows or application logs. | Useful but not a uniform, privacy-bounded request-attribution source. |
| Job evidence | [`JobRunRecorder`](../backend/app/services/job_runs.py) stores bounded job status/count evidence. | Operational evidence, not request attribution. |

### B.2 Exact identity boundary

Trusted identity becomes available inside `get_current_user` only after both
JWT verification and the database lookup/revocation checks. It remains
available through `require_active_user`, `require_admin`, and the endpoint
handler. A future attribution hook must consume identity from that trusted
dependency result. It must not:

- derive identity from an unverified JWT claim;
- parse the authorization header independently;
- accept an account ID from the body, query string, path, or client;
- copy identity into general-purpose request metrics; or
- treat the client-supplied form of `X-Request-Id` as an identity or
  idempotency key.

The current middleware boundary is useful: because it never receives the
dependency result, identity is deliberately discarded before
`api_request_metrics` persistence. The design preserves that boundary rather
than teaching general middleware about accounts.

### B.3 Existing conventions to reuse

Future implementation should reuse these repository conventions:

- a dedicated security table rather than general analytics;
- closed event/outcome/failure taxonomies and no free-form metadata;
- an application-generated UUID event ID with immutable idempotent replay;
- a service-role-executable, `SECURITY DEFINER` ingestion RPC with
  `search_path=pg_catalog`;
- explicit revocation from `PUBLIC`, `anon`, and `authenticated`;
- RLS enabled with no client policy;
- a trusted migration owner that also owns the narrowly scoped functions;
- database-first rollout, migration preflight, rollback-only synthetic
  verification, reapplication tests, and schema parity;
- fixed 180-day security retention, deterministic oldest-first batches,
  bounded work, and `JobRunRecorder` evidence; and
- sanitized warnings/monitoring that cannot change application behavior.

The existing application-level `admin` role is not an investigator role. It
is suitable for product administration through `require_admin`, but it
currently has neither a separately approved evidence-access capability nor
auditable break-glass key access.

## C. Threat model

### C.1 Protected assets

- the relationship between a security event and an account;
- environment-specific HMAC epoch keys;
- historical keys retained for approved resolution;
- the raw internal account UUID set used by a resolver;
- incident windows and investigator access records; and
- the continuing anonymity of general metrics and product analytics.

### C.2 Adversaries and consequences

| Threat | Consequence | Required control |
| --- | --- | --- |
| Security-telemetry database compromise | An attacker sees timestamps, bounded routes, outcomes, and within-epoch behavioral groups. | No raw account ID, target/resource ID, PII, body, header, token, or free-form field; monthly rotation; 180-day deletion; table inaccessible to clients and the ordinary application read path. |
| Application service compromise | The process can see trusted account IDs and the active epoch key, so it can enumerate current-epoch pseudonyms and forge current events. | The application holds only the active key (plus a short retry grace for the immediately previous key), cannot read the evidence table, and never receives the historical resolver key set. Rotate the active key immediately on compromise. |
| Active epoch-key compromise | Anyone with both the key and candidate account UUIDs can run an offline dictionary attack for that epoch. | Independent random keys per environment and epoch; do not derive all epochs from a long-lived root available to the application; version and revoke compromised keys. |
| Historical key-store compromise | An attacker could resolve the retained history covered by those keys. | Separate custody, named approvers, audited access, least-privilege resolver, fixed destruction deadline, and no key exposure in application configuration or query results. |
| Insider misuse | An operator could profile an account or resolve a pseudonym without a valid incident. | Dedicated no-login investigator capability, structured investigation UUID, bounded query RPCs, an append-only access audit, independent provider audit logs, and two-person approval for resolution. |
| Cross-environment joining | Reused identifiers could link local/dev/staging/production activity. | Independent random epoch keys in every environment and an environment value inside the canonical HMAC input; never copy keys or real production accounts into lower environments. |
| UUID dictionary attack | UUID entropy alone does not protect a deterministic plain hash when a candidate user table is available. | Keyed HMAC, not an unkeyed hash or public salt. Key compromise is treated as identity compromise. |
| Replay/enumeration of ingestion | A caller could submit duplicate or fabricated rows. | Service-role-only ingestion RPC, exact payload validation, immutable event-ID replay, clients denied execute, and no account ID in the RPC payload. |
| Long-term behavioral profiling | A stable identifier could become a user activity profile. | Exact endpoint allowlist, monthly epochs, no cross-epoch identifier in storage, 180-day deletion, and no general request/product telemetry change. |
| Joining with other datasets | Fine timestamps, route names, or client request IDs can enable re-identification. | Store a server-generated security request UUID, not `X-Request-Id`; store closed route keys instead of raw URLs; restrict time-window queries and exports. |
| Account deletion | A retained mapping could recreate a deleted identity. | No persistent mapping and no user foreign key. Keep the pseudonymous security row for the approved 180-day period, but make resolution intentionally unavailable after the account record is deleted unless identity was already preserved in an approved incident case. |

HMAC is pseudonymization, not anonymization. A pseudonym remains personal or
security-sensitive data when the organization retains a practical resolution
path. Rotation reduces the blast radius; it does not make access control,
retention, or key governance optional.

## D. Options considered

### D.1 Option A — rotating salted account pseudonym in broad request telemetry

On every authenticated request selected by a broad middleware rule, derive a
deterministic pseudonym from account ID, environment, rotation epoch, and a
secret key.

**Advantages**

- Strong same-account grouping within one epoch.
- No second identity mapping table.
- Environment and epoch binding can prevent permanent linkage.
- Storage adds one bounded identifier rather than raw account data.

**Disadvantages**

- Adding it to middleware or `api_request_metrics` turns general request
  telemetry into an account activity history, even if the value is
  pseudonymous.
- A stable epoch value supports behavioral profiling for every authenticated
  route.
- Cross-epoch investigations need retained keys and controlled resolution.
- App/key compromise plus the user UUID set permits enumeration.
- “Security relevant” can silently broaden when implemented as a negative
  filter rather than an exact allowlist.

Historical resolution is possible only if epoch keys are retained and a
resolver is approved. Destroying an epoch key makes unknown pseudonyms
intentionally irreversible, except for relationships already recorded in an
incident case.

**Decision:** reject as a standalone broad middleware/metrics design.

### D.2 Option B — opaque per-request correlation ID plus controlled mapping

Generate a random request correlation ID for telemetry and keep a restricted
mapping from that ID to raw account ID.

**Advantages**

- Excellent investigator usability across arbitrary windows.
- The telemetry store alone has no deterministic account grouping.
- Mapping retention can be shorter than telemetry retention.
- Mapping deletion can make old telemetry unresolvable.

**Disadvantages**

- The mapping store is a concentrated identity index. Exposure of both stores,
  or mapping-store access by an insider, reconstructs the complete request
  history.
- A distinct mapping row is needed for every request, increasing row and index
  volume.
- Telemetry and mapping writes must be atomic to avoid orphaned telemetry or
  silently unattributable requests. A single database RPC could provide that
  atomicity, but separate stores cannot do so without a distributed
  consistency problem.
- If mapping persistence fails, the system must either fail the user request,
  keep an unresolvable event, or lose the event. None matches the repository's
  current non-fatal observability convention cleanly.
- Deletion and retention must coordinate across two stores, backups, and query
  tooling.

If the telemetry store alone leaks, request-level activity is visible but not
groupable by account. If only the mapping leaks, raw account relationships to
opaque IDs are visible but route/outcome context is absent. Exposure of both
restores the complete join.

**Decision:** reject for initial implementation. Its operational and privacy
cost is not justified by the narrow incident question.

### D.3 Option C — attribution only on security-relevant endpoints

Reuse `authentication_audit_events` and domain audit records where they
already answer the question. Add direct account attribution only to a closed
set of uncovered security routes.

**Advantages**

- Lowest event volume and smallest risk of expansion into product analytics.
- Existing authentication, moderation, retention, and verification patterns
  can be reused.
- Direct account IDs are easy for investigators and remain queryable across
  the full retention window.
- Failures can follow existing non-fatal audit behavior.

**Disadvantages**

- Raw account IDs remain directly linkable for the entire retention period.
- Existing domain audits are inconsistent, have different schemas and
  retention, and do not uniformly represent denied or failed requests.
- A union of authentication, moderation, and endpoint-specific stores is hard
  to reason about.
- Direct IDs create a larger blast radius if the security table is exposed.

**Decision:** the allowlist is the right scope boundary, but direct IDs are
not the preferred new identifier.

### D.4 Option D — exact allowlist plus rotating HMAC pseudonym

Create a separate append-only security-attribution table for the exact route
registry in section H. Derive an environment-bound monthly pseudonym only
after trusted identity resolution. Keep no persistent mapping. Use the
existing authentication audit as the authoritative credential-lifecycle
record, without modifying or backfilling it.

**Advantages**

- Directly answers same-account grouping within an epoch.
- Keeps general metrics and analytics unchanged.
- Limits route coverage, leak blast radius, data growth, and profiling.
- Independent environment/epoch keys limit cross-environment and
  cross-window linkage.
- Avoids dual-write mapping consistency and a permanent identity index.
- Uses existing security audit, RPC, retention, and verification conventions.

**Disadvantages**

- Cross-month grouping requires a separately controlled resolver.
- Monthly key generation, custody, access logging, and destruction are real
  operations that the repository does not yet implement.
- App compromise exposes current-epoch linkability.
- Investigators cannot resolve an account after deletion if no approved case
  captured that relationship.

**Decision:** recommend, subject to the approval gates in section R.

## E. Weighted decision matrix

Scores range from 1 (poor) to 5 (strong). The maximum weighted score is 500.
For the two linkability criteria, a higher score means stronger prevention of
unapproved linkage. Investigator usefulness is scored separately.

The highest weights go to investigation value and privacy minimization because
both are explicit acceptance criteria. Expansion resistance is also high
because identity in general metrics would reverse an intentional product
decision. Blast radius, investigator usability, and failure safety follow.
Complexity and storage matter, but cannot outweigh the security/privacy
boundary.

| Criterion | Weight | A: rotating/broad | B: opaque + mapping | C: allowlist/direct | D: allowlist + rotating |
| --- | ---: | ---: | ---: | ---: | ---: |
| Incident investigation value | 14 | 4 | 5 | 3 | 5 |
| Privacy minimization | 14 | 4 | 2 | 4 | 5 |
| Blast radius if telemetry leaks | 9 | 4 | 2 | 3 | 4 |
| Protection from cross-window linkage | 6 | 4 | 1 | 1 | 4 |
| Protection from cross-environment linkage | 5 | 5 | 4 | 3 | 5 |
| Implementation simplicity | 5 | 3 | 2 | 4 | 3 |
| Operational simplicity | 5 | 3 | 2 | 4 | 3 |
| Failure safety | 7 | 3 | 2 | 4 | 4 |
| Data growth | 3 | 3 | 2 | 5 | 4 |
| Retention compatibility | 4 | 4 | 3 | 5 | 5 |
| Testability | 4 | 4 | 3 | 4 | 5 |
| Revocation/deletion semantics | 5 | 4 | 2 | 3 | 4 |
| Investigator usability | 9 | 3 | 5 | 5 | 4 |
| Resistance to accidental analytics expansion | 10 | 2 | 3 | 5 | 5 |
| **Weighted total / 500** | **100** | **356** | **291** | **375** | **441** |
| **Normalized result** |  | **71.2%** | **58.2%** | **75.0%** | **88.2%** |

Option D wins by keeping Option C's narrow coverage while reducing the
retention-wide linkability of direct IDs. Its lower operational score is
accepted only if key custody and investigator access are explicitly owned.

## F. Recommended architecture

Use four deliberately separate planes:

1. **General request metrics:** unchanged `api_request_metrics`, containing no
   identity or pseudonym.
2. **Anonymous product analytics:** unchanged `analytics_events` and
   `share_events`, containing no identity or pseudonym.
3. **Security evidence:** existing `authentication_audit_events` plus a future
   `security_request_attribution_events` table for the exact allowlist.
4. **Controlled investigation:** bounded query functions and an independently
   authorized resolver with access auditing. No frontend, product-admin
   endpoint, dashboard, or persistent mapping.

The future application flow is:

1. request context creates its ordinary request ID as today;
2. the existing auth dependency verifies the credential and account state;
3. an allowlist registry matches the exact HTTP method and route template;
4. a security-specific dependency/wrapper, not the general metrics
   middleware, captures one UTC `occurred_at` value and generates a new
   server-only `security_request_id`;
5. it derives the epoch pseudonym from the trusted internal account ID and
   that captured timestamp;
6. after the endpoint outcome is known, it calls the append-only ingestion RPC
   with the same timestamp and bounded values only; and
7. general request metrics complete exactly as they do today, without seeing
   the account or pseudonym.

The server-only security request ID is distinct from `X-Request-Id`. The
current request header may be client-selected, so it is not stored in the
security table and is not used for deduplication.

The security-specific dependency must also cover authorization failures that
occur after identity resolution but before handler entry. It may keep a
request-local attribution context for that purpose, but the general metrics
middleware must never read or persist it.

Existing authentication audit rows are neither changed nor backfilled. They
remain authoritative for credential lifecycle. A security-attribution event
for an authenticated auth endpoint represents the request envelope, not a
replacement for its login/revocation audit rows.

## G. Privacy rationale

The privacy boundary is:

- identity-bearing evidence exists only for a reviewed security purpose;
- only exact allowlisted routes can emit it;
- stored identity is a monthly pseudonym, not a raw account ID;
- no target/resource identifier is stored;
- no general request metric or product event gains an identity field;
- no request body, header, cookie, authorization data, JWT, token, credential,
  email, username, phone, display name, IP, user agent, raw URL, query string,
  or free-form metadata is stored;
- no permanent cross-window or cross-environment identifier exists;
- default investigators see pseudonymous groups, not account identity;
- resolution is case-bound, separately approved, and audited; and
- rows and resolver keys have finite, enforced lifetimes.

This design intentionally does not make every authenticated read auditable.
That would answer a broader tracing question by creating a comprehensive
account activity history. Instead it includes narrowly justified private or
privileged reads and explicitly excludes ordinary gameplay/product traffic.

## H. Exact scope and endpoint allowlist

The future route registry must match **both** HTTP method and FastAPI route
template. There are no prefix wildcards and no “all authenticated routes”
fallback. Each entry maps to a closed `route_key` and
`security_event_category`. Adding or removing an entry requires a reviewed
privacy/design change, schema constraint update, and tests.

### H.1 Account security and recovery

| Method and route | Route key | Event category | Inclusion reason |
| --- | --- | --- | --- |
| `POST /auth/logout` | `auth_logout` | `session_security_change` | Ends the current session and revokes tokens. |
| `GET /auth/account-methods` | `auth_account_methods_read` | `credential_configuration_read` | Reveals configured authentication methods. |
| `POST /auth/link/google` | `auth_google_link` | `credential_method_change` | Adds a sign-in method. |
| `POST /auth/unlink/google` | `auth_google_unlink` | `credential_method_change` | Removes a sign-in method and revokes tokens. |
| `POST /auth/set-password` | `auth_password_set` | `credential_method_change` | Adds a password and revokes tokens. |
| `POST /auth/remove-password` | `auth_password_remove` | `credential_method_change` | Removes a password and revokes tokens. |
| `POST /auth/password-reset/confirm` | `auth_password_reset_confirm` | `credential_recovery` | Changes a credential and revokes tokens; attribute only after the recovery token resolves a trusted account. |
| `POST /auth/verify-email` | `auth_email_verify` | `account_assurance_change` | Establishes control of an account email; attribute only after the verification token resolves a trusted account. |
| `DELETE /auth/account` | `auth_account_delete` | `account_lifecycle_change` | Destructive account lifecycle action. |

`POST /auth/login` and `POST /auth/google` begin without an authenticated
actor. They remain in `authentication_audit_events`; successful login already
has a resolved account and failed login may intentionally have no account.
They do not create a second request-attribution row.

### H.2 Narrow private reads and user access controls

| Method and route | Route key | Event category | Inclusion reason |
| --- | --- | --- | --- |
| `GET /field-reports/mine` | `field_reports_mine_read` | `private_security_record_read` | Reads the account's submitted safety reports. |
| `GET /moderation/blocks` | `user_blocks_read` | `access_control_read` | Reads an account-specific access-control list. |
| `POST /moderation/blocks/{blocked_user_id}` | `user_block_create` | `access_control_change` | Changes who can interact with the account. |
| `DELETE /moderation/blocks/{blocked_user_id}` | `user_block_delete` | `access_control_change` | Changes who can interact with the account. |
| `GET /notifications` | `notifications_private_read` | `private_notification_read` | Reads private, account-scoped notification content. |
| `GET /notifications/preferences` | `notification_preferences_read` | `private_security_setting_read` | Reads private notification/location preference settings. |
| `PUT /notifications/preferences` | `notification_preferences_update` | `private_security_setting_change` | Changes private delivery/location settings. |
| `POST /notifications/push-token` | `push_token_bind` | `notification_delivery_binding_change` | Binds a delivery destination to the account. |
| `DELETE /notifications/push-token` | `push_token_unbind` | `notification_delivery_binding_change` | Removes a delivery destination from the account. |

The event records only the route key and acting pseudonym. It does not store
the blocked account, report, notification, location, device token, or any
request value.

### H.3 Privileged admin reads

All entries below require the existing database-backed `require_admin`
decision. Valid non-admin credentials denied by `require_admin` are recorded
with outcome `denied`; missing, invalid, expired, or otherwise untrusted
credentials have no attributable account.

| Method and route | Route key | Event category |
| --- | --- | --- |
| `GET /admin/me` | `admin_self_read` | `admin_sensitive_read` |
| `GET /admin/users` | `admin_users_read` | `admin_sensitive_read` |
| `GET /admin/field-reports` | `admin_field_reports_read` | `admin_sensitive_read` |
| `GET /admin/stats` | `admin_stats_read` | `admin_sensitive_read` |
| `GET /admin/fields` | `admin_fields_read` | `admin_sensitive_read` |
| `GET /admin/fields/pending` | `admin_fields_pending_read` | `admin_sensitive_read` |
| `GET /admin/fields/duplicates` | `admin_field_duplicates_read` | `admin_sensitive_read` |
| `GET /admin/games` | `admin_games_read` | `admin_sensitive_read` |
| `GET /admin/engagement` | `admin_engagement_read` | `admin_sensitive_read` |
| `GET /admin/monitoring` | `admin_monitoring_read` | `admin_sensitive_read` |
| `GET /admin/content-reports` | `admin_content_reports_read` | `admin_sensitive_read` |
| `POST /notifications/candidates` | `admin_notification_candidates_read` | `admin_sensitive_read` |

`POST /notifications/candidates` is included despite its method because it is
a privileged candidate query, not a mutation.

### H.4 Privileged admin mutations

| Method and route | Route key | Event category |
| --- | --- | --- |
| `POST /admin/users/{user_id}/ban` | `admin_user_ban` | `admin_account_control` |
| `POST /admin/users/{user_id}/unban` | `admin_user_unban` | `admin_account_control` |
| `POST /admin/users/{user_id}/suspend` | `admin_user_suspend` | `admin_account_control` |
| `POST /admin/users/{user_id}/unsuspend` | `admin_user_unsuspend` | `admin_account_control` |
| `PATCH /admin/field-reports/{report_id}/status` | `admin_field_report_status` | `admin_moderation_change` |
| `PATCH /admin/field-reports/{report_id}/resolve` | `admin_field_report_resolve` | `admin_moderation_change` |
| `POST /admin/fields/{field_id}/approve` | `admin_field_approve` | `admin_content_control` |
| `POST /admin/fields/{field_id}/reject` | `admin_field_reject` | `admin_content_control` |
| `PATCH /admin/fields/{field_id}/status` | `admin_field_status` | `admin_content_control` |
| `PATCH /admin/fields/{field_id}` | `admin_field_update` | `admin_content_control` |
| `DELETE /admin/fields/{field_id}` | `admin_field_delete` | `admin_content_control` |
| `PATCH /fields/{field_id}/status` | `admin_field_status_external` | `admin_content_control` |
| `POST /admin/reminders/scheduled-games/run` | `admin_reminders_run` | `admin_operational_action` |
| `POST /admin/notifications/cleanup` | `admin_notification_cleanup` | `admin_operational_action` |
| `POST /admin/games/{game_id}/close` | `admin_game_close` | `admin_content_control` |
| `POST /admin/games/{game_id}/extend` | `admin_game_extend` | `admin_content_control` |
| `POST /admin/games/{game_id}/cancel` | `admin_game_cancel` | `admin_content_control` |
| `PATCH /admin/content-reports/{report_id}` | `admin_content_report_update` | `admin_moderation_change` |

Target user, field, report, game, and job payload values are deliberately not
part of this attribution store. Existing domain tables remain authoritative
for the target and mutation details.

### H.5 Explicit exclusions

The initial denylist is as important as the allowlist:

- public field/game reads and health/root routes;
- `GET /games/me` and all game create/join/leave/close/extend/cancel traffic;
- field creation and ordinary field-report submission;
- notification unread-count polling, read/read-all actions, and test push;
- analytics ingestion, share events, app-open, and screen-view events;
- registration, username/email availability, password-reset request,
  resend-verification, terms acceptance, and account-method availability
  probes before identity is trusted;
- unmatched routes, CORS preflight, static assets, and internal health checks;
- any route added later unless explicitly reviewed and registered; and
- all anonymous or invalid-credential requests for which no trusted account
  exists.

Failed authorization attempts are attributable only when the JWT and database
lookup establish a trusted account first. A valid active non-admin denied at
`require_admin`, or a trusted account failing endpoint reauthentication, may
produce `denied`. A missing, malformed, expired, revoked, or unverifiable
credential does not produce an account pseudonym. Existing authentication
audit and aggregate monitoring remain the appropriate evidence for those
failures.

## I. Identifier design

### I.1 Primitive and key material

- Primitive: HMAC using SHA-256 as standardized by RFC 2104/FIPS 198-1.
- Key: 32 independently random bytes for each environment and calendar-month
  epoch. A public salt or unkeyed SHA-256 is not acceptable.
- Environments: a closed deployment enum such as `local`, `dev`, `staging`,
  and `production`. Production and non-production never share a key.
- Epoch: UTC calendar month, encoded as `YYYY-MM`.
- Key version: a positive integer local to the environment/epoch. Normal
  monthly rotation starts at version 1; emergency replacement increments it.
- Key source: a managed, access-audited secret store selected by the owner.
  The repository currently proves Railway/Vercel environment separation, but
  does not prove an HSM/KMS or historical-key access-audit capability. This is
  an approval gate, not an assumed facility.

Do not derive every epoch from a long-lived root key held by the application.
Compromise of such a root would defeat epoch isolation. Generate independent
epoch keys. The normal application receives only the active key and, for at
most 24 hours after rollover, the immediately previous key for an in-flight
retry that retains its original event timestamp.

### I.2 Canonical input

Validate every component before construction. The HMAC message is UTF-8:

```text
yesh_mishak.security-account-pseudonym:v1
environment=<closed-environment>
epoch=<YYYY-MM>
account_uuid=<lowercase-canonical-uuid>
```

The labels and order are literal, adjacent lines are separated by one LF byte
(`0x0A`), and there is **no trailing newline** after the UUID. Public test
vectors must fix those bytes. The environment is included even though keys are
already environment-specific, providing defense in depth against secret
misconfiguration. The internal UUID comes only from the trusted dependency.

### I.3 Output

Compute all 32 HMAC bytes and encode them with unpadded Base64url. The result
is exactly 43 ASCII characters matching `^[A-Za-z0-9_-]{43}$`. Do not truncate
it.

The random collision probability is negligible at 256 bits. The application
cannot reliably detect a collision without a raw identity mapping. The
controlled resolver must reject and escalate if two candidate accounts ever
match one pseudonym; it must not invent a suffix or silently alter
determinism.

### I.4 Linkability and resolution

- Same account, environment, epoch, and key version: same pseudonym.
- Different account: computationally independent pseudonym.
- Same account in another month: different pseudonym.
- Same account in another environment: different pseudonym.
- Emergency key rotation in one month: a different pseudonym with a different
  key version.

Default investigation can group rows directly within an epoch. Cross-epoch
grouping uses an approved resolver that reads the relevant keys and the
internal UUID candidate set, then emits an ephemeral case-local actor label.
It does not persist a mapping or reveal a key.

Raw account resolution is a second, higher-privilege operation. When approved,
the resolver may return the internal account UUID only. Email, username,
phone, display name, and other profile data are outside this design.

After the resolver key is destroyed, historical resolution for that epoch is
intentionally impossible. After account deletion, unknown pseudonyms are also
intentionally unresolvable because there is no retained mapping and the user
row no longer supplies a candidate UUID.

## J. Proposed data model

### J.1 `public.security_request_attribution_events`

This is a future proposal, not a migration in this branch.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key; application-generated immutable event/idempotency ID. |
| `occurred_at` | `timestamptz` | Not null; server UTC time captured when the trusted attribution context is created, then reused for retention and epoch validation. |
| `security_request_id` | `uuid` | Not null; server-generated per request, never copied from a header. |
| `security_event_category` | `text` | Not null; exact closed taxonomy from section H. |
| `route_key` | `text` | Not null; exact closed method/template key from section H, never a raw URL. |
| `account_pseudonym` | `text` | Not null; exactly 43 Base64url characters. |
| `pseudonym_epoch` | `date` | Not null; first UTC day of the event's calendar month. |
| `pseudonym_key_version` | `smallint` | Not null and positive. |
| `outcome` | `text` | One of `succeeded`, `denied`, `failed`, `ambiguous`. |
| `source_environment` | `text` | Not null; closed environment enum and consistent with key configuration. |
| `failure_category` | `text` | Null for success; otherwise one of `authorization_denied`, `reauthentication_failed`, `validation_rejected`, `conflict`, `not_found`, `rate_limited`, `dependency_unavailable`, `outcome_unknown`, `internal_error`. |

Required constraints:

- one row per `(security_request_id, route_key)`;
- success requires null `failure_category`;
- every other outcome requires a compatible bounded failure category;
- `pseudonym_epoch` must be the first day of the UTC month containing
  `occurred_at`;
- route/category pairs must exactly match the reviewed registry;
- no update path exists; exact replay of the same `id` and payload returns
  false, while reuse with different payload fails safely; and
- there is no foreign key to `users`.

Required indexes:

- `(occurred_at desc)` for retention/window queries;
- `(account_pseudonym, pseudonym_epoch, occurred_at desc)` for within-epoch
  grouping;
- `(security_event_category, occurred_at desc)` for incident filtering; and
- the unique constraint on `(security_request_id, route_key)`.

The table has no JSON/JSONB, array, target/resource ID, raw status code,
method, path, URL, metadata, or free-text column. Method and route are
represented by the reviewed `route_key`.

### J.2 `public.security_investigation_access_events`

Access to security evidence and resolver keys also needs durable
accountability.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key. |
| `accessed_at` | `timestamptz` | Not null; server UTC time. |
| `investigation_id` | `uuid` | Not null; identifier from the approved case process, not free text. |
| `investigator_principal` | `text` | Not null; lowercase opaque database role name, 1–63 characters matching `^[a-z][a-z0-9_]{0,62}$`; never an email or application user ID. |
| `action` | `text` | One of `query`, `group`, `resolve`, `export`. |
| `window_started_at` | `timestamptz` | Required for query/group/export. |
| `window_ended_at` | `timestamptz` | Required and later than start. |
| `event_count` | `integer` | Integer from 0 through 10,000; no row IDs. |
| `source_environment` | `text` | Closed environment enum. |
| `outcome` | `text` | `succeeded` or `failed`. |
| `failure_category` | `text` | Null on success; otherwise a bounded access/resolver category. |

It contains no queried pseudonym, account ID, PII, query text, export
contents, or free-form case notes. Independent database/secret-manager audit
logs remain necessary because a caller-controlled transaction could otherwise
roll back an in-database access record.

## K. Access-control model

### K.1 Ownership and ingestion

- The existing trusted migration role owns both proposed tables and all
  `SECURITY DEFINER` functions. It must not be `PUBLIC`, `anon`,
  `authenticated`, or `service_role`.
- `security_request_attribution_events` is append-only outside the bounded
  retention function.
- The trusted owner has exact ordinary table privileges `SELECT`, `INSERT`,
  and `DELETE`, plus column-scoped `UPDATE(id)` only where PostgreSQL requires
  an update privilege for `SELECT ... FOR UPDATE SKIP LOCKED`. It has no
  table-wide `UPDATE`.
- `service_role` has only `EXECUTE` on
  `record_security_request_attribution_event(...)` and the dedicated cleanup
  RPC. It has no direct `SELECT`, `INSERT`, `UPDATE`, or `DELETE` on the new
  evidence or access-audit tables.
- The ingestion RPC is `SECURITY DEFINER`, has exact signature/ownership/ACL,
  `search_path=pg_catalog`, accepts only typed bounded fields, and never
  accepts raw account identity, SQL, JSON, or metadata.
- `PUBLIC`, `anon`, and `authenticated` have no table/column/function
  privilege. The frontend cannot ingest or query evidence.
- RLS is enabled with no client policies. `FORCE ROW LEVEL SECURITY` remains
  disabled so the trusted owner functions can operate; exact ACLs and function
  bodies are the primary boundary.

The application derives the pseudonym before the RPC call. This prevents the
database evidence function from receiving raw account identity and prevents a
future table leak from exposing a joinable user foreign key.

### K.2 Investigator access

- Create a dedicated no-login database capability such as
  `security_evidence_reader`; do not reuse the application `admin` role or
  frontend JWT roles.
- Human access comes through named, MFA-protected database/SSO principals that
  may assume the capability for an approved case.
- The capability has no direct table `SELECT`. It may execute only bounded
  query/group RPCs requiring an `investigation_id`, environment, finite time
  window, closed category filter, row limit, and pagination cursor.
- A single call may cover at most 31 days and return at most 10,000 rows.
  Larger investigations paginate deliberately; the access audit records each
  call.
- Query RPCs return only proposed evidence columns. They cannot accept raw SQL,
  arbitrary column names, free-form predicates, or profile identifiers.
- Evidence query and cross-epoch resolution are separate privileges. The
  resolver additionally requires two-person approval and historical key-store
  access.
- Resolver outputs default to an ephemeral case-local actor label. Returning
  an internal account UUID requires explicit identity-resolution approval.
- Investigator query/resolution fails closed if its access evidence cannot be
  committed or the independent provider audit trail is unavailable.

The current repository does not establish the named human principal provider,
MFA mechanism, managed key store, or immutable provider audit log. Those must
be selected and verified before the resolver PR can be implementation-ready.

## L. Retention and rotation

### L.1 Event and access-evidence retention

Use the same fixed **180-day** security retention policy as
`authentication_audit_events`.

This is appropriate because the new rows answer the same delayed incident
question, the existing decision covers approximately two quarterly review
cycles, and a different duration would create confusing gaps between
credential and request evidence. Longer retention would increase linkable
behavioral history without repository evidence of a need; shorter retention
would recreate the delayed-discovery gap.

Cleanup must:

- run daily through the existing Railway scheduling platform;
- use a dedicated `SECURITY DEFINER` cleanup RPC for each table;
- delete only `occurred_at/accessed_at < cutoff`;
- keep rows exactly at the cutoff;
- lock/delete deterministic oldest-first batches;
- accept 1–1,000 rows per batch;
- default to 1,000 rows and at most 50 batches per daily run;
- return only deleted counts;
- retry a failed, non-destructive batch on the next daily run; and
- record bounded `JobRunRecorder` status/count/category evidence.

A separate cleanup RPC preserves table-specific ACLs and failure isolation.
The future job may invoke both new RPCs from one security-retention entry point
or use a second command in the same scheduler platform. The implementation PR
must choose one reviewed deployment shape and prove there is exactly one daily
schedule per cleanup target.

No event is deleted because an account was rotated, suspended, or deleted.
Deletion is time-based only. There is no legal-hold mechanism in this design;
one requires a separate approved change before affected evidence expires.

### L.2 Growth bound

The repository contains no representative production count for the proposed
allowlist, so this document does not invent one. At most one row is proposed
per allowlisted request/route key.

```text
retained_rows
  <= average_daily_allowlisted_requests × 180 + expired_cleanup_backlog

cleanup_capacity_per_run
  = batch_size × max_batches
  = 1,000 × 50
  = 50,000 rows/day by default
```

Finite recovery requires average daily rows aging out to remain below cleanup
capacity. Before enabling the full allowlist, use aggregate route counts from
identity-free `api_request_metrics` to measure daily allowlisted volume and
validate recovery headroom. Repeated maximum-batch runs are a capacity alert,
not permission to remove the cap. A change to batch bounds or partitioning
requires measured evidence and a separate review.

### L.3 Key lifetime

- Rotate active pseudonym keys at 00:00 UTC on the first day of each month.
- Remove the prior key from the application no later than 24 hours after
  rollover.
- A historical resolver key becomes eligible for destruction only after
  `epoch_end + 180 days` and successful verification that no row for that
  epoch remains.
- If verification still finds expired rows, retry cleanup but retain the key
  for no more than seven additional days. At `epoch_end + 187 days`, destroy
  it even if stale expired rows remain. Those rows remain groupable within
  their epoch but become intentionally unresolvable.
- Cleanup failure retains rows and retries; it never causes early deletion.
- Key destruction is irreversible. It must produce independent key-store
  audit evidence and a bounded investigation-access record.

An emergency key rotation starts a new key version immediately. It cannot make
already observed pseudonyms unlinkable, so the incident record must identify
the compromised environment/epoch/version and resolver access must treat that
epoch as exposed.

## M. Failure model

### M.1 User-request behavior

Security attribution is investigative evidence, not an authorization
dependency. The initial implementation is **fail-open for application
requests**:

- the authoritative handler result does not change if pseudonym derivation,
  event persistence, logging, or monitoring fails;
- a mutation that already committed is never reported as failed merely because
  the separate evidence write failed; and
- a read is not denied because the evidence store is unavailable.

Failing closed for admin/credential mutations was considered. It would be
defensible only if the authoritative mutation and attribution insert were one
database transaction. The repository currently uses several independent
PostgREST calls and services, so imposing fail-closed behavior inconsistently
would create availability failures and ambiguous outcomes. A future,
separately reviewed mutation-specific transaction may strengthen this
boundary, but it is not part of the initial design.

### M.2 Outcome classification

- `succeeded`: the handler has a confirmed successful result.
- `denied`: trusted identity exists, but authorization, account state, or
  endpoint reauthentication denies the operation.
- `failed`: the operation is confirmed not to have completed.
- `ambiguous`: the application cannot prove whether the authoritative
  operation committed, for example after an outcome-ambiguous database
  response.

An attribution persistence failure does not create a false `failed` business
event. It emits a bounded health warning instead. If the primary insert itself
cannot complete, no durable attribution row can be promised.

### M.3 Retry and duplicate behavior

- Generate `id` and `security_request_id` once per server request.
- The ingestion RPC serializes exact replay by event ID.
- Exact immutable replay returns “already recorded” without a second row.
- Reuse of an event ID with different payload fails as a sanitized idempotency
  conflict.
- Do not run an unbounded or background retry queue in the initial
  implementation.
- A caller may make at most one bounded immediate retry for a classified
  transient transport failure, with the same IDs and identical payload.
- A client retry is a new HTTP request and receives a new security request ID;
  it is not deduplicated with the earlier attempt.

### M.4 Observability failure

Persistence failure emits only:

- stable event name;
- route key and security event category;
- intended outcome and bounded failure category;
- source environment;
- `account_identity_present=true/false`;
- exception class/category from an allowlist; and
- `result=partial_failure`.

It must not emit the raw account ID, pseudonym, event/request ID, target ID,
request body/header, token, credential, raw database response, exception text,
or stack data containing request values. Monitoring uses bounded aggregate
tags only. Logger or monitoring failure is swallowed and cannot crash the
request.

When the database itself is unavailable, this design cannot guarantee a
second durable record of the missing attribution without an outbox or an
independent durable sink. Neither is approved here. The observable bounded
warning and monitoring alert are the accepted initial evidence of that gap;
existing authentication/domain audit rows may still provide independent
evidence where their own write succeeded. This residual must be approved
rather than hidden.

Investigator query/resolver operations use the opposite boundary: they fail
closed when access cannot be independently audited, because no end-user
availability requirement justifies unaudited identity resolution.

## N. Investigation workflow

Example: an investigator receives an approved incident UUID and a UTC window
spanning the last five weeks.

1. Confirm the target environment and approval scope. Use a named,
   MFA-protected principal; never use the application's `service_role` secret.
2. Call the bounded evidence query RPC in two 31-day-or-smaller pages,
   supplying the investigation UUID and closed security categories.
3. Group results by
   `(source_environment, pseudonym_epoch, pseudonym_key_version,
   account_pseudonym)`. This directly answers same-account activity inside
   each epoch without exposing an account identity.
4. Because the window crosses a month boundary, request cross-epoch grouping.
   The resolver verifies two-person approval, reads only the required epoch
   keys and candidate internal UUIDs, and emits ephemeral case-local labels
   linking matching epoch pseudonyms.
5. If the case requires an actual account, obtain the separate identity
   resolution approval. The resolver returns only the internal account UUID.
6. Query existing `authentication_audit_events` for that UUID and window
   through its separately approved security query path to compare login,
   logout, and revocation evidence. Do not join on email or other PII.
7. Produce an evidence summary containing the incident UUID, window, route
   categories, outcomes, counts, and case-local actor labels. Exclude keys,
   raw account/profile data, target IDs, and request contents.
8. Confirm `security_investigation_access_events`, database audit logs, and
   secret-manager key-access logs show the query/resolution/export actions.
9. Delete ephemeral resolver working data when the case process ends. The
   source security rows continue to age out under the fixed 180-day policy.

If the account was deleted or the epoch key was destroyed, the investigator
can still group stored events within that epoch but cannot recover the
identity or prove a cross-epoch match. The report must state that limitation;
operators must not reconstruct identity from unrelated datasets as a
workaround.

## O. Rollout plan

No rollout is authorized by this document branch.

1. **Design approval:** approve this document and every decision in section R.
2. **Schema PR:** add tables, exact constraints/indexes, ingestion/query/cleanup
   RPCs, owner/ACL/RLS checks, schema parity, retention job integration,
   preflight, rollback-only verification, and zero-skip PostgreSQL tests.
3. **Cryptography PR:** add the independently reviewed HMAC library,
   canonical test vectors, closed environment/key configuration, and unit
   tests. Provision no production key in source control.
4. **Minimal instrumentation PR:** instrument account security routes and the
   four admin account-control mutations first. General metrics/analytics
   schema assertions are release gates.
5. **Investigator PR:** add bounded query/group tooling, access-audit
   persistence, resolver runbook, role provisioning documentation, and
   provider-audit verification. No HTTP admin endpoint.
6. **Isolated-dev verification:** use synthetic accounts and independent dev
   keys. Verify allowlist/denylist, ACLs, RLS, same/different account grouping,
   cross-epoch/environment separation, failure behavior, and cleanup.
7. **Shadow mode:** enable persistence for the minimal dev allowlist while no
   investigator resolution is enabled. Compare aggregate allowlisted request
   counts with attribution counts; inspect only bounded counts, never user
   content.
8. **Access-control gate:** prove named principals, MFA, two-person resolution
   approval, access-audit commit, provider DB audit, and secret-key access
   audit. Denied roles must produce zero rows and no key access.
9. **Retention gate:** create rollback-only synthetic rows around the exact
   cutoff, verify bounded cleanup and job evidence, and validate measured
   daily volume is below recovery capacity.
10. **Production approval:** create independent production epoch keys and
    deploy schema before application instrumentation. Do not copy dev data or
    keys. Enable only the minimal allowlist after explicit privacy/security
    approval.
11. **Expansion:** add the remaining approved routes in small reviewed batches
    after the minimal set demonstrates completeness and acceptable volume.
12. **Post-rollout audit:** observe at least one normal daily cleanup, inspect
    access and key-audit trails, prove general metrics/analytics remain
    anonymous, and review allowlist drift.

## P. Rollback plan

1. Disable attribution instrumentation or redeploy the previous application
   version first.
2. Stop creation of new pseudonyms and resolver operations. No mapping
   creation exists to stop.
3. Disable only the new table's cleanup schedule if rollback investigation
   needs rows preserved temporarily; do not disable authentication-audit
   retention accidentally.
4. Preserve existing evidence tables and rows. The previous application does
   not use them, so additive schema can remain inert.
5. Preserve required historical epoch keys until the corresponding rows reach
   the approved key-destruction deadline. Early destruction intentionally
   removes resolution capability and requires separate approval.
6. Revoke investigator/resolver role assumption if the access system is part
   of the rollback, while preserving provider audit records.
7. Drop functions/tables only through a separately reviewed forward migration
   after confirming no retained evidence or investigation depends on them.
8. Prove rollback by showing no new attribution rows after disablement,
   ordinary application behavior is unchanged, general metrics/analytics
   still have no identity fields, and remaining rows still follow the approved
   retention decision.

Rollback cannot make already recorded telemetry “unseen,” undo an investigator
export, or reverse a previously disclosed pseudonym/account relationship.

## Q. Test plan for future implementation

### Q.1 Pseudonym unit tests

- same canonical account/environment/epoch/version produces the same output;
- different accounts produce different outputs;
- the same account in another UTC month produces a different output;
- the same account in dev and production produces different output;
- emergency key-version change produces different output;
- output is exactly 43 unpadded Base64url characters;
- fixed public test vectors catch canonicalization drift;
- uppercase, non-canonical, missing, malformed, or non-UUID identity is
  rejected before persistence;
- unknown/free-form environments and invalid epoch/version values fail closed;
- key lookup/rotation failure emits only bounded diagnostics;
- the previous key is unavailable to the app after its 24-hour grace; and
- no key, canonical raw input, account ID, or pseudonym enters logs,
  monitoring, exceptions, or test artifacts.

### Q.2 Scope and application tests

- unauthenticated and invalid-token requests receive no account attribution;
- a trusted account denied by `require_active_user`/`require_admin` on an
  allowlisted route records `denied`;
- non-allowlisted endpoints never emit attribution;
- every exact allowlisted method/template emits one event;
- a method mismatch does not match the route registry;
- ordinary gameplay, metrics, analytics, health, and polling routes remain
  excluded;
- recovery/email-verification routes attribute only after their one-time token
  resolves a trusted account;
- no target/resource/request value is copied into an event;
- success, confirmed failure, denial, and ambiguous outcome mappings are
  exact;
- attribution persistence failure leaves ordinary request/authentication
  behavior correct;
- security-critical mutation tests prove the documented fail-open boundary;
- at most one immediate transient retry uses identical IDs/payload;
- logger and monitoring failure cannot crash the request; and
- bounded warnings contain none of the sensitive sentinel values.

### Q.3 PostgreSQL tests

- service role can execute ingestion and cleanup RPCs;
- service role cannot directly read, insert, update, or delete either table;
- `PUBLIC`, `anon`, and `authenticated` cannot execute ingestion, cleanup,
  query, grouping, or resolution functions;
- investigator capability can execute only bounded query/group functions and
  has no direct table access;
- resolver and ordinary investigator privileges remain separate;
- exact replay inserts no duplicate; conflicting replay fails and rolls back;
- malformed pseudonym, epoch, environment, route/category, outcome/failure,
  and request IDs fail;
- no schema column can hold PII, credentials, raw request data, target IDs,
  JSON, arrays, or free-form metadata;
- table/function owner, table and column ACLs, function ACLs, volatility,
  `SECURITY DEFINER`, fixed search path, RLS, FORCE RLS, policies, constraints,
  and indexes are exact;
- expired rows are deleted, exact-cutoff/newer rows remain, oldest rows are
  first, limits hold, zero returns zero, and repeated cleanup reaches zero;
- failed cleanup/persistence batches roll back completely;
- access audit is appended for query/group/resolve/export and contains no
  evidence-row identifiers;
- an investigator query fails when access auditing cannot commit;
- migration reapplication is safe and repairs allowed ACL drift;
- a deliberately late migration failure rolls back every change;
- fresh `schema.sql` and sequential migrations are equivalent;
- authentication audit behavior and retention do not regress; and
- CI executes every PostgreSQL module with zero skips and treats skipped tests
  as failure.

### Q.4 Resolver and privacy tests

- default query groups within an epoch without raw identity;
- approved cross-epoch resolution produces one case-local label;
- resolution without a valid investigation UUID, approver set, key scope, or
  named principal fails;
- service role cannot read or use historical resolver keys;
- key-store, database, and access-audit evidence agree on each resolution;
- deleted accounts and destroyed keys are intentionally unresolvable;
- resolver output contains no email, username, phone, display name, or
  profile fields;
- database-only compromise fixtures cannot resolve pseudonyms;
- key-plus-candidate fixtures demonstrate the documented dictionary-attack
  risk;
- general `api_request_metrics`, `analytics_events`, `share_events`, admin
  monitoring responses, and schemas gain no account/pseudonym field; and
- retention removes expired events/access records and key destruction follows
  the latest retained row for the epoch.

## R. Open decisions

These require explicit owner/security/privacy approval before implementation:

1. **Architecture:** approve Option D and reject broad request-metric identity
   plus a persistent mapping table.
2. **Allowlist:** approve every route in section H, especially the limited
   private reads and the decision to exclude ordinary gameplay reads/writes.
3. **Key custody:** name the owner and managed secret system that can generate,
   version, audit, restrict, and destroy independent environment/month keys.
4. **Resolver:** decide whether approved cases may recover a raw internal UUID
   or only case-local cross-epoch groups.
5. **Investigator identity:** select the named principal/MFA/role-assumption
   mechanism and independent provider database audit source.
6. **Two-person approval:** name the two roles that authorize historical-key
   use and identity resolution.
7. **Retention/privacy basis:** approve 180 days for request-attribution and
   investigator-access evidence, with no legal hold in initial scope.
8. **Account deletion:** approve retaining non-resolvable pseudonymous
   security evidence until normal expiry and accepting that deletion prevents
   later identity resolution.
9. **Failure boundary:** approve fail-open attribution for user/admin requests
   and fail-closed access auditing for investigators.
10. **Capacity:** measure aggregate allowlisted route volume and approve the
    50,000-row daily default or provide evidence for a separately reviewed
    bound.
11. **Environment inventory:** confirm the currently active dev/staging/
    production separation and exact closed labels before keys are provisioned;
    older repository environment documents conflict with the now-verified
    hosted isolated-dev evidence from PR #1037.

Until these are resolved, the design is reviewable but implementation is not
authorized.

## S. Acceptance-criteria mapping

| Issue/user criterion | Design answer |
| --- | --- |
| Group security-relevant authenticated requests by originating account for a window | Direct grouping by monthly pseudonym; audited resolver supplies case-local cross-epoch groups. |
| Preserve privacy rationale | Sections C, D, E, and G explicitly analyze linkability, compromise, retention, and alternatives. |
| No personal data in general metrics | General request metrics and anonymous analytics remain unchanged and have explicit schema regression tests. |
| No permanent cross-environment identifier | Independent environment keys plus environment-bound HMAC input. |
| Exact endpoint scope | Section H is a positive method/template allowlist with explicit exclusions and no wildcard fallback. |
| Reads/admin/failed authorization addressed | Only narrowly private and privileged reads are included; admin reads/mutations are exact; denied requests are attributed only after trusted identity exists. |
| Standard identifier construction | HMAC-SHA-256, independent 256-bit epoch keys, canonical input, full 256-bit Base64url output. |
| Linkability/rotation/key custody analyzed | Monthly grouping, independent keys, 24-hour app grace, 180-day resolver lifecycle, compromise handling, and named approval gates. |
| Minimal future data model | Closed scalar columns only; no raw identity, target, request data, JSON, or free-form metadata. |
| Exact access control | Trusted owner, execute-only application path, no service read, no client access, RLS/no policy, bounded investigator RPCs, separate resolver. |
| Retention interaction with item 4 | Same 180-day cutoff semantics, bounded batches/default capacity, daily scheduler platform, job evidence, and failure retry. |
| Failure and retry model | User requests fail open; investigation access fails closed; outcomes include ambiguous; immutable IDs make bounded retry idempotent. |
| Investigation workflow | Section N gives a case-bound, least-disclosure workflow including cross-month resolution and evidence auditing. |
| Rollout/rollback | Sections O and P stage documentation, schema, crypto, instrumentation, access, dev/shadow, retention, production, and safe disablement. |
| Complete future tests | Section Q covers crypto, allowlist, application failures, exact PostgreSQL security, retention, resolution, privacy, parity, and zero skips. |
| Documentation-only item 3 | This branch adds only this document and performs no runtime, schema, configuration, workflow, environment, or deployment change. |

## T. Implementation task decomposition

Do not combine these into one implementation PR.

1. **Schema, ACL, retention, and verification**
   - Add both proposed tables, exact constraints/indexes, append-only ingestion,
     bounded query/access-audit and cleanup RPCs.
   - Add `schema.sql` parity, preflight, post-verification, reapplication,
     rollback, fresh-vs-sequential, exact ACL/RLS/function/index, and zero-skip
     PostgreSQL tests.
   - Integrate the new fixed 180-day cleanup target with the existing scheduler
     and `JobRunRecorder` pattern.
2. **Pseudonym derivation library**
   - Add canonical HMAC-SHA-256 construction, public test vectors, closed
     environment/epoch/key-version configuration, rollover behavior, and
     sensitive-sentinel unit tests.
   - Keep secret provisioning outside source control and blocked until the
     key custodian is approved.
3. **Minimal security-event instrumentation**
   - First PR: account security routes plus admin ban/unban/suspend/unsuspend.
   - Prove fail-open behavior, exact outcomes/idempotency, no middleware metric
     identity, and no sensitive diagnostics.
   - A later small PR may add the remaining approved private/admin routes after
     dev volume and completeness evidence.
4. **Investigator query/runbook and access audit**
   - Add bounded operator tooling, named-role setup documentation,
     case-local grouping, separately approved resolution, access-audit
     reconciliation, and least-disclosure export guidance.
   - Do not add an HTTP admin endpoint or dashboard.
5. **Hosted isolated-dev verification**
   - Apply database-first to synthetic dev, verify ACLs, ingestion, grouping,
     key/environment rotation, failure behavior, capacity, and retention.
   - Preserve only bounded catalog/count evidence.
6. **Production rollout documentation**
   - Record the approved key/access owners, exact deployment order, shadow
     gates, rollback, cleanup schedule, post-rollout audit, and unresolved
     blockers.
   - Production execution remains a separate explicitly authorized task.
