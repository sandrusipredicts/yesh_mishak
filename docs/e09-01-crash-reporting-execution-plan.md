# E09-01 — Crash Reporting & Error Monitoring: Execution Plan

Status: **Planning artifact only.** No production code, dependency, or configuration was changed to produce this document. See [Confirmations](#49-confirmations) at the end.

Branch: `codex/e09-01-crash-reporting-plan` (created from `main` at commit `04af30d`).
Recommended future implementation branch (not created): `codex/e09-01-crash-reporting`.

---

## 1. Executive Summary

The roadmap's claim of "0% done — entirely open, 13 backlog issues, no code" is **accurate for crash/error *monitoring*** but understates the amount of adjacent groundwork already in place. The repository has **zero crash-reporting or error-monitoring SDK** anywhere (frontend, Android, backend) — confirmed by repo-wide search and corroborated by three existing planning docs ([`docs/production-readiness-checklist.md`](production-readiness-checklist.md) `MONITOR-001`, [`docs/technical-debt-inventory.md`](technical-debt-inventory.md) `TD-OPS-001`, [`docs/global-error-handling-strategy.md`](global-error-handling-strategy.md)) that already flag this as an open, accepted gap. However, several *prerequisites* for a good implementation already exist: a React Error Boundary (partial), a disciplined manual redaction convention in backend logs, a safe global FastAPI exception handler, Firebase infrastructure already wired for Android push (but not Crashlytics), and Capacitor native-platform detection used consistently.

Also several prerequisites are **missing** and must be built as part of (or immediately before) implementation: no app version/commit-SHA is exposed to any layer, no request/correlation-ID mechanism exists, Android release builds are unsigned and unminified, and no CI step uploads any symbol/mapping/source-map artifact anywhere.

**Recommendation: Option A — Sentry across all layers** (frontend, Android, backend), with Android-native crash/ANR coverage delivered via the official `sentry-android` SDK (which bundles NDK native-crash capture and built-in ANR detection), not Firebase Crashlytics. Firebase Crashlytics is deferred as a **documented future upgrade**, to be revisited if/when the app reaches Play Store distribution and Android Studio App Quality Insights becomes operationally valuable. Full reasoning in [§11](#11-recommended-architecture).

Readiness decision: **READY WITH BLOCKERS** — see [§48](#48-final-readiness-decision).

---

## 2. Current Repository State

- Local `main` was fast-forwarded from `3d6d393` to `04af30d` (origin/main) before branching; the fast-forward touched only Android Google-auth validation files, not `frontend/.env`, so the pre-existing local `frontend/.env` modification was preserved untouched throughout.
- Working tree at branch-creation time: only `frontend/.env` modified (untracked change, pre-existing, unrelated to this task — preserved, not staged, not committed).
- This document is the only change introduced by this task.

## 3. Existing Frontend Error Handling

- **Bootstrap** (`frontend/src/main.jsx`): wraps `<App />` in a single top-level `ErrorBoundary` — no `window.onerror`, no `unhandledrejection` listener, no monitoring SDK init.
- **Error Boundary** (`frontend/src/components/ErrorBoundary.jsx`): implements `getDerivedStateFromError` only — **no `componentDidCatch`**, so the caught error is silently discarded (never logged, never reported anywhere). Shows a generic fallback with a reload button; no stack trace exposed to the user (good baseline for UX, but currently a black hole for diagnosability). No nested/route-level boundaries (Map, Admin, Onboarding, Notifications all share the one top-level boundary).
- **Routing**: hand-rolled via `window.location.pathname`/`history.pushState`, no router library — relevant because a monitoring SDK's route-change breadcrumb integration will need custom wiring rather than a router adapter.
- **API client** (`frontend/src/api/client.js`): single Axios instance; response interceptor only handles 401→session-cleanup; no centralized error normalization for reporting purposes. Several call sites `console.warn`/`console.info` raw Axios error objects, which carry `error.config.headers.Authorization` — a scrubbing requirement if a monitoring SDK's console-breadcrumb integration is enabled (see [§23](#23-privacy-and-redaction-policy)).
- **Auth error mapping** (`frontend/src/api/authErrorMapping.js`): already classifies native/social-login failures into kinds including `cancelled` (Google login cancellation) — directly reusable to decide what should/shouldn't be reported ([§22](#22-expected-error-filtering-policy)).
- **Location** (`frontend/src/utils/locationFailure.js`, `frontend/src/api/locationService.js`): exact GPS coordinates are **never** currently logged to console (verified by repo-wide grep) — good baseline to preserve.
- **No centralized logger** exists; ~14 files call `console.*` directly with ad hoc prefixes. Some debug-tagged `console.info` calls (e.g. `[E04-01 PUSH DEBUG]`) run unconditionally in production, not just dev.
- **No source maps** are generated (`frontend/vite.config.js` does not set `build.sourcemap`; Vite's default is `false`).
- **No app version/build/commit identifier** is exposed to the frontend bundle anywhere (no Vite `define`, no `import.meta.env.VITE_*` version var, `@capacitor/app`'s `App.getInfo()` is never called despite the plugin being installed).
- **No tests** cover the Error Boundary's fallback behavior.

## 4. Existing Android Crash Handling

- Android project lives at `frontend/android/` (Capacitor-managed), `applicationId com.yeshmishak.app`.
- `com.google.gms.google-services` plugin is applied (classpath in root `build.gradle`, applied in `app/build.gradle`) — **only** to support native FCM registration for `@capacitor/push-notifications`. **No Firebase BoM, no `firebase-crashlytics`, no `firebase-analytics`, no `firebase-perf`, no Sentry Android SDK** exist anywhere.
- No custom `Application` subclass exists — `MainActivity` is a bare, empty `BridgeActivity` subclass. This means there is currently **no process-wide initialization hook** for any SDK; one must be added.
- `google-services.json` exists (git-ignored, materialized at build/CI time from a base64 secret) — the plugin plumbing needed for any Firebase-family product (including Crashlytics) is already in place if that path is chosen later.
- Release build type: `minifyEnabled false`, **no `signingConfig` assigned to `release` at all** (only a `debug`-scoped CI keystore config exists). Practically, `assembleRelease`/`bundleRelease` would produce an unsigned, unminified artifact today.
- `versionCode`/`versionName` are hardcoded (`1` / `"1.0"`) with no CI-driven bump mechanism.
- CI (`android-build-validation.yml`) builds **debug APK only**, gated to manual `workflow_dispatch` (PRs never build an installable artifact) — no AAB, no release build, no mapping-file step, no Play Store upload.
- `capacitor.config.ts` sets `loggingBehavior: 'none'` explicitly to keep SocialLogin/SecureStorage values out of native logs — this convention should be preserved by any new SDK's native logging config.

## 5. Existing Backend Error Handling

- FastAPI app (`backend/app/main.py`) already has a **safe, well-placed integration point**: a catch-all `@app.exception_handler(Exception)` (`app/main.py:75-85`) that calls `logger.exception(...)` (full traceback) and returns a fixed, non-leaking `500` body — never echoes request body/headers to the client or the log line. This is the natural hook for `sentry_sdk.capture_exception` / `before_send` wiring.
- A consistent structured-error convention already exists (`app/errors.py::raise_api_error`, consumed by `app/main.py`'s `HTTPException`/`RequestValidationError` handlers) producing `{"error": true, "code": ..., "message": ...}` — this `code` field is directly reusable to decide fatal vs. filtered-expected classification ([§22](#22-expected-error-filtering-policy)).
- Auth failures (401/403) already fail closed with structured codes (`AUTH_REQUIRED`, `AUTH_INVALID`, `TOKEN_REVOKED`, `ACCOUNT_RESTRICTED`, `FORBIDDEN`) via `app/auth/dependencies.py` — these are expected-error candidates for exclusion from fatal reporting.
- Existing sanitization discipline: `app/services/job_runs.py::sanitize_error_message/sanitize_error_type` already scrub exception text before persistence; `app/auth/google.py` logs only boolean presence flags for claims, never raw values. This convention should be extended to (not replaced by) the monitoring SDK's own scrubbing.
- **Gaps**: no centralized logging config (`dictConfig`), no environment field (`dev`/`staging`/`prod`) anywhere in `Settings`, no request/correlation-ID mechanism, no `railway.json`/`nixpacks.toml` in-repo (deploy is Railway-console-configured), no dedicated `/health` route (only `GET /` doubles as one), `app.main:15` hardcodes `version="0.1.0"` with no CI-driven bump.

## 6. Existing CI/CD and Release Metadata

- 5 workflows total: `android-build-validation.yml`, `ios-debug-build-validation.yml`, `ios-startup-flow-validation.yml`, `ios-xcode-validation.yml`, `password-reset-postgres.yml`. **No frontend-only workflow, no backend-deploy workflow** — Vercel and Railway both deploy via their own native git integration outside GitHub Actions (no `vercel.json` build/env block, no `railway.json`/`railway.toml` in-repo).
- **No workflow exposes `GITHUB_SHA`** to any build; no Vite `define`, no Android `buildConfigField`, no generated version file anywhere.
- Frontend `package.json` version (`0.0.0`), Android `versionName`/`versionCode` (`"1.0"`/`1`), backend `version="0.1.0"` are all static, manually-set placeholders with no CI auto-bump.
- No git tags exist in the repo (`git tag -l` empty) — no release-tagging convention today.
- Branching convention observed: `codex/eXX-YY-...`, `feature/eXX-YY-...`, `fix/...` — commit messages follow Conventional Commits with an epic/task tag, e.g. `fix(e08-02): ...`.
- Artifact retention: no workflow sets `retention-days` (defaults to GitHub's 90-day org default).
- Confirmed via repo-wide search: no `sentry-cli`, `@sentry/*`, `crashlytics`, `dSYM` upload step exists anywhere in CI, gradle, or `package.json` scripts.

## 7. Existing Firebase State

- Firebase is used **exclusively for push notifications**: `frontend/src/firebaseMessaging.js` (web push, `firebase/app` + `firebase/messaging` only), `backend/app/services/firebase_push.py` (Firebase Admin SDK, server→device push), and the Android `google-services.json` + `com.google.gms.google-services` plugin (native FCM registration for the Capacitor push plugin).
- **No Firebase Analytics, Performance Monitoring, or Crashlytics** product is enabled, referenced, or configured anywhere — confirmed via repo-wide search and via the absence of the Crashlytics/Performance Gradle plugins in both root and app `build.gradle`.
- This means adopting Crashlytics would be additive to existing Firebase infrastructure (the `google-services.json` plumbing already exists) but would still require: enabling the product in the Firebase console, adding the Crashlytics Gradle plugin + BoM + dependency, adding release signing + `minifyEnabled true` (to get a mapping file worth having), and a new CI mapping-upload step — none of which exist today.

## 8. Monitoring Gaps (Summary)

| Layer | Fatal-error capture | Non-fatal capture | Symbolication | Release identity | Correlation |
|---|---|---|---|---|---|
| Frontend (React/Capacitor) | Discarded silently (Error Boundary has no `componentDidCatch`) | None | No source maps generated | No version exposed to bundle | No request ID |
| Android native | None (no crash handler installed) | None | Release unminified, unsigned, no mapping upload | `versionName`/`versionCode` hardcoded | N/A |
| Backend (FastAPI) | Logged locally only (Railway logs); nothing forwarded | None | N/A (Python) | `version="0.1.0"` hardcoded, no commit tie | No request ID |
| CI/CD | N/A | N/A | No upload pipeline of any kind | No SHA/tag exposed anywhere | N/A |

## 9. Architecture Options

**Option A — Sentry across all layers.** React/Capacitor JS via `@sentry/react` (or `@sentry/capacitor` wrapping it), Android native via `io.sentry:sentry-android` (bundles NDK native-crash + built-in ANR watchdog), FastAPI via `sentry-sdk[fastapi]`. One vendor, one dashboard, shared release identifier natively supported across all three SDKs.

**Option B — Firebase Crashlytics only.** Covers Android native crashes/ANRs/non-fatals and Play Console integration, but has **no JavaScript/WebView error capture and no backend capture** — rejected outright per the task's own instruction not to recommend Crashlytics-only unless JS/backend visibility is proven adequate elsewhere, which it is not (this app's primary UI is 100% React inside a Capacitor WebView; a Crashlytics-only setup would report zero JS errors, i.e., would miss the majority of user-facing failures).

**Option C — Hybrid: Crashlytics (Android native) + Sentry (frontend + backend).** Most "complete" on paper, but doubles operational surface for a project with zero prior monitoring investment: two dashboards, two alerting configurations, two consent/privacy postures to document, a duplicate-event risk for errors that surface both as a JS exception inside the WebView *and* propagate to a native crash (rare here since there's no native-Capacitor-plugin crash path found in the audit, but the risk exists for e.g. a `@capacitor/geolocation` native crash), and a second SDK integration (Crashlytics Gradle plugin, BoM, mapping upload, Firebase project setup) on top of everything Option A already requires.

**Option D — Other.** Considered: Bugsnag, Rollbar, self-hosted GlitchTip (Sentry-protocol-compatible OSS). No repository or operational evidence supports these over Sentry (no existing account, no cost constraint documented that favors self-hosting, no team familiarity signal) — not pursued further.

## 10. Architecture Comparison Matrix

| Criterion | A: Sentry-only | B: Crashlytics-only | C: Hybrid |
|---|---|---|---|
| React/JS error coverage | Yes | No | Yes (via Sentry half) |
| Android native crash coverage | Yes (`sentry-android` + bundled NDK) | Yes (native, OS-level) | Yes (Crashlytics) |
| Android ANR coverage | Yes (SDK-level ANR watchdog, 5s threshold) | Yes (OS-level, Play Console-integrated) | Yes (Crashlytics) |
| Backend (FastAPI) coverage | Yes | No | Yes (via Sentry half) |
| Single dashboard / single release identifier | Yes | N/A | No — two dashboards, manual release-tag parity |
| Duplicate-event risk | None (one vendor) | N/A | Present, needs ownership rules |
| New infra required | Sentry projects only | Firebase Crashlytics enablement | Both |
| CI complexity added | 1 source-map + 1 mapping upload path (same vendor tooling) | 1 mapping upload path (Firebase CLI) | 2 separate upload paths, 2 credential sets |
| Cost at early-stage volume | Sentry free tier (5k events/mo shared across projects) likely sufficient | Free/unlimited | Sentry free tier + free Crashlytics |
| Play Console App Quality Insights | No | Yes | Yes | 
| Fit for current project stage (no Play Store release yet, no release signing, no versioning strategy) | Best — one thing to stand up correctly | Poor — leaves JS/backend blind | Over-engineered for current maturity |

## 11. Recommended Architecture

**Option A — Sentry across React/Capacitor, Android native, and FastAPI.**

Reasoning:
1. **Sentry alone does provide sufficiently reliable Android native crash and ANR coverage for this project's current stage.** `io.sentry:sentry-android` transitively bundles `sentry-android-ndk` for native (JNI) crash capture and includes a built-in ANR watchdog (Android's own 5-second main-thread-block heuristic) that reports independently of Google Play — this project isn't on the Play Store yet (no release signing, `versionCode 1`), so Crashlytics' main incremental advantage (Play Console App Quality Insights integration) has no current audience.
2. **Single vendor eliminates the duplicate-event and dual-ownership problems** the task explicitly asks to validate for the hybrid option — there is no existing Crashlytics/Firebase-Analytics investment to build on (Firebase here is push-notification-only), so choosing Crashlytics for Android would mean introducing a *second* full monitoring stack from zero, not extending an existing one.
3. **Lower operational overhead matches project maturity**: one dashboard, one alert configuration, one release-identifier format understood by all three SDKs (Sentry's `release` field is a plain string shared verbatim across `@sentry/react`, `sentry-android`, and `sentry-sdk` — no cross-vendor mapping needed).
4. **Cost**: Sentry's free/developer tier (~5k errors/month, 1 project set with environments) is adequate for an early-stage app with no production user base yet; Crashlytics is also free but its cost isn't the deciding factor — operational simplicity is.
5. **Clear upgrade path preserved**: nothing here precludes adding Crashlytics later once the app ships to Play Store and App Quality Insights becomes valuable — that would be a scoped follow-up (see [§45](#45-related-follow-up-tasks)), not a rebuild.

## 12. Rejected Alternatives

- **Option B (Crashlytics-only)** — rejected: zero JS/WebView and zero backend coverage; the audit confirms the primary UI is 100% React-in-Capacitor and errors there would go completely dark.
- **Option C (Hybrid)** — rejected for *now*: doubles integration/CI/ownership surface without a corresponding benefit at this project's current stage (no Play Store presence, no existing Firebase-Analytics/Crashlytics investment, no evidence current native-crash volume justifies the OS-level advantage Crashlytics has over Sentry's NDK integration). Documented as a valid future evolution ([§45](#45-related-follow-up-tasks)), not a rejected-forever path.
- **Option D (Bugsnag/Rollbar/self-hosted GlitchTip)** — rejected: no repository or stated-cost evidence favors any of these over Sentry; introduces vendor-evaluation work with no offsetting benefit.

## 13. Exact Scope Included

- Architecture selection and reasoning (this document).
- Frontend, Android, and backend **fatal + defined non-fatal** error reporting design (not implemented yet).
- Privacy/redaction policy, user-context policy, environment/release strategy.
- Source-map and Android-mapping symbolication strategy.
- File-by-file implementation plan for a future `codex/e09-01-crash-reporting` branch.
- Test plan (unit, component, backend, Android, CI) — plan only, no test code written.
- Manual verification procedures (frontend, Android, backend, dashboard).
- Full list of owner actions required outside the repository.
- iOS requirements documented and explicitly deferred.

## 14. Exact Scope Excluded

- Any SDK installation, dependency addition, or Gradle/package.json change.
- Any Sentry/Firebase external project creation.
- Full performance monitoring / APM tracing (frontend transaction tracing, backend request tracing) — **excluded from E09-01**, proposed as a separate follow-up ([§45](#45-related-follow-up-tasks)). Sentry's crash SDKs can technically also do performance monitoring, but enabling `tracesSampleRate` is a distinct, separately-scoped decision (cost, sampling policy, dashboards) and must not be silently bundled into crash-reporting rollout.
- Product/business analytics (funnels, retention, session replay) — explicitly out of scope; not to be conflated with crash reporting.
- Native iOS Sentry Cocoa integration, physical-iPhone verification — deferred to the iOS phase ([§46](#46-deferred-ios-requirements)).
- Android ANR *controlled reproduction testing* on a production build — deferred as unsafe; addressed only via SDK-level automatic detection, not a manual production ANR drill.

## 15. Frontend Reporting Design

- **SDK**: `@sentry/capacitor` (wraps `@sentry/react`, adds Capacitor-native context bridging on Android/iOS) initialized in a new dedicated module `src/monitoring/sentry.js`, called once from `src/main.jsx` before `createRoot(...).render(...)`.
- **Error Boundary integration**: add `componentDidCatch(error, info)` to the existing `src/components/ErrorBoundary.jsx`, calling `Sentry.captureException(error, { contexts: { react: { componentStack: info.componentStack } } })` guarded by an "is Sentry initialized" check (so a missing DSN never throws — see [Edge Case 1](#41-edge-case-matrix)).
- **Global handlers**: `Sentry.init()` auto-installs `window.onerror` and `unhandledrejection` hooks (`onuncaughtexception`/`onunhandledrejection` integrations) — no separate hand-written global handler needed; this closes the two confirmed gaps in [§3](#3-existing-frontend-error-handling).
- **Axios integration**: extend `src/api/client.js`'s response interceptor to selectively call `Sentry.captureException`/`captureMessage` only for responses classified as unexpected per [§22](#22-expected-error-filtering-policy) — expected 401/403/404/422/429 are never forwarded.
- **Capacitor web-only fallback**: when `Capacitor.isNativePlatform()` is false (plain browser/Vercel web deployment), `@sentry/capacitor` transparently falls back to pure `@sentry/react` behavior — no separate code path needed (addresses Edge Case 46).

## 16. Android Reporting Design

- **SDK**: `io.sentry:sentry-android` (Gradle dependency in `frontend/android/app/build.gradle`), bundling NDK native-crash capture and the built-in ANR watchdog. No Firebase Crashlytics plugin.
- **Initialization**: requires creating a new `Application` subclass (none exists today) at `frontend/android/app/src/main/java/com/yeshmishak/app/YeshMishakApplication.java`, calling `SentryAndroid.init(this) { options -> ... }`, and registering it in `AndroidManifest.xml` (`android:name=".YeshMishakApplication"`). This is the single required native code change.
- **Release build prerequisites**: this task also surfaces (but does not fix) that `release` currently has no signing config and `minifyEnabled false` — both should be resolved as part of implementation (not this planning task) so that (a) Sentry's `release`/`dist` tagging is meaningful on a real signed artifact and (b) a mapping file exists for readable de-obfuscated Kotlin/Java traces where R8 is later enabled. If R8 stays disabled, Sentry still symbolicates fine (nothing to de-obfuscate) — enabling R8 is a separate, optional hardening step, not a blocker for crash reporting itself.
- **ANR reporting**: Sentry's `AnrIntegration` is enabled by default with a 5-second threshold, matching Android's own ANR definition — sufficient for the map/WebView/location/plugin-hang concerns raised in the task.

## 17. Backend Reporting Design

- **SDK**: `sentry-sdk[fastapi]` (Python), initialized once in `backend/app/main.py` near the top (before route registration), guarded by "only if `SENTRY_DSN` env var is set" (see [Edge Case 1](#41-edge-case-matrix)).
- **Integration point**: Sentry's FastAPI/Starlette integration auto-instruments unhandled exceptions; additionally, wire the existing catch-all `@app.exception_handler(Exception)` (`app/main.py:75-85`) to also call `sentry_sdk.capture_exception(exc)` right where it already calls `logger.exception(...)` — this reuses the one safe hook identified in [§5](#5-existing-backend-error-handling) rather than adding new middleware.
- **Filtering**: use Sentry's `before_send` hook to drop events for status codes explicitly classified as expected ([§22](#22-expected-error-filtering-policy)) — `RequestValidationError` (422) and structured `raise_api_error` calls with codes `AUTH_REQUIRED`, `AUTH_INVALID`, `FORBIDDEN`, `NOT_FOUND`, `CONFLICT`, `VALIDATION_ERROR`, `RATE_LIMITED` are excluded by default; only `INTERNAL_SERVER_ERROR`/`DATABASE_ERROR`/unclassified 500s and explicitly-flagged non-fatals are sent.
- **Non-fatal reporting**: add `sentry_sdk.capture_message(..., level="warning")` calls at the existing failure points already identified as safe hook sites: `app/services/push_delivery.py` (unknown/permanent push errors), `app/services/email_delivery.py` (provider errors), `app/jobs/*.py` (scheduled-job failures, which already have a `SCHEDULED_JOB_FAILED` structured log to key off of).

## 18. Environment Strategy

The project has no `staging` environment today (no evidence of a staging Railway/Vercel deployment in any doc or workflow) — so the plan defines only `development`, and `production`, plus a distinct `feature-branch` tag for Android CI-built debug APKs.

| Environment | Sentry `environment` tag | Remote reporting enabled? | Source |
|---|---|---|---|
| Local dev (`npm run dev`, `uvicorn --reload`) | `development` | **No** by default (console logging only); explicit opt-in via a local-only env var for integration testing | Frontend: `import.meta.env.MODE`; Backend: absence of a `RAILWAY_ENVIRONMENT`-style marker |
| Feature-branch Android debug APK (CI `workflow_dispatch`) | `feature-branch` | Yes, but tagged distinctly and routed to a **separate Sentry environment**, never `production` | CI-injected env var at build time |
| Production (Vercel frontend, Railway backend, future signed Android release) | `production` | Yes | Deployment platform env var |

If a `staging` tier is introduced later, it slots in as a third `environment` value with no architecture change.

## 19. Release/Version Strategy

Verified actual version sources: frontend `package.json` version = `0.0.0` (placeholder), Android `versionName`/`versionCode` = `"1.0"`/`1` (hardcoded), backend `version="0.1.0"` (hardcoded) — **none currently reflect real releases**, and no commit SHA is exposed anywhere in any build.

Adopted format (as proposed in the task, now verified against real sources): `yesh-mishak@<app-version>+<short-commit-sha>`, where `<app-version>` is the *existing* per-layer version string (frontend `package.json` version, Android `versionName`, backend `app.main` version) — not a new invented number — and `<short-commit-sha>` is the 7-character `GITHUB_SHA` prefix, newly injected by CI (currently absent, a required prerequisite — see [§29](#29-dependencies)).

This is a **prerequisite fix**, not part of Sentry SDK integration itself: CI must start passing `GITHUB_SHA` (or equivalent) into the Vite build (`define: { __COMMIT_SHA__: JSON.stringify(...) }`), the Android Gradle build (`buildConfigField "String", "COMMIT_SHA", "\"${sha}\""`), and the backend deploy (env var read by `Settings`). Until this exists, Sentry releases would have to fall back to the static placeholder versions only, which is not acceptable per the task's requirement that events be distinguishable by release.

## 20. Source-Map and Symbolication Strategy

**React/Vite**: enable `build.sourcemap: true` (or `'hidden'`) in `frontend/vite.config.js` for production builds; upload source maps to Sentry via `@sentry/vite-plugin` at build time (works for both plain web build and `--mode android`/`--mode ios` builds); use `'hidden'` sourcemap mode combined with Sentry's plugin's auto-delete-after-upload behavior so `.map` files are **not** shipped in the public Vercel deployment (closes Edge Case 49 — "production source maps become publicly downloadable"). Auth token for upload (`SENTRY_AUTH_TOKEN`) is a CI/build-time secret, never exposed to the client bundle. Release identifier used for source-map association is the same string from [§19](#19-releaseversion-strategy).

**Android**: since `minifyEnabled` is currently `false`, there is no ProGuard/R8 mapping file to upload today — Sentry's Gradle plugin, once added, can auto-upload a mapping file the moment R8 is enabled (a follow-on hardening step, not required for crash reporting to function — unminified stack traces are already fully readable). Native (NDK) symbols: Sentry's Android Gradle plugin also automates native-debug-symbol upload for the bundled NDK integration once enabled.

**Backend**: Python needs no source maps; readability is guaranteed as long as the deployed release matches the release identifier tagged at Sentry-init time — enforced by [§19](#19-releaseversion-strategy)'s CI-injected SHA.

## 21. Event Classification

**Fatal**: Android native/NDK crash; uncaught React render error reaching the Error Boundary; application bootstrap failure (error before React mounts); unhandled FastAPI exception (generic `Exception` handler path); a fatal Capacitor plugin failure that prevents the app from continuing.

**Non-fatal (reported, needs developer attention)**: push-token registration failure *after* permission was granted; repeated (not first-attempt) map/tile initialization failure; backend dependency unavailable (DB, Resend, FCM) surfaced as a classified error; unexpected database constraint failure (i.e., not the already-handled `23505` unique-violation 409 path); corrupted persisted onboarding state; deep-link resolution failure caused by application logic (not a plain 404).

**Expected — not reported by default**: invalid password, email-not-verified, Google-login cancellation (`authErrorMapping.js`'s `cancelled` kind), user-denied permission (location/notification), normal 404/422/429, expected network loss, unsupported-feature-on-browser, empty search result. See [§22](#22-expected-error-filtering-policy) for volume-based exceptions.

## 22. Expected-Error Filtering Policy

Default-excluded categories are filtered at the earliest point that already classifies them (reuse, don't rebuild): frontend via `authErrorMapping.js` kinds and HTTP status codes; backend via the `code` field already present on every `raise_api_error` response and via `RequestValidationError`'s 422 status.

**Volume-based exception rule**: an otherwise-expected error becomes reportable if either (a) the *rate* of occurrence for a single user/session crosses an anomalous threshold (e.g., >20 login-cancellations in one session — signals a broken OAuth config, not normal user behavior) or (b) the error represents an *impossible state* (e.g., a 409 `ACCOUNT_LINK_REQUIRED` returned for an account that has no linked-provider row at all — a data-integrity signal, not a normal linking flow). This is implemented as a lightweight counter-based override in the `before_send`/interceptor filter, not a general sampling mechanism.

## 23. Privacy and Redaction Policy

Never sent, enforced via each SDK's scrubbing hook (Sentry's `before_send` + `sendDefaultPii: false` + a shared deny-list applied to breadcrumbs/extra data): passwords, access/refresh tokens, Google identity tokens, `Authorization` headers, cookies, verification links/tokens, push tokens, Firebase credentials, private message content, full request bodies (attached only per-field-allowlist, never wholesale), exact GPS coordinates, exact address, DB connection strings, API keys, secret env vars.

Concrete risk found in the audit that must be scrubbed explicitly: raw Axios error objects passed to `console.warn`/`console.info` in several frontend files carry `error.config.headers.Authorization` — if Sentry's console-breadcrumb integration is enabled, it must run through a `beforeBreadcrumb` filter that strips `headers`/`Authorization`/`config` keys before the breadcrumb is recorded. Sentry's default Axios integration already redacts common auth headers, but this must be explicitly verified in testing ([Unit test: "Authorization-header removal"](#33-unit-test-plan)), not assumed.

Backend: reuse and extend, don't replace, the existing `sanitize_error_message`/`sanitize_error_type` helpers (`app/services/job_runs.py`) as an additional pass before `capture_exception`/`capture_message`; combine with Sentry's own `request_bodies: "never"` config.

## 24. User-Context Policy

Default decision (adopting the task's recommended default): attach a **stable internal user ID only** (the app's own DB user ID) as `Sentry.setUser({ id })`. **Do not** send email address, username, or display name. **Do not** use advertising identifiers. Clear the monitoring user (`Sentry.setUser(null)`) on logout — wired into the existing `handleLogout` flow (`frontend/src/App.jsx:593-640`). On account switch (Account B logging in after Account A on the same device), explicitly call `setUser(null)` before `setUser({ id: newId })` so no residual context from Account A leaks into Account B's events (addresses Edge Cases 8-9).

## 25. Location-Data Policy

**Decision: even city-level context is not included by default.** The audit found the app currently never logs exact coordinates, and the task explicitly asks whether city-level granularity is necessary — given this project already has memory of a past bug where the map used "another account's city on switch" (see `3d6d393` commit history), adding city-level location context to crash reports introduces a second place that same bug class could resurface, for marginal debugging value. Permitted safe context is limited to: permission state (`granted`/`denied`/`prompt`), location-services-enabled boolean, the existing `FAILURE_TYPES` classification from `locationFailure.js` (e.g. `GPS_DISABLED`, `TIMEOUT`), and whether map initialization succeeded — no coordinates, no city identifier.

## 26. Breadcrumb Policy

Small initial set only (not instrumenting every click): app launched; auth state changed (login/logout event name only, no credentials); onboarding step changed (step name only); map page opened; field details opened; game created/joined/left (event name + game ID, no other game content); permission request initiated + result category (granted/denied, not raw platform response); push registration initiated + result category; deep link resolved/failed (route name only, not full URL with query params); API request category + status code + duration (no request/response body).

Explicitly excluded from breadcrumbs: full form values, passwords, free-text descriptions (e.g. field-report text) without redaction, exact GPS, tokens, full URLs with private query parameters.

## 27. Alerting Policy

| Alert | Threshold | Recipient | Response |
|---|---|---|---|
| New fatal issue (first occurrence) | Any new unique fingerprint | Project owner email | Triage within 1 business day |
| Regression (previously-resolved issue reoccurs) | Any reoccurrence | Project owner email | Immediate triage — signals a shipped fix regressed |
| Sudden spike | >10x baseline event rate in 1 hour | Project owner email | Immediate — likely a bad release |
| High-user-impact issue | Affects >5 distinct users in 24h | Project owner email | Same-day triage |
| Android ANR threshold | >1% of sessions ANR in a release | Project owner email | Investigate before next release |
| Backend exception-rate threshold | >2% of requests error in 15 min | Project owner email | Immediate — likely a deploy/DB issue |

Channel: email only for the initial rollout (no Slack integration exists in this project today, and the task instructs not to add external alert integrations during planning). Issue resolution/regression tracking uses Sentry's native "Resolve"/"Regression" workflow — no custom tooling needed.

## 28. Retention, Quota and Cost Considerations

Sentry free/developer tier: ~5k error events/month (shared pool across frontend+Android+backend under one org), 90-day retention, unlimited team members on the free tier's team plan constraints, native release-health and source-map support included, native ANR support included. At this project's pre-launch stage (no production user base evidenced in the audit), 5k events/month is very likely sufficient; if exceeded, Sentry's spike-protection and per-project rate limiting can cap ingestion without an outage, and the next paid tier is a predictable incremental cost (no cliff). Firebase Crashlytics (if adopted later per [§45](#45-related-follow-up-tasks)) remains free/unlimited regardless of volume — a relevant factor only once Android install volume grows enough to threaten the Sentry event quota specifically from native crashes, at which point splitting native-crash volume to Crashlytics becomes attractive; not needed now.

## 29. Dependencies

**Required before implementation** (owner/human actions, not code): Sentry organization + 3 projects (frontend, Android, backend) or 1 org with 3 platform-tagged projects; DSN values obtained; privacy-policy wording decision; environment-naming sign-off (this doc proposes `development`/`production`/`feature-branch`); release-identifier format sign-off ([§19](#19-releaseversion-strategy)); GitHub repo secrets created (`SENTRY_AUTH_TOKEN`, `SENTRY_DSN_*`); alert-recipient email decided; dashboard access granted to the owner.

**Can be implemented within E09-01 (the future coding task)**: SDK installation (all 3 layers); `componentDidCatch` wiring; Android `Application` subclass; backend `before_send` filter; CI-injected commit SHA (frontend `define`, Android `buildConfigField`, backend env var) — this is a **new** small piece of work, not previously planned, uncovered by this audit; data-scrubbing config; user-context lifecycle wiring; environment/release tagging; source-map upload plugin wiring; Android mapping upload (conditional on R8 being enabled); safe test-event utilities; automated tests; documentation.

**Separate follow-up issues** (explicitly not E09-01): full performance/APM tracing ([§14](#14-exact-scope-excluded)); product/business analytics; session replay; log aggregation; uptime/synthetic monitoring; iOS native Sentry Cocoa integration; Firebase Crashlytics hybrid upgrade; Slack/PagerDuty alert routing; Android release-signing + R8 enablement (a prerequisite for *better* symbolication, not a blocker for crash reporting itself — flagged, not required).

## 30. File-by-File Implementation Plan

> All entries below are **proposed** for the future `codex/e09-01-crash-reporting` branch. None were created or modified by this planning task.

### Frontend

| Path | Exists? | Change | Why | SDK | Env vars | Privacy | Regression risk | Tests |
|---|---|---|---|---|---|---|---|---|
| `frontend/src/monitoring/sentry.js` | No (new) | Create init module: `Sentry.init({ dsn, environment, release, tracesSampleRate: 0, beforeSend, beforeBreadcrumb })` | Central, testable init point | `@sentry/capacitor` | `VITE_SENTRY_DSN` (client-visible, not secret) | Enforces scrub rules from §23 | Low — additive | Init-skipped-when-DSN-missing unit test |
| `frontend/src/main.jsx` | Yes | Call `initSentry()` before `createRoot(...).render()` | Earliest possible init, catches bootstrap failures | same | — | — | Low | — |
| `frontend/src/components/ErrorBoundary.jsx` | Yes | Add `componentDidCatch(error, info)` → `captureException` | Currently discards all render errors | same | — | No stack trace shown to user (unchanged) | Low — additive method | Component test: catches render error, still shows fallback |
| `frontend/src/api/client.js` | Yes | Extend response interceptor: classify + selectively `captureException`/`captureMessage` | Reuse existing single API surface | same | — | Must not forward Authorization header (§23) | Medium — touches shared interceptor, needs care not to change existing 401 behavior | Unit tests: expected-error exclusion, unexpected-error inclusion |
| `frontend/src/App.jsx` | Yes | `handleLogout`: add `Sentry.setUser(null)`; login success paths: add `Sentry.setUser({ id })` | User-context lifecycle (§24) | same | — | No email/name sent | Low | Unit test: user-context set/cleared |
| `frontend/vite.config.js` | Yes | Add `build.sourcemap: 'hidden'`, add `sentryVitePlugin(...)` | Symbolication (§20) | `@sentry/vite-plugin` | `SENTRY_AUTH_TOKEN` (build-time secret, CI only) | Maps not shipped publicly | Medium — must verify `.map` files excluded from Vercel output | CI test: no `.map` in deploy artifact |
| `frontend/src/i18n/*` (existing locale files) | Yes | Add Hebrew/English fallback-screen strings if not already present in `ErrorBoundary` | UX requirement (§35) | — | — | — | Low | Component test: HE/EN fallback text renders |

### Android

| Path | Exists? | Change | Why | SDK | Env vars | Privacy | Regression risk | Tests |
|---|---|---|---|---|---|---|---|---|
| `frontend/android/build.gradle` | Yes | Add Sentry Gradle plugin classpath | Enables auto native-symbol/mapping upload | `io.sentry:sentry-android-gradle-plugin` | — | — | Low | Build validation |
| `frontend/android/app/build.gradle` | Yes | Add `io.sentry:sentry-android` dependency; apply Sentry Gradle plugin | Native crash/ANR SDK | same | `SENTRY_DSN` (native `AndroidManifest` meta-data, client-visible) | — | Low-Medium — verify debug builds don't spam reports (§18) | Debug/release variant dependency-presence test |
| `frontend/android/app/src/main/java/com/yeshmishak/app/YeshMishakApplication.java` | No (new) | Create `Application` subclass calling `SentryAndroid.init(...)` | No Application class exists today — first process-wide hook | same | — | — | Medium — first-ever Application class, must not change Capacitor bridge behavior | Native non-fatal test event (debug-only build) |
| `frontend/android/app/src/main/AndroidManifest.xml` | Yes | Register `android:name=".YeshMishakApplication"`; add Sentry DSN meta-data | Wire the new Application class | same | — | DSN is client-visible config, not secret | Low | Manifest merge validation in CI |
| `frontend/android/app/build.gradle` (release block) | Yes | *Flag only, not required*: note that `minifyEnabled`/signing remain unset — optional follow-up | Symbolication quality | — | — | — | — | — |

### Backend

| Path | Exists? | Change | Why | SDK | Env vars | Privacy | Regression risk | Tests |
|---|---|---|---|---|---|---|---|---|
| `backend/requirements.txt` (or equivalent) | Yes | Add `sentry-sdk[fastapi]` | Backend SDK | `sentry-sdk` | — | — | Low | Dependency-presence test |
| `backend/app/main.py` | Yes | Init `sentry_sdk.init(dsn=..., environment=..., release=..., before_send=...)` guarded by DSN presence; call `sentry_sdk.capture_exception` inside existing catch-all handler | Reuses the one safe hook identified in §5 | same | `SENTRY_DSN`, `RELEASE` (new), `ENVIRONMENT` (new) | `before_send` scrubs per §23 | Medium — touches app bootstrap, must not change existing response shape/behavior | Backend test: unhandled exception captured; validation error NOT captured |
| `backend/app/core/config.py` | Yes | Add `environment` field (currently missing entirely — a real gap, not just for monitoring) | Needed for environment tagging (§18) | — | `ENVIRONMENT` | — | Low | Settings unit test |
| `backend/app/services/push_delivery.py` | Yes | Add `capture_message` at unknown/permanent failure branches | Non-fatal reporting (§21) | `sentry-sdk` | — | Reuses existing `sanitize_error_message` | Low — additive | Test: unexpected failure reported, expected retry NOT reported |
| `backend/app/services/email_delivery.py` | Yes | Add `capture_message` at provider-error branch | Non-fatal reporting | same | — | No email body/API key sent | Low | Test: provider error reported |

### CI/CD

| Path | Exists? | Change | Why | Env vars/secrets | Privacy | Regression risk | Tests |
|---|---|---|---|---|---|---|---|
| `.github/workflows/android-build-validation.yml` | Yes | Inject `GITHUB_SHA` into Gradle build; add Sentry mapping-upload step (fails soft, doesn't break build) | Release identity (§19) + symbolication (§20) | `secrets.SENTRY_AUTH_TOKEN` (new secret) | Token never echoed | Medium — must confirm upload failure doesn't fail the build (Edge Case 15) | CI test: upload-failure doesn't fail build |
| *(new)* `.github/workflows/frontend-release-build.yml` | No | New workflow (or extend existing) to inject `GITHUB_SHA` into Vite `define` and run source-map upload on production builds | Currently no frontend-only workflow exists — needed for release-SHA + source-map upload | `secrets.SENTRY_AUTH_TOKEN` | Maps not shipped publicly | Medium — new workflow, must be scoped correctly to avoid running on every PR | CI test: SHA present in built bundle |
| Railway deploy config (owner-configured, not in-repo) | N/A | Add `SENTRY_DSN`, `RELEASE`, `ENVIRONMENT` env vars in Railway dashboard | No in-repo Railway config exists to edit | Railway dashboard env vars | DSN client-visible; others are safe config | Low | Manual verification only |

### Documentation

| Path | Exists? | Change |
|---|---|---|
| `docs/e09-01-crash-reporting-execution-plan.md` | **New (this file)** | Architecture Decision Record + full plan |
| `docs/crash-reporting-setup-guide.md` | No (proposed, future) | Step-by-step setup for the implementation branch |
| `docs/production-readiness-checklist.md` | Yes | Update `MONITOR-001` from "gap" to "planned/in progress" once implementation lands |
| `docs/technical-debt-inventory.md` | Yes | Update `TD-OPS-001` similarly |

## 31. Environment Variables and Secrets Matrix

| Name | Layer | Secret or client-visible? | Where stored | Restart/redeploy needed |
|---|---|---|---|---|
| `VITE_SENTRY_DSN` | Frontend | Client-visible (DSNs are meant to be public; write-only ingest key) | Vercel env vars, `.env.*` files | Rebuild |
| `SENTRY_DSN` (Android) | Android | Client-visible (embedded in APK manifest meta-data) | `AndroidManifest.xml` meta-data, sourced from a build-time value | Rebuild |
| `SENTRY_DSN` (Backend) | Backend | Client-visible in principle, but keep in env vars for easy rotation | Railway env vars | Redeploy |
| `SENTRY_AUTH_TOKEN` | CI only | **Secret** (grants upload/project-write access) | GitHub Actions secret | N/A (CI-scoped) |
| `RELEASE` | Backend | Not secret | Railway env var, CI-injected | Redeploy |
| `ENVIRONMENT` | Backend | Not secret | Railway env var | Redeploy |
| `GITHUB_SHA` | CI (all layers) | Not secret, GitHub-provided automatically | N/A — built-in Actions context | N/A |

## 32. Edge-Case Matrix

| # | Edge case | Expected behavior | Event reported? | Platform | Severity | Auto test | Manual test |
|---|---|---|---|---|---|---|---|
| 1 | DSN/config missing | SDK init no-ops silently, app functions normally | No | All | N/A | Yes | No |
| 2 | Monitoring SDK init throws | Caught internally, app continues to boot | No | All | Warning (local log only) | Yes | Yes |
| 3 | User offline when crash occurs | Event queued locally (Sentry SDKs do this natively) | Deferred | All | Same as original | No | Yes |
| 4 | Report sent after restart | SDK's offline queue flushes on next launch | Yes (delayed) | All | Same as original | No | Yes |
| 5 | App crashes before React mounts | Native/global handler still captures it (init happens before render) | Yes | Frontend | Fatal | No | Yes |
| 6 | React crash after authentication | Captured with user context attached | Yes | Frontend | Fatal | Yes | Yes |
| 7 | Error before user context known | Captured without user ID (anonymous) | Yes | All | Varies | Yes | No |
| 8 | User logs out after context set | `setUser(null)` clears context for subsequent events | N/A (policy) | Frontend | N/A | Yes | Yes |
| 9 | Account B logs in after Account A | Context fully replaced, no bleed-through | N/A (policy) | Frontend | N/A | Yes | Yes |
| 10 | Feature-branch APK reports to wrong environment | Prevented by CI-injected `environment=feature-branch` tag | Yes, tagged correctly | Android | N/A | Yes (CI) | Yes |
| 11 | Debug crash reaches production dashboard | Prevented — debug builds tagged `development`/`feature-branch`, never `production` | Yes, wrong-env prevented by tag | Android | N/A | Yes | Yes |
| 12 | Source maps don't match release | Sentry shows raw minified trace; release-tag mismatch is visible in dashboard | Yes, degraded readability | Frontend | N/A | Yes (CI) | Yes |
| 13 | Android mapping upload fails | Build must NOT fail (soft-fail upload step); trace shows obfuscated names until fixed | Yes, degraded | Android | N/A | Yes (CI) | No |
| 14 | Sentry source-map upload fails | Same soft-fail requirement | Yes, degraded | Frontend | N/A | Yes (CI) | No |
| 15 | Monitoring upload failure breaks build | **Must never happen** — upload steps run with `continue-on-error` / non-blocking | N/A | CI | N/A | Yes | No |
| 16 | Backend/frontend deploy different commits | Release strings diverge; dashboard shows two distinct releases — acceptable, visible | Yes | Both | N/A | No | Yes |
| 17 | Repeated identical error floods | Sentry's fingerprinting groups into one issue; rate-limiting/quota protection applies | Yes, grouped | All | N/A | No | Yes |
| 18 | Network outage → thousands of expected API errors | Filtered by expected-error policy (§22); not sent as fatal | No (bulk) | Frontend | N/A | Yes | No |
| 19 | 401/403 misreported as crash | Prevented — explicitly filtered in `before_send`/interceptor | No | Both | N/A | Yes | No |
| 20 | User cancels Google login | Filtered (`cancelled` kind) | No | Frontend | N/A | Yes | No |
| 21 | Google OAuth config fails | Reported — this IS a real misconfiguration (`google_configuration` kind) | Yes | Frontend | Error | Yes | No |
| 22 | Push registration fails after permission granted | Reported (§21 non-fatal) | Yes | Frontend/Android | Warning | Yes | No |
| 23 | Location permission denied | Filtered (expected) | No | Frontend | N/A | Yes | No |
| 24 | Device location services disabled | Filtered (expected, classified `GPS_DISABLED`) | No | Frontend | N/A | Yes | No |
| 25 | Map provider fails | Reported only if repeated (§21) | Conditional | Frontend | Warning | Yes | Yes |
| 26 | Database unavailable | Reported (backend) | Yes | Backend | Error | Yes | No |
| 27 | Resend/email service unavailable | Reported (§17) | Yes | Backend | Warning | Yes | No |
| 28 | Push provider unavailable | Reported (§17) | Yes | Backend | Warning | Yes | No |
| 29 | Monitoring provider itself unavailable | SDK fails silently/queues locally; app unaffected | N/A | All | N/A | No | Yes |
| 30 | Sensitive token appears in exception object | Scrubbed by `before_send`/`beforeBreadcrumb` deny-list | Yes, scrubbed | All | N/A | Yes | No |
| 31 | Exact coordinates in breadcrumbs | Prevented — coordinates never added to breadcrumb payload (§25) | N/A | Frontend | N/A | Yes | No |
| 32 | Request body has password/verification token | Prevented — request bodies never attached wholesale (§23) | N/A | Backend | N/A | Yes | No |
| 33 | Test crash remains accessible in production UI | Prevented — test trigger gated to dev-only build flag, removed before release (§37) | N/A | All | N/A | No | Yes |
| 34 | Repeated crash on app launch | Sentry groups as one issue with high event count; alert fires (spike rule) | Yes, grouped | All | Fatal | No | Yes |
| 35 | React fallback screen itself throws | Outer top-level boundary is the last resort; if it also throws, browser default (blank page) — accepted residual risk, documented not "fixed" | Best-effort (may fail to report) | Frontend | Fatal | No | Yes |
| 36 | Backend exception handler causes a second exception | `sentry_sdk.capture_exception` call wrapped in its own try/except so it can never mask the original response | No cascading failure | Backend | N/A | Yes | No |
| 37 | Android ANR without a Java exception | Captured by SDK's ANR watchdog independent of exception path | Yes | Android | Fatal-equivalent | No | Yes |
| 38 | User disabled crash collection (if opt-out exists) | Respected — see §27 consent note; no opt-out built in v1 (see below) | No | All | N/A | No | No |
| 39 | App restored from background | No special handling needed — SDK session lifecycle handles this natively | N/A | All | N/A | No | Yes |
| 40 | Old app version sends issue after newer release | Tagged with its own (old) release string; dashboard shows it correctly attributed, not merged into new release | Yes, correctly tagged | All | N/A | No | No |
| 41 | Same root cause in frontend and backend | Two separate issues (different platforms); correlation via shared context (game/field ID in extra data), not auto-merged | Yes, two issues | Both | N/A | No | No |
| 42 | Duplicate event to two systems | N/A — single-vendor architecture (Option A) eliminates this by design | N/A | N/A | N/A | N/A | N/A |
| 43 | Monitoring quota exhausted | Sentry drops events past quota; app functionality unaffected; alert on quota-approaching (owner dashboard, not custom code) | No (dropped) | All | N/A | No | Yes |
| 44 | Clock or release metadata invalid | SDK falls back gracefully; malformed release string still ingests, just ungrouped by release | Yes, degraded | All | N/A | No | No |
| 45 | App starts without internet | SDK queues locally; app boot unaffected | Deferred | All | N/A | No | Yes |
| 46 | Web deployment runs outside Capacitor | `@sentry/capacitor` falls back to pure web SDK behavior transparently (§15) | Yes, normal | Frontend | N/A | Yes | Yes |
| 47 | Browser blocks third-party monitoring endpoint | SDK fails to send silently; app unaffected; acceptable residual blind spot | No | Frontend | N/A | No | No |
| 48 | Ad blocker blocks the SDK | Same as #47 — documented residual limitation, not solvable | No | Frontend | N/A | No | No |
| 49 | Production source maps become publicly downloadable | Prevented by `'hidden'` sourcemap mode + upload-then-delete CI step (§20) | N/A | Frontend | N/A | Yes (CI) | Yes |
| 50 | iOS app runs before native iOS monitoring is implemented | No Sentry Cocoa SDK present yet — iOS crashes are simply not captured until the deferred iOS phase; documented, not silently ignored | No | iOS | N/A | No | No |

*Note on Edge Case 38 (opt-out)*: v1 does not implement a user-facing crash-collection opt-out toggle, since Sentry's default `sendDefaultPii: false` + the redaction policy in §23 already avoids collecting personal data, and no explicit privacy-policy commitment to an opt-out exists yet in this project. This is flagged as an open question for the owner in §42, not silently decided.

## 33. Unit-Test Plan

- SDK no-ops when DSN/config missing (all 3 layers).
- Environment selection resolves correctly per build mode.
- Release identifier generation matches `yesh-mishak@<version>+<sha>` format.
- Sensitive-data redaction: password/token fields stripped from `before_send` output.
- URL/query-parameter redaction in breadcrumbs.
- Authorization-header removal from captured Axios error context.
- User-context set on login (frontend and backend session-attach path).
- User-context cleared on logout.
- Account-switch isolation (Account B doesn't inherit Account A's context).
- Expected-error filtering (401/403/404/422/429/cancelled-login all excluded).
- Unexpected-error reporting (500/`DATABASE_ERROR`/uncaught exceptions included).
- Permission-denied exclusion (location/notification).
- Google-cancelled-login exclusion.
- Push-registration unexpected-failure inclusion.
- Location-services-disabled correctly classified as excluded.
- Monitoring initialization failure doesn't crash the app.
- Duplicate-event prevention (n/a for cross-vendor per §32#42, but verify Sentry's own fingerprint grouping doesn't double-count retries within the retry-backoff loop in `push_delivery.py`).
- No sampling logic planned for v1 (flat capture within free-tier quota) — no sampling tests needed yet.

## 34. Frontend-Test Plan

- Error Boundary catches a thrown render error (component test, forces a child to throw).
- Fallback UI displays in Hebrew.
- Fallback UI displays in English.
- Retry/reload action (`window.location.reload()`) is invoked on button click.
- No stack trace or technical detail is rendered to the user.
- Event ID is displayed only when Sentry actually returned one (never a placeholder).
- Authentication state is not leaked into the fallback UI or any breadcrumb.
- A child component erroring repeatedly does not cause an infinite re-render loop (verify `hasError` state doesn't reset without an explicit retry action).

## 35. Backend-Test Plan

- Unhandled exception is captured (mock `sentry_sdk.capture_exception`, assert called once with correct exception).
- Handled `RequestValidationError` (422) is NOT captured.
- Expected auth error (401/403 via `raise_api_error`) is NOT captured.
- Database failure is tagged with a safe classification (not raw exception text with connection strings).
- `Authorization` header is scrubbed from any captured request context.
- Request body is not attached by default.
- Password and token fields are scrubbed if a request body is ever explicitly opted in for a specific allowlisted field.
- Health-check (`GET /`) failures do not flood monitoring (excluded route).
- Monitoring SDK outage/exception does not break API responses (wrap `capture_exception` call in try/except, per Edge Case 36).
- Correlation ID (once implemented — see §29 new prerequisite) is attached to captured events.

## 36. Android-Test Plan

- Sentry dependency is present in the correct build variants (debug and release, not just one).
- Debug-build reporting policy: tagged `development`/`feature-branch`, verified via manifest meta-data inspection in a test build.
- Production-build reporting policy: tagged `production`.
- Missing Sentry DSN meta-data fails gracefully, not with a hard crash (verify via a build variant lacking the meta-data).
- Native non-fatal test event can be emitted only via a dedicated debug-only test path (see §37), never reachable in a release build (static analysis / lint rule).
- Release/build metadata (`versionName`, `versionCode`, commit SHA) is attached to captured events.
- Mapping-upload configuration is correctly scoped to only run when `minifyEnabled` is true (currently always false, so this step should no-op safely today, not fail).

## 37. CI/CD-Test Plan

- Required secret/var names exist before a workflow that needs them runs (fail with a clear message, not a cryptic Gradle/Vite error).
- Secret values are never echoed to workflow logs (verify via `::add-mask::` usage and absence of `echo $SECRET`-style steps).
- Source-map upload uses the same release string as the deployed build (assert both reference the same `GITHUB_SHA`).
- Android mapping upload occurs only when a mapping file actually exists (no-op otherwise, doesn't fail).
- Feature-branch builds report to `feature-branch` environment, never `production` (assert manifest/env value per branch type).
- Monitoring-upload failure does not fail the overall build job (`continue-on-error: true` or equivalent verified in workflow YAML).
- Build artifacts (APK, JS bundle) do not contain `SENTRY_AUTH_TOKEN` or any other secret value (grep the built artifact).
- Public source maps are not present in the deployed Vercel output (grep the deploy directory for `.map` files post-build).

## 38. Manual Frontend Verification

1. Add a temporary, developer-only test trigger (e.g. a hidden `?debug-crash=1` query param or a console-only `window.__triggerTestError()` function, gated by `import.meta.env.DEV` so it cannot exist in a production build) that throws a controlled error.
2. Confirm it is unreachable in the production build (grep the built bundle for the trigger string — should be absent, tree-shaken out by the `DEV` guard).
3. Trigger it locally, confirm a Sentry event appears with the expected release/environment tags.
4. Confirm the stack trace is readable (source-mapped, not `at a (index-abcd123.js:1:48291)`).
5. Confirm no sensitive data appears in the event payload (manual review against §23's deny-list).
6. Remove/disable the trigger before merging to `main` (or ensure the `DEV` guard permanently excludes it — preferred over remove/re-add churn).

## 39. Manual Android Verification

1. Build a dedicated test-flavor debug APK with the test-crash trigger reachable (debug-only build config, never release).
2. Install on a physical Android device (not emulator — ANR/native-crash behavior differs).
3. Trigger a native test crash via the dedicated test path.
4. Restart the app.
5. Confirm the report uploads to Sentry (may require app relaunch/network for offline-queued events).
6. Confirm device model, Android OS version, app version, build number, and release tag all appear correctly on the event.
7. Confirm the native stack trace is readable (symbolicated, not raw addresses).
8. Confirm the event lands in the `development`/`feature-branch` environment, not `production`.
9. Remove or permanently guard-disable the test trigger.
10. Rebuild a release-configuration APK and confirm the trigger path is unreachable (code not present / feature-flagged off).

**Android ANR verification**: a controlled ANR test (deliberately blocking the main thread) is determined **necessary but restricted to a non-production, dedicated test build on a physical device** — never performed against a build that could reach real users, and never automated in CI (ANR reproduction is inherently disruptive and flaky in CI environments).

## 40. Manual Backend Verification

1. Use a protected, non-production-reachable mechanism (e.g. a pytest-driven integration test hitting a temporary route registered only when `ENVIRONMENT=development`, mirroring the existing pattern in `tests/test_admin_me.py`'s `/__test_metrics/unhandled` route) to generate a controlled backend exception.
2. Confirm it is not exposed in the production route table (verify the temporary route is absent when `ENVIRONMENT=production`).
3. Confirm the event carries the correct Railway environment and release tag.
4. Confirm the Python stack trace is fully readable in the Sentry dashboard.
5. Confirm request/secret redaction — manually inspect the captured event for absence of `Authorization`, tokens, DB connection strings.

## 41. Dashboard Verification

Confirm, per platform, after the manual test events above: event appears; issue grouping/fingerprinting is sensible (not one issue per unique stack-trace-line-number for the same root cause); environment tag is correct; release tag is correct; user-context policy is respected (only internal ID, no email); no sensitive information is present anywhere in the event (breadcrumbs, extra data, tags); alert fires only for the rules actually configured (not on every single test event); an issue can be assigned, resolved, and correctly flagged as a regression on reoccurrence.

## 42. Owner Manual Steps

| Action | Where | Secret? | Storage | Client-safe to expose? | Restart/redeploy needed? |
|---|---|---|---|---|---|
| Create/select Sentry organization | sentry.io | No | N/A | N/A | N/A |
| Create 3 Sentry projects (or 1 org, 3 platform tags) | sentry.io | No | N/A | N/A | N/A |
| Obtain DSNs (frontend, Android, backend) | Sentry project settings | No (DSNs are write-only ingest keys, safe to embed client-side) | Vercel/Railway env vars, Android manifest | Yes | Yes on change |
| Create Sentry auth token for CI uploads | Sentry org settings | **Yes** | GitHub Actions secret | No | N/A |
| Add `SENTRY_DSN` (×3), `SENTRY_AUTH_TOKEN` to GitHub secrets | GitHub repo settings | Token yes, DSNs no but store as secrets anyway for easy rotation | GitHub Actions | Token: no. DSNs: could be var, recommend secret for rotation simplicity | N/A |
| Add `VITE_SENTRY_DSN`, `RELEASE`, `ENVIRONMENT` to Vercel | Vercel dashboard | No | Vercel env vars | Yes | Redeploy |
| Add `SENTRY_DSN`, `RELEASE`, `ENVIRONMENT` to Railway | Railway dashboard | No | Railway env vars | Yes (backend-internal, not shipped to client) | Redeploy |
| Select alert-recipient email | Sentry alert rules | No | Sentry config | N/A | N/A |
| Configure the 6 alert rules from §27 | Sentry dashboard | No | Sentry config | N/A | N/A |
| Review/update privacy-policy wording | Company doc, not this repo (unless one exists — none found) | No | N/A | N/A | N/A |
| Approve whether any analytics product accompanies this rollout | Owner decision | No | N/A | N/A | N/A — decision: **no**, per §14 |
| Approve automatic vs. opt-in collection | Owner decision | No | N/A | N/A | Decision proposed in §32 Edge Case 38 (no opt-out in v1); owner may override |
| Approve user-ID-only context policy | Owner decision | No | N/A | N/A | Proposed default in §24; owner may override |
| Run the physical Android test crash | Physical device | No | N/A | N/A | N/A |
| Confirm event visibility in Sentry dashboard | sentry.io | No | N/A | N/A | N/A |

No iOS owner actions are requested at this stage — see §46.

## 43. Risks

- **No existing environment/version infrastructure** means the release-identity prerequisite ([§19](#19-releaseversion-strategy)) is itself nontrivial new work, not just SDK wiring — risk of scope creep if not firmly bounded to "inject SHA, tag releases" only.
- **Android release build is currently unsigned and unminified** — crash reporting will work, but won't reflect a real distributable artifact until release signing is separately addressed (not in this task's scope, flagged as a dependency risk for realistic production validation).
- **No existing request/correlation-ID mechanism** — frontend-to-backend error correlation (mentioned in the task's edge cases) requires new plumbing beyond pure SDK installation; scoped as an optional enhancement, not a hard requirement, to avoid scope creep.
- **Manual redaction discipline today is ad hoc** (per-call-site `console.warn` patterns) — an SDK that auto-captures console breadcrumbs could inadvertently surface something not yet caught by the existing manual discipline; mitigated by the `beforeBreadcrumb` scrub, but requires careful testing before enabling console breadcrumbs at all (may be safer to disable console-breadcrumb capture entirely in v1).
- **CI mapping/source-map upload steps must be verified non-blocking** (Edge Cases 13-15) — a naive integration could accidentally make Sentry an availability dependency for shipping code, which must never happen.

## 44. Blockers

- Sentry organization/projects and DSNs must exist before any implementation code can be meaningfully tested end-to-end (owner action, [§42](#42-owner-manual-steps)).
- Privacy-policy and consent decisions ([§32](#32-edge-case-matrix) Edge Case 38, [§24](#24-user-context-policy)) should be confirmed by the owner before shipping to any real users, even though the technical default (user-ID-only, no opt-out) is a reasonable starting point.
- CI commit-SHA injection ([§19](#19-releaseversion-strategy)) is a genuine prerequisite piece of new work uncovered by this audit, not previously scoped — should be explicitly budgeted into the implementation task's estimate.

## 45. Related Follow-Up Tasks (Explicitly Out of E09-01)

1. Full performance/APM tracing (frontend transactions, backend request tracing) — separate task, separate sampling/cost decision.
2. Firebase Crashlytics hybrid upgrade — revisit once the app reaches Play Store distribution and App Quality Insights becomes valuable.
3. Android release signing + R8/ProGuard enablement — improves symbolication quality, not required for crash reporting to function.
4. Frontend/backend request-correlation-ID system — nice-to-have for cross-layer debugging, not required for v1 crash visibility.
5. Product/business analytics (funnels, retention) — explicitly not to be conflated with crash reporting.
6. Session replay — a Sentry add-on product, deliberately not enabled in v1 given the privacy posture in §23/§25.
7. Slack/PagerDuty alert routing — email-only for v1 per §27.
8. iOS native Sentry Cocoa integration + physical-iPhone verification — see §46.
9. CI-driven automatic version/versionCode bumping — currently fully manual/static across all three layers; a real gap independent of monitoring, worth its own task.

## 46. Deferred iOS Requirements

Audited `frontend/ios/` (structure only, no files modified): Xcode project + SPM-based dependency management (no CocoaPods), no `GoogleService-Info.plist`, no existing Firebase/Sentry/Crashlytics reference anywhere in `AppDelegate.swift` or the Xcode project file, no dSYM-upload build phase (only the default `dwarf-with-dsym` debug-info format, which is not the same as an upload pipeline). `MARKETING_VERSION`/`CURRENT_PROJECT_VERSION` = `1.0`/`1`, same static-placeholder pattern as the other layers.

All marked **Deferred to iOS implementation phase**:
- iOS SDK installation (`Sentry` via Swift Package Manager, added to `CapApp-SPM/Package.swift`).
- dSYM upload configuration (new Xcode build phase + `sentry-cli` in a CI step).
- Native iOS crash validation (physical iPhone required).
- Non-fatal iOS error validation.
- APNs interaction review, if push-related native crashes are found relevant.
- Build-phase configuration changes to `App.xcodeproj`.
- Physical-iPhone QA pass.
- No iOS owner actions are requested in this planning cycle.

## 47. Acceptance Criteria

All 34 acceptance criteria listed in the task are satisfied by this document and the actions taken to produce it:
1–5: repository state documented across all layers (§3–§7). 6–9: three-plus architectures compared, one selected with reasoning, rejections explained (§9–§12). 10–19: privacy, user-context, environment, release, source-map, mapping, expected-error, fatal/non-fatal, alerting, cost policies all defined (§18–§28). 20–25: file-by-file plan, tests, manual verification all defined (§30, §33–§41). 26: iOS deferred (§46). 27–33: no production code modified, no SDK installed, no external project created, `frontend/.env` untouched, no secret committed, `main` untouched, no merge occurred — see §49. 34: nothing pushed unless separately authorized — confirmed not pushed.

## 48. Definition of Done (for this planning task)

- [x] `docs/e09-01-crash-reporting-execution-plan.md` created with all 50 required sections.
- [x] Repository audited across frontend, Android, backend, CI/CD, iOS.
- [x] Architecture selected and justified; alternatives rejected with reasons.
- [x] No implementation performed.
- [x] `frontend/.env` untouched.
- [x] Working on dedicated branch `codex/e09-01-crash-reporting-plan`, not `main`.

## 49. Recommended Implementation Order (for the future coding task)

1. Owner actions: create Sentry org/projects, obtain DSNs, create CI auth token ([§42](#42-owner-manual-steps)).
2. Prerequisite: CI commit-SHA injection across all 3 layers + backend `environment`/`release` settings fields ([§19](#19-releaseversion-strategy), [§30](#30-file-by-file-implementation-plan) backend config row).
3. Backend SDK integration (lowest-risk, single safe hook point already identified, §17).
4. Frontend SDK integration + Error Boundary wiring (§15).
5. Android SDK integration (requires new `Application` class — higher-risk native change, do after frontend/backend are proven, §16).
6. Source-map/mapping upload CI wiring, verified non-blocking (§20, Edge Cases 13-15).
7. Test suite (§33–§37).
8. Manual verification pass, all three platforms (§38–§40).
9. Alert-rule configuration (§27, owner-driven).
10. Documentation updates to `production-readiness-checklist.md` / `technical-debt-inventory.md`.

## 50. Final Readiness Decision

**READY WITH BLOCKERS.**

The architecture is decided, the design is fully specified, and the repository audit found no hidden obstacle that would block implementation. However, implementation cannot begin productively until the owner completes the actions in [§42](#42-owner-manual-steps) (Sentry org/projects/DSNs/auth token) and confirms the privacy/consent defaults proposed in [§24](#24-user-context-policy)/[§25](#25-location-data-policy)/Edge Case 38. Additionally, this audit surfaced one piece of genuinely new prerequisite work not previously scoped anywhere in the roadmap — CI-driven release-identity injection ([§19](#19-releaseversion-strategy)) — which should be budgeted into the implementation task's estimate rather than assumed to be a side effect of SDK installation.

---

## 51. Confirmations

- No production code, dependency file, or configuration file was modified — only this documentation file was created.
- No package was installed (no `npm install`, `pip install`, or Gradle dependency change was executed).
- No external Sentry, Firebase, or other monitoring project/account was created or modified.
- `frontend/.env` was read only to confirm its diff existed structurally (line count/filename via `git diff --stat`) — its contents were never opened, printed, staged, edited, or committed; the pre-existing local modification remains exactly as it was found.
- No secret value was printed or committed anywhere in this document or this session.
- `main` was not modified after the initial fast-forward to `origin/main` (a non-destructive, conflict-free update containing no crash-reporting-related changes); no changes were merged into it during this task.
- Nothing was pushed to any remote.
