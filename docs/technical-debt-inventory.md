# Technical Debt Inventory

## Purpose

This file centralizes known technical debt, accepted gaps, incomplete hardening work, and follow-up engineering risks across the yesh_mishak project.

It serves as the single source of truth for debt items identified during audits (ISSUE-092, ISSUE-106, ISSUE-110), production readiness reviews (ISSUE-121, ISSUE-122), and codebase analysis.

## Inventory Policy

- This file documents debt; it does not fix debt.
- Each debt item must have evidence (code path, doc reference, or audit finding).
- P0/P1 items must not be ignored or downgraded because the inventory issue (ISSUE-123) is P2.
- When debt is fixed, update the item status to FIXED with the resolving issue/PR — do not silently delete the entry.
- When debt becomes irrelevant (e.g., feature removed), mark as OBSOLETE with explanation.
- New debt discovered in future issues should be added here with the discovering issue as the source.

## Severity Definitions

| Severity | Definition |
| :--- | :--- |
| P0 Critical | Production blocker / security takeover / data loss risk |
| P1 High | Serious reliability/security/operational risk before production scale |
| P2 Medium | Maintainability/scalability/testing risk |
| P3 Low | Cleanup/documentation/nice-to-have |

## Status Definitions

| Status | Definition |
| :--- | :--- |
| OPEN | Known, not addressed |
| PARTIAL | Partially addressed, remaining work documented |
| ACCEPTED GAP | Acknowledged risk, accepted for now with documented rationale |
| FIXED | Resolved — include resolving issue/PR |
| OBSOLETE | No longer relevant — include reason |
| NEEDS VERIFICATION | Believed fixed but not independently verified |

## Technical Debt Summary

| ID | Severity | Area | Title | Status | Source / Evidence | Recommended Follow-Up |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| TD-AUTH-001 | P0 Critical | Security | Google OAuth account-takeover via email-only linking | OPEN | ISSUE-092, ISSUE-110, ISSUE-122; backend/app/auth/google.py:186-193 | ISSUE-111 |
| TD-OPS-001 | P1 High | Monitoring | No error monitoring (Sentry or equivalent) | OPEN | ISSUE-121 MONITOR-001; codebase grep returns 0 results | Implement error monitoring |
| TD-OPS-002 | P1 High | Monitoring | No uptime monitoring or alerting | OPEN | ISSUE-121 MONITOR-002; no monitoring config found | Implement uptime monitoring |
| TD-OPS-003 | P1 High | Reliability | Staging environment not live | OPEN | ISSUE-114 STAGING-001; all 5 services unprovisioned | Provision staging services |
| TD-OPS-004 | P1 High | Reliability | Supabase backup settings not confirmed | OPEN | ISSUE-119 BACKUP-001; requires dashboard access | Verify in Supabase dashboard |
| TD-OPS-005 | P1 High | Reliability | Live database restore not validated | OPEN | ISSUE-120 RESTORE-001; tabletop only | Run live staging restore drill |
| TD-DB-001 | P2 Medium | Database | RLS not enabled on most tables | OPEN | backend/schema.sql; only user_moderation_audit and push_tokens have RLS | Enable RLS on remaining tables or document decision |
| TD-DB-002 | P2 Medium | Database | No migration runner/tool — manual SQL files only | OPEN | backend/migrations/ (12 files); no alembic/migration tool found | Adopt migration tool or document manual process |
| TD-OPS-006 | P2 Medium | Logging | No formal PII-safe logging policy | OPEN | ISSUE-121 LOGGING-001; not found in docs | Document PII-safe logging policy |
| TD-OPS-007 | P2 Medium | Ops | No log retention owner assigned | OPEN | ISSUE-121; not assigned | Assign log retention ownership |
| TD-PRIVACY-001 | P2 Medium | Privacy | No formal data retention policy | OPEN | ISSUE-121 PRIVACY-001; not found in docs | Document data retention policy |
| TD-PRIVACY-002 | P2 Medium | Privacy | No account deletion/export process | OPEN | ISSUE-121 PRIVACY-002; not found in codebase | Implement account deletion |
| TD-PRIVACY-003 | P2 Medium | Privacy | No privacy policy document confirmed | OPEN | ISSUE-121 PRIVACY-003; not found in repo | Create/confirm privacy policy |
| TD-PERF-001 | P2 Medium | Performance | No load testing performed | OPEN | ISSUE-121 PERF-001; k6 test exists but no results documented | Run load testing and document results |
| TD-PERF-002 | P2 Medium | Performance | No latency targets or SLAs defined | OPEN | ISSUE-121 PERF-002; not found in docs | Define latency targets |
| TD-PERF-003 | P2 Medium | Performance | In-process rate limiter resets on restart | OPEN | backend/app/rate_limit.py; in-memory dict with no persistence | Acceptable at current scale; revisit for multi-instance |
| TD-PERF-004 | P2 Medium | Performance | In-memory auth user cache (300s TTL) not shared across instances | OPEN | backend/app/auth/dependencies.py:18-37; process-local dict | Acceptable at current scale; revisit for multi-instance |
| TD-FE-001 | P2 Medium | Frontend | No frontend unit/component tests | OPEN | frontend/src/ — no *.test.* or *.spec.* files found | Add component tests |
| TD-FE-002 | P2 Medium | Frontend | Frontend version is scaffold default 0.0.0 | OPEN | frontend/package.json:4 | Set meaningful version per release-versioning-policy.md |
| TD-TEST-001 | P2 Medium | Testing | Playwright e2e tests exist but no CI integration confirmed | PARTIAL | frontend/tests/ (8 spec files); test:e2e script in package.json | Verify e2e tests run in CI |
| TD-RELEASE-001 | P2 Medium | Release | No CHANGELOG.md exists | OPEN | release-versioning-policy.md gap table | Create CHANGELOG.md |
| TD-RELEASE-002 | P2 Medium | Release | No automated release tagging in CI | OPEN | release-versioning-policy.md gap table | Implement CI release tagging |
| TD-NOTIFY-001 | P2 Medium | Notifications | No notification delivery failure monitoring | OPEN | production-readiness-checklist.md:91 | Add FCM delivery failure tracking |
| TD-OPS-008 | P2 Medium | Ops | No on-call rotation or escalation chain | OPEN | rollback-simulation-report.md finding | Define on-call rotation |
| TD-OPS-009 | P2 Medium | Ops | Dashboard access inventory missing | OPEN | rollback-simulation-report.md finding; unknown who has Vercel/Railway/Supabase access | Create dashboard access inventory |
| TD-OPS-010 | P2 Medium | Ops | Exact Vercel/Railway project names not documented | OPEN | rollback-simulation-report.md finding | Document project/service names for rollback |
| TD-PERF-005 | P2 Medium | Performance | Frontend bundle size not measured | OPEN | production-readiness-checklist.md:64 | Audit frontend bundle size |
| TD-DB-003 | P3 Low | Database | No seed data process for staging/testing | OPEN | database-backup-strategy.md:425; ISSUE-131 reference | Implement seed data (ISSUE-131) |
| TD-DOCS-001 | P3 Low | Documentation | Admin dashboard UI not implemented | OPEN | production-support-handbook.md:383 | Build admin dashboard UI |

## Detailed Debt Items

### TD-AUTH-001 — Google OAuth account-takeover via email-only linking

- **Severity**: P0 Critical
- **Status**: OPEN
- **Area**: Security / Authentication
- **Source**: ISSUE-092, ISSUE-110, ISSUE-111, ISSUE-121 (AUTH-001), ISSUE-122
- **Evidence**: backend/app/auth/google.py:186-193 — find_or_create_google_user queries .eq("email", email) without checking email_verified claim or matching google_sub against stored value. The email_verified field is read in _token_debug_claims (line 35) for logging only, never enforced.
- **Impact**: An attacker can create a Google account with the victim's email (unverified), obtain a Google ID token, and call the login endpoint. The backend finds the existing user by email and returns a valid JWT for the victim's account. Full account takeover.
- **Risk if ignored**: Any user account can be hijacked via Google login.
- **Recommended fix**: Enforce email_verified == true before accepting Google token. When an existing user is found by email, verify google_sub matches the stored value before linking. If no google_sub stored, require explicit account linking flow.
- **Suggested follow-up issue**: ISSUE-111: Harden Google OAuth account linking
- **Blocks production**: **YES**

### TD-OPS-001 — No error monitoring (Sentry or equivalent)

- **Severity**: P1 High
- **Status**: OPEN
- **Area**: Monitoring
- **Source**: ISSUE-121 (MONITOR-001), ISSUE-122
- **Evidence**: Codebase grep for sentry, newrelic, datadog returns 0 results in application code. Only health check GET / exists. Errors detectable only through manual Railway/Vercel log review.
- **Impact**: Production errors go undetected until users report them. No error rate tracking, no alerting.
- **Risk if ignored**: Silent production failures. Delayed incident response. Unknown error rates.
- **Recommended fix**: Integrate Sentry or equivalent error monitoring with alerting.
- **Suggested follow-up issue**: Add error monitoring to backend
- **Blocks production**: NO (accepted gap)

### TD-OPS-002 — No uptime monitoring or alerting

- **Severity**: P1 High
- **Status**: OPEN
- **Area**: Monitoring
- **Source**: ISSUE-121 (MONITOR-002), ISSUE-122
- **Evidence**: No uptime monitoring configuration found in codebase or infrastructure config. Health check endpoint exists but no external service polls it.
- **Impact**: Downtime detected only when users report it. No automated notification to team.
- **Risk if ignored**: Extended undetected downtime. Poor user trust.
- **Recommended fix**: Implement uptime monitoring (e.g., UptimeRobot, Better Uptime) polling GET / with alerting.
- **Suggested follow-up issue**: Add uptime monitoring and alerting
- **Blocks production**: NO (accepted gap)

### TD-OPS-003 — Staging environment not live

- **Severity**: P1 High
- **Status**: OPEN
- **Area**: Reliability
- **Source**: ISSUE-114 (STAGING-001), ISSUE-121, ISSUE-122
- **Evidence**: ISSUE-114 status: PREPARED / WAITING FOR EXTERNAL DASHBOARD SETUP. All 5 external services (Vercel, Railway, Supabase, Firebase, Google OAuth) remain unprovisioned.
- **Impact**: Cannot perform live rollback drills, live restore drills, or pre-production validation. All simulations are tabletop only.
- **Risk if ignored**: Untested operational procedures. Unknown real-world recovery times.
- **Recommended fix**: Provision all 5 staging services per docs/staging-setup.md.
- **Suggested follow-up issue**: Provision staging environment services
- **Blocks production**: NO (accepted gap)

### TD-OPS-004 — Supabase backup settings not confirmed

- **Severity**: P1 High
- **Status**: OPEN
- **Area**: Reliability
- **Source**: ISSUE-119 (BACKUP-001), ISSUE-121, ISSUE-122
- **Evidence**: database-backup-strategy.md documents RPO ≤24h, RTO ≤4h targets, but Supabase dashboard has not been accessed to confirm backup frequency, retention, or PITR availability.
- **Impact**: Backups may not be configured, or may not meet stated RPO/RTO targets.
- **Risk if ignored**: Data loss in production incident.
- **Recommended fix**: Access Supabase dashboard and verify/document backup settings.
- **Suggested follow-up issue**: Verify Supabase backup configuration
- **Blocks production**: NO (accepted gap)

### TD-OPS-005 — Live database restore not validated

- **Severity**: P1 High
- **Status**: OPEN
- **Area**: Reliability
- **Source**: ISSUE-120 (RESTORE-001), ISSUE-121, ISSUE-122
- **Evidence**: database-recovery-validation-report.md documents tabletop/dry-run simulation only. No live restore has been performed.
- **Impact**: Actual restore time, success rate, and data integrity after restore are unknown.
- **Risk if ignored**: Failed or slow restore during real incident.
- **Recommended fix**: Perform live restore drill on staging once staging is provisioned.
- **Suggested follow-up issue**: Run live database restore drill
- **Blocks production**: NO (accepted gap)

### TD-DB-001 — RLS not enabled on most tables

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Database
- **Source**: ISSUE-122 review; backend/schema.sql
- **Evidence**: Only user_moderation_audit (schema.sql:139) and push_tokens (push_notifications.sql:54) have ENABLE ROW LEVEL SECURITY. The remaining 7 tables (users, fields, games, game_players, field_reports, notification_preferences, notifications) have no RLS. Access control is enforced at the API layer.
- **Impact**: If the Supabase anon key is compromised or PostgREST is accessed directly, all table data is accessible without API-layer authorization checks.
- **Risk if ignored**: Defense-in-depth gap. Acceptable for current architecture but risky at scale.
- **Recommended fix**: Enable RLS on remaining tables with appropriate policies, or document the architectural decision to rely on API-layer authorization.
- **Suggested follow-up issue**: Enable RLS on additional database tables
- **Blocks production**: NO

### TD-DB-002 — No migration runner/tool — manual SQL files only

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Database
- **Source**: ISSUE-123 codebase review
- **Evidence**: 12 SQL migration files in backend/migrations/ with no alembic, migrate, or other migration tool. No migration runner found in pyproject.toml or code. Migrations are applied manually.
- **Impact**: Risk of migrations being applied out of order, skipped, or applied twice. No migration state tracking.
- **Risk if ignored**: Schema drift between environments. Deployment errors from missing migrations (as simulated in ISSUE-118 rollback scenario).
- **Recommended fix**: Adopt a migration tool (alembic, yoyo) or document the manual migration process with a checklist.
- **Suggested follow-up issue**: Implement migration management tool
- **Blocks production**: NO

### TD-OPS-006 — No formal PII-safe logging policy

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Logging
- **Source**: ISSUE-121 (LOGGING-001), ISSUE-122
- **Evidence**: Backend uses Python logging module across 9 files with structured extra fields. Auth events avoid logging passwords/tokens. But no formal policy document defines what must/must not be logged.
- **Impact**: Future code changes could inadvertently log PII (emails, phone numbers, tokens).
- **Risk if ignored**: Privacy violation, compliance risk.
- **Recommended fix**: Create a PII-safe logging policy document.
- **Suggested follow-up issue**: Create PII-safe logging policy
- **Blocks production**: NO

### TD-OPS-007 — No log retention owner assigned

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Ops
- **Source**: ISSUE-121, ISSUE-122
- **Evidence**: No person or role assigned to manage log retention, rotation, or archival.
- **Impact**: Logs may grow unbounded or be lost without notice.
- **Risk if ignored**: Inability to investigate past incidents. Storage cost growth.
- **Recommended fix**: Assign log retention ownership.
- **Suggested follow-up issue**: Assign monitoring and logging ownership
- **Blocks production**: NO

### TD-PRIVACY-001 — No formal data retention policy

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Privacy
- **Source**: ISSUE-121 (PRIVACY-001)
- **Evidence**: No data retention policy document found in docs/.
- **Impact**: No defined rules for how long personal data (users, notifications, game history, push tokens) is retained.
- **Risk if ignored**: Compliance risk (GDPR, privacy regulations).
- **Recommended fix**: Create data retention policy.
- **Suggested follow-up issue**: Create data retention policy
- **Blocks production**: NO

### TD-PRIVACY-002 — No account deletion/export process

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Privacy
- **Source**: ISSUE-121 (PRIVACY-002)
- **Evidence**: No account deletion or data export endpoint/process found in codebase.
- **Impact**: Users cannot request deletion of their data. Required for App Store and GDPR compliance.
- **Risk if ignored**: App store rejection. Compliance violation.
- **Recommended fix**: Implement account deletion endpoint and data export.
- **Suggested follow-up issue**: Implement account deletion process
- **Blocks production**: NO

### TD-PRIVACY-003 — No privacy policy document confirmed

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Privacy
- **Source**: ISSUE-121 (PRIVACY-003)
- **Evidence**: No privacy policy document found in repo.
- **Impact**: Required for App Store submission and GDPR compliance.
- **Risk if ignored**: App store rejection. Legal risk.
- **Recommended fix**: Create or confirm privacy policy.
- **Suggested follow-up issue**: Create privacy policy document
- **Blocks production**: NO

### TD-PERF-001 — No load testing performed

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Performance
- **Source**: ISSUE-121 (PERF-001)
- **Evidence**: k6 load test script exists (backend/load_tests/game_creation_load_test.js) but no results are documented. No baseline performance data.
- **Impact**: Unknown capacity limits. Unknown behavior under concurrent load.
- **Risk if ignored**: Production outage under unexpected load.
- **Recommended fix**: Run k6 load tests against staging, document results and capacity limits.
- **Suggested follow-up issue**: Run backend load testing
- **Blocks production**: NO

### TD-PERF-002 — No latency targets or SLAs defined

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Performance
- **Source**: ISSUE-121 (PERF-002)
- **Evidence**: No latency targets found in docs or code.
- **Impact**: No way to detect performance regressions or set user expectations.
- **Risk if ignored**: Gradual performance degradation without detection.
- **Recommended fix**: Define p50/p95/p99 latency targets for critical endpoints.
- **Suggested follow-up issue**: Define API latency targets
- **Blocks production**: NO

### TD-PERF-003 — In-process rate limiter resets on restart

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Performance / Security
- **Source**: ISSUE-122 review; backend/app/rate_limit.py
- **Evidence**: RateLimiter uses in-memory dict (line 21). State lost on process restart. No Redis or external store.
- **Impact**: Rate limits reset after every deployment or crash. In a multi-instance deployment, each instance has independent limits.
- **Risk if ignored**: Bypass rate limiting by triggering restarts or hitting different instances.
- **Recommended fix**: Acceptable at current single-instance scale. For multi-instance, move to Redis-backed rate limiting.
- **Suggested follow-up issue**: Evaluate distributed rate limiting
- **Blocks production**: NO

### TD-PERF-004 — In-memory auth user cache not shared across instances

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Performance
- **Source**: ISSUE-122 review; backend/app/auth/dependencies.py:18-37
- **Evidence**: _user_cache is a process-local dict with 300s TTL. Not shared across instances. Cache invalidation (invalidate_cached_user) only affects local process.
- **Impact**: In multi-instance deployment, one instance may serve stale user data after ban/suspension on another instance.
- **Risk if ignored**: Banned/suspended user can continue using the app for up to 300s on another instance.
- **Recommended fix**: Acceptable at current single-instance scale. For multi-instance, use Redis or reduce TTL.
- **Suggested follow-up issue**: Evaluate shared auth cache
- **Blocks production**: NO

### TD-FE-001 — No frontend unit/component tests

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Frontend / Testing
- **Source**: ISSUE-123 codebase review
- **Evidence**: Glob for frontend/src/**/*.{test,spec}.{ts,tsx,js,jsx} returns 0 files. 8 Playwright e2e spec files exist in frontend/tests/ but no component-level tests.
- **Impact**: Frontend component regressions not caught before e2e. No isolated testing of UI logic.
- **Risk if ignored**: UI regressions caught late or not at all.
- **Recommended fix**: Add component tests (Vitest + Testing Library).
- **Suggested follow-up issue**: Add frontend component tests
- **Blocks production**: NO

### TD-FE-002 — Frontend version is scaffold default 0.0.0

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Frontend / Release
- **Source**: ISSUE-123 codebase review; frontend/package.json:4
- **Evidence**: version field is "0.0.0" — the Vite scaffold default. release-versioning-policy.md documents this as a known gap.
- **Impact**: No version tracking for frontend releases. Cannot correlate deployments to versions.
- **Risk if ignored**: Inability to trace bugs to specific releases.
- **Recommended fix**: Set version per release-versioning-policy.md before first production release.
- **Suggested follow-up issue**: Set initial frontend version
- **Blocks production**: NO

### TD-TEST-001 — Playwright e2e tests exist but CI integration not confirmed

- **Severity**: P2 Medium
- **Status**: PARTIAL
- **Area**: Testing
- **Source**: ISSUE-123 codebase review
- **Evidence**: 8 Playwright spec files in frontend/tests/. test:e2e script in package.json. No CI workflow file found confirming e2e tests run in CI pipeline.
- **Impact**: E2e tests may not run automatically on PRs or merges.
- **Risk if ignored**: Regressions not caught before merge.
- **Recommended fix**: Verify and document CI e2e test integration.
- **Suggested follow-up issue**: Verify e2e tests run in CI
- **Blocks production**: NO

### TD-RELEASE-001 — No CHANGELOG.md exists

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Release
- **Source**: release-versioning-policy.md gap table
- **Evidence**: No CHANGELOG.md file found in repo. release-versioning-policy.md lists this as "Not implemented."
- **Impact**: No human-readable record of changes between releases.
- **Risk if ignored**: Difficult to communicate changes to users or app reviewers.
- **Recommended fix**: Create CHANGELOG.md and update per release.
- **Suggested follow-up issue**: Create CHANGELOG.md
- **Blocks production**: NO

### TD-RELEASE-002 — No automated release tagging in CI

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Release
- **Source**: release-versioning-policy.md gap table
- **Evidence**: No CI workflow for git tagging or GitHub Releases. release-versioning-policy.md lists automated release tagging and GitHub Releases as "Not implemented."
- **Impact**: Releases not tagged automatically. No GitHub Releases for distribution.
- **Risk if ignored**: Manual error in release process. Inconsistent tagging.
- **Recommended fix**: Implement CI release tagging workflow.
- **Suggested follow-up issue**: Implement CI release tagging
- **Blocks production**: NO

### TD-NOTIFY-001 — No notification delivery failure monitoring

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Notifications
- **Source**: production-readiness-checklist.md:91
- **Evidence**: firebase_push.py logs errors locally but no monitoring/alerting for FCM delivery failures. No delivery success rate tracking.
- **Impact**: Push notification failures go undetected. Users may stop receiving notifications silently.
- **Risk if ignored**: Silent notification delivery degradation.
- **Recommended fix**: Add FCM delivery failure tracking and alerting.
- **Suggested follow-up issue**: Add notification delivery monitoring
- **Blocks production**: NO

### TD-OPS-008 — No on-call rotation or escalation chain

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Ops
- **Source**: rollback-simulation-report.md section 9
- **Evidence**: No on-call rotation defined. Rollback simulation found that detection relies on user reports. No defined escalation chain for off-hours incidents.
- **Impact**: Incidents outside business hours go undetected and unhandled.
- **Risk if ignored**: Extended outages. No accountability for incident response.
- **Recommended fix**: Define on-call rotation and escalation chain.
- **Suggested follow-up issue**: Define on-call rotation
- **Blocks production**: NO

### TD-OPS-009 — Dashboard access inventory missing

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Ops
- **Source**: rollback-simulation-report.md section 9
- **Evidence**: Unknown which team members have access to Vercel, Railway, Supabase, Firebase, and Google Cloud dashboards.
- **Impact**: During rollback, the person with access may be unavailable. Access bottleneck.
- **Risk if ignored**: Delayed rollback or recovery if access holder is unavailable.
- **Recommended fix**: Create dashboard access inventory with at least 2 people per service.
- **Suggested follow-up issue**: Create dashboard access inventory
- **Blocks production**: NO

### TD-OPS-010 — Exact Vercel/Railway project names not documented

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Ops
- **Source**: rollback-simulation-report.md section 9
- **Evidence**: Rollback procedure references Vercel and Railway dashboards but exact project/service names are not documented.
- **Impact**: Rollback operator must search for the correct project during an incident.
- **Risk if ignored**: Delayed rollback. Wrong service rolled back.
- **Recommended fix**: Document exact project/service names in rollback-procedure.md.
- **Suggested follow-up issue**: Document deployment project names
- **Blocks production**: NO

### TD-PERF-005 — Frontend bundle size not measured

- **Severity**: P2 Medium
- **Status**: OPEN
- **Area**: Performance
- **Source**: production-readiness-checklist.md:64
- **Evidence**: No bundle size measurement or budget found in docs or CI config.
- **Impact**: Bundle size may grow without detection, affecting load times.
- **Risk if ignored**: Slow mobile load times. Poor user experience.
- **Recommended fix**: Measure and document bundle size. Optionally set budget.
- **Suggested follow-up issue**: Audit frontend bundle size
- **Blocks production**: NO

### TD-DB-003 — No seed data process for staging/testing

- **Severity**: P3 Low
- **Status**: OPEN
- **Area**: Database
- **Source**: database-backup-strategy.md:425; ISSUE-131 reference
- **Evidence**: No seed data script or process found. database-backup-strategy.md lists seed data as "Not implemented" with reference to ISSUE-131.
- **Impact**: Staging environment (when provisioned) will have empty database. Manual test data setup required.
- **Risk if ignored**: Slower testing. Inconsistent test data.
- **Recommended fix**: Implement seed data process (ISSUE-131).
- **Suggested follow-up issue**: ISSUE-131: Create seed data process
- **Blocks production**: NO

### TD-DOCS-001 — Admin dashboard UI not implemented

- **Severity**: P3 Low
- **Status**: OPEN
- **Area**: Documentation / Frontend
- **Source**: production-support-handbook.md:383
- **Evidence**: production-support-handbook.md lists "Admin dashboard UI" as "Not implemented." Admin operations currently performed via API endpoints.
- **Impact**: Admin operations require API calls or curl. No visual moderation interface.
- **Risk if ignored**: Operational friction for admin tasks. Higher barrier for non-technical admins.
- **Recommended fix**: Build admin dashboard UI.
- **Suggested follow-up issue**: Build admin dashboard UI
- **Blocks production**: NO
