# E12-04 — Staging Smoke-Test Suite: Execution Plan

**Status: PLANNING ONLY — no implementation has started.**
**Branch:** `qa/e12-04-staging-smoke-tests` (based on `origin/main` @ `856b51a`)
**Depends on:** E12-03 staging verification (branch `qa/e12-03-staging-verification`, report `docs/e12-03-staging-verification-report.md`)

Unknowns in this document are marked exactly one of: `BLOCKER`, `OWNER CONFIRMATION REQUIRED`, `SAFE ASSUMPTION`, `DEFERRED`.

---

## 1. Executive summary

E12-04 will deliver a small, deterministic, high-signal automated smoke suite that verifies the staging frontend, staging backend, database connectivity, one meaningful API contract, and frontend-to-staging (not production) wiring — runnable locally and from GitHub Actions.

The dominant fact discovered during planning: **no operational staging environment exists.** E12-03 verified that the expected staging frontend URL returns a Vercel `DEPLOYMENT_NOT_FOUND` 404 and the expected staging backend URL serves Railway's default placeholder, not the FastAPI app. Staging provisioning (E12-03A/B/C) is entirely owner-gated dashboard work.

Consequently this plan splits E12-04 into:

- **Implementable now:** the test code, configuration, npm script, GitHub Actions workflow, documentation, and negative-path validation (suite correctly fails against a dead URL). All of this can be authored and validated against a locally run backend/frontend pointed to by the same environment-variable interface the staging run will use.
- **Blocked until staging exists:** any green run against real staging, canonical URL confirmation, test-account creation, and CI secret configuration.

The recommended architecture reuses the repository's existing Playwright installation (no new framework): a dedicated `playwright.staging.config.js` with an API-level project (Playwright `request` fixture, no browser) and a browser project (page load, console errors, network-target assertion). Authenticated tests (Tier B) are included in the design but **skip automatically** unless dedicated staging test credentials are provided via environment/CI secrets.

## 2. Current repository state

- Branch `qa/e12-04-staging-smoke-tests` created from latest `origin/main` (`856b51a` — "Merge pull request #1013 … fix/backend-ci-required-check-name").
- Working tree clean of tracked changes. Pre-existing **untracked** local artifacts unrelated to this work were observed and left untouched: `backend/.coverage`, `backend/coverage.xml`, `supabase/`. They are not committed by this plan.
- Recent `main` history is E12 QA work: E12-01 backend test paths/CI (#1007/#1008), E12-02 backend coverage gate (#1012), backend required-check name fix (#1013).

## 3. E12-03 findings and dependencies

Source: `docs/e12-03-staging-verification-report.md` (commit `b18b462`, on branch `qa/e12-03-staging-verification`, **not merged to `main`**), plus `docs/staging-setup.md` (ISSUE-114), `docs/staging-environment-strategy.md` (ISSUE-113), `docs/environment-inventory.md` (ISSUE-112), `docs/staging-smoke-test-checklist.md` (the manual checklist this suite automates a subset of).

### 3.1 Verified staging facts (from E12-03 evidence)

| Question | Answer | Evidence |
| :--- | :--- | :--- |
| Staging frontend operational? | **No** | `https://staging-yesh-mishak.vercel.app/` → 404 `DEPLOYMENT_NOT_FOUND` |
| Staging backend operational? | **No** | `https://yesh-mishak-api-staging.railway.app/` → Railway placeholder ASCII art, not `{"status":"ok"}` |
| Staging database exists? | **No** | Requires a new Supabase project (E12-03A) |
| Staging Firebase project exists? | **No** | Requires a new Firebase project (E12-03A) |
| Staging Google OAuth client exists? | **No** | Requires a new GCP web client (E12-03A) |
| Canonical staging URLs | **Documented expectations only, never served the app**: frontend `https://staging-yesh-mishak.vercel.app`, backend `https://yesh-mishak-api-staging.railway.app` (from `.env.staging.example` files and `docs/staging-setup.md`) | `OWNER CONFIRMATION REQUIRED` — the real URLs are whatever the owner provisions |
| Staging isolated from production? | **Vacuously — staging does not exist.** Isolation requirements are documented (separate Supabase/Firebase/OAuth/JWT secret) but unproven | `docs/staging-setup.md` §3, §6–8 |
| Safe test data in staging? | **None exists** (no database). Seeding is a documented owner step (`staging-setup.md` §6: synthetic users, 10–15 seeded fields; seed script tracked as ISSUE-131) | `BLOCKER` for data-dependent assertions |
| Flows E12-03 verified manually | Only the *negative* facts above (URL probes). No application flow was verified — E12-03 stopped at "environment absent" | report §Evidence |
| Flows remaining unverified | Everything in `docs/staging-smoke-test-checklist.md` (frontend load, auth, fields, games, admin, notifications, logs) | report warning block |
| Could smoke tests send real notifications / create real accounts / pollute shared data? | **Not answerable until provisioning.** If the owner follows `staging-setup.md` (dedicated Firebase + dedicated Supabase), staging pushes cannot reach production tokens. The suite must still be designed read-only-first because misprovisioning (production credentials reused) is a real risk the suite itself should detect, not assume away | §5, §8 of this plan |

### 3.2 What E12-04 inherits

- E12-03A (Supabase/Firebase/OAuth provisioning), E12-03B (Railway backend), E12-03C (Vercel frontend) are **hard prerequisites for any green smoke run** — `BLOCKER` for execution, not for implementation.
- The manual checklist `docs/staging-smoke-test-checklist.md` defines the behaviors worth automating; this plan automates its Pre-Test, Frontend, Backend, and parts of Auth/Fields/Admin sections and explicitly defers the rest (§6).
- The E12-03 report is not on `main`. `SAFE ASSUMPTION`: treat its content as authoritative evidence anyway (it matches independent repo facts); no need to merge it for E12-04 to proceed.

## 4. Existing test infrastructure

| Layer | Framework | Config | Exact current command |
| :--- | :--- | :--- | :--- |
| Backend tests | pytest + pytest-cov (`backend/requirements-test.txt`) | `backend/tests/` (58 files), `conftest.py`; env stubs like CI | `cd backend && python -m pytest tests/ --cov=app --cov-fail-under=89 --cov-report=term-missing --cov-report=xml` (mirrors `.github/workflows/backend-tests.yml`) |
| Frontend unit tests | Node built-in test runner | `frontend/tests/*.test.js` | `cd frontend && npm run test:monitoring` / `test:analytics` / `test:auth-interceptor` / `test:errors` / `node --test tests/<file>` (no single aggregate script) |
| Frontend E2E | Playwright `@playwright/test` ^1.60 | `frontend/playwright.config.js` — testDir `./tests`, match `**/*.spec.js`, chromium only, baseURL `http://127.0.0.1:5173`, auto-starts Vite dev server (skippable via `PLAYWRIGHT_SKIP_WEB_SERVER`), CI retries 2 | `cd frontend && npm run test:e2e` (`playwright test`) |
| Linting | ESLint 10 | `frontend/eslint.config` | `cd frontend && npm run lint` |
| Type checking | None wired | `typescript` is a devDependency but no `tsc`/typecheck script exists | n/a |
| Build verification | Vite | `frontend/vite.config.js` | `cd frontend && npm run build` |

There is **no root `package.json`** — `frontend/` is the only npm workspace; backend dependencies are `backend/requirements.txt` / `requirements-test.txt`.

Reusable CI/infra patterns found in `.github/workflows/`:

- **Path filtering:** `dorny/paths-filter@v3` + always-created required check (`backend-tests.yml`).
- **workflow_dispatch-gated expensive jobs** and **explicit secret presence validation** with `::error::` annotations (`android-build-validation.yml`).
- **Artifact upload:** `actions/upload-artifact@v4` with `if-no-files-found: error`.
- **Secret-leak guard:** grep the built bundle for secret material (`android-build-validation.yml`) — pattern to reuse for log redaction validation.
- **Dependency caching:** `actions/setup-node@v5` with `cache: npm` + `cache-dependency-path: frontend/package-lock.json`; `actions/setup-python@v5` with `cache: pip`.
- **Retry/timeout conventions:** Playwright `retries: process.env.CI ? 2 : 0`; no repo-wide HTTP retry helper exists.
- No deployment workflows exist: production deploys are dashboard-driven (Vercel/Vercel Git + Railway on `main`); there is **no GitHub-visible deployment event for staging to chain from** today.

Existing helpers relevant to the suite: `frontend/src/api/client.js` (axios base-URL resolution — the exact mechanism the misconfiguration test must attack), backend error envelope (`app/main.py` handlers: `{"error": true, "code": …, "message": …}`), CORS assembly (`app/main.py:132-167`), and `backend/tests/test_cors.py` as a reference for expected CORS semantics. No existing test authenticates against a *deployed* environment; all current tests are local.

## 5. Proposed smoke-test scope

Design rules applied: read-only first; every test states component-attributing failure messages; nothing depends on third-party visual behavior; no test asserts on data that another run can change unless the assertion is shape-based, not value-based.

### Tier A — required on every staging smoke run (unauthenticated, no created data)

| ID | Test | Route / method | Auth | Expected | Contract asserted | Mutates? | Third-party deps |
| :-- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| A1 | Backend health | `GET {BACKEND}/` | No | 200 | body equals `{"status":"ok"}` | No | Railway |
| A2 | Backend↔DB connectivity + fields contract | `GET {BACKEND}/fields/` | No | 200 | JSON array; if non-empty, first item has `id`, `lat`, `lng`, `status`, `active_game`, `upcoming_games` keys | No (pure read) | Railway, Supabase |
| A3 | Error envelope contract | `GET {BACKEND}/fields/{random-uuid}` | No | 404 | body `{"error":true,"code":"FIELD_NOT_FOUND",…}` | No | Railway, Supabase |
| A4 | CORS for staging origin | `OPTIONS {BACKEND}/fields/` preflight with `Origin: {FRONTEND}` | No | 200 | `access-control-allow-origin` echoes the staging frontend origin | No | Railway |
| A5 | Frontend responds | `GET {FRONTEND}/` (HTTP, follow ≤ 1 same-host redirect) | No | 200 | `content-type: text/html`, body contains the app root mount markup | No | Vercel |
| A6 | Frontend boots without fatal JS error | Browser: load `{FRONTEND}/` | No | page renders app shell | no uncaught exception; no console error matching missing-env patterns; root element non-empty | No | Vercel (+ OSM tiles explicitly **not** asserted) |
| A7 | Frontend targets staging backend, not production | Browser: load `{FRONTEND}/`, record network | No | ≥ 1 request to `{BACKEND}` | every `/fields`-, `/games`-, `/auth`-prefixed request host == `{BACKEND}` host; **zero** requests to the production API host | No | Vercel, Railway |
| A8 | Public static route renders | Browser: `{FRONTEND}/privacy` (and `/terms`) | No | 200 | page body non-empty, no uncaught exception | No | Vercel |

Notes:
- A2 is the "backend can reach its staging database" probe: `GET /` (A1) never touches Supabase (`app/main.py:182-184`), so A1 alone cannot detect a broken DB — this is why both exist.
- A7 is the required production-misconfiguration detector (acceptance criterion 5). Production API host constant: the workflow passes `PRODUCTION_BACKEND_HOSTS` (comma-separated, e.g. `yesh-mishak-api.railway.app`) so the denylist is explicit, not guessed. `OWNER CONFIRMATION REQUIRED`: exact production API hostname(s) (environment-inventory.md says "or similar").
- Public **games** endpoints (`/games/active`, `/games/upcoming`, `/games/{id}`) are deliberately **excluded from Tier A**: they run `finish_expired_games` — a lazy write that transitions expired games (`backend/app/routers/games.py:377-410,473-480`). Idempotent and reconciling, but not read-only; they move to Tier B where mutation policy is explicit.

### Tier B — authenticated smoke tests (conditional; auto-skip without credentials)

Feasibility verdict: **feasible and safe only after** (a) a dedicated synthetic staging account exists (`staging-setup.md` §6 pattern, e.g. `user1@staging.local`) and (b) its credentials are injected via GitHub environment secrets. Manual-password login (`POST /auth/login`) exists, so **no Google interaction is needed** — this is what makes Tier B automatable at all. Until then every Tier B test is `test.skip()` with the reason printed.

| ID | Test | Route / method | Expected | Mutates? | Cleanup | Side-effect risk |
| :-- | :--- | :--- | :--- | :--- | :--- | :--- |
| B1 | Login with staging test account | `POST /auth/login` | 200, `TokenResponse` with non-empty `access_token` | Updates `last_login` only | none needed | none (no email, no push) |
| B2 | Authenticated user data | `GET /games/me` with B1 token | 200, JSON array | No | none | none |
| B3 | Notifications contract | `GET /notifications/unread-count` with B1 token | 200, numeric count field | No | none | rate-limited 30/60s/user — single call is safe |
| B4 | Invalid token rejected | `GET /games/me` with garbage Bearer | 401, `code: "AUTH_REQUIRED"` | No | none | none |
| B5 | Authorization boundary | `GET /admin/stats` with B1 (non-admin) token | 403, `code: "FORBIDDEN"` | No | none | none |

**Excluded from Tier B v1** (violate "no persistent data without deterministic cleanup" or side-effect rules):
- Create/join/leave/close game — mutating; requires a seeded field id, a cleanup contract (close+cancel semantics fire notification fan-out to field subscribers), and an owner-approved data policy. `DEFERRED` to a follow-up issue after the initial suite is green.
- `POST /notifications/test-push` — dispatches through FCM; external side effect by definition. `DEFERRED`/manual.
- `POST /auth/register` — creates accounts; forbidden by issue rules.

### Tier C — manual or deferred verification (documented, not automated)

Google native/browser sign-in (interactive device + consent screen), Android push delivery, all iOS behavior (also excluded by standing project rules), camera/photo upload, native App Links, Waze/external navigation handoff, real FCM push receipt, map-tile visual correctness (third-party OSM), admin mutation flows (no staging admin identity yet — `GET /admin/*` positive-path needs a dedicated staging admin account: `OWNER CONFIRMATION REQUIRED` whether to create one; B5 covers the protection boundary without it), email delivery flows (Resend; password reset / email verification — external side effect), Railway log cleanliness (dashboard-only today), `/__test/sentry-trigger` (exists on non-production by design but intentionally raises + reports to Sentry — noisy, not a health signal).

## 6. Explicit out-of-scope items

- Provisioning staging infrastructure (owned by E12-03A/B/C).
- Load, stress, soak, or performance testing.
- Visual regression testing.
- Mutating game lifecycle tests (deferred, see Tier B exclusions).
- Any production-environment testing; any test using production credentials or data.
- Making the suite a required `main` branch check (explicitly rejected — staging downtime must not block unrelated PRs; see §11).
- Modifying application behavior in any environment.

## 7. Recommended architecture

**Option comparison**

| Option | Verdict | Reasoning |
| :--- | :--- | :--- |
| 1. Lightweight API script (node/curl) | Rejected as sole solution | Cannot cover A6–A8 (browser boot, console errors, network-target assertion) — criterion 5 needs a browser or bundle inspection; no reporting/trace artifacts for free |
| 2. Playwright browser tests | Partially right | Browser coverage yes, but pure-API checks don't need a browser per test |
| 3. Pytest integration tests | Rejected | Backend-only; cannot verify frontend at all; would also create a second E2E stack alongside Playwright |
| **4. Playwright with two projects: API (request fixture, no browser) + browser** | **Recommended** | Single existing framework (no new dependency), built-in retries/timeouts/reporter/trace-screenshot artifacts, `request` fixture gives clean HTTP assertions, projects give tiering, CI patterns already exist in-repo |

**Concrete design**

- **Files:** `frontend/playwright.staging.config.js` (new config — deliberately separate so the default local E2E config and its dev-server bootstrapping are untouched); `frontend/tests/staging/api.smoke.spec.js` (A1–A4, B1–B5); `frontend/tests/staging/frontend.smoke.spec.js` (A5–A8); `frontend/tests/staging/helpers.js` (env parsing, URL normalization, prod-host denylist, skip logic).
- **Runner/commands:** npm script `"test:staging-smoke": "playwright test --config playwright.staging.config.js"`. Local: `cd frontend && STAGING_FRONTEND_URL=… STAGING_BACKEND_URL=… npm run test:staging-smoke`.
- **Environment-variable interface** (fail fast with a named error if required vars are missing):
  - `STAGING_FRONTEND_URL` (required), `STAGING_BACKEND_URL` (required), `PRODUCTION_BACKEND_HOSTS` (required for A7), `STAGING_TEST_USER_EMAIL`/`STAGING_TEST_USER_PASSWORD` (optional → Tier B skips when absent). No defaults are baked into code — URLs come only from env, so unconfirmed URLs never get committed.
- **Timeouts:** per-test 30s; API `expect` polls none (single-shot asserts); global run timeout via workflow (§11). First request of each target gets a warm-up: a bounded readiness poll (up to 90s, 5s interval) against `GET {BACKEND}/` and `GET {FRONTEND}/` in config `globalSetup`, so Railway/Vercel cold starts don't fail individual tests (`DEFERRED` tuning until real cold-start behavior is measurable).
- **Retries:** `retries: 1` in CI, 0 locally (flake here means staging is unhealthy — we want that signal, one retry only absorbs single-packet blips).
- **Failure messages:** every assert wrapped with component-prefixed messages (`[backend-health]`, `[db-connectivity]`, `[frontend-wiring]`, …) so the failing component is identifiable from the one-line summary (criterion 9).
- **Isolation/test-data strategy:** Tier A/B touch no created data; the suite is safe under parallel/repeated runs by construction. Browser project runs with a fresh context, no storage state.
- **Cleanup strategy:** nothing to clean (v1 contains no mutating tests). The deferred game-lifecycle tests must ship with create→verify→cancel-in-`finally` plus a sweep step before any of them are admitted.
- **CI execution:** §8 workflow. Artifacts: Playwright HTML report + traces/screenshots `on-first-retry`/failure, uploaded always-on-failure.
- **Secrets:** only via GitHub environment secrets; the test code never logs credential values; Playwright's HTTP logging is limited to method/URL/status (no auth-header dumps); a redaction validation step is in the testing matrix (§15).

## 8. Proposed files to create or modify (implementation phase — not in this commit)

| Path | Change |
| :--- | :--- |
| `frontend/playwright.staging.config.js` | New — staging config (projects `staging-api`, `staging-browser`; no `webServer`; reporter list + html; retries CI:1) |
| `frontend/tests/staging/api.smoke.spec.js` | New — Tier A API + Tier B tests |
| `frontend/tests/staging/frontend.smoke.spec.js` | New — Tier A browser tests |
| `frontend/tests/staging/helpers.js` | New — env contract, readiness poll, prod-host denylist |
| `frontend/package.json` | Modify — add `test:staging-smoke` script only |
| `.github/workflows/staging-smoke-tests.yml` | New — §11 design |
| `docs/staging-smoke-test-checklist.md` | Modify — annotate which checklist rows are now automated vs manual |
| `docs/qa/e12-04-staging-smoke-test-suite.md` (or extend this doc) | New — setup, local run, CI run, troubleshooting (criterion 14) |

Existing app code, existing tests, and existing workflows are **not** modified. `frontend/playwright.config.js` `testMatch: '**/*.spec.js'` would also pick up `tests/staging/*.spec.js` in local `npm run test:e2e` runs — the implementation must prevent that (add `testIgnore: '**/staging/**'` to the default config — a test-infrastructure-only edit — or place staging specs outside `tests/`; decision recorded in implementation step 2). `SAFE ASSUMPTION`: adjusting only `testIgnore` in the default config does not violate "do not modify existing functionality" since it restores today's effective behavior.

## 9. Test-data and cleanup strategy

- **v1 principle: the suite owns no data.** Tier A reads public data or asserts pure contracts; Tier B reads the test account's own (empty-or-not) data with shape-only assertions (e.g. "JSON array", not "array of length N").
- Seeded staging data (10–15 fields, per `staging-setup.md` §6 / ISSUE-131) improves signal (A2 non-empty branch, marker rendering) but is **not required** for the suite to pass: A2 asserts array-shape always and item-shape only when non-empty. Empty-staging behavior is therefore deterministic. `OWNER CONFIRMATION REQUIRED`: whether seeding will exist before first CI enablement (affects how much A6/A7 can additionally assert about map content — currently they assert boot and wiring, not markers).
- Dedicated staging test user: synthetic email (e.g. `smoke-user@staging.local` pattern from staging-setup.md), password stored only in GitHub environment secrets and the owner's vault. Never a real personal account (issue rule).
- Deferred mutating tests get admitted only with: unique-per-run naming (`smoke-<runId>`), cancel/close in `finally`, and a pre-run sweep deleting leftovers older than 24h — spec'd now so the future issue has an acceptance bar, implemented later.

## 10. Environment-variable and secret contract

| Name | Kind | Where set | Consumed by | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `STAGING_FRONTEND_URL` | GitHub Actions **variable** (staging environment) + local env | helpers.js, workflow | Public URL, not secret. `OWNER CONFIRMATION REQUIRED` (canonical value) |
| `STAGING_BACKEND_URL` | GitHub Actions **variable** (staging environment) + local env | helpers.js, workflow | Public URL, not secret. `OWNER CONFIRMATION REQUIRED` |
| `PRODUCTION_BACKEND_HOSTS` | GitHub Actions **variable** | A7 denylist | e.g. `yesh-mishak-api.railway.app` + any custom API domain. `OWNER CONFIRMATION REQUIRED` |
| `STAGING_TEST_USER_EMAIL` | GitHub Actions **secret** (staging environment) | Tier B | Synthetic account only |
| `STAGING_TEST_USER_PASSWORD` | GitHub Actions **secret** (staging environment) | Tier B | Rotatable without code change |

Explicitly **not** available to CI and never requested: `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET`, `FIREBASE_SERVICE_ACCOUNT_JSON`, any production credential, any Google OAuth client secret. The suite authenticates exclusively through the public login API, exactly like a user.

## 11. GitHub Actions design

| Item | Decision |
| :--- | :--- |
| Filename | `.github/workflows/staging-smoke-tests.yml` |
| Display name | `Staging smoke tests` |
| Job name | `staging-smoke` |
| Triggers | `workflow_dispatch` (primary, always). `schedule` (e.g. daily) — `DEFERRED`, enable only after ≥ 1 week of stable manual runs and owner approval (avoids alert fatigue from an immature environment). Post-deployment trigger: **not possible today** — staging deploys will be Vercel/Railway dashboard-driven with no GitHub deployment event; if the owner later adds a Railway/Vercel → GitHub webhook or `deployment_status` events, add that trigger then (`OWNER CONFIRMATION REQUIRED` whether such hooks will exist) |
| Concurrency | `group: staging-smoke`, `cancel-in-progress: false` (runs are cheap and sequential results are the point) |
| Timeout | `timeout-minutes: 15` job-level |
| Environment protection | Job runs with `environment: staging` so secrets are scoped and the owner can add reviewers later |
| Permissions | `permissions: contents: read` (repo convention) |
| Secrets/vars | Per §10; first step validates presence of required vars with `::error::` (android-build-validation.yml pattern) and prints which tier will run — values of secrets never echoed |
| Caching | `actions/setup-node@v5`, `cache: npm`, `cache-dependency-path: frontend/package-lock.json`; `npx playwright install --with-deps chromium` |
| Artifacts | `actions/upload-artifact@v4`, `if: failure()` upload of `frontend/playwright-report/` + `frontend/test-results/` (traces/screenshots), retention 14 days, `if-no-files-found: warn` |
| Failure visibility | Red workflow run + component-prefixed test names in the summary; report artifact for drill-down. Notification routing (e.g. to email) `DEFERRED` |
| Required branch check? | **No.** The suite tests a deployed environment whose availability is independent of any PR; making it required would let staging downtime block unrelated PRs. Revisit only if staging gains guaranteed availability SLOs (`DEFERRED`) |

## 12. Edge cases and mitigations

| Risk | Prevention / detection |
| :--- | :--- |
| Frontend deployed, backend down | A1/A2 fail with `[backend-*]` prefixes while A5 passes — component attribution is direct |
| Backend healthy, DB broken | A2 exists precisely for this (A1 never touches Supabase); expected failure mode: 500 + `DATABASE_ERROR`/`INTERNAL_SERVER_ERROR` envelope |
| Staging URL redirects unexpectedly | A5 allows ≤ 1 same-host redirect; cross-host redirect fails with the resolved chain printed |
| Vercel/Railway cold start | globalSetup readiness poll (≤ 90s) before any test; poll timings logged |
| Slow response → false timeout | 30s per-test + readiness poll + CI retry 1; persistent slowness should fail (that is signal, not flake) |
| Expired staging credentials | B1 fails distinctly (`[auth-login]` 401); runbook entry: rotate secret; Tier A remains green so outage vs credential decay is distinguishable |
| Missing GitHub secret | Tier B auto-skips with printed reason; missing required *vars* hard-fail in the validation step before tests run |
| Empty public staging data | A2 shape-asserts on empty arrays; no test requires non-empty data (§9) |
| Data changes between runs | Only shape/contract assertions on shared data; no value pinning |
| Duplicate users/games from tests | v1 creates nothing; deferred mutating tests carry unique naming + cleanup bar (§9) |
| Cleanup fails | n/a in v1; deferred design mandates `finally`-cleanup plus next-run sweep |
| Rate limiting | Single call per rate-limited endpoint per run (`/notifications/unread-count` limit 30/60s); retries capped at 1 |
| Google/Firebase down | No Tier A/B test touches Google or Firebase (manual login path chosen deliberately); Tier C documents them as manual |
| Map tile provider fails while app healthy | A6 does not assert tile loads; tile-request failures are ignored except as console noise filtered by pattern |
| HTML loads but JS crashes | A6 fails on uncaught exception / empty root while A5 passes — attribution clear |
| Frontend points at production | A7 hard-fails on any request to `PRODUCTION_BACKEND_HOSTS`; also fails if zero API calls hit `STAGING_BACKEND_URL` (silence ≠ pass) |
| 200 but contract violated | A2/A3/B1 assert bodies/error envelope, not just status (criterion 4) |
| Parallel runs mutate same entity | No mutation in v1 + workflow concurrency group serializes CI runs |
| Secrets in logs | Secrets only via env; no test logs request headers/bodies for auth calls; testing matrix includes a grep of run output + report artifact for the secret value (pattern from android-build-validation.yml); GitHub's native secret masking as backstop |
| Passes locally, fails on hosted runners | Same env-var interface both places; readiness poll absorbs egress latency; failure artifacts (trace) enable diagnosis; runbook documents IP-based differences (e.g. Vercel protection/allowlists — `OWNER CONFIRMATION REQUIRED` that staging has no Vercel Deployment Protection blocking anonymous GET, else runner access breaks) |

## 13. Owner-required manual actions

Implementation of the test code can proceed without all of these; **every green run against real staging is blocked** on items 1–6.

| # | Action | Why | Exact need | Where | Can implementation proceed without it? | Verification |
| :-- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | Provision staging infra (E12-03A/B/C) | No staging exists | Supabase + Firebase + OAuth projects, Railway service, Vercel project per `docs/staging-setup.md` §10 | Supabase/Firebase/GCP/Railway/Vercel dashboards | Yes (code) / No (execution) — `BLOCKER` for execution | `GET <backend>/` returns `{"status":"ok"}`; frontend URL serves the app |
| 2 | Confirm canonical staging frontend URL | Docs value never actually served the app | Final URL string | Vercel | Yes (env-driven design) | URL loads app shell |
| 3 | Confirm canonical staging backend URL | Same | Final URL string | Railway | Yes | A1 passes against it |
| 4 | Confirm production API hostname(s) for the A7 denylist | environment-inventory.md marks the Railway prod domain as "or similar" | Exact hostname list | Railway/DNS knowledge | Yes (var-driven) | Denylist var set; A7 meaningful |
| 5 | Create dedicated staging test user | Tier B without real personal credentials | Synthetic email + strong password, terms accepted, **email verified** (`/auth/login` may reject unverified accounts — owner should verify via staging DB flag or the verification flow) | Staging Supabase (seed/SQL or registration flow) | Yes — Tier B auto-skips | B1 returns 200 + token |
| 6 | Add GitHub `staging` environment with vars/secrets from §10 | CI needs the interface filled | 3 variables + 2 secrets | GitHub repo → Settings → Environments | Yes — workflow fails fast with clear error until set | Validation step green in a dispatch run |
| 7 | Create staging admin identity | Only if admin positive-path tests are wanted later | Admin-flagged synthetic user | Staging Supabase | Yes — B5 needs only a non-admin | `GET /admin/me` 200 for that account |
| 8 | Confirm staging notification isolation | Guarantee tests can never push to production users | Statement that staging Firebase project + staging DB contain no production tokens | Firebase/Supabase dashboards | Yes (v1 sends no pushes anyway) | Checklist §9 of staging-smoke-test-checklist.md |
| 9 | Confirm test-created data may be deleted in staging | Prerequisite for future mutating tests | Written policy (issue comment suffices) | — | Yes (v1 creates none) | Policy recorded in the follow-up issue |
| 10 | Confirm staging DB isolation from production | Safety root-invariant | Distinct `SUPABASE_URL` on Railway staging vs production service | Railway env vars | Yes | Owner attests; A-suite can't verify credentials directly by design |
| 11 | Decide deployment hooks / schedule enablement | Trigger strategy beyond manual dispatch | Railway/Vercel → GitHub notification or approval to add `schedule` | Dashboards / repo | Yes — `workflow_dispatch` suffices for v1 | Trigger fires and run appears |
| 12 | Approve environment protection settings | Whether `staging` environment requires reviewers | Choice: none vs required reviewer | GitHub Environments | Yes | Settings match decision |
| 13 | Confirm no Vercel Deployment Protection on staging (or provide bypass) | GitHub runners must reach the frontend anonymously | Protection disabled, or `VERCEL_AUTOMATION_BYPASS_SECRET` provided (would move to secrets) | Vercel | Yes | A5 from a hosted runner returns 200 |

## 14. Detailed ordered implementation steps (for the future implementation phase)

1. Create `frontend/tests/staging/helpers.js`: env contract (required/optional vars, hard error listing missing names), URL normalization, prod-host denylist parser, `tierBEnabled()` predicate.
2. Add `testIgnore: ['**/staging/**']` to `frontend/playwright.config.js` (test-infra-only change, keeps `npm run test:e2e` behavior identical) — verify by running the existing E2E list before/after (`npx playwright test --list`).
3. Create `frontend/playwright.staging.config.js`: no `webServer`; `globalSetup` readiness poll; projects `staging-api` (spec `api.smoke.spec.js`) and `staging-browser` (chromium, spec `frontend.smoke.spec.js`); `retries: process.env.CI ? 1 : 0`; reporters `list` + `html` (outputFolder `playwright-report`); trace/screenshot on failure.
4. Implement Tier A tests A1–A8 with component-prefixed titles/messages.
5. Implement Tier B tests B1–B5 behind `tierBEnabled()` skip.
6. Add `test:staging-smoke` script to `frontend/package.json`.
7. Validate locally against a **local** stack: run backend (`uvicorn app.main:app`) + built frontend preview, point `STAGING_*_URL` at them, confirm all Tier A pass and Tier B passes with a local test account; then negative-validate: point at a dead port and at a wrong-API build to confirm A1/A7 fail with the intended messages.
8. Author `.github/workflows/staging-smoke-tests.yml` per §11 (validation step → install/cache → `npx playwright install --with-deps chromium` → run → artifact upload on failure). Lint with `actionlint` if available locally; otherwise rely on a dispatch dry run once vars exist.
9. Write the suite documentation (setup, local run, CI run, troubleshooting/runbook incl. cold start, credential rotation, component attribution table).
10. Update `docs/staging-smoke-test-checklist.md` rows with `Automated (staging-smoke)` / `Manual` annotations.
11. Run full existing validation (backend pytest, frontend lint, `npx playwright test --list` for the default config) to prove no regressions.
12. Commit in reviewable slices (helpers/config → tests → workflow → docs); push and open PR only on explicit approval, per project workflow rules.
13. After owner completes §13 items 1–6: first real dispatch run against staging; capture the run URL + report artifact as completion evidence; fix environment-revealed issues; re-run to green.

## 15. Testing matrix (validation required before E12-04 implementation is called done)

| # | Validation | Exact command / method |
| :-- | :--- | :--- |
| 1 | Existing backend tests still pass | `cd backend && python -m pytest tests/ --cov=app --cov-fail-under=89 --cov-report=term-missing` |
| 2 | Existing frontend unit tests still pass | `cd frontend && npm run test:monitoring && npm run test:analytics && npm run test:auth-interceptor && npm run test:errors` |
| 3 | Existing E2E suite unaffected (list identical pre/post `testIgnore` change) | `cd frontend && npx playwright test --list` (diff against pre-change output) |
| 4 | Lint clean | `cd frontend && npm run lint` |
| 5 | New smoke suite passes against local stack | `cd frontend && STAGING_FRONTEND_URL=http://127.0.0.1:4173 STAGING_BACKEND_URL=http://127.0.0.1:8000 PRODUCTION_BACKEND_HOSTS=yesh-mishak-api.railway.app npm run test:staging-smoke` (backend via uvicorn, frontend via `npm run build && npm run preview`) |
| 6 | New smoke suite passes against real staging (locally) | Same command with real URLs — blocked on §13 items 1–4 |
| 7 | New smoke suite passes from CI | GitHub → Actions → Staging smoke tests → Run workflow — blocked on §13 item 6 |
| 8 | Negative failure validation | Point `STAGING_BACKEND_URL` at a dead port → expect A1/A2 fail with `[backend-*]`; build a frontend with production `VITE_API_URL` locally → expect A7 fail with `[frontend-wiring]` |
| 9 | Secret-redaction validation | Run Tier B locally with a known sentinel password; grep the full stdout + `playwright-report/` + `test-results/` for the sentinel → zero hits |
| 10 | Timeout/retry behavior | Simulate slow backend (e.g. local proxy adding > test-timeout delay) → verify single retry then clean failure, readiness-poll logs present |
| 11 | Cleanup verification | n/a for v1 (no mutations) — asserted by review that no spec issues POST/PATCH/DELETE except `POST /auth/login` |
| 12 | Manual frontend staging verification | Load staging URL in a browser, run `docs/staging-smoke-test-checklist.md` §2 manually once — blocked on §13 item 1 |
| 13 | Regression of existing workflows | Confirm no `.github/workflows/*` file besides the new one changed (`git diff --name-only origin/main -- .github/workflows`) |

## 16. Acceptance criteria (binary)

1. `cd frontend && npm run test:staging-smoke` (documented env vars) runs the suite locally — command exists and is documented.
2. `.github/workflows/staging-smoke-tests.yml` runs the suite via `workflow_dispatch` against staging.
3. Suite verifies frontend availability (A5/A6) and backend availability (A1) in every run.
4. Suite validates ≥ 1 meaningful API contract beyond HTTP 200: A2 (fields shape) and A3 (error envelope) both qualify.
5. Suite detects frontend-to-production misconfiguration (A7 denylist + required-staging-target assertion).
6. All v1 tests are deterministic and safe to repeat (no created data; shape-only shared-data assertions; serialized CI concurrency).
7. No production credentials or production data are used anywhere (only §10 interface; Tier B account is synthetic staging-only).
8. No secrets committed; secret-redaction validation (matrix #9) passes; workflow echoes no secret values.
9. Every failure message is component-prefixed (`[backend-health]` etc.) identifying the affected component.
10. CI uploads Playwright report + traces/screenshots on failure (14-day retention).
11. v1 contains zero mutating tests (beyond `POST /auth/login`'s `last_login` touch); mutating tests are explicitly excluded and their admission bar documented (§9).
12. Matrix #1–#4 pass (existing tests, unit tests, E2E list, lint unchanged/green).
13. Tier C items are documented as manual-only in the suite docs and the annotated checklist — none claimed automated.
14. Suite documentation covers setup, local execution, CI execution, troubleshooting.
15. Completion evidence per §17 is produced.

## 17. Completion-evidence requirements (for the implementation phase)

- Commit hashes of the implementation slices and the PR URL.
- Local run transcript: Tier A green against local stack; Tier B green with local account; both negative validations failing as designed (matrix #5, #8).
- Redaction grep output (matrix #9) showing zero sentinel hits.
- Once unblocked: CI run URL of a green `workflow_dispatch` execution against real staging + the report artifact; screenshot or HTML report excerpt showing per-test component prefixes.
- `git diff --name-only origin/main` proving only the files in §8 changed.
- Annotated `staging-smoke-test-checklist.md` diff.

## 18. Definition of Ready checklist

| Item | State |
| :--- | :--- |
| Repository analyzed; branch from latest `origin/main` | **READY** |
| E12-03 evidence located and reviewed | **READY** |
| Existing test frameworks inventoried; no new framework needed (Playwright reuse) | **READY** |
| Backend/frontend contracts for candidate tests mapped from code | **READY** |
| Smoke scope tiered with mutation/side-effect analysis | **READY** |
| Architecture, file layout, commands, env interface defined | **READY** |
| CI workflow design defined incl. trigger, concurrency, artifacts, secret handling | **READY** |
| Edge cases enumerated with mitigations | **READY** |
| Validation matrix and acceptance criteria defined | **READY** |
| Staging environment operational | **BLOCKED** — E12-03A/B/C owner provisioning (§13 #1) |
| Canonical staging URLs confirmed | **BLOCKED** — owner (§13 #2–3) |
| Production API hostname denylist confirmed | **BLOCKED** — owner (§13 #4) |
| Staging test user exists | **BLOCKED** — owner (§13 #5); implementation proceeds, Tier B skips |
| GitHub `staging` environment vars/secrets configured | **BLOCKED** — owner (§13 #6) |
| Vercel deployment-protection status for staging known | **BLOCKED** — owner (§13 #13) |
| Data-deletion policy for future mutating tests | **BLOCKED** — owner (§13 #9); not needed for v1 |

**Verdict:** implementation of the suite (code + workflow + docs, validated against a local stack including negative paths) is READY to start upon approval. A green run against real staging is BLOCKED on owner provisioning.

## 19. Open blockers and unresolved questions

1. `BLOCKER` — No staging environment exists (E12-03A/B/C). Everything execution-related waits on this.
2. `OWNER CONFIRMATION REQUIRED` — Canonical staging frontend/backend URLs (docs values are placeholders that have never served the app).
3. `OWNER CONFIRMATION REQUIRED` — Exact production API hostname(s) for the misconfiguration denylist.
4. `OWNER CONFIRMATION REQUIRED` — Staging test user creation + whether its email-verification gate will be satisfied via seed SQL or the verification flow.
5. `OWNER CONFIRMATION REQUIRED` — Whether a staging admin identity should exist (enables future admin positive-path tests; not needed for v1).
6. `OWNER CONFIRMATION REQUIRED` — Deployment-hook availability (Railway/Vercel → GitHub) and whether scheduled runs should be enabled after the burn-in week.
7. `OWNER CONFIRMATION REQUIRED` — Vercel Deployment Protection status for the staging project (hosted runners need anonymous GET or a bypass secret).
8. `OWNER CONFIRMATION REQUIRED` — Whether staging will be seeded (ISSUE-131) before CI enablement.
9. `DEFERRED` — Mutating game-lifecycle smoke tests (admission bar in §9), scheduled runs, failure notification routing, required-check status (rejected for now).
10. `SAFE ASSUMPTION` — E12-03 report content is authoritative despite living on an unmerged branch; `testIgnore` addition to the default Playwright config is test-infrastructure-only and permissible.
