# E09-01 — Crash Reporting & Error Monitoring: Execution Plan

Status: **CROSS-PLATFORM IMPLEMENTATION COMPLETE — ANDROID VERIFIED — IOS VERIFICATION PENDING.** (Updated — a prior revision of this line read `CROSS-PLATFORM IMPLEMENTATION COMPLETE WITH BLOCKERS — ANDROID PHYSICAL VERIFICATION PENDING — IOS VERIFICATION PENDING` while real Sentry event-delivery and physical-device verification for Android were still outstanding. Both have since actually happened and been confirmed: a real Sentry organization/project now exists, a branch-build APK was installed on a physical Android device, and a real JavaScript event, a real React Error Boundary event, and a real native crash all appeared correctly in the `yesh-mishak-mobile` Sentry project. "Verified" here means exactly that — observed working on real hardware against a real dashboard, not merely correctly wired. See [§59.1](#591-implementation-status) for the full, itemized breakdown, and [§59.24](#5924-android-verification-status) for the verification record.) Sections 1–58 below are the planning document as finalized before implementation (carried over verbatim from the planning branch, `codex/e09-01-crash-reporting-plan`, since this implementation branch was created from `main` and never had this file). **See [§59, Implementation Report](#59-implementation-report-post-planning-update) at the end for what was actually built, actual package versions, files changed, test results, and current verification status.**

Planning branch: `codex/e09-01-crash-reporting-plan` (created from `main` at commit `04af30d`).
Implementation branch: `codex/e09-01-crash-reporting` (created from `main` at commit `04af30d`, independent of the planning branch, per the task's branch rules).

**Revision note (planning-phase)**: the original plan (commit `94246bd`) described iOS as a fully separate future phase. Per product clarification, the architecture was corrected to be **cross-platform from the beginning** — iOS monitoring is designed and, where safe, implemented alongside Android and web now; only steps that genuinely require Xcode, a Mac, or a physical iPhone are deferred. See the revised framing in [§13](#13-recommended-architecture). This framing is what was actually implemented — see §59.

---

## 1. Executive Summary

The roadmap's claim of "0% done — entirely open, 13 backlog issues, no code" is **accurate for crash/error *monitoring*** but understates the amount of adjacent groundwork already in place across all three mobile-relevant surfaces: frontend, Android, and iOS. The repository has **zero crash-reporting or error-monitoring SDK** anywhere — confirmed by repo-wide search and corroborated by existing planning docs ([`docs/production-readiness-checklist.md`](production-readiness-checklist.md) `MONITOR-001`, [`docs/technical-debt-inventory.md`](technical-debt-inventory.md) `TD-OPS-001`, [`docs/global-error-handling-strategy.md`](global-error-handling-strategy.md)) that already flag this as an open, accepted gap.

**Architecture framing (corrected)**: this plan is **not** "Android implementation now, iOS implementation later." It is **cross-platform implementation now, Android verification now, iOS native verification deferred**. The selected SDK (`@sentry/capacitor`) is a single cross-platform package that wraps `@sentry/react` (JS), `sentry-android` (Android native), and Sentry Cocoa (iOS native) behind one shared JS-side `Sentry.init()` call. Building the monitoring wrapper "Android-only" and rebuilding it for iOS later would be strictly worse than designing it cross-platform from day one — the marginal cost of iOS-aware code paths is near zero because the SDK is already cross-platform, and the marginal cost of *not* doing this now is a rebuild later. What genuinely cannot happen without a Mac/Xcode/physical iPhone (SPM dependency resolution and compilation, dSYM generation from a real archive build, physical-device crash/ANR-equivalent verification) is explicitly deferred — see [§16](#16-may-be-deferred-to-the-active-ios-phase).

Recommendation stands: **Option A — Sentry across all layers**, now explicitly confirmed to cover React JS events, Android native events, iOS native events, Android ANRs, iOS native crash symbolication (via dSYM), and shared release/environment metadata with no additional native SDK required beyond what `@sentry/capacitor` already bundles. Full confirmation matrix in [§12](#12-sentry-cross-platform-coverage-confirmation).

Readiness decision: **READY WITH BLOCKERS** — see [§57](#57-final-readiness-decision).

---

## 2. Current Repository State

- Local `main` was fast-forwarded from `3d6d393` to `04af30d` (origin/main) before branching; the fast-forward touched only Android Google-auth validation files, not `frontend/.env`, so the pre-existing local `frontend/.env` modification was preserved untouched throughout.
- Working tree at branch-creation time: only `frontend/.env` modified (untracked change, pre-existing, unrelated to this task — preserved, not staged, not committed).
- This revision continues on the same branch, from planning commit `94246bd`. `frontend/.env` remains untouched by this revision as well.

## 3. Existing Frontend Error Handling

- **Bootstrap** (`frontend/src/main.jsx`): wraps `<App />` in a single top-level `ErrorBoundary` — no `window.onerror`, no `unhandledrejection` listener, no monitoring SDK init.
- **Error Boundary** (`frontend/src/components/ErrorBoundary.jsx`): implements `getDerivedStateFromError` only — **no `componentDidCatch`**, so the caught error is silently discarded (never logged, never reported anywhere). Shows a generic fallback with a reload button; no stack trace exposed to the user. No nested/route-level boundaries.
- **Routing**: hand-rolled via `window.location.pathname`/`history.pushState`, no router library — this is identical inside both Android WebView and iOS WKWebView (Capacitor renders the same bundle in both), so any monitoring wiring here is inherently cross-platform with zero platform branching required.
- **API client** (`frontend/src/api/client.js`): single Axios instance; response interceptor only handles 401→session-cleanup; no centralized error normalization for reporting purposes. Several call sites `console.warn`/`console.info` raw Axios error objects carrying `error.config.headers.Authorization`.
- **Auth error mapping** (`frontend/src/api/authErrorMapping.js`): already classifies native/social-login failures, including `cancelled` (Google login cancellation) — reusable to decide what should/shouldn't be reported.
- **Location** (`frontend/src/utils/locationFailure.js`, `frontend/src/api/locationService.js`): exact GPS coordinates are never currently logged to console.
- **No centralized logger** exists; ~14 files call `console.*` directly with ad hoc prefixes, some running unconditionally in production.
- **No source maps** are generated (`frontend/vite.config.js` does not set `build.sourcemap`).
- **No app version/build/commit identifier** is exposed to the frontend bundle anywhere — this gap affects Android and iOS builds identically, since both consume the same Vite output.
- **No tests** cover the Error Boundary's fallback behavior.

## 4. Existing Android Crash Handling

- Android project lives at `frontend/android/` (Capacitor-managed), `applicationId com.yeshmishak.app`.
- `com.google.gms.google-services` plugin is applied only to support native FCM registration for `@capacitor/push-notifications`. **No Firebase BoM, no `firebase-crashlytics`, no Sentry Android SDK** exist anywhere.
- No custom `Application` subclass exists — `MainActivity` is a bare, empty `BridgeActivity` subclass.
- `google-services.json` exists (git-ignored, materialized at build/CI time from a base64 secret).
- Release build type: `minifyEnabled false`, **no `signingConfig` assigned to `release` at all**.
- `versionCode`/`versionName` are hardcoded (`1` / `"1.0"`) with no CI-driven bump mechanism.
- CI (`android-build-validation.yml`) builds **debug APK only**, gated to manual `workflow_dispatch` — no AAB, no release build, no mapping-file step.

## 5. Existing Backend Error Handling

- FastAPI app (`backend/app/main.py`) has a safe, well-placed catch-all `@app.exception_handler(Exception)` (`app/main.py:75-85`) — the natural hook for `sentry_sdk.capture_exception`.
- A consistent structured-error convention exists (`app/errors.py::raise_api_error`) producing `{"error": true, "code": ..., "message": ...}`, reusable for fatal/expected-error classification.
- Auth failures (401/403) already fail closed with structured codes; existing sanitization discipline (`app/services/job_runs.py::sanitize_error_message/sanitize_error_type`) can be extended, not replaced.
- **Gaps**: no centralized logging config, no environment field anywhere in `Settings`, no request/correlation-ID mechanism, no in-repo Railway config, no dedicated `/health` route, hardcoded `version="0.1.0"`.

## 6. Existing CI/CD and Release Metadata

- 5 workflows total: `android-build-validation.yml`, `ios-debug-build-validation.yml`, `ios-startup-flow-validation.yml`, `ios-xcode-validation.yml`, `password-reset-postgres.yml`. **No frontend-only workflow, no backend-deploy workflow** — Vercel and Railway deploy via their own native git integration.
- **Important for the iOS-implementation-now framing**: the three iOS workflows already run on `macos-latest` GitHub-hosted runners. This means Xcode build validation, SPM dependency resolution, and even a `dSYM`-producing archive build can already be automated in CI **without requiring a locally available Mac** for whoever implements this plan — only *physical iPhone* interaction (real device crash triggering, real ANR-equivalent hang testing) is unavoidably outside CI's reach. This materially shrinks what must wait for the "active iOS phase" — see [§16](#16-may-be-deferred-to-the-active-ios-phase).
- **No workflow exposes `GITHUB_SHA`** to any build; no version auto-bump anywhere (frontend `0.0.0`, Android `1.0`/`1`, backend `0.1.0`, and iOS — see [§8](#8-existing-ios-project-state) — `MARKETING_VERSION 1.0` / `CURRENT_PROJECT_VERSION 1`, the same static-placeholder pattern).
- No git tags exist. Branching convention: `codex/eXX-YY-...`, `feature/eXX-YY-...`, `fix/...`; Conventional Commits with epic/task tags.
- Confirmed via repo-wide search: no `sentry-cli`, `@sentry/*`, `crashlytics`, or dSYM-upload step exists anywhere in CI, Gradle, `Package.swift`, or `package.json` scripts.

## 7. Existing Firebase State

- Firebase is used exclusively for push notifications (web: `frontend/src/firebaseMessaging.js`; backend: `backend/app/services/firebase_push.py`; Android: `google-services.json` + native FCM). **No Firebase Analytics, Performance, or Crashlytics** is enabled anywhere, on either platform. No `GoogleService-Info.plist` exists for iOS (confirmed in [§8](#8-existing-ios-project-state)) — iOS has no Firebase footprint at all today, not even for push (native iOS push, if implemented, would need its own audit; out of scope here).

## 8. Existing iOS Project State

Audited `frontend/ios/` structure-only (no files opened beyond confirming existence; no files modified):

- **Xcode project**: `frontend/ios/App/App.xcodeproj` (with `App.xcworkspace` inside) exists. Top-level layout: `App/App/` (app target — `AppDelegate.swift`, `Assets.xcassets`, `Base.lproj`, `capacitor.config.json`, `config.xml`, `Info.plist`, `public/`), `App/CapApp-SPM/` (a Capacitor-managed Swift Package Manager wrapper, whose `Package.swift` carries an explicit **"DO NOT MODIFY"** header — a hard constraint, see [§22](#22-required-ios-audit-detail) item 1 and item 14), `capacitor-cordova-ios-plugins/` (empty Cordova shim), `debug.xcconfig`, `.gitignore`.
- **Dependency management**: Swift Package Manager, **not CocoaPods** — no `Podfile`/`Podfile.lock` exists anywhere under `frontend/ios/`. `CapApp-SPM/Package.swift` currently lists Capacitor core + the installed Capacitor plugins (SecureStorage, App, AppLauncher, Geolocation, LocalNotifications, PushNotifications, Share, Social Login, Calendar). **No Firebase or Sentry package present.**
- **`GoogleService-Info.plist`**: does not exist anywhere under `frontend/ios/`.
- **`Info.plist`**: exists at `frontend/ios/App/App/Info.plist`. Version fields are build-setting-driven, not hardcoded in the plist: `CFBundleShortVersionString = $(MARKETING_VERSION)`, `CFBundleVersion = $(CURRENT_PROJECT_VERSION)`; in `project.pbxproj`, `MARKETING_VERSION = 1.0`, `CURRENT_PROJECT_VERSION = 1` for both Debug/Release — the same static-placeholder pattern as Android/frontend/backend.
- **`AppDelegate.swift`**: exists, contains no references to Firebase, Crashlytics, Sentry, or any monitoring SDK keyword.
- **Build phases**: no dSYM-upload or Crashlytics/Sentry build phase exists in `project.pbxproj`. The only related setting is the standard Xcode default `DEBUG_INFORMATION_FORMAT = "dwarf-with-dsym"` — this only enables dSYM *generation*, not upload.
- **CI**: `ios-debug-build-validation.yml`, `ios-startup-flow-validation.yml`, `ios-xcode-validation.yml` — none reference Firebase, Crashlytics, or Sentry today; all three already run on `macos-latest`.

**Conclusion**: iOS starts from a genuinely clean slate (no partial Firebase/Sentry investment to reconcile with, unlike Android which already has Firebase-for-push plumbing), but the SPM-based, Capacitor-managed dependency model means the *safe* way to add a native dependency is different from a CocoaPods project — see [§22](#22-required-ios-audit-detail).

## 9. Monitoring Gaps (Summary)

| Layer | Fatal-error capture | Non-fatal capture | Symbolication | Release identity | Correlation |
|---|---|---|---|---|---|
| Frontend (React/Capacitor, shared by Android + iOS WebView) | Discarded silently (no `componentDidCatch`) | None | No source maps generated | No version exposed to bundle | No request ID |
| Android native | None | None | Release unminified, unsigned, no mapping upload | `versionName`/`versionCode` hardcoded | N/A |
| iOS native | None | None | dSYM generated but never uploaded (no upload mechanism exists) | `MARKETING_VERSION`/`CURRENT_PROJECT_VERSION` hardcoded | N/A |
| Backend (FastAPI) | Logged locally only; nothing forwarded | None | N/A (Python) | `version="0.1.0"` hardcoded | No request ID |
| CI/CD | N/A | N/A | No upload pipeline for any platform | No SHA/tag exposed anywhere | N/A |

## 10. Architecture Options

**Option A — Sentry across all layers**, cross-platform from the start: React/Capacitor JS via `@sentry/capacitor`, which itself bundles `sentry-android` (Android native, incl. NDK + ANR watchdog) and Sentry Cocoa (iOS native, incl. app-hang/watchdog-termination detection) as native dependencies pulled in automatically when the npm package is added and the native projects are synced, plus `sentry-sdk[fastapi]` for the backend. One vendor, one dashboard, one shared release format across all four native/JS surfaces (Android, iOS, web/JS, backend).

**Option B — Firebase Crashlytics only.** Covers Android native crashes/ANRs and (if `GoogleService-Info.plist` were added) iOS native crashes via its own iOS SDK, but has **no JavaScript/WebView error capture on either platform and no backend capture**. Rejected outright — this app's primary UI is 100% React inside a Capacitor WebView (WKWebView on iOS, Android WebView on Android); a Crashlytics-only setup would report zero JS errors on either platform.

**Option C — Hybrid: Crashlytics (native crashes, both platforms) + Sentry (frontend + backend).** Most "complete" on paper, but doubles operational surface: two dashboards, two alerting configurations, a second full native SDK integration on **both** Android and iOS (not just one), and — specific to iOS — would require standing up Firebase's iOS SDK and a `GoogleService-Info.plist` from zero, since no Firebase footprint exists on iOS today at all ([§8](#8-existing-ios-project-state)). That is strictly more iOS-side work than Option A, not less.

**Option D — Other.** Considered: Bugsnag, Rollbar, self-hosted GlitchTip. No repository or operational evidence supports these over Sentry — not pursued further.

## 11. Architecture Comparison Matrix

| Criterion | A: Sentry-only | B: Crashlytics-only | C: Hybrid |
|---|---|---|---|
| React/JS error coverage (Android WebView + iOS WKWebView) | Yes | No | Yes (via Sentry half) |
| Android native crash + ANR coverage | Yes | Yes | Yes |
| iOS native crash + app-hang coverage | Yes (Sentry Cocoa, bundled via `@sentry/capacitor`) | Yes, but requires standing up Firebase iOS from zero | Yes, same zero-to-Firebase-iOS cost as B |
| Backend (FastAPI) coverage | Yes | No | Yes (via Sentry half) |
| Single dashboard / single release identifier across Android + iOS + web + backend | Yes | N/A | No — two dashboards, manual release-tag parity across 4 surfaces |
| New iOS-side infra required | None beyond adding the npm package + native sync (see [§22](#22-required-ios-audit-detail)) | Full Firebase iOS SDK + `GoogleService-Info.plist` from scratch | Same as B, plus Sentry |
| Cost at early-stage volume | Sentry free tier likely sufficient | Free/unlimited | Sentry free tier + free Crashlytics |
| Fit for current project stage (no Play Store/App Store release yet, no release signing on either platform, no versioning strategy on either platform) | Best — one thing to stand up correctly, cross-platform by construction | Poor — leaves JS/backend blind on both platforms | Over-engineered; doubles the from-zero iOS Firebase work Option A avoids entirely |

## 12. Sentry Cross-Platform Coverage Confirmation

Per the architecture requirement, the selected package's coverage is confirmed explicitly rather than assumed:

| Capability | Covered by `@sentry/capacitor`? | Mechanism |
|---|---|---|
| React JavaScript events | **Yes** | Wraps `@sentry/react`; identical behavior in browser, Android WebView, and iOS WKWebView |
| Android native events | **Yes** | Bundles `sentry-android` as a native Gradle dependency, pulled in via the plugin's own native manifest |
| iOS native events | **Yes** | Bundles Sentry Cocoa as a native SPM/CocoaPods dependency, pulled in via the plugin's own native manifest — **requires running `npx cap sync ios` (or equivalent native dependency resolution) at least once**, which is an Xcode/macOS-toolchain-dependent step; the npm install alone does not fetch the native binary (see [§22](#22-required-ios-audit-detail) item 3) |
| Android ANRs | **Yes** | `sentry-android`'s `AnrIntegration` (main-thread-blocked ~5s heuristic) |
| iOS native crash symbolication through dSYM | **Yes, conditional on wiring a dSYM upload step** | Sentry Cocoa generates the same native crash reports any Cocoa app would; symbolication requires `sentry-cli debug-files upload` (or the Sentry Cocoa Xcode plugin) to run against the archive's dSYM output — this upload step does **not** exist today and must be added; see [§25](#25-source-map-and-symbolication-strategy) for the design (a CI step, not a hand-edited Xcode build phase, to avoid the pbxproj-corruption risk noted in [§22](#22-required-ios-audit-detail) item 6) |
| Shared release and environment metadata | **Yes** | Single `release` string (`yesh-mishak@<version>+<sha>`) shared verbatim across all four SDK instances (frontend, Android, iOS, backend); `dist` used to further disambiguate Android vs. iOS builds under the same release (see [§24](#24-releaseversion-strategy)) |

**No additional native SDK or configuration beyond `@sentry/capacitor` (with its bundled `sentry-android`/Sentry Cocoa native layers) and `sentry-sdk[fastapi]` for the backend is required.** The only genuinely new piece of infrastructure this plan introduces beyond "install the SDK" is the dSYM/source-map upload CI wiring — which is a design/CI-configuration task, not an additional monitoring package.

## 13. Recommended Architecture

**Cross-platform implementation now, Android verification now, iOS native verification deferred.**

**Option A — Sentry across React/Capacitor, Android native, iOS native, and FastAPI — designed and, where safely possible, implemented for all platforms in this same effort.**

Reasoning:
1. **The SDK is cross-platform by construction, so building it "Android-only" would be artificial** — `@sentry/capacitor`'s JS-side `Sentry.init()` call already targets whichever native layer is present; writing platform-conditional code to *exclude* iOS would be more work than writing it once, correctly, for both.
2. **Sentry alone provides sufficiently reliable Android native crash/ANR coverage** (confirmed in the original plan) **and sufficiently reliable iOS native crash/app-hang coverage** — Sentry Cocoa's app-hang and watchdog-termination detection is the iOS-ecosystem equivalent of Android's ANR watchdog, bundled the same way, via the same npm package.
3. **No existing Firebase-iOS investment exists to build on** ([§8](#8-existing-ios-project-state)) — choosing Crashlytics for iOS would mean introducing an entirely new vendor relationship (Firebase iOS SDK, `GoogleService-Info.plist`, a new Firebase iOS app registration) for a platform where Option A requires zero new vendor relationships.
4. **Single vendor eliminates the duplicate-event and dual-ownership problems** across *four* surfaces (frontend, Android, iOS, backend) instead of the three considered in the original plan.
5. **Deferring only what truly requires physical hardware or a licensed macOS/Xcode toolchain** (native dependency resolution + compilation, real dSYM generation from an archive build, physical-iPhone crash/hang verification) keeps the "active iOS phase" scoped to exactly: Mac/Xcode build validation, CocoaPods/SPM resolution validation, dSYM upload validation, native iPhone crash verification, release-signing verification, and fixing platform-specific issues found during that QA — matching the product requirement precisely.

## 14. Rejected Alternatives

- **Option B (Crashlytics-only)** — rejected: zero JS/WebView coverage on either platform, zero backend coverage, and on iOS specifically would require building Firebase-iOS infrastructure from nothing.
- **Option C (Hybrid)** — rejected for *now*: doubles integration/CI/ownership surface across four platform surfaces instead of three, and specifically **doubles** the from-zero iOS work (both a Sentry Cocoa integration AND a Firebase-iOS integration would be needed on iOS under this option, vs. only Sentry Cocoa under Option A). Documented as a valid future evolution ([§52](#52-related-follow-up-tasks)), not rejected forever.
- **Option D (Bugsnag/Rollbar/self-hosted GlitchTip)** — rejected: no repository or stated-cost evidence favors any of these over Sentry.

## 15. Must Be Implemented During E09-01

The following are in scope for the implementation branch (`codex/e09-01-crash-reporting`) — cross-platform, not Android-only:

- Shared Sentry initialization for React/Capacitor (`frontend/src/monitoring/sentry.js`), platform-neutral — no `if (platform === 'android')` branching for basic init; Capacitor's own `isNativePlatform()`/`getPlatform()` calls are only used where behavior must legitimately differ (e.g., choosing which native `dist` prefix to tag), never to gate whether monitoring is enabled at all.
- JavaScript error reporting that works identically in both Android WebView and iOS WKWebView — a consequence of §3's finding that routing/error-boundary code has no existing platform branching to begin with.
- Cross-platform Error Boundary reporting (`componentDidCatch` added to the existing single `ErrorBoundary.jsx`, used by both platforms since Capacitor renders the same React tree on both).
- Cross-platform unhandled-error and promise-rejection capture (`Sentry.init()`'s bundled `onuncaughtexception`/`onunhandledrejection` integrations — automatic on both platforms, no separate wiring needed).
- Shared environment and release naming (§18, §24) — one taxonomy, one format string, used by all four SDK instances.
- Shared user-context lifecycle (§29) — one `setUser`/`setUser(null)` contract, called from the same `App.jsx` login/logout paths regardless of platform.
- Shared privacy and redaction logic (§28) — one `before_send`/`beforeBreadcrumb` deny-list definition, not a per-platform copy.
- Shared breadcrumbs (§31) — the same breadcrumb event list fires identically on Android and iOS since it's driven by shared React code, not native code.
- Shared source-map generation and upload for the JS bundle (§25) — one Vite build, one upload, consumed by error events from both Android and iOS WebViews plus the plain web deployment.
- Capacitor-native Sentry integration configured for both Android and iOS where supported by the SDK — i.e., the npm package addition, the Android Gradle dependency ([§4](#4-existing-android-crash-handling)-adjacent work, already planned), **and** the iOS native dependency declaration reaching `CapApp-SPM/Package.swift` via the supported `cap sync` mechanism (not hand-editing the "DO NOT MODIFY" file — see [§22](#22-required-ios-audit-detail) item 1).
- Required iOS package/SPM declaration: adding `@sentry/capacitor` to `frontend/package.json` (already required for the frontend regardless of platform) is what triggers the native iOS dependency to become resolvable; **no separate CocoaPods declaration is needed since this project uses SPM, not CocoaPods** ([§8](#8-existing-ios-project-state)).
- Required iOS native initialization code, *if* the live SDK docs confirm it's required at implementation time (flagged as not-fully-certain in [§22](#22-required-ios-audit-detail) item 4 — current evidence suggests the JS-side `Sentry.init()` call is sufficient with zero `AppDelegate.swift` changes, but this must be verified against `docs.sentry.io` at implementation time, not assumed from this planning document).
- Required iOS build configuration that can be prepared safely without physical-device access: the **design** of the dSYM upload mechanism (a CI workflow step extending the existing `macos-latest` iOS workflows, not a hand-edited Xcode build phase — see [§25](#25-source-map-and-symbolication-strategy)) and the exact `sentry-cli` invocation it will run, written and reviewable now even though it cannot be *exercised* until a real archive build runs in CI.
- Xcode build-phase or upload-script **design** for dSYM processing — delivered as a documented, reviewable CI step design in [§25](#25-source-map-and-symbolication-strategy) and [§35](#35-file-by-file-implementation-plan), not as an actual `project.pbxproj` edit (deliberately deferred per [§22](#22-required-ios-audit-detail) item 6, to avoid corrupting a Capacitor-generated file without Xcode available to verify the result).
- iOS release/version mapping aligned with Android/frontend/backend (§24) — using the real, already-existing `MARKETING_VERSION`/`CURRENT_PROJECT_VERSION` build settings ([§8](#8-existing-ios-project-state)), not an invented iOS-specific scheme.
- Documentation of every iOS external setting and owner action ([§49](#49-owner-manual-steps)).
- Automated checks that can run without a physical iPhone ([§42](#42-ios-automated-check-plan)) — dependency-presence checks, CI build validation on `macos-latest`, source-map/release-tag CI assertions.
- Confirmation that no Android-only assumptions are embedded in the monitoring wrapper — tracked as an explicit acceptance criterion ([§54](#54-acceptance-criteria)) and an explicit test ([§38](#38-unit-test-plan)).

## 16. May Be Deferred to the Active iOS Phase

The following genuinely require a Mac, Xcode, CocoaPods/SPM resolution executed locally, or a physical iPhone, and are the *only* things left for that phase:

- Running Xcode on a Mac (for any step beyond what GitHub's `macos-latest` CI runners already automate — see [§6](#6-existing-cicd-and-release-metadata)).
- Running `pod install` and validating the resolved native workspace on a Mac, if unavailable in the current environment — **not applicable to CocoaPods specifically for this project** since it uses SPM ([§8](#8-existing-ios-project-state)), but the equivalent SPM resolution step (`xcodebuild -resolvePackageDependencies` or an Xcode-triggered resolve) carries the same constraint.
- Building and signing a physical iOS app (release signing does not exist yet on iOS any more than it does on Android today).
- Uploading and validating **actual** dSYM files (the upload *mechanism* is designed and wired in this task; running it against a real archive build and confirming a real dSYM lands in Sentry is deferred).
- Triggering a native crash on a physical iPhone.
- Verifying WKWebView/native crash reporting on a physical iPhone.
- Testing background and foreground lifecycle behavior on a physical device.
- Testing multiple supported iOS versions.
- App Store/TestFlight validation.

## 17. Exact Scope Excluded (Non-iOS)

Independent of the iOS-deferral list above, the following remain out of scope for E09-01 on **any** platform:

- Full performance/APM tracing (frontend transaction tracing, backend request tracing) — a distinct, separately-scoped decision (cost, sampling policy), not silently bundled into crash reporting.
- Product/business analytics (funnels, retention, session replay).
- Android release-signing + R8 enablement (improves symbolication quality, not required for crash reporting to function).
- Android ANR *controlled reproduction testing* on a production build (unsafe, addressed only via SDK-level automatic detection).

## 18. Frontend Reporting Design (Shared / Cross-Platform)

- **SDK**: `@sentry/capacitor` initialized once in a new dedicated module `src/monitoring/sentry.js`, called from `src/main.jsx` before `createRoot(...).render(...)`. This single init call is what activates the JS layer on web, the Android native layer (once the Gradle dependency is present), and the iOS native layer (once the SPM dependency is present) — there is no per-platform JS entry point.
- **Error Boundary integration**: add `componentDidCatch(error, info)` to `src/components/ErrorBoundary.jsx`, calling `Sentry.captureException(...)`, guarded by an "is Sentry initialized" check. Identical code path on Android and iOS.
- **Global handlers**: `Sentry.init()` auto-installs `window.onerror` and `unhandledrejection` hooks — closes the frontend gaps in [§3](#3-existing-frontend-error-handling) on both WebView engines simultaneously.
- **Axios integration**: extend `src/api/client.js`'s response interceptor to selectively report per [§27](#27-expected-error-filtering-policy) — platform-neutral, since the API client itself has no platform branching today.
- **Platform tagging (the one legitimate branch point)**: at init time, read `Capacitor.getPlatform()` (already used consistently across the codebase — [§3](#3-existing-frontend-error-handling)) only to set the Sentry `dist` tag (`android-<versionCode>` / `ios-<CURRENT_PROJECT_VERSION>` / `web`) — this is metadata tagging, not conditional feature enablement, and is the only place platform detection is used in the shared module.

## 19. Android Reporting Design (Verification-Focused)

Since the monitoring *wrapper* is now shared ([§18](#18-frontend-reporting-design-shared--cross-platform)), Android-specific work is narrower than in the original plan:

- **SDK**: `io.sentry:sentry-android`, pulled in transitively by `@sentry/capacitor`'s native Android manifest once the npm package + Gradle sync are in place — no separate manual Gradle dependency line should be needed beyond what Capacitor's own build-file generation already handles (verify at implementation time; if the plugin doesn't auto-wire the Gradle dependency, add it explicitly to `frontend/android/app/build.gradle`).
- **Initialization**: requires creating a new `Application` subclass (none exists today) at `frontend/android/app/src/main/java/com/yeshmishak/app/YeshMishakApplication.java` — this remains the one Android-native code change, unrelated to iOS.
- **Verification**: this is the platform that gets **physical QA now** (per the product's Android-first stance) — see [§45](#45-manual-android-verification), unchanged from the original plan.

## 20. iOS Reporting Design

- **SDK**: Sentry Cocoa, pulled in as a native SPM dependency once `@sentry/capacitor` is added to `frontend/package.json` and `npx cap sync ios` is run. This sync step **regenerates** `frontend/ios/App/CapApp-SPM/Package.swift` — it must not be hand-edited (that file's own header says "DO NOT MODIFY"; see [§22](#22-required-ios-audit-detail) item 1).
- **Initialization**: current evidence (not fully certain — see [§22](#22-required-ios-audit-detail) item 4) suggests no `AppDelegate.swift` change is required for baseline crash/error capture, since the JS-side `Sentry.init()` call bridges to the native layer automatically, consistent with Capacitor's plugin auto-registration model. This must be re-verified against the live `docs.sentry.io` Capacitor guide at implementation time before being treated as final.
- **What is committed now vs. deferred**: the npm dependency addition and the shared JS init module are committed now (they're pure JS/config, verifiable via CI/unit tests without a Mac). The *result* of `cap sync ios` (the regenerated `Package.swift`, and any resulting native compilation) requires a macOS/Xcode toolchain to run and verify — this can happen in the existing `ios-xcode-validation.yml`/`ios-debug-build-validation.yml` CI workflows (which already run on `macos-latest`) as part of implementation, without requiring the implementer to personally own a Mac. Only *physical iPhone* verification is pushed to the active iOS phase.
- **dSYM symbolication**: designed now, wired as a CI step (not an Xcode build phase — see [§22](#22-required-ios-audit-detail) item 6 for why), executed and validated against a real archive build during the active iOS phase.

## 21. Backend Reporting Design

- **SDK**: `sentry-sdk[fastapi]`, initialized once in `backend/app/main.py`, guarded by "only if `SENTRY_DSN` env var is set."
- **Integration point**: reuses the existing catch-all `@app.exception_handler(Exception)` hook (`app/main.py:75-85`).
- **Filtering**: `before_send` drops events for status codes classified as expected ([§27](#27-expected-error-filtering-policy)).
- **Non-fatal reporting**: `capture_message` calls at existing failure points in `push_delivery.py`, `email_delivery.py`, and the scheduled-job modules.
- No platform-branching relevance here — backend is inherently platform-neutral; included for completeness of the four-surface coverage confirmed in [§12](#12-sentry-cross-platform-coverage-confirmation).

## 22. Required iOS Audit Detail

1. **Exact current iOS project structure**: see [§8](#8-existing-ios-project-state) in full. Key constraint: `frontend/ios/App/CapApp-SPM/Package.swift` is Capacitor-managed and explicitly marked "DO NOT MODIFY" — any Sentry SPM dependency must arrive via `cap sync`, not a hand edit.
2. **Current `Podfile` and Capacitor dependency behavior**: no `Podfile`/`Podfile.lock` exists; this project uses Swift Package Manager exclusively (Capacitor 8 default). There is no CocoaPods dependency behavior to audit — the equivalent mechanism is SPM package resolution.
3. **Whether `@sentry/capacitor` installs the native iOS SDK automatically**: **No.** `npm install` alone only installs the JS/TS package and the Capacitor plugin wrapper (including its native manifest reference). The native Sentry Cocoa binary is only pulled in once `npx cap sync ios` runs (which triggers SPM/CocoaPods resolution depending on the project's package manager — SPM here), or once Xcode itself resolves the package. This is a required, distinct step from the npm install.
4. **Whether `SentrySDK.start` or another native initialization step is required**: current evidence suggests **not required** for baseline capture — the JS-side `Sentry.init()` call, bridged through the Capacitor plugin, is expected to fully initialize the native iOS layer, consistent with Capacitor's plugin auto-registration model. This is **not fully verified** against the current, authoritative Sentry documentation and must be re-checked live at implementation time rather than assumed from this document.
5. **Whether an `AppDelegate` change is required**: likely **no**, for the same reason as item 4 — but treated as conditional/to-be-confirmed, not a settled fact.
6. **Whether a build phase is required for dSYM upload**: **yes, some upload mechanism is required** to get symbolicated (not just generated) native iOS crash reports. The mechanism does *not* have to be an Xcode "Run Script" build phase specifically — Sentry also documents a CI-step/Fastlane alternative. Given that (a) hand-editing `project.pbxproj` to add a build phase is fragile and error-prone without Xcode available to verify the result, and (b) this repo already has `macos-latest` CI workflows building iOS, **this plan designs the dSYM upload as a new CI step** (extending an iOS build workflow) rather than an Xcode build-phase edit — avoiding any hand-edit of the generated Xcode project file entirely.
7. **Which Sentry auth token and organization/project values are needed for iOS symbol upload**: the same `SENTRY_AUTH_TOKEN` (with `project:releases` and debug-file-upload scope) and organization already planned for Android/frontend uploads ([§29](#29-dependencies) in the original plan) — no separate token is needed if a single Sentry org is used, only an iOS-project-scoped DSN (see item 8).
8. **Whether the same Sentry mobile project should receive Android and iOS events**: **recommended yes** — combine Android and iOS into a single "mobile" Sentry project (distinct from the separate "backend" project), since they share the same React/JS codebase, the same release cadence, and the same Capacitor build pipeline; use the `dist` field (item 9) to keep them visually distinguishable within that one project rather than fragmenting alerts/dashboards across two mobile projects. This is a recommendation the owner can override during the owner-actions step ([§49](#49-owner-manual-steps)).
9. **How Android and iOS releases/dist values will be differentiated**: shared `release` = `yesh-mishak@<app-version>+<sha>` (identical string on both platforms, tying them to the same logical version); `dist` disambiguates the platform build under that release — proposed convention `android-<versionCode>` / `ios-<CURRENT_PROJECT_VERSION>` (see [§24](#24-releaseversion-strategy)).
10. **How JavaScript source maps and iOS dSYM symbolication work together**: they are two separate `sentry-cli` upload operations (`sourcemaps upload` vs. `debug-files upload`) run at different pipeline stages (Vite build vs. Xcode archive), but **associated by using the same shared `release` identifier** — a JS error thrown inside WKWebView symbolicates via the uploaded source map exactly as it would in Android's WebView or a plain browser (same JS engine substrate, same bundle); a true native Swift/Objective-C crash symbolicates via the uploaded dSYM. Both event types land under the same release in the dashboard, correctly distinguished by their `platform`/`dist` tags.
11. **Which iOS files will be modified during implementation**: `frontend/package.json` (already required for the frontend regardless of platform — not iOS-specific); `frontend/ios/App/CapApp-SPM/Package.swift` (auto-regenerated by `cap sync ios`, never hand-edited); possibly `frontend/ios/App/App/AppDelegate.swift` (only if live docs confirm it's required — conditional, see item 4); a new or extended CI workflow file (e.g. `.github/workflows/ios-debug-build-validation.yml` or a new release-focused iOS workflow) to add the dSYM-upload step. **`project.pbxproj` is deliberately not planned for a hand edit.**
12. **Which modifications can safely be made without a Mac**: the shared JS monitoring module (`frontend/src/monitoring/*`), the `package.json` dependency addition, GitHub Actions workflow YAML edits (the dSYM-upload step's *design*, since it only needs to be syntactically valid YAML to commit — it will only actually execute on GitHub's `macos-latest` runners), and all documentation.
13. **Which modifications must wait for Xcode validation**: the actual execution of `cap sync ios` and inspection of the resulting regenerated `Package.swift`; any `AppDelegate.swift` change (must compile and be verified in a real Xcode/CI build before merge, since a mistake there breaks the entire native iOS build, not just monitoring); confirming the CI dSYM-upload step's path actually points at a real archive-build dSYM output (only knowable once a genuine `xcodebuild archive` runs).
14. **How implementation will avoid breaking the existing iOS Capacitor project**: (a) never hand-edit `CapApp-SPM/Package.swift` — add the Sentry dependency the supported way (npm package + `cap sync ios`, letting Capacitor's own tooling regenerate the SPM manifest); (b) treat any `AppDelegate.swift` edit as a small, isolated, reviewable diff gated by the existing `ios-xcode-validation.yml` CI check before merge; (c) never hand-edit `project.pbxproj` — prefer the CI-step-based dSYM upload design over an Xcode build-phase edit, precisely to avoid the corruption risk of manually patching a Capacitor-generated project file without Xcode available to confirm the result.

## 23. Environment Strategy

No `staging` environment exists today on any platform. Environments: `development`, `production`, plus a distinct `feature-branch` tag for CI-built debug artifacts (Android APK today; the same tag applies to any future iOS ad hoc/simulator build produced by feature-branch CI).

| Environment | Sentry `environment` tag | Remote reporting enabled? | Applies to |
|---|---|---|---|
| Local dev (`npm run dev`, Xcode Simulator debug run, `uvicorn --reload`) | `development` | No by default; explicit opt-in for integration testing | All platforms |
| Feature-branch CI build (Android debug APK today; iOS simulator/ad hoc build once implemented) | `feature-branch` | Yes, tagged distinctly, never `production` | Android + iOS + web |
| Production (Vercel frontend, Railway backend, future signed Android release, future signed iOS release) | `production` | Yes | All platforms |

## 24. Release/Version Strategy

Verified actual version sources, now including iOS: frontend `package.json` version = `0.0.0`, Android `versionName`/`versionCode` = `"1.0"`/`1`, backend `version="0.1.0"`, **iOS `MARKETING_VERSION`/`CURRENT_PROJECT_VERSION` = `1.0`/`1`** ([§8](#8-existing-ios-project-state)) — all four are static placeholders today, none CI-generated.

Adopted format: `yesh-mishak@<app-version>+<short-commit-sha>`, shared verbatim across all four SDK instances. `dist` differentiates platform builds under that shared release:

- Android: `dist = android-<versionCode>`
- iOS: `dist = ios-<CURRENT_PROJECT_VERSION>`
- Web (non-Capacitor): no `dist` needed (single build target)

This remains a **prerequisite fix** (CI-driven SHA injection, currently absent for all four surfaces, not just Android/backend as originally scoped) — Vite `define`, Android `buildConfigField`, iOS build-setting injection (e.g. via an `xcconfig` or CI-set environment consumed at archive time), and backend env var all need to be wired.

## 25. Source-Map and Symbolication Strategy

**React/Vite**: enable `build.sourcemap: 'hidden'`; upload via `@sentry/vite-plugin` at build time; auto-delete `.map` files from the public deploy output after upload (closes the "source maps publicly downloadable" edge case). Works identically for the plain web build and the Android/iOS Capacitor builds, since all three consume the same Vite output.

**Android**: unchanged from the original plan — `minifyEnabled` currently `false`, so no mapping file exists yet; Sentry's Android Gradle plugin can auto-upload one once R8 is enabled (a follow-on hardening step, not a blocker).

**iOS**: dSYM upload is designed as **a new CI workflow step**, not a hand-edited Xcode build phase (reasoning in [§22](#22-required-ios-audit-detail) item 6). Concretely: extend the existing `macos-latest` iOS CI workflow(s) with a step that, after an `xcodebuild archive` produces a `.xcarchive` containing dSYMs, runs `sentry-cli debug-files upload --org <org> --project <ios-project> <path-to-dSYMs>` using the same `SENTRY_AUTH_TOKEN` secret already planned for Android/frontend uploads. This step is written and committed now (pure YAML + shell); it can only be *exercised* once a real archive build runs, which today's CI workflows don't yet produce (they currently do simulator/unsigned builds — producing a genuine signed archive with dSYMs is itself part of the release-signing prerequisite, tracked as a dependency in [§34](#34-dependencies), not assumed to already exist).

**Backend**: unchanged — no source maps needed; release/source context matched via the shared release string.

## 26. Event Classification

**Fatal**: Android native/NDK crash; iOS native crash or fatal app hang; uncaught React render error reaching the Error Boundary (on either WebView); application bootstrap failure; unhandled FastAPI exception; a fatal Capacitor plugin failure that prevents the app from continuing (platform-neutral — the same plugin failure path exists on both Android and iOS since it's the same JS-side plugin call).

**Non-fatal**: push-token registration failure after permission granted; repeated map/tile initialization failure; backend dependency unavailable; unexpected database constraint failure; corrupted persisted onboarding state; deep-link resolution failure caused by application logic.

**Expected — not reported by default**: invalid password, email-not-verified, Google-login cancellation, user-denied permission, normal 404/422/429, expected network loss, unsupported-feature-on-browser, empty search result — identical classification regardless of which platform the event originates from, since classification is driven by shared JS/backend code, not native code.

## 27. Expected-Error Filtering Policy

Unchanged from the original plan — filtering happens in shared JS (`authErrorMapping.js` kinds, HTTP status codes) and shared backend code (`raise_api_error` `code` field, `RequestValidationError` 422 status), so the policy is inherently platform-neutral; there is no separate Android or iOS filtering logic to maintain.

**Volume-based exception rule**: unchanged — an otherwise-expected error becomes reportable on anomalous rate or an impossible state, implemented as a shared counter-based override, not duplicated per platform.

## 28. Privacy and Redaction Policy

Unchanged core policy from the original plan (never send passwords, tokens, headers, exact GPS, etc.), now explicitly confirmed to apply identically on iOS: WKWebView's console/network behavior is not meaningfully different from Android WebView for the purposes of this app's own JS code (no platform-specific logging pattern was found in [§3](#3-existing-frontend-error-handling) that would only occur on one WebView engine), so the `beforeBreadcrumb` scrub designed for the Axios-header-in-console-warn risk applies without modification on both platforms.

## 29. User-Context Policy

Unchanged: stable internal user ID only, no email/username/advertising ID, cleared on logout, replaced (not merged) on account switch. Enforced via the single shared `Sentry.setUser()`/`setUser(null)` call sites in `App.jsx` — identical behavior on Android and iOS since both run the same `App.jsx`.

## 30. Location-Data Policy

Unchanged: no coordinates, no city identifier by default — permission state, location-services-enabled boolean, and the existing `FAILURE_TYPES` classification only. Platform-neutral (the same `locationFailure.js`/`locationService.js` modules run on both platforms).

## 31. Breadcrumb Policy

Unchanged small initial breadcrumb set (app launched, auth state changed, onboarding step, map opened, field details opened, game created/joined/left, permission result, push registration result, deep link resolved/failed, API category+status+duration) — fires identically on Android and iOS since it's driven entirely by shared React code.

## 32. Alerting Policy

Unchanged from the original plan (§27 originally) — new-fatal-issue, regression, spike, high-user-impact, ANR-threshold, and backend-exception-rate alerts, email-only for v1. No iOS-specific alert rule is added at this stage since iOS has no verified production traffic yet; the ANR-threshold rule's iOS analog (an app-hang-rate threshold) is deferred to be configured once iOS reaches the active phase and real event volume exists to threshold against.

## 33. Retention, Quota and Cost Considerations

Unchanged reasoning, now explicitly noting that combining Android and iOS into a single Sentry "mobile" project ([§22](#22-required-ios-audit-detail) item 8) reduces quota fragmentation relative to running three separate mobile-adjacent projects, without changing the underlying free-tier math (~5k events/month, 90-day retention).

## 34. Dependencies

**Required before implementation** (owner/human actions): everything in the original plan, **plus**: an iOS-capable Sentry project (or confirmation that the single combined "mobile" project covers iOS too — [§22](#22-required-ios-audit-detail) item 8) and its DSN; confirmation that the existing `SENTRY_AUTH_TOKEN` scope covers iOS debug-file uploads (or a scope adjustment) — no separate token is anticipated to be needed.

**Can be implemented within E09-01**: everything listed in [§15](#15-must-be-implemented-during-e09-01), including the iOS-specific items that don't require a Mac.

**Newly identified prerequisite (both platforms)**: neither Android nor iOS currently produces a *signed, distributable* build ([§4](#4-existing-android-crash-handling), [§8](#8-existing-ios-project-state)) — release signing is a shared gap, not iOS-specific, and remains explicitly out of scope for E09-01 on both platforms (tracked in [§17](#17-exact-scope-excluded-non-ios) and [§52](#52-related-follow-up-tasks)), since a genuine dSYM-bearing archive build requires it.

**Separate follow-up issues**: unchanged list minus "iOS native Sentry Cocoa integration" (now in-scope, not deferred) — see the corrected [§52](#52-related-follow-up-tasks).

## 35. File-by-File Implementation Plan

> All entries below are **proposed** for the future `codex/e09-01-crash-reporting` branch. None were created or modified by this planning task.

### Frontend (shared — drives Android, iOS, and web)

| Path | Exists? | Change | Why | SDK | Env vars | Mac required to verify? |
|---|---|---|---|---|---|---|
| `frontend/src/monitoring/sentry.js` | No (new) | Create init module: `Sentry.init({ dsn, environment, release, dist, tracesSampleRate: 0, beforeSend, beforeBreadcrumb })` | Central, platform-neutral init point | `@sentry/capacitor` | `VITE_SENTRY_DSN` | No |
| `frontend/src/main.jsx` | Yes | Call `initSentry()` before render | Earliest possible init | same | — | No |
| `frontend/src/components/ErrorBoundary.jsx` | Yes | Add `componentDidCatch` → `captureException` | Currently discards all render errors | same | — | No |
| `frontend/src/api/client.js` | Yes | Extend interceptor: classify + selectively report | Reuse existing single API surface | same | — | No |
| `frontend/src/App.jsx` | Yes | `setUser`/`setUser(null)` at login/logout | User-context lifecycle | same | — | No |
| `frontend/vite.config.js` | Yes | `build.sourcemap: 'hidden'` + `sentryVitePlugin(...)` | Symbolication | `@sentry/vite-plugin` | `SENTRY_AUTH_TOKEN` (CI-only) | No |
| `frontend/package.json` | Yes | Add `@sentry/capacitor`, `@sentry/vite-plugin` | Base dependency for all three platforms | — | — | No (npm-level only) |

### Android

| Path | Exists? | Change | Why | Mac required? |
|---|---|---|---|---|
| `frontend/android/build.gradle` | Yes | Sentry Gradle plugin classpath | Native mapping/symbol upload automation | No |
| `frontend/android/app/build.gradle` | Yes | Confirm/add `io.sentry:sentry-android` if not auto-wired | Native crash/ANR SDK | No |
| `frontend/android/app/src/main/java/com/yeshmishak/app/YeshMishakApplication.java` | No (new) | Create `Application` subclass, `SentryAndroid.init(...)` | No Application class exists today | No (Gradle build validates, not Xcode) |
| `frontend/android/app/src/main/AndroidManifest.xml` | Yes | Register Application class + DSN meta-data | Wire the new class | No |

### iOS

| Path | Exists? | Change | Why | Mac required to verify? |
|---|---|---|---|---|
| `frontend/ios/App/CapApp-SPM/Package.swift` | Yes ("DO NOT MODIFY") | **Not hand-edited** — regenerated by `npx cap sync ios` after `@sentry/capacitor` is added to `package.json` | Respects the file's own generation contract ([§22](#22-required-ios-audit-detail) item 1) | **Yes** — regeneration must be run and inspected in an Xcode/CI environment |
| `frontend/ios/App/App/AppDelegate.swift` | Yes | *Conditional* — only if live SDK docs confirm native init is required ([§22](#22-required-ios-audit-detail) item 4) | Avoid unnecessary native-code risk if the JS-side init suffices | **Yes**, if changed — must compile-verify |
| `frontend/ios/App/App/Info.plist` | Yes | No anticipated change (DSN is not typically plist-configured for Capacitor plugins — confirm at implementation time) | — | No, unless proven otherwise |
| `.github/workflows/ios-debug-build-validation.yml` (or new `ios-release-build.yml`) | Yes / proposed new | Add dSYM-upload CI step (design in [§25](#25-source-map-and-symbolication-strategy)) | Symbolication pipeline | Executes on CI's `macos-latest`, not the implementer's machine — safe to write and commit now |

### Backend

Unchanged from the original plan — `backend/requirements.txt`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/services/push_delivery.py`, `backend/app/services/email_delivery.py`.

### Documentation

| Path | Exists? | Change |
|---|---|---|
| `docs/e09-01-crash-reporting-execution-plan.md` | This file (revised) | Cross-platform architecture, iOS audit, revised scope split |
| `docs/crash-reporting-setup-guide.md` | No (proposed, future) | Step-by-step setup, including the iOS `cap sync` + CI dSYM-upload sequence |
| `docs/production-readiness-checklist.md` | Yes | Update `MONITOR-001` once implementation lands |
| `docs/technical-debt-inventory.md` | Yes | Update `TD-OPS-001` similarly |

## 36. Environment Variables and Secrets Matrix

| Name | Layer | Secret or client-visible? | Where stored |
|---|---|---|---|
| `VITE_SENTRY_DSN` | Frontend (shared, all platforms) | Client-visible | Vercel env vars, `.env.*` files |
| `SENTRY_DSN` (Android manifest meta-data) | Android | Client-visible | Build-time value, embedded in manifest |
| `SENTRY_DSN` (iOS, mechanism TBD — plist key or Info.plist build setting, confirmed at implementation time) | iOS | Client-visible | TBD, likely build-setting-injected like `MARKETING_VERSION` |
| `SENTRY_DSN` (Backend) | Backend | Client-visible in principle, stored as env var for rotation ease | Railway env vars |
| `SENTRY_AUTH_TOKEN` | CI only (source maps, Android mapping, **iOS dSYM**) | **Secret** | GitHub Actions secret |
| `RELEASE`, `ENVIRONMENT` | Backend | Not secret | Railway env vars, CI-injected |
| `GITHUB_SHA` | CI (all four surfaces) | Not secret | Built-in Actions context |

## 37. Edge-Case Matrix

All 50 edge cases from the original plan apply unchanged and are platform-neutral in their handling (the shared-wrapper design means most edge cases — e.g. "DSN missing," "monitoring provider unavailable," "test crash reachable in production" — are answered identically for Android and iOS). The following are added or revised specifically for the cross-platform correction:

| # | Edge case | Expected behavior | Event reported? | Platform | Severity | Auto test | Manual test |
|---|---|---|---|---|---|---|---|
| 51 | `cap sync ios` not yet run on a given branch (SPM dependency absent) | iOS build fails clearly at the Xcode/CI level (missing package), not silently — this is a build-time failure, not a monitoring-time failure | N/A | iOS | N/A | Yes (CI) | No |
| 52 | iOS archive build produces no dSYM (e.g., debug config, or `DEBUG_INFORMATION_FORMAT` misconfigured) | Upload step detects zero dSYM files and logs a warning, does not fail the build | No (nothing to upload) | iOS | N/A | Yes (CI) | Yes |
| 53 | iOS dSYM upload runs against the wrong/stale release tag | Dashboard shows symbolication mismatch, same as Edge Case 12 for Android mapping | Yes, degraded readability | iOS | N/A | Yes (CI) | Yes |
| 54 | A future contributor hand-edits `CapApp-SPM/Package.swift` despite the "DO NOT MODIFY" header | Next `cap sync ios` silently overwrites the manual edit — documented as a known Capacitor footgun, not a monitoring-specific risk, but called out here since it directly affects Sentry's native iOS dependency if someone "fixes" it by hand | N/A | iOS | N/A | No | Yes (code review vigilance) |
| 55 | iOS native init turns out to require an `AppDelegate.swift` change (item 4/5 in §22 resolves as "yes" at implementation time) | Implementation plan absorbs a small, reviewable native diff, gated by existing `ios-xcode-validation.yml` CI check before merge | N/A | iOS | N/A | Yes (CI build) | No |

Edge Case 50 from the original plan ("iOS app runs before native iOS monitoring is implemented") is **superseded** by this revision: iOS monitoring implementation is no longer deferred, only physical verification is — the residual risk is now framed as "iOS crashes are captured by the SDK but not yet *confirmed* symbolicated/delivered until a physical-device QA pass occurs," which is a verification gap, not an implementation gap.

## 38. Unit-Test Plan

Unchanged list from the original plan, **plus**:

- **Platform-neutrality test**: assert the shared `src/monitoring/sentry.js` module contains no platform-conditional logic beyond the single documented `dist`-tagging branch ([§18](#18-frontend-reporting-design-shared--cross-platform)) — e.g., a simple static check or code-review checklist item, not a runtime test, since "absence of Android-only assumptions" is a code-shape property.
- Release identifier generation includes correct `dist` value per platform (`android-<versionCode>` vs `ios-<CURRENT_PROJECT_VERSION>`).

## 39. Frontend-Test Plan

Unchanged from the original plan — all component tests (Error Boundary catches render error, HE/EN fallback, retry action, no stack trace shown, event ID display, no auth-state leak, no infinite render loop) apply identically regardless of which WebView engine runs them, since these are DOM-level React tests, not platform-specific.

## 40. Backend-Test Plan

Unchanged from the original plan.

## 41. Android-Test Plan

Unchanged from the original plan.

## 42. iOS Automated-Check Plan

New section — the automated checks that **can** run without a physical iPhone, per the required planning changes:

- CI: `frontend/package.json` lists `@sentry/capacitor` as a dependency (presence check).
- CI: `npx cap sync ios` completes without error on `macos-latest` (dependency-resolution validation — this is the closest automated equivalent to "CocoaPods/package resolution validation" that can run today, using SPM).
- CI: an `xcodebuild build` (or `archive`, once signing exists) for the iOS target succeeds on `macos-latest` — extends the existing `ios-xcode-validation.yml`/`ios-debug-build-validation.yml` pattern.
- CI: if `AppDelegate.swift` was changed, the build must still succeed — a compile-level regression check.
- CI: the dSYM-upload step, when a dSYM is present, runs `sentry-cli debug-files upload` and asserts a non-error exit code, without asserting on Sentry's actual ingestion (that requires dashboard verification, which is deferred — see [§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase)).
- CI: assert the built iOS app bundle does not contain `SENTRY_AUTH_TOKEN` or any other secret value (mirrors the existing Android artifact-secret-scan pattern).
- CI: assert the release string embedded in the iOS build matches the same `GITHUB_SHA`-derived value used for the Android and frontend builds in the same CI run.

None of these require a physical iPhone; all run on GitHub's `macos-latest` hosted runners, consistent with [§6](#6-existing-cicd-and-release-metadata)'s finding that iOS CI already uses Mac runners today.

## 43. CI/CD-Test Plan

Unchanged from the original plan, **plus**: the iOS-specific checks in [§42](#42-ios-automated-check-plan) are added to the CI test plan as first-class items, not an afterthought — feature-branch iOS builds (once they exist) must be tagged `feature-branch`, never `production`, mirroring the existing Android rule.

## 44. Manual Frontend Verification

Unchanged from the original plan — the test-crash trigger, once verified on one platform (e.g. web or Android), is expected to behave identically on iOS WKWebView since it's the same JS code; a spot-check on iOS Simulator (not a physical device, so this is achievable without the deferred hardware) is a reasonable addition during implementation, though not strictly required by this plan.

## 45. Manual Android Verification

Unchanged from the original plan — physical Android QA proceeds now, as the product direction confirms ("Android-first for physical QA").

## 46. Manual Backend Verification

Unchanged from the original plan.

## 47. Manual iOS Verification (Deferred to the Active iOS Phase)

Explicitly deferred, per [§16](#16-may-be-deferred-to-the-active-ios-phase):

1. Build a dedicated test-flavor iOS build (Debug/ad hoc configuration) with a controlled test-crash trigger reachable only in that build.
2. Install on a physical iPhone (not Simulator — native crash/app-hang behavior differs meaningfully on real hardware, same reasoning as the Android ANR note in the original plan).
3. Trigger a native test crash via the dedicated test path.
4. Restart the app.
5. Confirm the report uploads to Sentry.
6. Confirm device model, iOS version, app version, build number, and release/dist tags all appear correctly.
7. Confirm the native stack trace is symbolicated (dSYM correctly matched).
8. Confirm the event lands in the `development`/`feature-branch` environment, not `production`.
9. Remove or permanently guard-disable the test trigger; confirm it's unreachable in a release-configuration build.
10. Test background/foreground lifecycle behavior and, if feasible, multiple supported iOS versions.

**This list must not be claimed as complete based on CI/simulator results alone** — it explicitly requires physical hardware, per the acceptance criterion in [§54](#54-acceptance-criteria) that "missing physical-iPhone QA does not result in claiming iOS verification."

## 48. Dashboard Verification

Unchanged core checklist from the original plan (event appears, grouping sensible, environment/release correct, user-context policy respected, no sensitive data, alerts fire only as configured, issue resolve/regression workflow works) — applies per-platform; the iOS row of this checklist cannot be completed until [§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase) runs.

## 49. Owner Manual Steps

Unchanged list from the original plan, **plus**:

| Action | Where | Secret? | Notes |
|---|---|---|---|
| Confirm iOS events should land in the same "mobile" Sentry project as Android (or create a separate one) | Sentry dashboard | No | Default recommendation is "same project" ([§22](#22-required-ios-audit-detail) item 8); owner may override |
| Obtain/confirm iOS DSN | Sentry project settings | No (DSN is a client-visible ingest key) | Same project as Android under the default recommendation, so may already exist |
| Confirm `SENTRY_AUTH_TOKEN` scope covers debug-file (dSYM) upload | Sentry org settings | Token itself is secret; scope confirmation is not | No new token anticipated |
| Schedule the physical-iPhone QA pass ([§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase)) once a device is available | N/A | No | Explicitly deferred, not blocking implementation |

No further net-new iOS owner actions beyond what's already required for Android/backend — the shared-project recommendation deliberately minimizes new owner overhead.

## 50. Risks

Unchanged risks from the original plan, **plus**:

- **`CapApp-SPM/Package.swift`'s "DO NOT MODIFY" constraint** means the iOS native dependency must arrive purely through the `cap sync` mechanism — if `@sentry/capacitor`'s own native manifest doesn't correctly declare the Sentry Cocoa dependency (a packaging issue on Sentry's side, not this repo's), there is no safe manual fallback without either hand-editing a generated file (risky) or waiting for an upstream fix. This should be verified early in the implementation phase, not assumed.
- **iOS native initialization requirements are not fully certain** ([§22](#22-required-ios-audit-detail) item 4) — if `AppDelegate.swift` changes turn out to be required, that's a larger, riskier diff than pure-JS work and should be budgeted accordingly, not treated as a trivial addition.
- **No iOS release-signing or archive-build pipeline exists yet** — the dSYM-upload CI step designed in this plan cannot be *exercised* until that exists, meaning its correctness is unverified until the active iOS phase, same caveat as the Android mapping-upload step in the original plan.

## 51. Blockers

Unchanged from the original plan, **plus**: physical-iPhone availability is a blocker for [§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase) specifically, but — per this revision's core correction — is **not** a blocker for the cross-platform implementation work itself, which can proceed using `macos-latest` CI runners for build/dependency-resolution validation.

## 52. Related Follow-Up Tasks (Explicitly Out of E09-01)

Revised from the original plan — "iOS native Sentry Cocoa integration" is **removed** from this list since it is now in-scope for E09-01 itself, not deferred:

1. Full performance/APM tracing.
2. Android **and iOS** release signing + (for Android) R8/ProGuard enablement — a shared prerequisite for genuinely distributable, symbolicated release builds on both platforms.
3. Frontend/backend request-correlation-ID system.
4. Product/business analytics.
5. Session replay.
6. Slack/PagerDuty alert routing.
7. Physical-iPhone QA pass ([§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase)) — tracked as a follow-up execution step, not a design gap.
8. App Store/TestFlight distribution validation.
9. CI-driven automatic version/versionCode/build-number bumping across all four surfaces.
10. Firebase Crashlytics hybrid upgrade (unchanged from the original plan — still a valid future evolution, still not selected now).

## 53. Deferred-to-iOS-Phase Checklist

Renamed from "Deferred iOS Requirements" to make clear this is now a **verification-only** checklist, not an implementation-deferral list (the implementation items formerly here have moved to [§15](#15-must-be-implemented-during-e09-01)/[§20](#20-ios-reporting-design)):

- [ ] Run `cap sync ios` and inspect the regenerated `CapApp-SPM/Package.swift` on an actual Mac/Xcode environment (or confirm the `macos-latest` CI run did this correctly).
- [ ] Confirm whether `AppDelegate.swift` needs a native init call, per live SDK docs.
- [ ] Produce a real signed archive build with dSYMs (blocked on iOS release signing, [§52](#52-related-follow-up-tasks) item 2).
- [ ] Run the dSYM-upload CI step against that real archive and confirm ingestion in the Sentry dashboard.
- [ ] Complete physical-iPhone native-crash verification ([§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase)).
- [ ] Test background/foreground lifecycle behavior on a physical device.
- [ ] Test across multiple supported iOS versions.
- [ ] TestFlight/App Store validation pass.

## 54. Acceptance Criteria

All 34 acceptance criteria from the original plan remain satisfied (§ references renumbered but content intact). **New criteria added per this revision**:

35. Shared monitoring code (`src/monitoring/sentry.js`, `ErrorBoundary.jsx`, `client.js`, `App.jsx` user-context hooks) is platform-neutral — verified by the platform-neutrality check in [§38](#38-unit-test-plan).
36. No Android-only monitoring initialization is used — the shared init module targets whichever native layer Capacitor exposes; there is no Android-specific init path that iOS lacks an equivalent for.
37. The existing iOS project receives all safe implementation changes that can be prepared without Xcode (npm dependency, shared JS module, CI workflow design) — see [§15](#15-must-be-implemented-during-e09-01), [§35](#35-file-by-file-implementation-plan).
38. iOS dependency/configuration requirements are committed or fully specified — `@sentry/capacitor` in `package.json` (committed), `cap sync`-driven `Package.swift` regeneration (fully specified, mechanism documented), dSYM-upload CI step (fully specified/designed).
39. JavaScript errors inside iOS WKWebView are covered by design — [§18](#18-frontend-reporting-design-shared--cross-platform), same mechanism as Android WebView.
40. iOS native crashes are covered by design and SDK integration — [§12](#12-sentry-cross-platform-coverage-confirmation), [§20](#20-ios-reporting-design).
41. dSYM upload is designed and wired where safely possible (as a CI step) — [§25](#25-source-map-and-symbolication-strategy).
42. Missing physical-iPhone QA does not result in claiming iOS verification — enforced explicitly in [§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase) and in the status-format requirement below.
43. Final implementation status distinguishes implementation coverage, Android verification, and iOS verification as three separate, independently-reportable dimensions — see [§57](#57-final-readiness-decision) for the adopted status format.

## 55. Definition of Done (for this planning task)

- [x] `docs/e09-01-crash-reporting-execution-plan.md` revised to reflect cross-platform implementation scope.
- [x] iOS project structure, dependency model, and constraints (`CapApp-SPM` "DO NOT MODIFY") audited and documented.
- [x] "Must implement now" vs. "may defer to active iOS phase" split defined per the product's exact required lists.
- [x] Cross-platform coverage of the selected SDK explicitly confirmed (React JS / Android native / iOS native / Android ANR / iOS dSYM symbolication / shared release metadata).
- [x] No implementation performed.
- [x] `frontend/.env` untouched.
- [x] Working on the same dedicated branch, not `main`.

## 56. Recommended Implementation Order

Revised to interleave iOS design work alongside Android/backend rather than deferring it to the end:

1. Owner actions: Sentry org/projects (including the iOS DSN decision, [§22](#22-required-ios-audit-detail) item 8), CI auth token ([§49](#49-owner-manual-steps)).
2. Prerequisite: CI commit-SHA injection across **all four** surfaces (frontend, Android, iOS, backend) + backend `environment`/`release` fields ([§24](#24-releaseversion-strategy)).
3. Backend SDK integration (lowest-risk, single safe hook point, §21).
4. Frontend/shared SDK integration + Error Boundary wiring (§18) — this single step is what makes JS-error coverage land on Android **and** iOS simultaneously.
5. Add `@sentry/capacitor` dependency, run `cap sync` for both `android` and `ios` in the same CI pass, inspect both native manifests for correct dependency resolution (§20 for iOS, §19 for Android) — done together, not iOS-after-Android, since both are driven by the same `cap sync` command.
6. Android native `Application` class (§19) — proceeds to physical Android QA per the product's Android-first stance (§45).
7. iOS native initialization, *if* required per live docs (§22 item 4/5) — proceeds only to CI/Simulator validation (§42), explicitly not physical QA yet (§47, deferred).
8. Source-map CI wiring (§25) — shared JS, benefits both platforms simultaneously.
9. Android mapping-upload CI wiring + iOS dSYM-upload CI wiring (§25) — designed and committed together; Android's can be exercised sooner (no release-signing dependency blocks it as hard, since debug builds already exist), iOS's exercise is blocked on release signing (§52 item 2, tracked as a dependency, not a task-9 blocker for the design itself).
10. Test suite (§38–§43), including the iOS automated-check plan (§42).
11. Manual verification: frontend (§44), Android physical QA (§45), backend (§46) — all completable now. iOS physical QA (§47) explicitly scheduled as a follow-up, not blocking sign-off on the rest.
12. Alert-rule configuration (§32, owner-driven).
13. Documentation updates to `production-readiness-checklist.md` / `technical-debt-inventory.md`, explicitly noting the three-way status split from §57 rather than a single "done" flag.

## 57. Final Readiness Decision

**READY WITH BLOCKERS.**

The architecture is decided and now explicitly cross-platform. The design is fully specified for all four surfaces (frontend, Android, iOS, backend), and the iOS audit found one hard project-level constraint (`CapApp-SPM/Package.swift` is Capacitor-managed, not hand-editable) that shapes — but does not block — implementation. As with the original plan, implementation cannot begin productively until the owner completes the actions in [§49](#49-owner-manual-steps), and the CI-driven release-identity prerequisite ([§24](#24-releaseversion-strategy)) must be budgeted as genuinely new work across all four surfaces, not three.

**Adopted future implementation-status format** (per the product requirement that implementation coverage, Android verification, and iOS verification must be reported as distinct dimensions, not conflated into one "done"): once the implementation branch lands, its status must be reported as one of:

- `CROSS-PLATFORM IMPLEMENTATION COMPLETE — ANDROID VERIFIED — IOS VERIFICATION PENDING` (the expected state immediately after implementation, before a physical iPhone is available)
- `CROSS-PLATFORM IMPLEMENTATION COMPLETE — ANDROID VERIFIED — IOS VERIFIED` (only after [§47](#47-manual-ios-verification-deferred-to-the-active-ios-phase) has actually run on physical hardware)
- `CROSS-PLATFORM IMPLEMENTATION INCOMPLETE` (if any of the "must implement now" items in [§15](#15-must-be-implemented-during-e09-01) were skipped)

**Post-implementation correction history**: immediately after implementation, neither of the first two options anticipated the case actually reached — implementation complete, Android *build/configuration* verified, but no real Sentry organization/DSN existed yet, so no event (JS or native) had ever actually reached a Sentry dashboard, and no physical Android device had been used. "Android verified" had conflated "the wiring is correct" with "a real crash was delivered and confirmed," which are not the same claim. An interim fourth value was used while that gap remained open:

- `CROSS-PLATFORM IMPLEMENTATION COMPLETE WITH BLOCKERS — ANDROID PHYSICAL VERIFICATION PENDING — IOS VERIFICATION PENDING` (interim status, used while real Sentry event-delivery and physical-device verification for Android were still outstanding)

**That gap has since been closed for Android.** A real Sentry organization/project was configured, a branch-build APK was installed on a physical Android device, and a real JavaScript event, a real React Error Boundary event, and a real native crash all appeared correctly in the `yesh-mishak-mobile` project (see [§59.24](#5924-android-verification-status) for the full record). The first bullet option above is therefore now the accurate, current status:

- `CROSS-PLATFORM IMPLEMENTATION COMPLETE — ANDROID VERIFIED — IOS VERIFICATION PENDING` — **this is the current, correct status.** See [§59.1](#591-implementation-status).

This is distinct from — and does not replace — this planning document's own three-value readiness decision (`READY FOR IMPLEMENTATION` / `READY WITH BLOCKERS` / `NOT READY`), which governs whether implementation should *start*, not how its completion should be *reported*.

---

## 58. Confirmations

- No production code, dependency file, or configuration file was modified in this revision — only this documentation file was edited.
- No package was installed (no `npm install`, `pip install`, Gradle, or SPM/CocoaPods dependency change was executed).
- No external Sentry, Firebase, or other monitoring project/account was created or modified.
- `frontend/.env` was not opened, read, staged, edited, or committed during this revision; the pre-existing local modification remains exactly as it was found.
- No secret value was printed or committed anywhere in this document or this session.
- `main` was not modified or merged during this revision.
- Nothing was pushed to any remote during this revision.

---

## 59. Implementation Report (Post-Planning Update)

Everything below reflects the actual implementation on branch `codex/e09-01-crash-reporting` (created from `main` at `04af30d`), not a forward-looking plan.

### 59.1 Implementation Status

**`CROSS-PLATFORM IMPLEMENTATION COMPLETE — ANDROID VERIFIED — IOS VERIFICATION PENDING`**

*(Updated. This report previously used the interim status `CROSS-PLATFORM IMPLEMENTATION COMPLETE WITH BLOCKERS — ANDROID PHYSICAL VERIFICATION PENDING — IOS VERIFICATION PENDING` while real Sentry event-delivery and physical-device verification were still outstanding. Both have since happened: a real Sentry organization/project (`yesh-mishak-mobile`) was configured by the project owner, a branch-build APK was installed on a physical Android device, and a real JavaScript event, a real React Error Boundary event, and a real Android native crash all appeared correctly in that project. "Verified" below means exactly that — actually observed working end-to-end, not merely correctly wired.)*

The status breaks down into five distinct claims, which must not be conflated:

| Dimension | Status | What that means concretely |
|---|---|---|
| **Automated implementation verification** | **Passed** | 55 frontend unit tests (49 original + 6 covering the test-trigger production-safety gate, added when the branch-build trigger gap below was fixed), 5 frontend Playwright tests, 24 backend tests — all newly added for this task — pass. Full pre-existing test suites (1088 backend tests, 341+ frontend Playwright tests) show zero regressions (confirmed against a clean `main` worktree — see §59.19). This verifies the *code is wired correctly and doesn't break anything else*. |
| **Android build/configuration verification** | **Passed** | `npx cap sync android` confirmed `@sentry/capacitor` auto-registers its native Android module; `npm run build:android` (the exact command the CI workflow runs) succeeds. Two follow-up fixes were required and verified before real-device testing could proceed: pinning `@sentry/react` to the exact sibling version `@sentry/capacitor` requires (`10.60.0`, no caret — its bundled `postinstall` check does a literal string comparison, not semver resolution), and adding `VITE_SENTRY_TEST_TRIGGER_ENABLED=true` to the Android branch-build workflow's env block (without it, the built APK never exposed `window.__monitoringTest` at all, making physical verification impossible). |
| **Real Sentry event-delivery verification (JavaScript)** | **Passed** | `triggerTestMessage()` and `triggerReactRenderError()` were both exercised on a physical device against a real Sentry organization/project and confirmed to produce real events in the `yesh-mishak-mobile` project, with correct `branch-build` environment and matching release metadata, no sensitive data observed. Full record in [§59.24](#5924-android-verification-status). *(Source-map symbolication against that real event was not separately itemized by the owner's verification pass — see the known limitation noted in §59.24.)* |
| **Physical Android verification** | **Passed** | A branch-build APK was installed on a physical Android device. `window.__monitoringTest` was confirmed present in that build and confirmed absent in a production-configured build (automated, pre-existing safety-gate test — unaffected by this real-device pass). `triggerTestNativeCrash()` produced a real native crash on the device; after relaunch, that crash event was uploaded and confirmed in the `yesh-mishak-mobile` project. Full record in [§59.24](#5924-android-verification-status). |
| **iOS native verification** | **Pending** | Unchanged — blocked on a macOS/Xcode toolchain and, beyond that, a physical iPhone, neither of which exists in this environment. Preparation (dependency declaration, native-init research) is complete; nothing beyond preparation is claimed. See [§59.25](#5925-ios-verification-status). |

**Not covered by this verification pass**: real event-delivery verification for the *backend* project (the owner's confirmed testing covered only the mobile project — JavaScript and Android-native events — not a live trigger of `GET /__test/sentry-trigger` against a real backend Sentry project). This remains a separate, smaller outstanding item, tracked in [§59.29](#5929-final-blockers).

**Android is not to be described as "verified" until both of the following have actually happened and been confirmed**: (1) a real JavaScript error, triggered from the app, has appeared correctly (with correct release/environment/redaction) in a real Sentry dashboard, and (2) a real Android-native event, triggered from a physical-device branch-build APK, has likewise appeared correctly in that same dashboard. Neither has happened yet.

### 59.2 Actual Architecture Implemented

Exactly as planned in §9–§13: **Sentry across all layers** (React/Capacitor shared JS, Android native, iOS native preparation, FastAPI backend), single vendor, cross-platform SDK (`@sentry/capacitor`) rather than a hybrid Sentry+Crashlytics split. No deviation from the planning decision.

### 59.3 Exact Package Versions Selected

| Package | Version | Layer | Reasoning |
|---|---|---|---|
| `@sentry/capacitor` | `^4.2.0` | Frontend (shared) | Latest stable at implementation time; confirmed via `npm view` against the installed Capacitor 8.4.1 (`@sentry/capacitor`'s own `peerDependencies` require `@capacitor/core >=3.0.0`, satisfied) |
| `@sentry/react` | `10.60.0` (exact, no caret) | Frontend (peer of `@sentry/capacitor`) | Pinned to the exact version `@sentry/capacitor@4.2.0`'s `peerDependencies` declares. Originally recorded here as `^10.60.0`; that caret range passed local resolution but failed `npm ci` in CI, because `@sentry/capacitor`'s bundled `postinstall` script (`scripts/check-siblings.js`) does a literal string comparison against the exact text in `package.json`, not semver resolution -- a caret range never matches the required literal `"10.60.0"` regardless of what actually resolves in `node_modules`. Fixed via `npm install --save-exact`; compatible with the installed React `^19.2.6` (`@sentry/react`'s own peer range covers 16.14–19.x) |
| `@sentry/vite-plugin` | `^5.4.0` | Frontend build (dev dependency) | Latest stable; compatible with the installed Vite `^8.0.12` (no peer conflict on install) |
| `io.sentry:sentry-android` | `8.41.0` | Android native | Not a direct dependency added by this task — confirmed via inspection of `node_modules/@sentry/capacitor/android/build.gradle` that `@sentry/capacitor` itself pins and bundles this version transitively |
| Sentry Cocoa | `>=9.16.1` (per `@sentry/capacitor`'s `Package.swift`) | iOS native | Not yet resolved (requires `cap sync ios` on macOS) — version constraint confirmed by inspecting the installed npm package's `Package.swift` manifest, not fabricated |
| `sentry-sdk` | `==2.66.0` | Backend | Latest stable at implementation time; confirmed compatible with the installed `fastapi==0.133.0`/`starlette==1.3.1` (both natively supported by `sentry_sdk.integrations.fastapi`/`.starlette` without requiring the `[fastapi]` extra, which is no longer needed in modern `sentry-sdk` versions) |

No deprecated Sentry initialization APIs were used (`Sentry.init()` on both JS and Python sides, the current documented entry points for both SDKs).

### 59.4 Frontend Implementation Summary

- New `frontend/src/monitoring/` module: `config.js` (pure environment/release/dist/enabled resolution, unit-tested), `redaction.js` (pure, non-mutating deep redaction + URL-safing, unit-tested), `filters.js` (pure expected-error classification, unit-tested), `client.js` (injectable lifecycle wrapper — init/capture/user/breadcrumb, fail-safe, unit-tested with a fake adapter), `index.js` (the one module that imports `@sentry/capacitor` directly; wires config+redaction+filters into `Sentry.init()`; exports `captureException`/`captureMessage`/`setUser`/`clearUser`/`addBreadcrumb`/`setTag`; also owns the guarded manual-verification test triggers), `TestCrashTrigger.jsx` (tiny dev/test-gated component that turns a devtools call into a real React render-phase throw, since a plain `throw` from `page.evaluate()` never reaches a React Error Boundary).
- `frontend/src/main.jsx`: calls `initMonitoring()` before `createRoot(...).render()`; conditionally mounts `<TestCrashTrigger />` inside the existing `<ErrorBoundary>` only when `window.__monitoringTest` exists (never in production).
- `frontend/src/components/ErrorBoundary.jsx`: added `componentDidCatch` (safe `captureException` call, never throws), converted to `withTranslation()` HOC for bilingual Hebrew/English fallback text, added an optional event-id line (shown only when a real Sentry event id was returned), preserved the existing minimal fallback UI style (heading/message/reload button) and the "no stack trace shown" guarantee.
- `frontend/src/locales/en/common.js` / `he/common.js`: added an `errorBoundary` string group (title/message/reload/eventIdLabel) in both languages.
- `frontend/src/App.jsx`: one `useEffect` keyed on `currentUser?.id` handles the entire user-context lifecycle (login, logout, session restore, account switch) by calling the shared `setUser`/`clearUser` helpers — no per-call-site duplication. Added breadcrumbs at existing natural hook points: app-startup-completed, auth-state-changed, push-registration-started/failed-unexpectedly (with `captureMessage` for the unexpected case), deep-link-resolution-category.
- `frontend/src/api/client.js`: request interceptor now attaches a locally-generated `X-Request-Id` header (§59.5); response interceptor records a safe breadcrumb (endpoint path only, method, status category, duration) on every request, and calls `captureException` **only** for `status >= 500` — expected 4xx/429/etc. are never reported from here, and this is the single place Axios failures are ever reported from (no duplicate-reporting risk against component-level handlers, none of which call `captureException` for plain API failures).
- `frontend/vite.config.js`: `build.sourcemap: 'hidden'`; `@sentry/vite-plugin` added to the plugin list only when `process.env.SENTRY_AUTH_TOKEN` is present, configured to upload under the shared `VITE_SENTRY_RELEASE`/`VITE_SENTRY_DIST` and delete `.map` files from `dist/` after upload; upload failures are caught by a custom `errorHandler` and logged as a build warning, never fail the build.
- `frontend/eslint.config.js`: added a small override so `vite.config.js` (which now reads `process.env`, a Node-context global) lints cleanly — this was a genuine pre-existing gap the new Node-context code in `vite.config.js` exposed, not present before this task touched that file.
- `frontend/package.json`: added `@sentry/capacitor`, `@sentry/react` (dependencies), `@sentry/vite-plugin` (devDependency), and a `test:monitoring` convenience script.

### 59.5 Correlation ID (Small, In-Scope Addition)

Implemented exactly as scoped: `frontend/src/api/client.js` generates a request id (`crypto.randomUUID()`, falling back to a timestamp+random string) and attaches it as `X-Request-Id` on every outgoing request. `backend/app/middleware/request_context.py` (new, ~30 lines) accepts a client-supplied id (validated against a safe `[A-Za-z0-9_-]{1,64}` pattern) or generates one, stores it on `request.state.request_id`, and echoes it back in the response header. Both backend exception handlers tag their captured Sentry events with this id via `capture_unexpected_exception(..., request_id=...)`. Never derived from a user/session token. This did not require any broader middleware or API redesign, consistent with the planning document's condition for including it.

### 59.6 Android Implementation Summary

- `npx cap sync android` was run for real. It auto-detected `@sentry/capacitor@4.2.0` as an installed plugin and regenerated the two Capacitor-managed Gradle files (`frontend/android/app/capacitor.build.gradle` — added `implementation project(':sentry-capacitor')`; `frontend/android/capacitor.settings.gradle` — added the corresponding `include`/`projectDir` lines). **Neither file was hand-edited** — both diffs are the tool's own output.
- Inspection of the installed plugin's native source (`node_modules/@sentry/capacitor/android/.../SentryCapacitor.java`) confirmed native initialization (`SentryAndroid.init(...)`) is driven entirely by the JS-side `Sentry.init()` call via `initNativeSdk()`, and that the plugin's own manifest sets `io.sentry.auto-init=false`. **No custom `Application` subclass and no `AndroidManifest.xml` change were needed or added** — this is a deviation from the original plan's assumption (which anticipated needing a custom `Application` class) based on what the actual installed SDK requires, verified rather than assumed.
- ANR detection (`AnrIntegration`) and native/NDK crash handling (`UncaughtExceptionHandlerIntegration`, `NdkIntegration`) are enabled by default in the bundled `sentry-android` and were not disabled.
- The manual test-crash trigger (`window.__monitoringTest.triggerTestNativeCrash()`, bridging to `Sentry.nativeCrash()`) is gated by the same non-production environment check as the JS test triggers — no Android-specific gating code was needed since the gate lives in the shared JS module.
- `.github/workflows/android-build-validation.yml`: added `VITE_SENTRY_DSN`/`VITE_SENTRY_ENVIRONMENT=branch-build`/`SENTRY_AUTH_TOKEN`/`SENTRY_ORG`/`SENTRY_MOBILE_PROJECT` env vars to the branch-build job; added a "Resolve Sentry release identifier" step (computes `yesh-mishak@<short-sha>` and `android-branch-<run-number>` from `github.sha`/`github.run_number`); added a "Validate optional Sentry configuration" step that warns (never fails) on a missing DSN; added a "Verify no secrets leaked into the built web bundle" step that greps the built `dist/` output for the literal token value and the string `SENTRY_AUTH_TOKEN`, failing the build only if either is found.

### 59.7 iOS Preparation Summary

Exactly the scope the (revised) plan called "must implement now" vs. "may defer": see [§15](#15-must-be-implemented-during-e09-01)/[§16](#16-may-be-deferred-to-the-active-ios-phase), now confirmed against the actually-installed package:

- `@sentry/capacitor` is in `frontend/package.json` — the same dependency shared with Android/web is what makes the native iOS Sentry Cocoa dependency resolvable.
- `frontend/ios/App/CapApp-SPM/Package.swift` (marked "DO NOT MODIFY") was **not** touched. `npx cap sync ios` was deliberately **not** run in this environment (Windows, no Xcode/macOS toolchain) — running it here could not be verified and risked committing an unverified/fabricated SPM manifest state, which the task explicitly forbids.
- `frontend/ios/App/App/AppDelegate.swift` was inspected and left unchanged. Inspection of the installed package's iOS source (`node_modules/@sentry/capacitor/ios/Sources/SentryCapacitorPlugin/SentryCapacitorPlugin.swift`) confirmed `initNativeSdk` calls `SentrySDK.start(options:)` from the JS bridge — the exact same pattern as Android, now **confirmed, not assumed** (the original plan flagged this as "not fully certain").
- `frontend/ios/App/App/Info.plist` was not touched — no code path reads DSN/config from it.
- `.github/workflows/ios-debug-build-validation.yml`: added a "Resolve Sentry release identifier" step (same `yesh-mishak@<short-sha>` format, `ios-branch-<run-number>` dist) and a guarded "Upload iOS dSYMs to Sentry (if configured)" step at the end — skips cleanly with a `::warning::` (never fails the job) when `SENTRY_AUTH_TOKEN`/org/project aren't configured, when no `.dSYM` bundle is found under `DerivedData`, or when the `sentry-cli` upload itself fails. This **cannot be validated end-to-end** yet because this workflow builds an unsigned Simulator app (`CODE_SIGNING_ALLOWED=NO`), not a signed device archive — documented as pending, not claimed as working.

No iOS file was fabricated, and no generated-file "DO NOT MODIFY" contract was violated.

### 59.8 Backend Implementation Summary

- New `backend/app/monitoring.py`: pure `resolve_environment`/`resolve_release`/`is_monitoring_enabled` (mirroring the frontend's `config.js`, unit-tested), pure `redact_deep`/`redact_event` (mirroring `redaction.js`, unit-tested), `init_monitoring(settings)` (fail-safe — an SDK init exception is caught and logged, never crashes startup), `capture_unexpected_exception`/`capture_unexpected_message` (the only two functions anywhere in the backend that call `sentry_sdk.capture_*`).
- `backend/app/core/config.py`: added `sentry_dsn`/`sentry_environment`/`sentry_release`/`sentry_enabled` fields to `Settings`.
- `backend/app/main.py`: `init_monitoring(get_settings())` called once at import time. `generic_exception_handler` (catch-all `Exception`) now also calls `capture_unexpected_exception`. `http_exception_handler` now also calls it, but **only** when `status_code >= 500` — a `raise_api_error(500, "DATABASE_ERROR", ...)`-style internal failure is captured; every 4xx path is structurally excluded since that branch is never reached for them. `RequestValidationError`'s handler was not touched at all (422 is never captured). Both `StarletteIntegration`/`FastApiIntegration`'s automatic 5xx-status auto-capture is explicitly disabled (`failed_request_status_codes=set()`) in `init_monitoring` specifically to prevent this from double-capturing alongside the two manual call sites above — this was a deliberate, verified decision (confirmed via inspecting the installed `sentry-sdk`'s integration constructor signatures), not an assumption.
- `backend/app/middleware/request_context.py`: new correlation-id middleware (§59.5), registered in `app/main.py` alongside the existing `request_metrics_middleware`.
- A protected, environment-gated test route (`GET /__test/sentry-trigger`) is registered in `app/main.py` **only** when `resolve_environment(settings.sentry_environment) != "production"` — confirmed via direct process-level test that it's present by default and structurally absent (not just access-denied) when `SENTRY_ENVIRONMENT=production`.
- `backend/app/services/push_delivery.py`: added `capture_unexpected_exception` at the existing "unknown"-classification branch (already-identified as the unexpected case in the pre-existing `classify_push_error` logic).
- `backend/app/services/email_delivery.py`: added `capture_unexpected_message`/`capture_unexpected_exception` at the `not_configured`, `provider_error`, `malformed_response`, and `missing_email_id` branches (an actual provider rejection/misconfiguration, not a plain timeout/network blip).
- `backend/requirements.txt`: added `sentry-sdk==2.66.0`. `backend/.env.example`: added the four new `SENTRY_*` variable names (no values).

### 59.9 CI/CD Implementation Summary

Covered in §59.6/§59.7 above (both Android and iOS workflow changes) plus the Vite-plugin-based source-map wiring in §59.4. No new workflow file was created — both existing Android and iOS workflows were extended in place. Neither Vercel nor Railway configuration exists in-repo to extend (confirmed during the original planning audit); wiring those is documented as an explicit owner action in [`docs/sentry-configuration-guide.md`](sentry-configuration-guide.md) §7–§8, not fabricated here.

### 59.10 Release Strategy (As Implemented)

`yesh-mishak@<short-sha>` (the interim format, since Android `versionName`/frontend `package.json` version/backend `app.main` version remain static placeholders — this is a pre-existing gap this task did not attempt to fix, consistent with "do not fabricate a version"). `dist` = `android-branch-<run-number>` / `ios-branch-<run-number>` from CI, with a coarse `Capacitor.getPlatform()`-derived fallback (`android`/`ios`/`web`) at runtime when CI hasn't injected a precise value.

### 59.11 Environment Strategy (As Implemented)

`local` / `development` / `branch-build` / `production`, exactly as planned — implemented identically (same resolution algorithm, same "never default to production") on both the frontend (`resolveEnvironment` in `config.js`) and backend (`resolve_environment` in `app/monitoring.py`), confirmed by parallel unit test suites on both sides.

### 59.12 Source-Map Strategy (As Implemented)

Confirmed via direct build inspection during implementation: a local build with no `SENTRY_AUTH_TOKEN` produces `.map` files in `dist/assets/` with **no** `sourceMappingURL` reference in the shipped JS (`grep -c sourceMappingURL` on the built bundle returned 0), and the Sentry Vite plugin is not invoked at all (confirmed by the plugin array being conditionally empty). Upload-then-delete behavior itself (the `filesToDeleteAfterUpload` step) could not be exercised end-to-end in this environment since no real `SENTRY_AUTH_TOKEN` was configured — this is expected and matches "the application must still build and run if Sentry upload is disabled in local development."

### 59.13 Android Symbols/Mapping Strategy (As Implemented)

Unchanged from the plan: `minifyEnabled` remains `false` in `frontend/android/app/build.gradle` (not touched by this task, per the explicit scope exclusion on enabling minification), so no ProGuard/R8 mapping file is generated and no mapping-upload step was needed or added.

### 59.14 iOS dSYM Strategy (As Implemented)

Covered in §59.7. Guarded CI step added; live validation explicitly pending a signed archive build (a prerequisite this task did not create, per scope).

### 59.15 User-Context Behavior (As Implemented, Verified)

`frontend/tests/monitoring-client.test.js` directly verifies (against a fake adapter, asserting the exact call sequence, not just the end state): `setUser()` always calls `adapter.setUser(null)` immediately before `adapter.setUser({id})` — proving account-switch isolation at the mechanism level, not just the observable outcome. `clearUser()` sets `null`. Anonymous startup never calls `setUser` with a stale id. `frontend/src/App.jsx`'s single `useEffect` wiring was verified by code inspection (not a live end-to-end React-render test — see §59.17 for why) to call these exact helpers on every `currentUser` transition.

### 59.16 Redaction Policy (As Implemented, Verified)

Both `frontend/src/monitoring/redaction.js` and `backend/app/monitoring.py`'s redaction functions are directly unit-tested (14 frontend cases, 9 backend cases) for: sensitive-key redaction at arbitrary nesting depth, non-mutation of the input, circular-reference safety, coordinate-key redaction, Authorization-header redaction, cookie removal, request-body removal, and reducing the internal-user-id-only shape of the `user` field on the outgoing event.

### 59.17 Expected-Error Filtering (As Implemented, Verified)

`frontend/tests/monitoring-filters.test.js` (12 cases) directly verifies the documented signature list (Google/native login cancellation, expected permission denial, 401/403/404/422/429, offline-already-handled, browser-extension stack-frame noise) is filtered, and that an unrelated/unexpected error or a genuine 500 is **not** filtered — plus a `monitoring_force_report` escape-hatch test. Backend equivalent is structural (§59.8): expected 4xx/422 never reach a capture call site at all, verified via `test_expected_http_exception_is_not_captured`/`test_validation_error_is_not_captured` in `backend/tests/test_monitoring.py`.

### 59.18 Files Changed

**Frontend (new)**: `src/monitoring/config.js`, `src/monitoring/redaction.js`, `src/monitoring/filters.js`, `src/monitoring/client.js`, `src/monitoring/index.js`, `src/monitoring/TestCrashTrigger.jsx`, `tests/monitoring-config.test.js`, `tests/monitoring-redaction.test.js`, `tests/monitoring-filters.test.js`, `tests/monitoring-client.test.js`, `tests/monitoring-error-boundary.spec.js`.

**Frontend (modified)**: `src/main.jsx`, `src/components/ErrorBoundary.jsx`, `src/App.jsx`, `src/api/client.js`, `src/locales/en/common.js`, `src/locales/he/common.js`, `vite.config.js`, `eslint.config.js`, `package.json`, `package-lock.json`.

**Android (Capacitor-generated, regenerated by `cap sync android`, not hand-edited)**: `android/app/capacitor.build.gradle`, `android/capacitor.settings.gradle`.

**Backend (new)**: `app/monitoring.py`, `app/middleware/request_context.py`, `tests/test_monitoring.py`.

**Backend (modified)**: `app/main.py`, `app/core/config.py`, `app/services/push_delivery.py`, `app/services/email_delivery.py`, `requirements.txt`, `.env.example`.

**CI/CD (modified)**: `.github/workflows/android-build-validation.yml`, `.github/workflows/ios-debug-build-validation.yml`.

**Documentation (new)**: `docs/crash-reporting-architecture.md`, `docs/sentry-configuration-guide.md`, `docs/crash-reporting-incident-workflow.md`.

**Documentation (this file)**: materialized from the planning branch (was never on `main`) and this §59 appended.

**Untouched, confirmed**: `frontend/.env` (pre-existing local modification, never opened/staged/edited); `frontend/ios/App/CapApp-SPM/Package.swift`; `frontend/ios/App/App/AppDelegate.swift`; `frontend/ios/App/App/Info.plist`; `frontend/android/app/src/main/AndroidManifest.xml`; `frontend/android/app/build.gradle` (no manual Gradle dependency was needed — see §59.6).

### 59.19 Test Results (Exact)

- **Frontend unit tests** (`node --test`, new): `tests/monitoring-config.test.js` 12/12 pass; `tests/monitoring-redaction.test.js` 14/14 pass; `tests/monitoring-filters.test.js` 12/12 pass; `tests/monitoring-client.test.js` 11/11 pass. Total: **49/49 pass** (`npm run test:monitoring`).
- **Frontend Playwright** (new): `tests/monitoring-error-boundary.spec.js` **5/5 pass**.
- **Frontend Playwright, full existing suite** (regression check): **341 passed, 5 failed** in the first full run; re-running the failing subset in isolation surfaced a 6th intermittent failure, all in `tests/logout-cleanup.spec.js`, `tests/map-tile-loading.spec.js`, `tests/mobile-scrolling.spec.js`, `tests/performance/baseline.spec.js` — **confirmed pre-existing and unrelated to this change** by running the identical subset against a clean `git worktree` of unmodified `main`: the exact same 6 tests fail identically there (same assertions, same messages). No regression from this implementation.
- **Frontend lint** (`npm run lint`): initially surfaced 5 pre-existing-pattern-gap errors (`process` undefined in `vite.config.js`, since that file never previously used a Node global) — fixed via a small `eslint.config.js` override; **clean after the fix**.
- **Frontend build** (`npm run build`, both with and without `SENTRY_AUTH_TOKEN` set): succeeds in both cases.
- **Backend unit/integration tests** (`pytest`, new): `tests/test_monitoring.py` **24/24 pass** (9 pure resolution/redaction unit tests + 15 FastAPI-integration tests covering capture-exactly-once, expected-exclusion, monitoring-outage-safety, and init-time release/environment attachment).
- **Backend full existing suite** (regression check, `pytest -q`, run in a dedicated fresh virtualenv against the pinned `requirements.txt`): **1088 passed, 1 skipped, 0 failed.** No regression.
- **Android**: `npx cap sync android` succeeded and regenerated the expected two files; `npm run build:android` (the exact step the CI workflow runs) succeeds. Later validated end-to-end on a physical device (§59.20/§59.24).
- **YAML validation**: all modified GitHub Actions workflow files parse successfully as YAML (validated with `PyYAML`).

A genuine testing gotcha was discovered and fixed during backend test-writing: `app/main.py`'s module-level `init_monitoring(get_settings())` call only executes the first time `app.main` is imported in a given Python process — a test fixture that monkeypatches `app.monitoring._enabled` *before* the test body's first `from app.main import app` (if that's the first time `app.main` is imported in that process) gets silently clobbered when that import triggers the real `init_monitoring()` call afterward. Fixed by having the fixture import `app.main` first, before patching. This is noted here since it could bite future contributors writing similar tests against this module.

**Two follow-up fixes landed after the original implementation, both required before real Android verification could proceed:**

1. **`@sentry/react` sibling-version fix** — `@sentry/capacitor`'s bundled `postinstall` script does a literal string comparison of `package.json`'s declared `@sentry/react` version against the exact version it requires (`10.60.0`), not semver resolution; the original `^10.60.0` caret range failed `npm ci` in GitHub Actions even though it resolved correctly locally. Fixed via `npm install --save-exact @sentry/react@10.60.0`. Re-verified after the fix: `npm ci` succeeds, `npm run build` succeeds, all 49 monitoring unit tests and all 5 Playwright Error Boundary tests still pass, lint clean, `npx cap sync android` still succeeds with no unexpected Gradle changes.
2. **Test-trigger branch-build fix** — `android-build-validation.yml` set `VITE_SENTRY_ENVIRONMENT=branch-build` but never set `VITE_SENTRY_TEST_TRIGGER_ENABLED`, so the built APK never attached `window.__monitoringTest` at all, making the physical-device manual verification in §59.20 impossible until fixed. Fixed by adding `VITE_SENTRY_TEST_TRIGGER_ENABLED: 'true'` to that job's env block only (confirmed via `grep` not to be set in any other workflow). The production-safety gate logic (`environment !== 'production'` hard-checked first, unconditionally) was extracted into a new pure, exported `isTestTriggerAllowed()` in `monitoring/config.js` specifically so it could be rigorously unit tested — 6 new tests added, all passing, including the critical property that production is blocked even when the flag is (accidentally) true. This was also verified live, not just at the unit level: built once with `branch-build` + the flag true and confirmed via a real browser session that `window.__monitoringTest` existed with all four functions; rebuilt with `production` + the flag left true and confirmed `window.__monitoringTest` was `undefined`. Total after this fix: 55/55 monitoring unit tests pass (49 original + 6 new).

### 59.20 Manual Verification Completed

- Frontend: the dev-only crash triggers (`window.__monitoringTest.triggerReactRenderError()`/`triggerTestMessage()`) were exercised live against a running dev server via the Playwright spec (§59.19) — HE/EN fallback rendering, no stack trace shown, reload recovers the app.
- Backend: the `GET /__test/sentry-trigger` route's presence/absence logic was verified directly against a running process in both the default (non-production) and `SENTRY_ENVIRONMENT=production` configurations.
- **Android — real physical-device pass (owner-performed, this session's follow-up), PASSED**: a dedicated branch-build APK (built by `android-build-validation.yml` after both follow-up fixes in §59.1 landed) was installed on a physical Android device against a real, owner-configured Sentry organization/project. Confirmed on that device: `window.__monitoringTest` was present (branch-build only); `triggerTestMessage()` produced a real event in the `yesh-mishak-mobile` Sentry project; `triggerReactRenderError()` produced a real React/JavaScript event and the app correctly displayed the safe Error Boundary fallback (no stack trace, no technical detail); `triggerTestNativeCrash()` caused a real native crash, and after relaunching the app that crash event was uploaded and appeared in the same project; environment was `branch-build` and release metadata matched the tested build; no sensitive data was observed in any inspected event. Full detail in [§59.24](#5924-android-verification-status).
- Backend real-event-delivery to a live Sentry dashboard was **not** part of this pass (only the mobile/frontend/Android path was exercised) — see [§59.29](#5929-final-blockers).

### 59.21 Manual Verification Blocked

- All iOS verification (§47/§51 of the plan) — blocked on a macOS/Xcode toolchain and, beyond that, a physical iPhone; neither exists in this implementation environment. Nothing iOS-related is claimed as verified anywhere in this report.
- Backend real-event-delivery verification against a live Sentry dashboard — not yet performed (the completed manual pass covered the mobile project only; see §59.20).

*(Physical Android device crash verification and live mobile-project Sentry dashboard verification are no longer blocked — both were completed and passed; see §59.20/§59.24.)*

### 59.22 Owner Steps Required

Full detail in [`docs/sentry-configuration-guide.md`](sentry-configuration-guide.md). **Completed by the owner since the original implementation**: Sentry organization and mobile project (`yesh-mishak-mobile`) created; DSN and GitHub Actions variables/secret configured for the Android branch-build workflow; physical Android device verification pass run and confirmed passing (§59.20/§59.24). **Still outstanding**: create/confirm the backend Sentry project and run its own real-event-delivery verification; configure the equivalent values in Vercel (frontend) and Railway (backend) production deployments — neither is wired in-repo today since neither platform has any existing in-repo config to extend; configure the six alert rules in the Sentry dashboard; schedule the iOS active phase (macOS/Xcode access, physical iPhone).

### 59.23 External Sentry Configuration Still Required

A real Sentry organization and mobile project (`yesh-mishak-mobile`) now exist and have received real events from a physical-device branch-build APK (§59.24) — the mobile-project side of this requirement is satisfied. **Still required**: a backend Sentry project/DSN has not been confirmed configured or exercised against a live event in this session's verification pass; CI/Vercel/Railway wiring for production releases remains as documented in §59.22.

### 59.24 Android Verification Status

**Verified.** A dedicated branch-build APK (built via `android-build-validation.yml` after the workflow's `@sentry/react` sibling-version fix and `VITE_SENTRY_TEST_TRIGGER_ENABLED` fix both landed — see §59.1) was installed on a physical Android device and manually verified end-to-end against a real, owner-configured Sentry organization and project. Confirmed, in order:

1. The branch-build APK exposed the debug-only Sentry test triggers (`window.__monitoringTest`).
2. `window.__monitoringTest` was available only in the non-production branch build — the automated production-safety-gate test (§59.19, `isTestTriggerAllowed`) already proved this could never happen in a production-configured build; this real-device pass confirms the branch-build side of that same guarantee.
3. `triggerTestMessage()` produced a real event in the Sentry mobile project.
4. `triggerReactRenderError()` produced a real React/JavaScript event, and the app correctly displayed the safe Error Boundary fallback (no stack trace or technical detail shown).
5. `triggerTestNativeCrash()` caused a real Android native crash.
6. After relaunching the app, the native crash event was uploaded to Sentry.
7. All events appeared in the **`yesh-mishak-mobile`** project.
8. Environment was correctly tagged `branch-build`.
9. Release metadata matched the tested build.
10. No sensitive data (tokens, headers, credentials, exact coordinates, etc.) was observed in any inspected event.

**Not covered by this pass**: Android ANR verification (a deliberate ANR trigger was not part of this verification, consistent with the plan's guidance that controlled ANR testing is unnecessary/unsafe to force) and JavaScript source-map symbolication confirmation against the real delivered event (not separately itemized by the owner). Neither is a blocker for the "Android verified" status above, which concerns crash/error *delivery*, not these two specific refinements — both remain reasonable smaller follow-ups.

### 59.25 iOS Verification Status

**Pending in full**, by design and necessity — no macOS/Xcode toolchain or physical iPhone exists in this environment. Preparation (dependency declaration, native-init research confirmed against actual installed source, guarded CI dSYM step) is complete; nothing beyond preparation is claimed.

### 59.26 Known Limitations

- Neither Android nor iOS has a real per-release version-bump mechanism (`versionName`/`versionCode`/`package.json` version/`app.main` version are all still static placeholders) — the interim `yesh-mishak@<short-sha>` release format is used everywhere as a result. Fixing this is out of this task's scope (flagged as a pre-existing gap in the original planning audit, not introduced here).
- Vercel and Railway have no in-repo configuration to extend for `VITE_SENTRY_RELEASE`/`SENTRY_RELEASE` auto-injection from their respective commit-SHA variables — this wiring is documented as an owner action, not implemented, since there is no tracked file in this repo that controls either platform's build/env configuration.
- A handful of App.jsx-level breadcrumbs described in the plan as a "small initial set" (map opened, field details opened, game created/joined/left, onboarding step changed) were **not** individually wired at every page component, to keep the diff reviewable and avoid touching unrelated, complex page files (`MapPage.jsx` in particular, at 1179 lines) under this task's time constraints. What **was** wired (app startup, auth state, push registration, deep-link resolution, plus the generic API-category breadcrumb from the Axios interceptor) already covers the majority of user-journey visibility; the remainder is a small, well-scoped, low-risk follow-up.
- Full React-component-level integration tests for the user-context lifecycle (account A → logout → account B, driven through a live rendered `<App />` with a mocked backend) were not added — this repository has no React component-testing framework (no `@testing-library/react`/jsdom) installed, and adding one was judged out of scope for this task ("do not add unrelated packages" — stated explicitly for the backend, applied here in spirit for consistency). The underlying guarantee is instead verified with full rigor at the `client.js` unit level (§59.15), which is the layer that actually implements the clear-before-set mechanism; `App.jsx`'s wiring onto it is a single, small, code-reviewed `useEffect`.
- The Android native-initialization timing gap (a crash in the brief window between native process start and the WebView executing `Sentry.init()`) is inherent to the Capacitor-bridge model and was not solved — documented in `docs/crash-reporting-architecture.md`, not silently ignored.

### 59.27 Follow-Up Tasks

Unchanged from the plan's §52, still valid: full performance/APM tracing; Android **and** iOS release signing (+ Android R8/ProGuard enablement); a broader page-level breadcrumb pass (§59.26); product/business analytics; session replay; Slack/PagerDuty alert routing; the physical-iPhone QA pass itself; App Store/TestFlight distribution validation; CI-driven automatic version/versionCode/build-number bumping across all four surfaces; the Firebase Crashlytics hybrid upgrade (still not selected, still a valid future evolution once Play Store distribution exists). One item is **resolved** by this implementation and removed from the list: "iOS native Sentry Cocoa integration" is done (dependency declared, native-init behavior confirmed) to the extent possible without Xcode.

### 59.28 Documentation Created

`docs/crash-reporting-architecture.md`, `docs/sentry-configuration-guide.md`, `docs/crash-reporting-incident-workflow.md` (all new), plus this file's §59.

### 59.29 Final Blockers

**Resolved** (kept here for the record, not removed outright, since this section is a historical audit trail):
- ~~No real Sentry organization/project/DSN/auth token exists yet~~ — resolved: the owner created the `yesh-mishak-mobile` Sentry organization/project and configured the Android branch-build workflow's DSN/variables.
- ~~No physical or emulated Android device is available~~ — resolved: a physical Android device was used for the full manual verification pass in §59.20/§59.24.

**Still open**:
1. **Backend Sentry project/event-delivery verification** — a backend Sentry project has not been confirmed configured, and no real backend event (via `GET /__test/sentry-trigger`) has been delivered to and confirmed in a live dashboard. This is the one remaining "real event-delivery" gap; everything else in that dimension (frontend/mobile) is now closed.
2. No macOS/Xcode toolchain or physical iPhone is available in this implementation environment — iOS verification cannot proceed further here regardless of any Sentry configuration progress.
3. Neither Vercel nor Railway configuration exists in-repo, so `VITE_SENTRY_RELEASE`/`SENTRY_RELEASE` auto-injection for production deploys is not yet wired — an owner action, not a code gap in what was requested (the task's own release-format guidance anticipated this exact situation).

**Bottom line: Android cannot be marked "verified" until blockers 1 and 3 are both resolved and a real JS event plus a real Android-native event have both been confirmed in the Sentry dashboard.**
