# Issue #917 — E12-13 admin panel QA pass

## Scope and evidence boundary

This document is the execution record for the current admin panel on the `dev`
line. It covers the shipped frontend tabs, their backend APIs, authorization,
moderation side effects, monitoring privacy, automated regression coverage, and
an isolated-development operator runbook.

No production access, deployment, Railway change, database migration, RLS/ACL
change, or investigator-capability change is part of this work. Draft PR #1043
is not modified. All committed identities and IDs are synthetic test values.

### Verified facts

- The admin UI is available only at `/admin` and renders seven sections: Stats,
  Monitoring, Engagement, Fields, Games, Users, and Field Reports.
- `AdminRoute` checks `/admin/me`; it does not trust the role held in local
  storage. Every backend admin endpoint independently depends on
  `require_admin`, which depends on a fresh active-account lookup.
- Missing authentication returns 401. A non-admin, banned admin, or suspended
  admin is rejected before admin data access.
- The schema has no separate `inactive` user status: its closed status set is
  `active`, `banned`, and `suspended`. A principal whose user row is absent is
  rejected as invalid authentication; banned and suspended are the supported
  inactive/restricted states.
- The ordinary stored role is `user`; moderation targets with role `admin`
  cannot be moderated, so self-moderation is also rejected.
- The configured public client uses `SUPABASE_KEY` (the anon credential). It
  does not attach the authenticated application user's JWT and therefore cannot
  carry application admin authority through database RLS.
- Before this QA pass, `/admin/users`, user moderation, field deletion, field
  report writes, and content-report operations already used the trusted
  service-role client, while several other shipped admin reads and mutations
  still used the anon client.
- The repository fresh schema enables RLS on dedicated security/operations
  tables, but does not declare RLS for `users`, `fields`, `games`, or
  `field_reports`. Hosted policy parity is not proven by repository text alone.
- The monitoring response and UI expose aggregate counts, bounded operational
  status, and anonymous engagement data. The UI does not render arbitrary extra
  response fields.
- Security attribution added by PR #1044 covers the authenticated admin actor
  for ban, unban, suspend, unsuspend, and field deletion. It does not accept the
  target ID or moderation body as attribution evidence.

### Decision

All shipped admin-only database operations must use the existing trusted
server-side service-role client after `require_admin` succeeds. This is a
narrow boundary correction, not a new authorization system: clients still
receive no database credential, RLS and grants remain unchanged, and ordinary
public routes keep their existing client behavior.

### Bounded uncertainty

- Hosted-dev database policies and grants require operator verification; they
  were not queried during repository-only work.
- Hosted end-to-end verification requires a dedicated synthetic active admin,
  a synthetic ordinary login identity, and an isolated dev deployment. No such
  credentials were supplied to this task.
- Railway/Supabase runtime logs and durable rows were not inspected, so hosted
  success and cleanup are not claimed below.

## E05 dependency status

| Issue | Capability | Repository state |
| --- | --- | --- |
| #859 / E05-01 | API error-rate metric | Closed; backend metric and UI card present |
| #860 / E05-02 | Response-time metric | Closed; backend RPC wrapper and UI cards present |
| #861 / E05-03 | Scheduled-job history | Closed; bounded history and table present |
| #862 / E05-04 | Push-delivery metric | Closed; provider-acceptance semantics present |
| #863 / E05-05 | Monitoring dashboard UI | Closed; loading/error/partial/refresh/responsive states present |
| #864 / E05-06 | Field-report resolve action | Closed; endpoint, modal, notifications, and regression tests present |

The E05 implementation dependencies are present. The remaining E05 gap is
hosted manual verification, not missing source code.

## Current capability inventory

All rows require an authenticated, active `admin` at the backend boundary.

| Visible capability | Frontend | API | Success | Bounded failure | Audit/attribution |
| --- | --- | --- | --- | --- | --- |
| Admin gate | `AdminRoute` | `GET /admin/me` | Renders panel | 401 clears session; 403 redirects; other error offers retry | Authentication logs only |
| Stats | `AdminStats` | `GET /admin/stats` | Six backend counts; four rendered cards | Generic error and retry | No dedicated read audit |
| Monitoring | `AdminMonitoring` | `GET /admin/monitoring` | Aggregate health, users, games, notifications, API, latency, push, jobs | Initial bounded error/retry; background error retains prior data | Excluded from request-metric recursion; no dedicated read audit |
| Engagement | `AdminEngagement` | `GET /admin/engagement?window_days=7|30|90` | Anonymous activity/sharing totals, bars, tables | Partial sources remain visible; bounded error/retry | Excluded from request-metric recursion; no dedicated read audit |
| Pending fields | `AdminFields` | `GET /admin/fields/pending` | Pending queue | Generic error and retry | No dedicated read audit |
| All fields | `AdminFields` | `GET /admin/fields` | Non-removed fields across approval/status states | Generic error and retry | No dedicated read audit |
| Approve/reject field | `AdminFields` | `POST /admin/fields/{id}/approve|reject` | Persists approval/verified state; removes pending row | Bounded UI error; row remains | Structured decision log with authenticated actor; review state on row |
| Change field status | `AdminFields` | `PATCH /admin/fields/{id}/status` | Persists open/closed/renovation | Bounded UI error; prior select value remains | No dedicated durable audit |
| Edit field | `EditFieldModal` | `PATCH /admin/fields/{id}` | Persists bounded editable fields | Validation/conflict/generic errors retain form | Structured success log with authenticated actor |
| Remove field | `AdminFields` | `DELETE /admin/fields/{id}` | Atomic soft removal metadata | 404 missing; 409 already removed; other bounded error | PR #1044 actor attribution plus removal metadata |
| Games list | `AdminGames` | `GET /admin/games` | Active/recently-finished groups | Generic error and retry | No dedicated read audit |
| Extend game | `AdminGames` | `POST /admin/games/{id}/extend` | Adds one hour and refreshes | Generic bounded action error | Notification side effect; application log |
| Close game | `AdminGames` | `POST /admin/games/{id}/close` | Finishes game and refreshes | Confirmation plus bounded action error | Notification side effect; structured application log |
| Users list/search | `AdminUsers` | `GET /admin/users` | Loads statuses; local text search covers ID, username, name, email, phone, status | Empty/no-match/error states | No dedicated read audit |
| Ban/unban/suspend/unsuspend | `AdminUsers` | `POST /admin/users/{id}/{action}` | Valid transition persists and list reloads | Missing reason, invalid transition, admin target, missing target, and DB failures are bounded | `user_moderation_audit` plus PR #1044 actor attribution |
| Field reports queue/filter | `AdminFieldReports` | `GET /admin/field-reports` | Newest-first queue; local status filter | Empty/no-match/error states | No dedicated read audit |
| Manage report | `AdminFieldReports` | `PATCH /admin/field-reports/{id}/status` | Persists status, note, reviewer, timestamp | Validation/not-found/generic error; no optimistic row change | Review metadata and reporter notification |
| Resolve report | `AdminFieldReports` | `PATCH /admin/field-reports/{id}/resolve` | Resolves open/in-review report | 404 missing; 409 terminal; bounded DB error | Review metadata and reporter notification |

Backend-only admin capabilities not exposed by the current panel are field
duplicate candidates, game cancellation, scheduled reminder execution,
notification cleanup, and content-report listing/review. They are recorded as
existing APIs, not silently treated as shipped UI functionality.

## Test matrix and repository results

| Area | Automated evidence | Result |
| --- | --- | --- |
| Anonymous/ordinary/restricted/admin authorization | Backend endpoint matrix plus Playwright gate tests | Pass |
| Direct API authorization | Backend 401/403 matrix and existing direct-request Playwright checks | Pass |
| Trusted database boundary | Admin endpoint matrix fails if the anon client is invoked | Pass |
| User search and four reversible transitions | Stateful Playwright flow plus backend state/audit tests | Pass |
| Invalid/self/missing user moderation | Backend transition, admin-target, reason, missing-user tests | Pass |
| Admin actor vs target | Domain-audit and security-attribution tests | Pass |
| Field approve/reject/status/edit/delete | Stateful Playwright flows and focused backend tests | Pass |
| Removed/missing/repeated field delete | Existing backend and Playwright 404/409/metadata tests | Pass |
| Report queue/filter/manage/resolve | Stateful Playwright and backend integration tests | Pass |
| Game list/extend/close | Stateful Playwright persisted-refresh test | Pass |
| Monitoring success/zero/partial/loading/error | Existing monitoring Playwright suite | Pass |
| Monitoring stale-data refresh | Background refresh failure retains last successful snapshot | Pass |
| Monitoring privacy | Injected identity/token/header/body/SQL fields are absent from DOM and console | Pass |
| UTC/responsive/bounded windows | Existing monitoring and engagement Playwright/backend tests | Pass |

### Automated evidence (2026-08-02)

- Focused backend admin/moderation/attribution/ACL suite: `300 passed`.
- Disposable PostgreSQL 16 ACL migration suite: `14 passed`. It verifies the
  exact ACL matrix, DML preservation, unchanged policy/RLS catalogs,
  idempotence, fresh-schema default-ACL repair, and runtime TRUNCATE denial.
- Focused admin/monitoring Playwright suite: `31 passed`.
- Full backend suite with coverage: `1709 passed, 166 skipped`; coverage
  `90.98%`, above the required `89%` gate. The skips are PostgreSQL integration
  cases that require external disposable test databases and are not hidden;
  the 14 new ACL cases were also run separately against disposable PostgreSQL.
- Full Playwright suite: `374 passed`. An initial six-worker run had one
  unrelated deep-link timing failure; that case passed alone (`1 passed`) and
  the complete four-worker rerun passed cleanly.
- Frontend Node unit/QA suite: `500 passed`.
- Python compilation, frontend lint, and production frontend build: pass. The
  build reports only the existing chunk-size/dynamic-import advisories.

Commands:

```text
cd backend
python -m pytest tests/test_core_table_acl_hardening.py tests/test_admin_me.py tests/test_admin_user_moderation.py tests/test_field_report_admin_integration.py tests/test_field_edit.py tests/test_field_delete.py tests/test_inactive_field_lifecycle.py tests/test_security_attribution_admin_mutation_routes.py tests/test_admin_engagement.py -q --tb=short
CORE_TABLE_ACL_DATABASE_URL=<disposable PostgreSQL 16 DSN> python -m pytest tests/test_core_table_acl_hardening_migration_postgres.py -q --tb=short
python -m pytest tests/ --cov=app --cov-fail-under=89 --cov-report=term --basetemp C:\Users\orel1\yesh_mishak\backend\.pytest-tmp-issue917-full-final
python -m compileall -q app

cd ../frontend
npx playwright test --reporter=line --workers=4
$qaTestFiles = @((Get-ChildItem -LiteralPath .\tests -Filter *.test.js).FullName) + @((Get-ChildItem -LiteralPath .\scripts -Filter *.test.mjs).FullName)
node --test $qaTestFiles
npm run lint
npm run build

cd ..
python backend/scripts/check_qa_identity_hygiene.py .
git diff --check
```

The exact commands are recorded in the Draft PR. Automated evidence uses
mocked/local boundaries and does not substitute for the hosted-dev operator
gate below.

## Defect found and narrow fix

### P1 — admin authority stopped at the application boundary

**Reproduction from code:** authorize any affected route through `require_admin`
and observe the route then creating `get_supabase_client()`, which is configured
with the anon key and no caller JWT. Under RLS that database session is not an
admin session, so an authorized application request can receive empty results
or fail to mutate rows.

**Root cause:** authorization and database execution used different trust
contexts. The backend proved the caller was an active admin, then discarded that
fact by querying as anon.

**Fix:** shipped admin stats/monitoring counts, field/report/game reads, field
moderation/edit/status operations, and game operations now use the existing
service-role client. The service key remains server-side. No frontend code,
schema, grant, policy, migration, or application response contract changed.

### Hosted follow-up — public-role non-row privileges

Hosted-dev catalog verification then found `TRUNCATE`, `TRIGGER`, and
`REFERENCES` granted to both `anon` and `authenticated` on `users`, `fields`,
`games`, `field_reports`, and `user_moderation_audit`. RLS does not govern
`TRUNCATE`; the other two are schema/trigger capabilities that no runtime route
needs.

No repository migration or fresh-schema statement granted these privileges.
The bounded root cause is therefore a repository hardening gap: provider or
historical hosted ACL defaults were allowed to persist because core-table ACLs
were never normalized after table creation. The exact historical external
granting action remains unknown without provider/default-ACL audit evidence.

`migrations/core_table_acl_hardening.sql` transactionally and idempotently
revokes only those three privileges from the two public roles. It deliberately
does not mention `SELECT`, `INSERT`, `UPDATE`, or `DELETE`, and it does not alter
RLS or any policy. Current public flows continue using ordinary PostgREST row
operations: fields and games use bounded row reads/mutations, field reports use
the intended policy-governed `SELECT`/`INSERT` path, and trusted auth/admin
operations use the server-side service-role client.

Post-migration hosted verification query:

```sql
select grantee, table_name, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee in ('anon', 'authenticated')
  and table_name in (
    'users',
    'fields',
    'games',
    'field_reports',
    'user_moderation_audit'
  )
order by grantee, table_name, privilege_type;
```

The result must contain no `TRUNCATE`, `TRIGGER`, or `REFERENCES` rows. Capture
the `pg_policies` and `relrowsecurity` catalog rows before and after applying the
migration and require exact equality for policy definitions/RLS state. Do not
export application rows.

## Findings not implemented in this QA branch

| Severity | Finding | Disposition |
| --- | --- | --- |
| P2 | Hosted RLS/ACL parity for core tables cannot be inferred from `schema.sql` | Mandatory isolated-dev catalog check before merge |
| P2 | User moderation writes status and `user_moderation_audit` in separate requests; an audit-write failure can follow a committed status write | Follow-up requiring transactional design; PR #1044 attribution remains intentionally fail-open |
| P2 | Field approve/reject/status/edit and field-report review do not all have a uniform durable domain audit | Follow-up audit-policy decision; do not expand Issue #917 |
| P2 | User/report screens intentionally render moderation PII (email/phone); screenshots/evidence must be cropped or redacted | Operational restriction; monitoring UI itself remains aggregate-only |
| P3 | User, field, game, and report lists have no server pagination | Follow-up scalability issue |
| P3 | Monitoring has manual refresh and last-refreshed time but no automatic stale-age threshold | Follow-up product decision |
| P3 | Backend content-report moderation is not exposed in the current admin UI | Record as missing UI capability; not added in this QA pass |

## Isolated hosted-dev fixtures

Use only after confirming the Supabase project identifier is the isolated
development project. The operator must stop if any deterministic ID already
exists. The target user has no password or provider identity and cannot log in;
it is only a moderation target. The authenticated admin and ordinary-user gate
test must use existing project-controlled synthetic identities.

```sql
begin;

do $$
begin
  if exists (
    select 1 from public.users
    where id = '91700000-0000-4000-8000-000000000001'::uuid
  ) or exists (
    select 1 from public.fields
    where id = '91700000-0000-4000-8000-000000000101'::uuid
  ) or exists (
    select 1 from public.field_reports
    where id = '91700000-0000-4000-8000-000000000201'::uuid
  ) then
    raise exception 'Issue 917 deterministic fixture already exists';
  end if;
end
$$;

insert into public.users (
  id, email, name, role, status, email_verified, email_verified_at
) values (
  '91700000-0000-4000-8000-000000000001'::uuid,
  'issue917-moderation-target@example.invalid',
  'ISSUE 917 QA MODERATION TARGET',
  'user',
  'active',
  true,
  now()
);

insert into public.fields (
  id, name, lat, lng, sport_type, surface_type, has_nets, has_water,
  city, status, approval_status, verified, added_by, notes
) values (
  '91700000-0000-4000-8000-000000000101'::uuid,
  'TEST ISSUE 917 ADMIN QA FIELD',
  31.5000000,
  34.7500000,
  'basketball',
  'asphalt',
  false,
  false,
  'Synthetic Dev City',
  'open',
  'pending',
  false,
  '91700000-0000-4000-8000-000000000001'::uuid,
  'Disposable isolated-development fixture'
);

insert into public.field_reports (
  id, field_id, user_id, category, description, status
) values (
  '91700000-0000-4000-8000-000000000201'::uuid,
  '91700000-0000-4000-8000-000000000101'::uuid,
  '91700000-0000-4000-8000-000000000001'::uuid,
  'wrong_information',
  'Synthetic isolated-development report',
  'open'
);

commit;
```

Fixture verification (do not export row contents):

```sql
select
  (select count(*) from public.users
    where id = '91700000-0000-4000-8000-000000000001'::uuid
      and role = 'user' and status = 'active') as target_users,
  (select count(*) from public.fields
    where id = '91700000-0000-4000-8000-000000000101'::uuid
      and approval_status = 'pending' and removed_at is null) as test_fields,
  (select count(*) from public.field_reports
    where id = '91700000-0000-4000-8000-000000000201'::uuid
      and status = 'open') as test_reports;
```

Expected result is `1, 1, 1`.

## Hosted-dev operator sequence

1. Confirm the frontend, Railway API, and Supabase project are all isolated dev;
   record non-secret deployment identifiers. Keep production consoles closed.
2. Confirm one project-controlled synthetic active admin and one
   project-controlled synthetic ordinary login identity exist. Stop if either
   identity is personal, shared with production, inactive, or unverified.
3. Capture the bounded ACL, `pg_policies`, and RLS catalog snapshots; apply
   `backend/migrations/core_table_acl_hardening.sql` through the normal isolated
   dev migration path. Re-run the query above and prove the three dangerous
   privileges are absent while policy definitions and RLS state are identical.
4. Apply the fixture SQL above in the isolated dev SQL editor and run the
   verification query.
5. Sign in as the ordinary synthetic identity and navigate directly to
   `/admin`. Confirm the frontend redirects and direct `GET /admin/me`,
   `/admin/users`, and `/admin/monitoring` requests return 403 with no data.
6. Sign in as the synthetic active admin. Confirm all seven tabs load. Confirm
   `/admin/users` includes the deterministic target and pending fields/reports
   include the deterministic fixtures.
7. Search by the deterministic target label. Ban with a synthetic reason,
   verify banned, verify an invalid repeat is bounded, then unban. Suspend,
   verify suspended, verify an invalid repeat is bounded, then unsuspend.
8. Attempt to moderate the signed-in admin. Confirm the admin-target guard
   rejects it and the admin remains active.
9. Approve the deterministic field; verify approved-state semantics
   (`approval_status=approved`, `verified=true`). Change it through closed,
   renovation, and open; reject and approve as needed to observe all shipped
   approval/status states. Verify each UI refresh matches an authorized SQL
   query.
10. Manage the deterministic report through in-review and resolve. Confirm a
   repeat resolve is bounded and a random nonexistent UUID returns not found.
11. Remove the deterministic field through the UI. Confirm removal metadata is
    present and it disappears from the normal field list. Repeat removal and
    confirm bounded conflict; test a random UUID and confirm bounded not-found.
12. Verify Stats, Monitoring, and Engagement success states. In browser DevTools,
    block only the isolated-dev `/admin/monitoring` request, reload the tab to
    verify the bounded initial error/retry state, unblock and retry, then block
    the same request only after one successful load and press Refresh. Confirm
    the prior snapshot remains visible with the bounded error banner.
13. Inspect browser console/network previews and sanitized screenshots. Confirm
    no password, token, Authorization header, request body, secret, raw security
    attribution pseudonym, or personal mailbox is captured.
14. In the authorized SQL editor, verify `user_moderation_audit` records the
    signed-in admin as actor and the deterministic row as target. Verify the
    five PR #1044 route categories exist for the admin actor without exporting
    pseudonyms or target data.
15. Confirm the only intended ACL change is removal of `TRUNCATE`, `TRIGGER`,
    and `REFERENCES` from `anon`/`authenticated` on the five named tables;
    ordinary DML and field-report policies remain unchanged. Confirm anon cannot
    perform admin-only operations and the service-role key is server-only.
16. Perform cleanup below, attach sanitized pass/fail evidence to the Draft PR,
    and record that production was untouched.

## Cleanup and retained evidence

Do not hard-delete the moderation target after user moderation: the current
`user_moderation_audit.target_user_id` foreign key uses `ON DELETE CASCADE`, so
deleting it would also delete the required domain audit rows. Leave the target
as active with cleared restriction fields and no authentication method until a
separately approved retention process permits removal.

```sql
update public.users
set status = 'active',
    restriction_reason = null,
    restricted_at = null,
    restricted_by = null
where id = '91700000-0000-4000-8000-000000000001'::uuid
  and role = 'user';

select status, restriction_reason, restricted_at, restricted_by
from public.users
where id = '91700000-0000-4000-8000-000000000001'::uuid;
```

The field should remain soft-deleted because removal metadata is part of the
verified behavior. The report may remain resolved. These deterministic,
non-authenticating rows are retained dev evidence, not active test data. A hard
cleanup may run only after the owner confirms its evidence is no longer subject
to retention; delete child rows first and re-check foreign-key effects before
deleting the user. Never delete authentication or security-attribution evidence
to make fixture cleanup appear complete.

## Rollback

- Code rollback: revert the QA commits or redeploy the preceding `dev` commit.
- ACL rollback is not an ordinary application rollback because it restores a
  verified security exposure. If isolated-dev evidence proves an approved flow
  unexpectedly requires one of these privileges, stop and review that flow.
  Re-grant only the exact demonstrated privilege after explicit security
  approval; do not broadly grant all privileges or alter RLS/policies.
- Runtime rollback: disable the branch deployment and restore the prior dev
  artifact. Do not change production.
- Fixture rollback before any moderation action: delete the report, then field,
  then target user by deterministic ID in one dev-only transaction.
- Fixture rollback after moderation: use the retained-evidence cleanup above;
  do not delete the target or its audit/security evidence.

## Completion gate

Repository automation can be complete while Issue #917 remains **not
merge-ready**. Merge requires attached isolated-hosted-dev evidence for every
operator step, confirmation that all P0/P1 defects are closed, and confirmation
that deterministic fixtures are either safely retained as evidence or cleaned
without deleting retained audit data.
