# Crash Reporting Incident Workflow (E09-01)

How to triage, prioritize, and resolve issues that arrive in Sentry once monitoring is live. Companion to [`docs/crash-reporting-architecture.md`](crash-reporting-architecture.md) (what's reported and why) and [`docs/sentry-configuration-guide.md`](sentry-configuration-guide.md) (how to set it up).

## How to Triage a New Issue

1. **Identify the platform and environment first.** Every event carries `environment` (`local`/`development`/`branch-build`/`production`) and, for mobile events, a `dist` tag distinguishing Android from iOS. A `branch-build` or `development` event is never a production incident — deprioritize accordingly.
2. **Read the fingerprint/title and the first stack frame.** Confirm it's an application error, not third-party/browser-extension noise (the filter in `frontend/src/monitoring/filters.js` already excludes known extension-origin frames, but new patterns can slip through).
3. **Check the `release` tag** against the current deployed release. An event from an old release after a newer one has shipped may already be fixed — don't re-open work for it without confirming it still reproduces on the current release.
4. **Check the `request_id` tag** (backend events) or the frontend `X-Request-Id` correlation. If both a frontend and backend event share the same request id, they're almost certainly the same underlying failure — triage them together, not as two separate issues.
5. **Read the safe tags** (`endpoint`, `http_method`, `http_status`, `error_code` on the backend; `http_status`, breadcrumb `category`/`action`/`status_category` on the frontend) before diving into the stack trace — they usually narrow the failure to a specific route or flow immediately.

## How to Compare Affected Users

Use Sentry's **affected users** count on the issue page — this reflects the internal user ID set via `Sentry.setUser({ id })` (never email/name, per the privacy policy), so cross-reference against internal user records by ID, not by any PII visible in Sentry itself. An issue affecting many distinct users is a wider-blast-radius incident than the same error recurring many times for one user (a single user's device/network condition).

## How to Identify a Release Regression

Sentry auto-detects when a previously-resolved issue reoccurs on a newer release and flags it as a **regression** — this is the primary signal, and it triggers the "Regression of a resolved issue" alert (see the configuration guide's alert table). Manually, compare the issue's "first seen" release against the "last seen" release: if a fix shipped in release N and the issue reappears in release N+1 or later, treat it as a regression requiring immediate re-investigation of the original fix, not a fresh bug.

## How to Assign Severity

| Severity | Criteria | Response |
|---|---|---|
| **Critical** | Production fatal error/crash affecting >5 distinct users in 24h, or any Android ANR-rate/backend error-rate spike alert firing | Immediate triage, same-day fix or rollback |
| **High** | Production fatal error, low user count, first occurrence | Triage within 1 business day |
| **Medium** | Production non-fatal (reported unexpected-but-recoverable failure — e.g. an unknown push-delivery classification, an email-provider rejection) | Triage within the current work cycle |
| **Low** | `development`/`branch-build` environment event, or a low-frequency non-fatal with no user-facing impact confirmed | Backlog |

Regressions are automatically escalated one severity level above what the criteria above would otherwise assign, since a regression indicates a previous fix didn't hold.

## How to Mark Resolved

1. Confirm the fix has actually shipped to the environment the issue occurred in (check the `release` tag on the issue against the deployed release).
2. Mark the issue **Resolved** in Sentry, optionally scoped to "resolved in release X" so Sentry can auto-flag a regression if it reoccurs on a later release.
3. Do not mark an issue resolved based on code review alone — verify against the manual verification procedures in the execution plan (§48–§50 of `docs/e09-01-crash-reporting-execution-plan.md`) where practical, or against the automated test added for the fix.

## How to Verify a Fix

1. Prefer an automated regression test added alongside the fix (see the test plans in the execution plan for the existing coverage pattern — e.g. `frontend/tests/monitoring-*.test.js`, `backend/tests/test_monitoring.py`).
2. Where a live check is warranted, use the safe test-trigger mechanisms already wired for this purpose — never a production-reachable crash endpoint:
   - Frontend: `window.__monitoringTest.triggerReactRenderError()` / `triggerTestMessage()` (non-production environments only).
   - Backend: `GET /__test/sentry-trigger` (route only exists when the resolved environment is not `production`).
   - Android native: `window.__monitoringTest.triggerTestNativeCrash()` on a dedicated non-production branch-build APK.
3. Confirm the new event no longer reproduces the original failure signature, and that the original issue doesn't reopen on the next deploy.

## When to Create a Hotfix

Create a hotfix (bypassing the normal release cadence) when:
- A **Critical**-severity issue is confirmed in `production` and affects a core flow (authentication, map/field browsing, game join/create, push delivery).
- A regression reintroduces a previously-fixed Critical or High issue.
- The backend error-rate spike alert or Android ANR-rate spike alert fires and is confirmed (not a monitoring false positive — check that `is_monitoring_active()`/the SDK itself isn't the thing failing, per the "monitoring outage does not break the API/app" guarantee already tested).

Do not hotfix for `development`/`branch-build` events, or for events already scoped to a known, tracked follow-up (see the execution plan's Follow-Up Tasks section) unless they're unexpectedly blocking active work.

## Issue Ownership

- **Alert recipient**: project owner email (per the alert configuration in the setup guide — no team-routing logic exists yet, since this is a small/early-stage project).
- **Frontend/mobile issue triage**: whoever owns the affected feature area at the time; there is no dedicated on-call rotation yet.
- **Backend issue triage**: same — feature-area ownership, no dedicated rotation.
- **Release regression review**: the person who shipped the release the regression appeared in should be looped in first, since they have the most context on what changed.

No external alert-routing automation (Slack, PagerDuty) exists in this codebase — email alerts plus this manual workflow are the complete process for now, per the task's explicit scope.
