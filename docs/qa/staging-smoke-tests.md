# Staging Smoke-Test Suite (E12-04)

Automated, read-only smoke tests for the deployed staging environment.
Approved plan: [e12-04-staging-smoke-test-plan.md](e12-04-staging-smoke-test-plan.md).

> **Status blocker:** the real staging environment **does not exist yet**.
> E12-03 (report `docs/e12-03-staging-verification-report.md`, commit
> `b18b462` on the **unmerged** branch `qa/e12-03-staging-verification`)
> verified that the expected staging URLs serve a Vercel
> `DEPLOYMENT_NOT_FOUND` page and Railway's empty placeholder. This suite is
> implemented and validated against a local stack, but **E12-04 cannot be
> closed until (a) the E12-03 provisioning work and evidence land in the
> canonical project history and (b) this suite completes a real green run
> against provisioned staging via the GitHub Actions workflow.**

## 1. Purpose

Answer, in under a few minutes and without touching persistent data: is the
staging frontend deployed and booting, is the staging backend up and connected
to its database, do the core API contracts hold, and is the frontend wired to
the **staging** backend rather than production?

## 2. Architecture

- **Framework:** the repository's existing Playwright installation — no new
  test framework.
- **Config:** [frontend/playwright.staging.config.js](../../frontend/playwright.staging.config.js)
  (fully separate from the default `playwright.config.js`; no dev-server
  bootstrap).
- **Tests:** `frontend/tests/staging/`
  - `api.smoke.spec.js` — project **staging-api**, pure HTTP via Playwright's
    `request` fixture (no browser).
  - `frontend.smoke.spec.js` — project **staging-browser**, Chromium.
  - `helpers.js` — environment contract (validation, normalization,
    production-host denylist).
  - `global-setup.js` — fail-fast config validation + bounded readiness poll.
- **Discovery isolation:** the default `playwright.config.js` has
  `testIgnore: '**/staging/**'`, so `npm run test:e2e` never picks up staging
  tests; the staging config's `testDir` is `tests/staging` only.
- **Determinism:** `workers: 1`, no parallelism, retries `1` in CI / `0`
  locally, 30s per-test timeout.

## 3. Scope

### Tier A — always runs (unauthenticated, read-only)

| Test title prefix | What it proves |
| :--- | :--- |
| `[backend-health]` | `GET /` returns HTTP 200 **and** the exact `{"status":"ok"}` JSON contract (a placeholder page fails this) |
| `[db-connectivity]` | `GET /fields/` returns 200 + a JSON array (this route queries Supabase — it is the database probe; `GET /` never touches the DB). Empty arrays are valid; item shape (`id`, `lat`, `lng`, `status`, `active_game`, `upcoming_games`) is checked only when data exists |
| `[api-contract]` | `GET /fields/00000000-0000-4000-8000-000000000000` returns the stable 404 error envelope (`error: true`, `code: "FIELD_NOT_FOUND"`, string `message`) |
| `[cors]` | `OPTIONS /fields/` preflight with the staging frontend `Origin` is allowed, echoed exactly, and never `*` (the app uses explicit origins with credentials) |
| `[frontend-availability]` | `GET /` on the frontend returns 200 HTML containing the app root element, stays on the staging host, and contains no infrastructure placeholder markers (`DEPLOYMENT_NOT_FOUND`, `Home of the Railway API`) |
| `[frontend-boot]` | The app mounts in Chromium with zero uncaught page errors and zero non-allowlisted console errors |
| `[frontend-wiring]` | The served JS bundle contains the staging backend origin (the API base URL is baked at build time) and **no** `PRODUCTION_BACKEND_HOSTS` entry appears in it as a URL; additionally, no observed runtime request during a short boot window reaches a production host. Bundle inspection is the positive proof because a fresh anonymous visit can legitimately make zero API calls (onboarding gate). Offending URLs are reported origin+path only (query strings stripped) |
| `[frontend-legal]` | `/privacy` and `/terms` return 200, mount, and render meaningful text |

### Tier B — optional (authenticated, read-only; auto-skips without credentials)

Runs only when **both** `STAGING_TEST_EMAIL` and `STAGING_TEST_PASSWORD` are
set. When absent, the tests are skipped with an explicit reason naming the
missing variables; Tier A is unaffected.

| Test title prefix | What it proves |
| :--- | :--- |
| `[auth-login]` | `POST /auth/login` with the dedicated synthetic staging account returns 200 + a bearer token (the only write-adjacent call in the suite: it touches `last_login` for the test account) |
| `[auth-user-data]` | `GET /games/me` returns 200 + array with the fresh token |
| `[notifications-contract]` | `GET /notifications/unread-count` returns 200 + integer `unread_count` |
| `[auth-rejection]` | A garbage bearer token gets 401 + `code: "AUTH_REQUIRED"` |
| `[authz-boundary]` | The non-admin test account gets 403 + `code: "FORBIDDEN"` from `GET /admin/stats` (also guards that the test account was not accidentally given admin rights) |

## 4. Explicit exclusions (do not add without a new approved plan)

Game creation/join/leave/close/extend, field creation, photo upload, push
notification sending (`/notifications/test-push`), email sending, Google
sign-in (native or web), App Links, Waze, camera, all iOS behavior, map-tile
visual assertions, admin positive-path tests (no staging admin identity
exists), any test that mutates persistent staging state, and any intentional
contact with production. Positive admin tests require a formally provided
dedicated staging admin identity first.

## 5. Required variables and secrets

| Name | Required | Kind | Meaning |
| :--- | :--- | :--- | :--- |
| `STAGING_FRONTEND_URL` | Yes | GitHub environment **variable** / local env | Staging frontend base URL (http/https, no query/fragment) |
| `STAGING_BACKEND_URL` | Yes | GitHub environment **variable** / local env | Staging backend base URL |
| `PRODUCTION_BACKEND_HOSTS` | Yes | GitHub environment **variable** / local env | Comma-separated bare production API hostnames (denylist for `[frontend-wiring]`) |
| `STAGING_TEST_EMAIL` | No (enables Tier B) | GitHub environment **secret** | Synthetic staging test account email — never a personal account |
| `STAGING_TEST_PASSWORD` | No (enables Tier B) | GitHub environment **secret** | Its password |
| `STAGING_READINESS_TIMEOUT_MS` | No | env | Cold-start readiness window per target (default 90000, clamp 1000–600000) |

Contract enforcement (`helpers.js`): missing/empty required variables abort
immediately with a `[staging-smoke:config]` error naming them; malformed or
non-http(s) URLs are rejected; URLs are normalized (trailing slashes stripped,
query/fragment forbidden); the run **refuses to start** if the staging
frontend or backend hostname appears in `PRODUCTION_BACKEND_HOSTS`; providing
only one of the two Tier B secrets is a hard error; there are **no fallbacks**
to localhost or production.

## 6. Running locally

```powershell
cd frontend
$env:STAGING_FRONTEND_URL = "<staging frontend URL>"
$env:STAGING_BACKEND_URL = "<staging backend URL>"
$env:PRODUCTION_BACKEND_HOSTS = "<production API hostname>"
# Optional Tier B:
# $env:STAGING_TEST_EMAIL = "<synthetic staging account email>"
# $env:STAGING_TEST_PASSWORD = "<its password>"
npm run test:staging-smoke
```

Real URLs are deliberately not written in this document or in code: canonical
staging URLs are owner-confirmed values (plan §13) and are configured in the
GitHub `staging` environment, not in the repository.

### Local rehearsal against a local stack (what E12-04 validated)

```powershell
# Terminal 1 — backend (uses backend/.env):
cd backend; .venv\Scripts\python -m uvicorn app.main:app --port 8000

# Terminal 2 — frontend build + preview on an allowed CORS origin:
cd frontend
$env:VITE_API_URL = "http://127.0.0.1:8000"; npm run build
npm run preview -- --host 127.0.0.1 --port 5173

# Terminal 3:
cd frontend
$env:STAGING_FRONTEND_URL = "http://127.0.0.1:5173"
$env:STAGING_BACKEND_URL = "http://127.0.0.1:8000"
$env:PRODUCTION_BACKEND_HOSTS = "yesh-mishak-api.railway.app"
npm run test:staging-smoke
```

Note: preview must run on port 5173/5174 — those local origins are in the
backend's built-in CORS allowlist (`backend/app/main.py`), so the `[cors]`
test is meaningful locally.

## 7. Running from GitHub Actions

Workflow: **Staging smoke tests**
(`.github/workflows/staging-smoke-tests.yml`) — `workflow_dispatch` only
(GitHub → Actions → Staging smoke tests → Run workflow).

- Uses the GitHub **`staging` environment**: URLs from environment
  *variables*, credentials from environment *secrets*.
- Validates configuration presence before installing anything; a missing
  required variable fails the run with an `::error::` naming it.
- Installs only frontend npm dependencies + Playwright Chromium.
- 15-minute job timeout; concurrency group `staging-smoke` prevents duplicate
  simultaneous runs; not a required PR check by design.
- No scheduled or post-deployment triggers exist yet — do not add them until a
  reviewed staging deployment workflow exists (plan §11).

## 8. Failure interpretation

Every failure message starts with a component tag:

| Tag | Component to investigate |
| :--- | :--- |
| `[staging-smoke:config]` | Your environment variables (nothing was tested) |
| `[staging-smoke:backend-availability]` / `[staging-smoke:frontend-availability]` | Target unreachable within the readiness window — deployment down or cold start longer than `STAGING_READINESS_TIMEOUT_MS` |
| `[backend-health]` | Railway service (app not running / placeholder served) |
| `[db-connectivity]` | Backend↔Supabase connection or staging DB state |
| `[api-contract]`, `[cors]` | Backend configuration/regression |
| `[frontend-availability]` | Vercel deployment (missing, placeholder, or cross-host redirect) |
| `[frontend-boot]` | Frontend bundle/runtime (HTML served but app crashed) |
| `[frontend-wiring]` | Frontend build configuration (`VITE_API_URL`) — **production hit = misconfigured build** |
| `[frontend-legal]` | Frontend routing/content |
| `[auth-login]` | Test-account credentials/state (rotate secrets, check account) |
| `[auth-user-data]`, `[notifications-contract]`, `[auth-rejection]`, `[authz-boundary]` | Backend auth/authorization contracts |

Tier A green + `[auth-login]` red usually means credential decay, not an
outage.

## 9. Artifacts

- HTML report: `frontend/playwright-report-staging/`
- Traces/screenshots (browser project only, on failure):
  `frontend/test-results-staging/`
- CI uploads both as artifact `staging-smoke-report` (14-day retention) on
  failure only.

## 10. Troubleshooting

- **Immediate `[staging-smoke:config]` error** — read it; it names the exact
  variable. No requests were made.
- **Readiness poll timeout** — open the URL in a browser. If it responds,
  raise `STAGING_READINESS_TIMEOUT_MS`; if not, the deployment is down.
- **`[cors]` fails locally** — your preview origin is not in the backend
  allowlist; use port 5173/5174.
- **Passes locally, fails in CI** — check Vercel Deployment Protection on the
  staging project (hosted runners need anonymous GET) and IP-based
  restrictions; inspect the uploaded trace.
- **`[frontend-boot]` console-error failures** — the allowlist
  (`ALLOWED_CONSOLE_ERROR_PATTERNS` in `helpers.js`) covers only documented
  harmless third-party noise: OSM tile fetch failures, favicon 404s,
  `ERR_BLOCKED_BY_CLIENT`. Extend it only with review, never to silence an
  application error.

## 11. Cold-start behavior

Railway/Vercel free-tier services may cold start. `global-setup.js` polls
`GET <backend>/` and `GET <frontend>/` every 5s until HTTP 200, bounded by
`STAGING_READINESS_TIMEOUT_MS` (default 90s **per target**), then fails the
run with an availability-attributed error rather than retrying indefinitely.
Individual tests therefore run against warm targets and keep tight 30s
timeouts.

## 12. Secret-handling rules

- Credentials enter only via environment variables / GitHub environment
  secrets; they are never written to code, docs, reports, or logs.
- Failure assertions for authenticated calls print **status codes only** —
  never response bodies, tokens, cookies, or Authorization headers.
- Playwright tracing is **disabled for the API project** specifically because
  traces record request headers; the browser project records no credentialed
  traffic (Tier A only).
- `[frontend-wiring]` reports offending URLs stripped to origin+path (no query
  strings).
- The CI validation step reports secret **presence**, never values; GitHub's
  secret masking is a backstop, not the mechanism.
- Local validation includes a sentinel-grep proving the credential value
  appears nowhere in stdout or generated reports.

## 13. Dependencies and closure requirements

1. **E12-03 dependency:** staging verification evidence lives only in commit
   `b18b462` on the unmerged branch `qa/e12-03-staging-verification`. E12-04
   must not be considered complete until the E12-03 provisioning work and its
   evidence are available in the canonical project history (merged), and the
   staging environment it gates (E12-03A/B/C: Supabase, Firebase, Google
   OAuth, Railway, Vercel) is actually provisioned.
2. **Owner actions before the first real run** (plan §13): confirm canonical
   staging URLs, confirm production API hostname(s), create the synthetic
   email-verified staging test user, create the GitHub `staging` environment
   with the variables/secrets of §5, confirm Vercel Deployment Protection is
   off (or provide a bypass), confirm notification/database isolation.
3. **Closure requirement:** a green **Staging smoke tests** workflow run
   against the real provisioned staging environment, with the run URL recorded
   as completion evidence. Local rehearsal (this document §6) is not a
   substitute.
