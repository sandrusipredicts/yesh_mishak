# Crash Reporting Architecture (E09-01)

Status: **Implemented** (cross-platform implementation complete; Android CI-build verified; iOS native and physical-device verification pending — see [`docs/e09-01-crash-reporting-execution-plan.md`](e09-01-crash-reporting-execution-plan.md) for the full implementation report).

## Provider Decision

**Sentry**, across all four application surfaces, using a single cross-platform SDK family:

| Surface | Package | Version |
|---|---|---|
| React / Capacitor (shared JS, Android WebView, iOS WKWebView) | `@sentry/capacitor` | `^4.2.0` |
| React integration (peer of `@sentry/capacitor`) | `@sentry/react` | `^10.60.0` (pinned to match the peer requirement exactly) |
| Build-time source-map upload | `@sentry/vite-plugin` | `^5.4.0` (dev dependency) |
| Android native | `io.sentry:sentry-android` | `8.41.0` (bundled transitively by `@sentry/capacitor`'s own native Android module — not a direct dependency in this repo) |
| iOS native | Sentry Cocoa | `>=9.16.1` (bundled transitively via `@sentry/capacitor`'s own Swift Package manifest — not yet resolved in this repo; requires `npx cap sync ios` on a macOS/Xcode toolchain) |
| Backend (FastAPI) | `sentry-sdk` | `==2.66.0` |

No other monitoring, analytics, or observability product was introduced.

## Platform Coverage

| Capability | Covered | Mechanism |
|---|---|---|
| React rendering failures | Yes | `ErrorBoundary.componentDidCatch` → `captureException` |
| JavaScript runtime errors (uncaught) | Yes | `@sentry/capacitor`'s bundled global handler integration (installed automatically by `Sentry.init()`) |
| Unhandled promise rejections | Yes | Same bundled integration |
| Capacitor/WebView JS errors (Android WebView + iOS WKWebView) | Yes | Same JS bundle, same init call, runs identically on both WebView engines |
| Android native crashes | Yes (implemented, CI-build verified) | `sentry-android`, auto-initialized via the Capacitor plugin bridge (`SentryAndroid.init` inside the plugin's native code) |
| Android ANRs | Yes (implemented, CI-build verified; physical-device ANR trigger not exercised) | `sentry-android`'s bundled `AnrIntegration`, on by default |
| iOS native crashes | Designed and dependency-declared; **not yet resolved/compiled** (requires macOS/Xcode) | Sentry Cocoa, auto-initialized via the same Capacitor plugin bridge (`SentrySDK.start` inside the plugin's native Swift code) |
| iOS app hangs (ANR equivalent) | Designed; not yet verified | Sentry Cocoa's bundled App Hang detection |
| Backend unhandled exceptions | Yes | `generic_exception_handler` in `backend/app/main.py` → `capture_unexpected_exception` |
| Backend unexpected internal 500s raised via `raise_api_error` | Yes | `http_exception_handler`, only when `status_code >= 500` |
| Backend expected 4xx (`400`/`401`/`403`/`404`/`409`/`422`/`429`) | Correctly excluded | Only the `>=500` branch of `http_exception_handler` calls capture; the `RequestValidationError` handler never captures |

## Event Policy

**Fatal**: Android/iOS native crashes; uncaught React render errors reaching the Error Boundary; unhandled backend exceptions; a fatal Capacitor plugin failure.

**Non-fatal (reported)**: unexpected native push-token registration failure after permission was granted (`frontend/src/App.jsx`'s `onTokenError` callback); backend "unknown"-classified push delivery failures (`backend/app/services/push_delivery.py`); backend email-provider rejections/malformed responses/missing configuration (`backend/app/services/email_delivery.py`).

**Expected — filtered, never reported as a crash** (`frontend/src/monitoring/filters.js::isExpectedError`, and structurally by which backend handler calls capture): Google/native login cancellation, expected permission denial, HTTP `401`/`403`/`404`/`422`/`429`, offline errors already handled by calling code, browser-extension noise. An explicit `monitoring_force_report` tag escape hatch exists for the documented volume-based/impossible-state exception case, but nothing currently sets it (no such condition has been identified as needing it yet).

## Privacy Policy

`sendDefaultPii: false` on both the frontend (`monitoring/index.js`) and backend (`app/monitoring.py`). `tracesSampleRate: 0` (frontend) / `traces_sample_rate=0` (backend) — no performance monitoring enabled. No Session Replay integration is added anywhere.

Redaction (`frontend/src/monitoring/redaction.js`, `backend/app/monitoring.py::redact_deep`/`redact_event`) removes, on both frontend and backend, in every event and breadcrumb, at any nesting depth: passwords, access/refresh/ID tokens, `Authorization` headers, cookies, push tokens, verification tokens, API keys, exact latitude/longitude, and any key matching a broad case-insensitive sensitive-key pattern. Request bodies are never attached (deleted from the event's `request.data` unconditionally). URLs are reduced to origin+path only — query strings and fragments (which may carry tokens or verification codes) are dropped entirely, both in request context and breadcrumb data. Both redaction implementations are non-mutating and guard against circular references.

User context carries **only the internal application user ID** (`{ id: <uuid> }`) — no email, display name, Google account information, phone number, or advertising identifier is ever attached. `frontend/src/App.jsx` syncs this via a single `useEffect` keyed on `currentUser?.id`, so every path that changes the authenticated user (login, logout, session restore, account switch) stays consistent automatically. `setUser()` always clears before setting (`monitoring/client.js`), guaranteeing an account switch can never leak the prior account's context into the new one.

No exact GPS coordinates or city context are ever attached to any event (redaction removes latitude/longitude keys unconditionally; no code path adds city-level location context to monitoring events).

## Environment Strategy

| Environment | Meaning | Remote reporting |
|---|---|---|
| `local` | Frontend: `npm run dev` (Vite `DEV` mode) with no explicit override. Backend: no `SENTRY_ENVIRONMENT` set. | Disabled by default; explicit opt-in via `VITE_SENTRY_ENABLED=true` / `SENTRY_ENABLED=true` |
| `development` | Any deployed build (frontend or backend) with no explicit `SENTRY_ENVIRONMENT`/`VITE_SENTRY_ENVIRONMENT` override — the safe default for an unlabeled deploy | Enabled if a DSN is configured |
| `branch-build` | Feature-branch Android CI builds (`android-build-validation.yml` sets this explicitly) | Enabled if a DSN is configured; never conflated with production |
| `production` | Requires an explicit `SENTRY_ENVIRONMENT=production` / `VITE_SENTRY_ENVIRONMENT=production` set by the deployment platform | Enabled if a DSN is configured |

The resolution logic (`frontend/src/monitoring/config.js::resolveEnvironment`, `backend/app/monitoring.py::resolve_environment`) never defaults to `production` — production is only reachable via an explicit, deliberate configuration value, so a misconfigured or unlabeled deploy can never contaminate production issue statistics.

## Release Strategy

Format: `yesh-mishak@<app-version>+<short-sha>` where reliably available; the CI-wired interim format `yesh-mishak@<short-sha>` is used today since Android `versionName`/frontend `package.json` version/backend `app.main` version are all still static placeholders (`1.0`/`0.0.0`/`0.1.0`) with no per-release bump mechanism (a pre-existing gap, not introduced or fixed by this task — see [Known Limitations](e09-01-crash-reporting-execution-plan.md)).

`dist` differentiates platform builds sharing the same release: `android-branch-<CI run number>` (Android CI builds today), `ios-branch-<CI run number>` (once iOS CI wiring is exercised), coarse platform name (`android`/`ios`/`web`) as a runtime fallback when CI hasn't injected a precise value.

The frontend release string is injected at build time via `VITE_SENTRY_RELEASE`/`VITE_SENTRY_DIST` (currently wired in `android-build-validation.yml`; Vercel/Railway wiring is an owner action — see [`docs/sentry-configuration-guide.md`](sentry-configuration-guide.md)). The backend release string is injected via the `SENTRY_RELEASE` env var, read by `app/core/config.py::Settings`.

## Source Maps

`frontend/vite.config.js` sets `build.sourcemap: 'hidden'` (maps are generated for private upload but no `//# sourceMappingURL` comment ships in the bundle, so browsers/devices never fetch one). `@sentry/vite-plugin` is only added to the plugin list when `process.env.SENTRY_AUTH_TOKEN` (a Node-context build-time secret, never `VITE_`-prefixed, so it can never end up in the client bundle) is present — a local build with no token simply builds without attempting an upload. When active, the plugin uploads maps under the same `VITE_SENTRY_RELEASE`/`VITE_SENTRY_DIST` the app itself reports under, then deletes the `.map` files from the `dist/` output (`sourcemaps.filesToDeleteAfterUpload`) so production source maps are never publicly downloadable. Upload failures are caught by a custom `errorHandler` (logged as a build warning, never fails the build).

Verified: a local build with no `SENTRY_AUTH_TOKEN` produces `.map` files with no `sourceMappingURL` reference in the shipped JS (confirmed via direct build inspection during implementation).

## Android Native

`npx cap sync android` (run during implementation) confirmed `@sentry/capacitor` is auto-detected as an installed Capacitor plugin and added its native Gradle module (`frontend/android/app/capacitor.build.gradle`, `frontend/android/capacitor.settings.gradle` — both Capacitor-generated files, regenerated by the sync command, never hand-edited). Inspection of the installed package's native source (`node_modules/@sentry/capacitor/android/src/main/java/io/sentry/capacitor/SentryCapacitor.java`) confirmed:

- `io.sentry:sentry-android:8.41.0` is a direct dependency of the plugin's own `build.gradle` — no additional manual Gradle dependency was needed.
- The plugin's own manifest sets `io.sentry.auto-init=false` — native initialization is driven entirely by the JS-side `Sentry.init()` call bridging into `SentryCapacitor.initNativeSdk()`, which calls `SentryAndroid.init(...)`. **No custom `Application` subclass was needed or added** (none exists in this repo, and none was required).
- ANR (`AnrIntegration`) and native crash handling (`UncaughtExceptionHandlerIntegration`, `NdkIntegration`) are all enabled by default and were not disabled.
- No `AndroidManifest.xml` change was needed (the plugin doesn't read DSN/config from manifest meta-data).

A residual, documented limitation: native initialization only happens once the WebView loads and the JS bundle executes `Sentry.init()` — a crash in the brief native window before that point would not be captured. This is inherent to the Capacitor-bridge initialization model and was not solved with an unnecessary custom `Application` class, per the "smallest correct configuration" principle.

## iOS Preparation

Everything safely preparable without Xcode was done; nothing requiring Xcode/macOS was fabricated. See the [iOS section of the execution plan](e09-01-crash-reporting-execution-plan.md#10-ios-preparation-summary) for full detail. Summary:

- `@sentry/capacitor` is already in `frontend/package.json` (the same dependency shared with Android/web — adding it is what makes the native iOS Sentry Cocoa dependency resolvable).
- `frontend/ios/App/CapApp-SPM/Package.swift` (marked "DO NOT MODIFY" by Capacitor) was **not** hand-edited. It will be regenerated automatically the first time `npx cap sync ios` runs on a macOS/Xcode toolchain.
- `frontend/ios/App/App/AppDelegate.swift` was inspected and left unchanged: the installed package's iOS source (`node_modules/@sentry/capacitor/ios/Sources/SentryCapacitorPlugin/SentryCapacitorPlugin.swift`) confirms `initNativeSdk` calls `SentrySDK.start(options:)` from the JS bridge, exactly mirroring the Android pattern — no native Swift code change is required.
- A guarded, non-blocking dSYM-upload step was added to `.github/workflows/ios-debug-build-validation.yml`, skipping cleanly (with a CI warning, never a failure) when `SENTRY_AUTH_TOKEN`/org/project aren't configured or no `.dSYM` bundle is found. It cannot be validated end-to-end yet because that workflow builds an unsigned Simulator app, not a signed device archive.

## Backend Coverage

`backend/app/monitoring.py` centralizes all Sentry usage. `sentry_sdk.init()` is called once at FastAPI startup (`app/main.py`), guarded by DSN presence, with `send_default_pii=False`, `traces_sample_rate=0`, a `before_send` redaction hook, and the `StarletteIntegration`/`FastApiIntegration` auto-capture-on-5xx-status behavior explicitly disabled (`failed_request_status_codes=set()`) to guarantee exactly one capture path — the two existing exception handlers in `app/main.py` — rather than risking a duplicate between the SDK's own automatic integration and this codebase's manual capture calls.

A small request-correlation-id middleware (`app/middleware/request_context.py`) tags every Sentry event with the same `X-Request-Id` the frontend attaches to its outgoing requests and the backend echoes back in its response header, so a frontend-reported unexpected error and its backend counterpart can be cross-referenced.

## Rejected Alternatives

Full reasoning in the execution plan; summary:

- **Firebase Crashlytics (Android/iOS native only)** — rejected: zero JavaScript/WebView coverage on either platform, zero backend coverage. The primary UI is 100% React inside a Capacitor WebView on both platforms.
- **Hybrid (Crashlytics for native, Sentry for JS/backend)** — rejected for now: doubles integration/CI/ownership surface across four platform surfaces, and specifically requires standing up an entirely new Firebase-iOS integration from zero (no existing Firebase-iOS footprint in this repo — Firebase here is push-notification-only, and only on Android/web). Documented as a valid future evolution once the app reaches Play Store distribution and Android Studio App Quality Insights becomes operationally valuable.
- **Bugsnag / Rollbar / self-hosted GlitchTip** — rejected: no repository or cost evidence favored any of these over Sentry.
- **Full performance monitoring / APM tracing** — explicitly out of scope for E09-01 (`tracesSampleRate: 0` everywhere); a distinct, separately-scoped follow-up task, not silently bundled into crash reporting.
- **Session Replay, product/business analytics, Google Analytics** — explicitly not enabled anywhere in this implementation.
