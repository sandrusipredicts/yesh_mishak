# Staging Smoke Test Checklist

Run this checklist after deploying to the staging environment, before approving a production release.

## Automation status (E12-04)

A subset of this checklist is automated by the staging smoke suite
(`frontend/tests/staging/`, run via `npm run test:staging-smoke` or the
**Staging smoke tests** GitHub Actions workflow). See
[docs/qa/staging-smoke-tests.md](qa/staging-smoke-tests.md).

Status values: **Implemented** (automated test exists) · **Locally validated**
(proven against a local stack) · **Validated against real staging** (green run
against provisioned staging) · **Blocked** (cannot run until staging exists) ·
**Manual** (intentionally not automated).

| Checklist area | Automated coverage | Status |
| :--- | :--- | :--- |
| §1 Pre-test: frontend/backend URLs accessible | `[frontend-availability]`, `[backend-health]`, readiness poll | Implemented · Locally validated · real staging **Blocked** |
| §1 Pre-test: env vars set in dashboards / no production values | Partially: `[frontend-wiring]` detects a production-pointing frontend build | Implemented (partial) · Locally validated · real staging **Blocked**; dashboard review stays Manual |
| §1 Pre-test: staging DB reachable | `[db-connectivity]` (`GET /fields/` queries Supabase) | Implemented · Locally validated · real staging **Blocked** |
| §2 Frontend: loads without blank screen / console errors | `[frontend-boot]` | Implemented · Locally validated · real staging **Blocked** |
| §2 Frontend: map pan/zoom interaction, static assets | — | Manual |
| §2 Frontend: all requests target staging backend | `[frontend-wiring]` | Implemented · Locally validated · real staging **Blocked** |
| §3 Backend: `GET /` health, CORS headers | `[backend-health]`, `[cors]` (+ `[api-contract]` error envelope) | Implemented · Locally validated · real staging **Blocked** |
| §3 Backend: `GET /docs`, Railway log review | — | Manual |
| §4 Auth: Google OAuth login | — | Manual (interactive; excluded from automation) |
| §4 Auth: login returns valid JWT / authenticated requests / invalid token 401 | Tier B `[auth-login]`, `[auth-user-data]`, `[auth-rejection]` (password login with the dedicated staging test account) | Implemented · Locally validated (skip + failure paths) · real staging **Blocked** (needs staging test account + secrets) |
| §5 Fields: seeded fields returned | `[db-connectivity]` (shape only — empty staging allowed) | Implemented · Locally validated · real staging **Blocked**; seeded-content review Manual |
| §5 Fields: field creation, markers | — | Manual (mutating / visual) |
| §6 Games: create/join/leave/listing | — | Manual — mutating; excluded from the read-only suite (plan §9 admission bar) |
| §7 Admin: non-admin 403 | Tier B `[authz-boundary]` | Implemented · Locally validated · real staging **Blocked** |
| §7 Admin: admin positive-path | — | Manual — no dedicated staging admin identity |
| §8 Notifications: unread count | Tier B `[notifications-contract]` | Implemented · Locally validated · real staging **Blocked** |
| §8 Notifications: preferences update, test push | — | Manual (mutating / external side effect) |
| §9 Push safety | — | Manual (dashboard/device verification) |
| §10 Logs | — | Manual (Railway dashboard) |

## 1. Pre-Test Checks

- [ ] Staging frontend URL is accessible (not 404 or 503).
- [ ] Staging backend URL is accessible (not 404 or 503).
- [ ] All staging environment variables are set in Vercel and Railway dashboards.
- [ ] Staging environment variables do NOT contain production values.
- [ ] Staging database (Supabase) is reachable from the staging backend.

## 2. Frontend Checks

- [ ] Staging site loads without blank screen.
- [ ] No console errors related to missing environment variables.
- [ ] Map renders and is interactive (pan, zoom).
- [ ] All network requests target the staging backend URL (not production).
- [ ] Static assets (images, icons, fonts) load correctly.

## 3. Backend Checks

- [ ] `GET /` returns HTTP 200 with health check response.
- [ ] `GET /docs` loads Swagger/OpenAPI documentation page.
- [ ] API responses include correct CORS headers for the staging frontend origin.
- [ ] No database connection errors in Railway logs.

## 4. Auth Checks

- [ ] Google OAuth login button is visible and clickable.
- [ ] Google OAuth login completes successfully with a staging test account.
- [ ] Login returns a valid JWT token.
- [ ] Authenticated API requests succeed with the returned token.
- [ ] Invalid/expired tokens are rejected with 401.

## 5. Fields Checks

- [ ] `GET /fields/` returns seeded test fields.
- [ ] Field detail view loads for a specific field.
- [ ] Field creation works for authenticated users (if applicable in staging).
- [ ] Map markers appear for seeded fields.

## 6. Games Checks

- [ ] Game creation succeeds on a test field.
- [ ] Created game appears in the field detail view.
- [ ] Join game increments participant count.
- [ ] Leave game decrements participant count.
- [ ] Game listing/filtering works as expected.

## 7. Admin Protection Checks

- [ ] Non-admin users receive 403 when accessing admin endpoints.
- [ ] Admin users can access admin functionality (field approval, reports).
- [ ] Admin role is determined by the staging database, not hardcoded.

## 8. Notification Checks

- [ ] Notification preferences can be viewed and updated.
- [ ] Unread notification count endpoint responds correctly.
- [ ] Test push notification endpoint is functional (if `VITE_SHOW_TEST_PUSH` is enabled).

## 9. Push Notification Safety Checks

- [ ] Push notifications are sent using the staging Firebase project credentials.
- [ ] Push tokens in the staging database are synthetic/test tokens only.
- [ ] No production push tokens exist in the staging database.
- [ ] Test push notification is received only on staging test devices.
- [ ] Production users do NOT receive any staging notifications.

## 10. Logs Checks

- [ ] Railway staging container logs show no unhandled exceptions.
- [ ] No tracebacks or connection timeout errors in logs.
- [ ] No references to production URLs or credentials in staging logs.
- [ ] Log output is clean and expected for normal operation.

## 11. Pass/Fail Signoff

| Area | Pass | Fail | Notes |
| :--- | :--- | :--- | :--- |
| Pre-test checks | [ ] | [ ] | |
| Frontend | [ ] | [ ] | |
| Backend | [ ] | [ ] | |
| Auth | [ ] | [ ] | |
| Fields | [ ] | [ ] | |
| Games | [ ] | [ ] | |
| Admin protection | [ ] | [ ] | |
| Notifications | [ ] | [ ] | |
| Push notification safety | [ ] | [ ] | |
| Logs | [ ] | [ ] | |

**Tested by**: _______________
**Date**: _______________
**Result**: PASS / FAIL
**Notes**: _______________
