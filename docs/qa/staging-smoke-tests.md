# Staging Smoke-Test Suite (E12-04)

Automated, read-only smoke tests for the deployed staging environment.
Approved plan: [e12-04-staging-smoke-test-plan.md](e12-04-staging-smoke-test-plan.md).

> **Status: VALIDATED against the real environment.** The project's
> staging-equivalent environment is the **`dev` environment**
> (frontend `https://dev-yesh-mishak.vercel.app`, backend
> `https://yeshmishak-dev.up.railway.app`, isolated Supabase project
> `yesh_mishak_dev`; GitHub Environment **`dev`**). The suite ran green from
> GitHub Actions against it on 2026-07-24 — Tier A passed in full, Tier B
> skipped by design (no dedicated test credentials configured yet):
> https://github.com/sandrusipredicts/yesh_mishak/actions/runs/30122383892
> See [docs/e12-03-staging-verification-report.md](../e12-03-staging-verification-report.md)
> for the canonical environment-verification record. (Historical note: an
> earlier phase of E12-03 found the originally documented placeholder staging
> URLs non-operational; that finding is superseded and retained in the
> canonical report's historical section only.)

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

Canonical values (owner-confirmed, configured in the GitHub `dev`
environment):

- `STAGING_FRONTEND_URL` = `https://dev-yesh-mishak.vercel.app`
- `STAGING_BACKEND_URL` = `https://yeshmishak-dev.up.railway.app`

The variable names keep their `STAGING_` prefix — `dev` is this project's
staging-equivalent environment. Credentials are never written in code or docs.

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

- Uses the GitHub **`dev` environment**: URLs from environment
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

## 13. Closure record (E12-04)

1. **E12-03 dependency — satisfied.** The canonical environment-verification
   record is
   [docs/e12-03-staging-verification-report.md](../e12-03-staging-verification-report.md):
   the `dev` environment (dev Vercel frontend, dev Railway backend, isolated
   Supabase project `yesh_mishak_dev`) is provisioned and operational.
   (Historical: an earlier E12-03 draft on the unmerged branch
   `qa/e12-03-staging-verification`, commit `b18b462`, described the
   then-unprovisioned placeholder URLs; it is superseded.)
2. **Closure requirement — satisfied.** Green **Staging smoke tests**
   `workflow_dispatch` run against the real `dev` environment (2026-07-24):
   https://github.com/sandrusipredicts/yesh_mishak/actions/runs/30122383892
   — Tier A passed in full (backend health, DB connectivity, API contract,
   CORS, frontend availability/boot/wiring, production denylist, legal
   routes); Tier B skipped by design (credentials not configured). E12-04 does
   **not** claim Tier B passed, and does **not** claim push/Firebase isolation
   was validated.
3. **Optional follow-up (not a closure blocker):** enable Tier B by creating
   the dedicated synthetic dev test account and adding
   `STAGING_TEST_EMAIL`/`STAGING_TEST_PASSWORD` to the GitHub `dev`
   environment secrets.

## 14. Final status

```text
Implementation: COMPLETE
Local validation: COMPLETE
Real staging validation: COMPLETE
E12-04 closure readiness: READY
```

Tier B authenticated coverage remains optional follow-up work and is not a
blocker for E12-04 closure.
