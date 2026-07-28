# Issue #1031 authentication observability execution plan

**Issue:** [#1031 — observability: close authentication audit-log and request-correlation gaps](https://github.com/sandrusipredicts/yesh_mishak/issues/1031)

**Source audit:** `docs/evidence/dev-backend-performance-2026-07-26/exposure-window-audit-2026-07-26.md`

**Branch:** `codex/issue-1031-last-login-observability`

**Implementation scope on this branch:** Item 1 only

## 1. Objective

Make every supported successful login attempt persist `users.last_login` through
an authorization path that is consistent across configured environments. A
failure of this secondary write must remain non-fatal to authentication, but it
must produce a structured, safely redacted warning in application logs and the
canonical Sentry monitoring path.

This document also expands Items 2–4 into dependency-aware follow-up work. It
does not authorize or implement those items.

## 2. Evidence classification

### 2.1 Facts verified from code or runtime evidence

1. `_update_last_login` has exactly one definition:
   `backend/app/api/auth.py::_update_last_login`.
2. It has exactly two call sites:
   - successful `POST /auth/login` password authentication;
   - successful `POST /auth/google` provider authentication.
3. The Google endpoint covers:
   - an existing Google identity;
   - a legacy Google subject that is resolved/backfilled;
   - a newly created Google user;
   - a previously explicitly linked account logging in through Google.
   These variants converge before the single `_update_last_login` call.
4. A linked account logging in with its password uses the ordinary
   `POST /auth/login` call site. Account linking itself is an authenticated
   account mutation, not a login, and does not call `_update_last_login`.
5. Registration writes `last_login` as part of the initial user insert, but
   registration returns `RegistrationResponse` without a session. It does not
   call `_update_last_login`.
6. Email verification, resend verification, password-reset request/confirm,
   token validation, logout, and account-linking mutations do not represent a
   new successful login and do not call `_update_last_login`.
7. There is no refresh-token endpoint or alternate session-refresh path in the
   backend. Application JWTs are issued by the password and Google login
   endpoints (and refreshed only as part of account-method mutations, which
   preserve an already authenticated session).
8. Before this change, `_update_last_login` uses
   `get_supabase_client()`, which is configured with `SUPABASE_KEY` (the
   standard/anonymous key). It does not use
   `get_supabase_service_role_client()`.
9. Google identity resolution already uses the service-role client. Logout,
   account linking, account deletion, password reset, and other trusted user
   mutations establish an existing repository pattern for service-role writes.
10. The current update discards the PostgREST response. The installed pinned
    PostgREST client defaults updates to `returning=representation`, raises
    `APIError` for HTTP error responses, and can return a successful response
    whose `data` list contains no affected rows.
11. Consequently, a zero-row update is currently logged as
    `auth.last_login.success`. Only raised exceptions reach
    `auth.last_login.failure`.
12. The source audit directly verified that the synthetic dev account's stored
    `last_login` predated multiple known logins. Historical Railway logs could
    not be used to distinguish an exception from a zero-row response because
    the relevant window had rolled out of retention.
13. `last_login` is nullable `timestamptz`/`timestamp with time zone`, has no
    column default, and is indexed by `idx_users_last_login`.
14. `backend/migrations/manual_auth.sql` introduced the nullable
    `last_login timestamptz` column. `backend/migrations/issue_079_missing_indexes.sql`
    added the monitoring index. No later tracked migration changes the column
    type or adds a trigger/default.
15. `backend/schema.sql` explicitly grants `SELECT, UPDATE` on `public.users`
    to `service_role`.
16. The locally available production public-schema snapshot (inspected only;
    it is an untracked operator artifact and is not part of this branch) shows:
    - `last_login timestamp with time zone`;
    - the `idx_users_last_login` index;
    - `UPDATE` granted on `users` to `anon`;
    - all privileges granted on `users` to `service_role`;
    - no `ENABLE ROW LEVEL SECURITY` statement for `users`.
17. The tracked technical-debt inventory likewise records that RLS is not
    enabled on `users` and that most access control is presently enforced in
    the API layer. Therefore RLS or a categorically unauthorized standard
    client is not a repository-wide verified root cause.
18. All configured backend environment templates require or document
    `SUPABASE_SERVICE_ROLE_KEY`. The local `backend/.env` contains that variable
    name, but the source audit identifies its database target as production,
    which is out of bounds for local mutation testing.
19. The project's staging-equivalent environment is the isolated `dev`
    Vercel/Railway/Supabase environment documented in
    `docs/qa/staging-smoke-tests.md`. Its authenticated Tier B test account was
    not configured in the last committed staging-smoke closure record, although
    a separate synthetic performance account was later used by the E12-10 run.
20. No dedicated conventional staging environment is documented separately
    from this `dev` staging-equivalent environment.
21. Railway receives normal Python/Uvicorn application logs. Structured auth
    records use `logging` with `extra` fields. The canonical durable alerting
    integration is `backend/app/monitoring.py`; its
    `capture_unexpected_message` function emits a Sentry message with safe tags,
    and its `before_send` hook removes request bodies, headers, credentials,
    tokens, cookies, query strings, and sensitive keyed values.
22. The repository already permits internal `users.id` in security/auth
    logging and Sentry's redaction policy retains only an internal user ID when
    user context exists. Email addresses, provider subjects, usernames,
    credentials, and token material are not required to diagnose this write.
23. Focused baseline tests before implementation passed:
    `25 passed` for `test_manual_auth.py` and `test_google_auth.py`.
24. Existing tests prove successful password/Google authentication and the
    non-fatal behavior of a raised Google `last_login` update error. They do not
    prove service-role use, affected-row verification, Sentry surfacing,
    sanitized warning fields, or password-login behavior when this update
    fails.

### 2.2 Verified root cause and bounded uncertainty

The verified systemic defect is the update's failure-detection and
authorization boundary:

- it uses a standard-key client whose write authority can vary with
  environment grants/policies instead of the repository's trusted
  service-role write path;
- it does not verify that the intended user row was returned as updated;
- it therefore treats a successful zero-row PostgREST response as success and
  never emits the failure warning.

This explains how `last_login` can remain stale while authentication succeeds
and the application records no failure.

The exact historical database reason that the audited dev update affected no
row is not recoverable from committed evidence: the relevant logs expired, and
the audit did not preserve a dev grants/policy snapshot from that moment. It
could have been environment drift, a transient database failure, a zero-row
policy result, or another service boundary failure. This branch does not label
that missing historical fact as RLS.

### 2.3 Hypotheses (not treated as facts)

- The audited dev database may have had grants or policies different from the
  captured production schema.
- A raised database exception may have occurred during the historical window,
  but the rolling log buffer can no longer prove or disprove it.
- A zero-row PostgREST response is the most direct code-level route to a
  falsely logged success, but no retained response from the historical request
  exists.

### 2.4 Decisions for Item 1

1. Use `get_supabase_service_role_client()` only for the `last_login` update.
   Keep user lookup and all other authentication behavior unchanged.
2. Continue using a single direct update; add neither a retry loop nor a
   background job.
3. Verify the returned representation includes the intended internal user ID
   and a timezone-aware `last_login`. Empty, mismatched, or malformed
   representations are failures.
4. Preserve login success after any update, configuration, response-validation,
   logging, or monitoring failure handled by `_update_last_login`.
5. Keep `auth.last_login.failure` as the structured log event. Add an explicit
   authentication flow, resolved deployment environment, safe internal user
   ID, sanitized error category, exception class, endpoint/method, result, and
   optional random attempt ID.
6. Send the same failure boundary to
   `capture_unexpected_message` with constant text and safe tags so it is
   visible in Sentry when monitoring is enabled. Never send the exception text
   or database response body.
7. Keep the existing success log, but correct its flow metadata (the current
   Google call incorrectly places a random attempt ID in `auth_method`).
8. Do not change database schema, grants, policies, RLS, request metrics, JWT
   behavior, or account-linking behavior.

### 2.5 Unresolved questions requiring operator evidence

1. Does the currently deployed dev database still differ from the captured
   production grants/RLS state for `users`?
2. Is `SUPABASE_SERVICE_ROLE_KEY` present and paired with the same Supabase
   project as `SUPABASE_URL` in every current Railway environment?
3. Has a dedicated synthetic production verification account been approved and
   provisioned?
4. What Railway log retention currently applies, and is the Sentry
   `auth.last_login.failure` event searchable after deployment?

These questions do not block the code fix; they are explicit rollout gates and
must not be answered by inference.

## 3. Current behavior

### Password login

1. Query `users` by username, then normalized email when applicable, through
   the standard client.
2. Verify the password and email-verification state.
3. Reset brute-force state.
4. Call `_update_last_login` through the standard client.
5. Ignore all exceptions after logging a warning.
6. Issue the application JWT and log `auth.login.success`.

### Google/provider login

1. Verify the provider ID token.
2. Resolve/create the provider identity and application user through the
   service-role client.
3. Call `_update_last_login` through the separate standard client.
4. Ignore all exceptions after logging a warning.
5. Issue the same application JWT and log `auth.login.success`.

### Silent-failure boundary

The existing `try/except` preserves authentication on raised exceptions, but
the update response is not inspected. A successful response containing zero
rows reaches the success log. The warning therefore does not cover all failed
persistence outcomes.

## 4. Affected authentication flows

| Flow | Calls helper | Expected Item 1 behavior |
|---|---:|---|
| Password login by username | Yes | Service-role update, verified row |
| Password login by email | Yes | Same password flow |
| Google login, existing identity | Yes | Service-role update, verified row |
| Google login, legacy linked subject | Yes | Same Google flow |
| Google login, new provider user | Yes | Same Google flow after creation |
| Explicitly linked account, later Google login | Yes | Same Google flow |
| Explicitly linked account, later password login | Yes | Same password flow |
| Registration | No; insert includes value | Preserve existing behavior |
| Email verification/resend | No | No change |
| Password reset | No login/session creation | No change |
| Token validation/session restoration | No | No change |
| Logout/token revocation | No | No change |
| Account-method mutation returning fresh token | No new login | No change |
| Refresh token | Not implemented | No change |

## 5. Exact files expected to change

1. `docs/issue-1031-authentication-observability-execution-plan.md`
2. `backend/app/api/auth.py`
3. `backend/tests/test_manual_auth.py`
4. `backend/tests/test_google_auth.py`
5. `backend/tests/test_account_linking.py`
6. `backend/tests/test_brute_force_protection.py`

No migration, schema, frontend, Android, iOS, request-metrics, analytics, or
deployment-configuration file is expected to change.

## 6. Database, grants, and RLS implications

- No database migration is required.
- No grant or RLS change is required or authorized on this branch.
- The service-role client is intentionally server-only and already required for
  trusted authentication/account-management operations.
- The update remains constrained by `eq("id", user_id)` and writes only
  `last_login`.
- The returned row is used only to verify the intended row and timestamp; no
  row contents are logged.
- A missing/mismatched service-role configuration degrades to the existing
  non-fatal login behavior and becomes observable.

## 7. Implementation approach

1. Change `_update_last_login` to accept a stable `auth_flow`
   (`password` or `google`) separately from an optional correlation
   `attempt_id`.
2. Resolve the environment through the same
   `resolve_environment(settings.sentry_environment)` path used by monitoring.
3. Generate the UTC ISO-8601 timestamp immediately before the update.
4. Execute the update with `get_supabase_service_role_client()`.
5. Require the response representation to contain:
   - the requested internal user ID;
   - a parseable timezone-aware `last_login`.
6. Treat an exception or invalid/empty representation as a failed side effect.
7. Emit a structured warning and a Sentry warning message with safe,
   allowlisted context.
8. Return normally so token issuance and the successful login response continue.
9. Update both call sites with stable flow metadata.

## 8. Warning and observability design

### Application warning

Event: `auth.last_login.failure`

Safe fields:

- `auth_flow`: `password` or `google`;
- `auth_method`: compatibility alias with the same stable value;
- `environment`: monitoring's resolved environment;
- `user_id`: internal UUID/string only;
- `endpoint`: `/auth/login` or `/auth/google`;
- `method`: `POST`;
- `result`: `partial_failure`;
- `error_code`: stable compatibility value `DATABASE_ERROR`;
- `error_category`: one of a small sanitized set such as
  `no_rows_updated`, `configuration_error`, `postgrest_api_error`, or
  `database_error`;
- `exception_type`: class name only;
- `attempt_id`: optional random server-generated correlation value.

### Sentry message

- Constant message: no exception text.
- Level: warning.
- Same safe diagnostic fields as tags.
- No `exc_info`, response body, headers, token, credential, email, username,
  provider payload, or database row is attached.
- Monitoring failure remains fail-safe because
  `capture_unexpected_message` catches its own errors.

## 9. Failure semantics

- Authentication success is authoritative once credential/provider validation
  has passed.
- `last_login` remains a best-effort side effect, but is no longer silent.
- Database exceptions, missing service-role configuration, no affected row,
  mismatched row identity, or malformed timestamp all:
  1. emit the warning;
  2. attempt Sentry surfacing;
  3. allow JWT issuance and the HTTP 200 login response to continue.
- No retry occurs.

## 10. Test strategy

### Focused regression tests

1. Password login updates `last_login` on the service-role fake and not the
   standard-client fake.
2. The update filter receives the exact authenticated internal user ID.
3. The returned timestamp is parseable, UTC/timezone-aware, and later than a
   known old value.
4. Google login updates the same field through the service-role fake.
5. A linked Google identity and a password login both continue to resolve to
   the same user and update the field.
6. A raised database error emits a LogRecord with
   `auth.last_login.failure` and safe structured fields.
7. The same failure invokes the canonical monitoring helper with constant
   message text and safe tags.
8. A database error containing credential/token sentinel text in its exception
   message does not place that text in logs or monitoring arguments.
9. Login still returns HTTP 200 and a valid token after the side-effect failure.
10. An empty update response is classified as failure rather than success.
11. Two normal rapid sequential logins produce timezone-aware timestamps that
    do not move backwards.

### Regression suites

- `test_manual_auth.py`
- `test_google_auth.py`
- `test_account_linking.py`
- `test_email_verification.py`
- `test_jwt_lifecycle.py`
- `test_brute_force_protection.py`
- `test_monitoring.py`
- complete backend CI command with the repository's 89% coverage threshold

### Tooling checks

- `git diff --check`
- Python bytecode compilation for changed Python files
- full backend pytest/coverage command
- existing credential-hygiene tests
- review tracked diff for secret-like material

No standalone linter, formatter, or static type checker is configured in the
repository; none will be claimed as run.

## 11. Timestamp ordering and edge cases

1. `_now_iso()` uses `datetime.now(timezone.utc)`, so emitted values are
   timezone-aware UTC.
2. Normal sequential logins generate the timestamp immediately before each
   update and should be nondecreasing; regression tests cover this behavior.
3. The schema has no monotonic trigger or atomic `greatest(last_login, now())`
   function. Truly concurrent requests could commit out of order, causing the
   earlier generated timestamp to win last. This risk is bounded to concurrent
   login timing and is not evidence for the observed multi-login stale value.
4. Adding a database function/trigger solely for strict monotonicity would
   expand this small reliability fix into a migration. This branch will not do
   so without runtime evidence that concurrent inversion is material.
5. A system clock adjustment could likewise affect client-generated ordering.
   Railway hosts are expected to maintain synchronized clocks, but strict
   database-time monotonicity remains a possible follow-up if required.
6. A user deleted between credential verification and the side-effect update
   yields no row, emits the warning, and still preserves the already successful
   login response under the required contract.
7. Missing `SUPABASE_SERVICE_ROLE_KEY` is observable and non-fatal.
8. Provider-created users with null username/phone follow the same update path;
   those nullable profile fields are not part of the update condition.

## 12. Environment-verification strategy

Use a dedicated synthetic account in each environment. Never use a real user's
credentials or print tokens/row contents.

### Common verification procedure

1. Record `window_start` in UTC.
2. Through an authorized administrative query, select only `id` and
   `last_login` for the synthetic account and record the current timestamp.
3. Perform one successful public login. Keep credentials and the returned
   token out of shell history, stdout, screenshots, and committed files.
4. Record `window_end` in UTC.
5. Through the authorized administrative path, re-query only `id` and
   `last_login`.
6. Confirm:
   - the internal ID is unchanged;
   - `last_login` is greater than its previous value;
   - `last_login` falls within `[window_start, window_end]`, allowing a small
     documented clock-skew tolerance.
7. In a controlled local/dev deployment only, temporarily make the
   service-role update unavailable (for example, inject the tested fake failure
   or deploy with an intentionally invalid non-production service key).
8. Confirm login still returns 200.
9. Confirm Railway contains `auth.last_login.failure` with safe fields and
   Sentry contains the corresponding warning event/tag set.
10. Restore configuration immediately and repeat the success check.

### Local

- Unit/integration fakes directly verify standard-versus-service client use,
  affected row, timestamp, and failure behavior without contacting a live
  database.
- The current local backend configuration points at a production-scoped
  project per the source audit, so no live mutation will be performed from this
  checkout.
- If a genuinely isolated local Supabase instance is provisioned later, run the
  common procedure against a synthetic local user.

### Dev (staging-equivalent)

- Use the isolated `yesh_mishak_dev` project and its synthetic performance/test
  identity.
- Verify the Railway service has a project-matched service-role key before
  login.
- Run the common success and controlled-failure procedure.
- This is the required first deployed verification environment.

### Staging

- There is no separately verified conventional staging environment beyond
  `dev`; record this as `not separately configured`, not as passed.
- If a separate staging service now exists outside committed documentation,
  prove its isolation and synthetic account before applying the common
  procedure.

### Production

- Do not mutate an arbitrary or real user.
- Run only after an owner approves/provisions a dedicated synthetic production
  verification account.
- Do not intentionally break the shared production service-role key. Failure
  behavior is established in tests and dev; production verification is the
  safe success procedure plus observation that no failure warning appears.

## 13. Security and privacy considerations

- Service-role use stays entirely in the backend.
- The update is scoped to one internal ID and one timestamp column.
- No user identifier is added to request metrics or anonymous analytics.
- Internal user ID remains limited to existing auth/security warning policy.
- No email, username, phone, provider subject, IP, user agent, body, header,
  password, password hash, authorization value, access/refresh token, session
  material, or database error text is logged or sent to monitoring.
- The implementation does not make an authenticated-request attribution
  architecture decision.
- The service-role key itself is never read into output, logged, or committed.

## 14. Rollout and rollback

### Rollout

1. Land Item 1 tests and code together.
2. Deploy to dev/staging-equivalent.
3. Verify successful advancement and controlled failure observability.
4. Observe `auth.last_login.failure` volume through at least one normal login
   cycle.
5. Deploy to production.
6. Perform the approved synthetic success verification.
7. Watch Railway/Sentry for configuration or no-row failures.

### Rollback

- Revert the Item 1 commit and redeploy.
- No database rollback is required because there is no migration.
- Existing timestamps remain valid; rollback only restores the prior
  standard-client/unverified behavior.
- Authentication remains available throughout because the side effect is
  non-fatal before and after rollback.

## 15. Item 1 acceptance criteria

1. Password and Google/linked-provider successful login paths call the same
   reliable helper contract.
2. The helper uses the service-role client.
3. The intended updated row and timezone-aware timestamp are verified.
4. Empty/mismatched responses are not logged as success.
5. Any failure emits `auth.last_login.failure` with safe structured fields.
6. The failure is sent through the canonical monitoring helper.
7. No sensitive material appears in the warning or monitoring call.
8. Login still succeeds after the side-effect failure.
9. Focused auth/account-linking/monitoring tests and the canonical backend CI
   command pass.
10. Environment instructions distinguish direct evidence from operator work.
11. No Items 2–4 schema, telemetry, privacy, or retention implementation is
    present.

## 16. Explicit non-goals for this branch

- Durable authentication event table or external log sink.
- Authentication-event retention enforcement.
- Request-to-account mapping or pseudonyms.
- User identifiers in request metrics or product analytics.
- RLS/grant redesign for `users`.
- Authentication refactor, retry queue, or background job.
- Refresh-token design.
- Changes to Android, iOS, frontend, JWT claims/expiry/revocation, logout,
  registration, email verification, password reset, account linking, or
  monitoring redaction.
- Automatic deployment, pull-request merge, or production mutation.

## 17. Follow-up issue decomposition (Items 2–4)

### Follow-up 2: durable authentication audit events

**Dependency:** Item 1 may land first; no dependency on Item 3.

**Scope**

- Persist login success, login failure, logout, and token revocation.
- Define a minimal event schema:
  - event ID;
  - occurred-at UTC timestamp;
  - event type and outcome;
  - internal user reference when authentication has resolved it;
  - server-generated attempt/correlation ID;
  - auth method;
  - sanitized error category;
  - source environment;
  - optional bounded security-relevant endpoint category.
- Explicitly exclude tokens, credentials, provider payloads, raw request
  bodies/headers, password data, and free-form error text.
- Choose dedicated Postgres table versus managed external security-log sink
  based on operational ownership and query needs.
- Define access control: service-role write; narrowly authorized incident/admin
  read; no client-direct reads.
- Add indexes for time-window/event-type/user-reference investigations.
- Establish a growth model, partitioning/archival decision, maximum event rate,
  and cleanup path.
- Add idempotency/deduplication rules for retries or multi-worker emission.
- Migrate without backfilling unverifiable historical events.
- Verify queryability after Railway's rolling buffer has expired.

**Acceptance**

- A chosen historical window can be queried after platform logs roll over.
- Required events are complete and redacted.
- Access control and growth bounds are tested.
- Cleanup/retention hooks exist, but final cross-store retention policy waits
  for Follow-up 4.

### Follow-up 3A: privacy-preserving request attribution design decision

**Dependencies:** Follow-up 2 schema/identifiers should be known first. This is
a design/approval issue and must precede implementation.

Do not choose an option without explicit approval. Compare:

| Option | Investigation usefulness | Privacy / leakage | Reversibility and deletion | Key/salt/mapping operations | Complexity |
|---|---|---|---|---|---|
| Controlled correlation-ID mapping | High for selected windows; direct resolution behind separate access control | Mapping store becomes sensitive; general telemetry stays pseudonymous | Mapping can expire/delete independently; telemetry becomes unresolvable | Protect mapping access, audit lookups, define TTL and break-glass process | High |
| Salted rotating account pseudonyms | Good grouping inside a rotation period; weak across rotations | Stable-within-window pseudonym can still enable behavioral profiling | Deletion is difficult if records cannot be located after salt rotation; reversibility depends on design | Secret salt storage, versioning, rotation schedule, overlap policy, compromise response | Medium/high |
| Selected security-endpoint attribution only | High for explicitly instrumented auth/security actions; no coverage elsewhere | Lowest data expansion; endpoint list can drift or miss incidents | Easier deletion and bounded records | No global mapping if direct protected audit store is used; strict access controls still required | Medium |

The decision record must evaluate:

- exact incident questions each option can answer;
- identity-leakage and linkage risk;
- whether and by whom attribution can be reversed;
- mapping/key/salt storage and rotation;
- access logging for mapping resolution;
- deletion/data-subject implications;
- failure and compromise modes;
- operational burden and cost;
- endpoint coverage governance;
- prohibition on direct user identifiers in general-purpose request metrics.

### Follow-up 3B: implement the approved attribution design

**Dependencies:** approved Follow-up 3A decision and the relevant Follow-up 2
identifiers/store.

- Implement only the approved option.
- Add schema/config/telemetry changes with redaction and access-control tests.
- Add investigation runbooks and deletion/rotation procedures.
- Prove ordinary request metrics and anonymous product analytics retain their
  current privacy envelope.

### Follow-up 4: security-log retention enforcement and verification

**Dependencies:** Follow-up 2 and Follow-up 3B stores and data flows must be
known. The policy cannot be finalized against hypothetical stores.

**Scope**

- Define investigation-driven retention periods per store/data class.
- Document legal/privacy/product-owner approval and deletion requirements.
- Implement technical enforcement:
  - database cleanup job/partition expiry;
  - external sink lifecycle rule;
  - correlation mapping expiry;
  - salt/key retirement where applicable.
- Add measurable verification:
  - oldest/newest retained event query;
  - cleanup job success/failure monitoring;
  - bounded growth/partition size alerts;
  - restore/backup retention compatibility;
  - periodic access-control and deletion tests.
- Define emergency legal hold separately and narrowly.

**Acceptance**

- Retention is enforced by code/platform configuration, not documentation
  alone.
- A scheduled verification demonstrates that data older than the limit is
  removed and data within the limit remains queryable.
- All resulting auth and attribution stores are covered.

## 18. Recommended dependency order

1. Item 1 — reliable and observable `last_login` (this branch).
2. Item 2 — durable authentication audit events.
3. Item 3A — approved privacy-preserving attribution decision.
4. Item 3B — attribution implementation.
5. Item 4 — retention enforcement and measurable verification across all
   resulting stores.
