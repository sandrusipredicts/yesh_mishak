# E08-02 — Permission-Priming Screens for Location and Notifications: Execution Plan

Status: **Planning only.** No production code, native configuration, or tests were modified while producing this document, per the task's explicit instruction. This document converts E08-02 from a roadmap line item into an implementation-ready plan, grounded in an audit of the actual repository state as of commit `eae7ed8` (2026-07-17), not assumptions.

---

## 1. Executive summary

**The headline finding of this audit: E08-02 is already ~85-90% implemented.** The most recent commit on `main` before this planning branch was created — `7672b82 "Build six-step onboarding walkthrough"` (2026-07-17, same day as this task) — added a complete six-step onboarding flow (`welcome → city → location → notifications → guide → ready`) that includes a location permission-priming screen and a notifications permission-priming screen, both with benefit lists, primary/secondary actions, Hebrew+English copy, skip semantics, resumability, and a dedicated Playwright test suite (`frontend/tests/onboarding-flow.spec.js`, `frontend/tests/onboarding-storage.test.js`).

This changes the shape of the work under E08-02 from "build two priming screens" to:
1. **Verify** the existing implementation against every requirement in the E08-02 brief.
2. **Close identified gaps** (a real iOS crash risk, a documentation/policy conflict, missing denial-path test coverage, and a device-vs-account persistence question).
3. **Reconcile** existing architecture docs that now describe behavior the shipped code no longer follows.
4. **Complete native manual QA**, which has not been done for this feature yet (it shipped without device verification evidence).

No backend or database changes are required. No new Capacitor plugins are required. No new native permissions are required on Android. One native iOS configuration key is missing and is a genuine blocker for iOS testing of the *already-shipped* location step (see §7, §24).

---

## 2. Current repository state

- Branch created for this planning work: `codex/e08-02-permission-priming-plan`, based on `main` at `eae7ed8` (fast-forwarded from `7672b82` via `git fetch origin` + `git merge --ff-only origin/main` before branching — no local commits were lost or rewritten).
- Working tree had one pre-existing, unrelated local modification: `frontend/.env` (adds `VITE_GOOGLE_CLIENT_ID`, `VITE_FIREBASE_*` keys). This file was not created or touched by this audit and is left untouched; it is not part of this plan's file-by-file changes and must not be committed.
- Relevant commit history (most recent first): `7672b82` (six-step onboarding walkthrough — the feature this plan audits), `12dc11c`/`f2b19c5`/`d3edfb9`/`d4fd72a` (E07-01, device-calendar, unrelated), `e369c02` (E04-05, FCM token registration lifecycle — a dependency of the notification-priming step), `c22d317`/`68f5f15` (E06-02, sharing analytics, unrelated), `271e834`/`e369c02` region (native auth hardening, unrelated).
- The repo has an extensive `docs/` audit-document convention (120+ files) that this plan follows and extends.

---

## 3. Existing onboarding flow

Entry point: [frontend/src/App.jsx](frontend/src/App.jsx) — the render gate is (in order): session restore (`isSessionReady`) → language selection (`isLanguageSelected`, [LanguageSelectionScreen](frontend/src/components/LanguageSelectionScreen.jsx)) → reset/forgot-password/admin routes → **login** (`currentUser`) → **onboarding** (`onboardingState.status !== 'completed'`, [OnboardingPage.jsx:668-673](frontend/src/pages/OnboardingPage.jsx)) → map/app routes.

**Onboarding runs after login**, not before it. This is a deliberate, already-shipped decision and matters for E08-02 scoping (§12): the priming screens never render for an unauthenticated user.

Steps ([frontend/src/onboarding/onboardingSteps.js](frontend/src/onboarding/onboardingSteps.js)): `['welcome', 'city', 'location', 'notifications', 'guide', 'ready']`, driven by [OnboardingPage.jsx](frontend/src/pages/OnboardingPage.jsx) as a single component with per-step JSX branches, wrapped by [OnboardingLayout.jsx](frontend/src/components/onboarding/OnboardingLayout.jsx) (title/description/primary/secondary buttons, focus management, RTL back-icon swap, safe-area CSS) and [OnboardingProgress.jsx](frontend/src/components/onboarding/OnboardingProgress.jsx) (`role="progressbar"`).

State persistence: [frontend/src/onboarding/onboardingStorage.js](frontend/src/onboarding/onboardingStorage.js) — a single `localStorage` key `onboarding_state` holding `{ version, status, currentStep, completedSteps, city, locationPermission, notificationPermission, startedAt, updatedAt, completedAt }`, validated on every read/write (`validateOnboardingState`), with automatic migration from legacy keys (`onboarding_done`, `userCity`, `language_selected`/`app_language`) so **existing pre-feature users are marked `completed` with `locationPermission`/`notificationPermission: 'skipped'` and never see the new walkthrough** ([onboardingStorage.js:69-87](frontend/src/onboarding/onboardingStorage.js)). This directly satisfies the brief's "existing users upgrade" and "existing users have already denied/skipped" edge cases (#26, #27) — already implemented, already tested (`onboarding-storage.test.js`, "migrates legacy completed users without forcing the walkthrough").

**This storage key is device/installation-scoped, not account-scoped** — it is a flat `localStorage` key with no user-id namespacing. See §14 and §24 for why this matters.

Onboarding is route-less/component-based (no dedicated `/onboarding` path; it's a render-gate state in `App.jsx`), consistent with the rest of the app's manual pathname-based routing (no router library).

---

## 4. Existing location permission flow

Single source of truth: [frontend/src/api/locationPermission.js](frontend/src/api/locationPermission.js), documented in its own header comment as "the only place that talks to `@capacitor/geolocation` or `navigator.geolocation`" (ISSUE-255). Wrapped by [frontend/src/api/locationService.js](frontend/src/api/locationService.js) (caching, normalization, error mapping) which is what all UI callers use — `OnboardingPage.jsx` and `MapPage.jsx` both go through `locationService.js`, so there is **no duplicated/forked location logic** between onboarding and the map.

Key functions:
- `checkExistingPermission()` — non-invasive status read (native `Geolocation.checkPermissions()` / web `navigator.permissions.query({name:'geolocation'})`), never raises an OS prompt. Used by `OnboardingPage.jsx` on mount of the `location` step ([OnboardingPage.jsx:51-56](frontend/src/pages/OnboardingPage.jsx)) and by `MapPage.jsx` on mount ([MapPage.jsx:477](frontend/src/pages/MapPage.jsx)).
- `requestCurrentLocation({highAccuracy})` — the only function that triggers a real OS permission prompt + position fetch, called only from a button handler (`handleLocationPermission` in `OnboardingPage.jsx`, `handleRequestUserLocation` in `MapPage.jsx` via the `LocateFixed` toolbar button) — never on mount, never automatically.
- Repeat-denial heuristic: an in-memory `denialCount` (module-level variable, resets on reload/app restart) escalates from `'denied'` to `'settings'` guidance after 2 consecutive denials in the same runtime ([locationPermission.js:17-67](frontend/src/api/locationPermission.js)).

**Documented policy conflict** (flag, not blocker — resolved in §24): [docs/location-permission-strategy.md](docs/location-permission-strategy.md) §4 lists "Prohibited Times: First app launch, onboarding, user registration, login" for requesting location permission, and [docs/android-location-permission-requirements.md](docs/android-location-permission-requirements.md) §8 states permission triggers "must never trigger on first app launch or during onboarding." The shipped `OnboardingPage.jsx` location step's primary button **does** call `getCurrentLocation()` → `requestCurrentLocation()`, which **does** raise the real native/browser permission prompt, from within onboarding. This is E08-02's entire purpose (a user-initiated, in-context request during onboarding) and is compliant with the *spirit* of "point of need" (explicit user tap, never on mount/launch) but contradicts the *literal text* of both docs. These docs need a decision-record addendum, not a code change (see §17, §24).

No location coordinates are ever persisted into `onboarding_state` (explicitly tested: `onboarding-storage.test.js`, "starts a new six-step state without storing coordinates"; `onboarding-flow.spec.js`, "already granted onboarding location is not prompted again... `persisted` not.toContain('32.0853')"). Location is only used transiently to compute `mapEntryIntent` (§12) at the moment onboarding completes.

---

## 5. Existing notification permission flow

Native path: [frontend/src/api/nativePushNotifications.js](frontend/src/api/nativePushNotifications.js) wraps `@capacitor/push-notifications` (`checkPushPermission`, `requestPushPermission`, `initNativePush`) with 8s/120s/15s timeout guards mirroring the location service's pattern. Web fallback path: `frontend/src/firebaseMessaging.js` (`requestFirebasePushToken`), used when `isNativePushSupported()` is false.

Both paths are unified behind `App.jsx`'s `handleEnableNotifications()` ([App.jsx:480-519](frontend/src/App.jsx)), which is passed as `onEnableNotifications` prop to both `OnboardingPage` and `MapPage`/`NotificationsModal` — **one shared entry point**, no duplicated permission-request logic between onboarding and the existing Settings/notifications UI.

`OnboardingPage.jsx`'s `notifications` step primary button (`handleNotificationPermission`, [OnboardingPage.jsx:100-125](frontend/src/pages/OnboardingPage.jsx)) calls this shared `onEnableNotifications()`, which on success also wires up FCM/APNs token capture and starts the existing `createPushTokenSync` retry/backoff pipeline ([App.jsx:135-146](frontend/src/App.jsx)) — the exact "push token registration happens through the existing notification service" behavior the brief asks for is already the case.

**Notification permission is confirmed opt-in, not automatic on login**: `frontend/tests/push-token-logout.spec.js` was updated in the same commit to require an explicit "Enable push" click before any token registers (test renamed to "...after explicit enable"), and `frontend/tests/onboarding-flow.spec.js` has a dedicated regression test, "login state alone never requests browser notification permission," asserting `window.__notificationRequests === 0` after reaching the welcome screen.

Push token cleanup on logout/account-switch (unregister, no cross-account leakage) is pre-existing, unrelated-to-onboarding infrastructure from E04-05/E04-01 ([App.jsx:521-568](frontend/src/App.jsx), `frontend/tests/push-token-logout.spec.js` "switching accounts on the same device does not leave the token attached").

---

## 6. Android findings

- `frontend/android/app/src/main/AndroidManifest.xml` declares exactly `INTERNET`, `POST_NOTIFICATIONS` (with an explicit "Android 13+" comment), `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION`. **No `ACCESS_BACKGROUND_LOCATION`** — correct per this task's constraint.
- `compileSdkVersion`/`targetSdkVersion` = 36 (`frontend/android/variables.gradle`), `minSdkVersion` = 24 — comfortably above API 33, so the `POST_NOTIFICATIONS` runtime-prompt path is live and required (already declared, already exercised by `requestPushPermission`).
- No custom native Java/Kotlin permission code exists — `MainActivity.java` is a bare `BridgeActivity`. All permission logic is JS-side via Capacitor plugins, as designed.
- `google-services.json` is present and the Gradle build (`android/app/build.gradle`) hard-fails without it — Android push/FCM native wiring is complete and real (unlike iOS, see §7).
- Existing manifest-content regression test: `frontend/tests/background-location-policy.spec.js` (asserts `ACCESS_BACKGROUND_LOCATION` absence and no background-location packages).
- No Android-specific gap blocks E08-02. Manual device QA (Android 13+ prompt behavior, "Don't ask again," approximate-vs-precise dialog) has not been performed for this feature yet (§19).

## 7. iOS findings

- **Blocker**: `frontend/ios/App/App/Info.plist` has **zero location usage-description keys** — no `NSLocationWhenInUseUsageDescription` and (correctly, per this task's "no Always" constraint) no `NSLocationAlwaysAndWhenInUseUsageDescription` either, because none exist at all. This was already flagged as a High-severity risk in `docs/ios-project-structure-audit.md` before this feature existed ("will crash the app on first native geolocation prompt"). It is no longer a hypothetical: `OnboardingPage.jsx`'s location step calls the real Geolocation plugin on every platform, including iOS, the first time a user reaches that step. **Any iOS build attempting to exercise the shipped onboarding location step today will crash.** This is the single concrete pre-existing-code defect this audit surfaces (see §11, §17, §24).
- No notification-related `Info.plist` keys either (no `UIBackgroundModes`), but this is expected/non-blocking: `@capacitor/push-notifications`' local permission request (`UNUserNotificationCenter` authorization) does not require an `Info.plist` usage-description key the way location does, and background remote-notification delivery is a separate, larger concern already flagged as unverified in `docs/ios-startup-flow-validation.md`.
- No custom native Swift permission code (`AppDelegate.swift` is Capacitor boilerplate) — consistent with Android, all logic is JS/Capacitor-plugin-side.
- **No `GoogleService-Info.plist`, no Firebase iOS SDK, no `Podfile`.** iOS uses SPM only (confirmed intentional per `docs/ios-project-structure-audit.md`). This means the notification-priming screen's OS permission prompt will work on iOS (it only needs `@capacitor/push-notifications`), but end-to-end APNs token delivery is unconfigured/unverified — a pre-existing gap, not something E08-02 introduces or is scoped to fix (§10).
- No iOS localization infrastructure (`InfoPlist.strings`) exists, so the new `NSLocationWhenInUseUsageDescription` string will be a single, non-localized (English) value unless a much larger iOS-localization project is undertaken — out of scope for E08-02 (§10).

## 8. Web findings

- Location: `navigator.geolocation` + `navigator.permissions.query({name:'geolocation'})` where available, graceful `'unsupported'` fallback otherwise ([locationPermission.js:254-268](frontend/src/api/locationPermission.js)). Already exercised by existing Playwright tests using `browser.newContext({permissions:['geolocation']})`.
- Notifications: `firebaseMessaging.js`'s web push path, gated behind `typeof Notification === 'undefined'` → `'unsupported'` outcome in `App.jsx`'s `handleEnableNotifications` catch block ([App.jsx:515](frontend/src/App.jsx)) — already produces the `unavailableMessage` copy in the onboarding step. No secure-context handling gap identified (Vite dev server + production both serve HTTPS/localhost, satisfying the Notifications/Geolocation API's secure-context requirement).
- All permission requests are already triggered directly from a user gesture (button `onClick`), never from an effect or on mount — required by both the Notifications API and Geolocation API to avoid silent browser blocking, and already the pattern used throughout.
- `frontend/tests/onboarding-flow.spec.js` already runs the full flow against a real (mocked) browser Notification API and a real Playwright `geolocation` permission context — this is meaningfully more real than a mocked unit test, satisfying the brief's "do not mark E08-02 complete based only on mocked permission tests" for the web tier specifically. Native tiers still need physical/emulator verification (§19-20).

---

## 9. Scope included in E08-02

Given the audit, "implementing E08-02" is reframed as a **verification-and-gap-closure** task:

1. Fix the iOS `Info.plist` missing `NSLocationWhenInUseUsageDescription` (blocker for any iOS QA of the shipped feature).
2. Add automated test coverage for the denied/permanently-denied paths of both priming steps (currently only granted/skipped/already-granted are covered).
3. Decide and, if needed, implement the device-vs-account onboarding persistence question (§14, §17) — at minimum, document the decision even if no code changes.
4. Reconcile `docs/location-permission-strategy.md` and `docs/android-location-permission-requirements.md` with the shipped onboarding-priming pattern (documentation-only, decision-record addendum).
5. Correct the onboarding notification-denial copy that references "Settings" (§17) to point at the actual retry surface, or add a minimal retry affordance — whichever is decided cheaper/safer.
6. Perform and record the Android + iOS + web manual QA passes that have not yet been done for this feature (§19-21).
7. Verify no regression in the areas the shipped commit touched: map entry-intent handoff, deep-link-during-onboarding, push-token lifecycle, account switching.

## 10. Scope explicitly excluded

- Any change to `AndroidManifest.xml` permissions (already correct, already minimal).
- Background location in any form.
- New notification categories/types beyond what `NotificationsModal.jsx`/backend already support.
- Full iOS push (APNs/Firebase) native wiring — pre-existing, unrelated, larger gap; tracked separately, not part of E08-02.
- iOS `Info.plist` localization infrastructure (`InfoPlist.strings`) — the one new string added for E08-02 stays English-only.
- A native "open app settings" deep link (e.g., `app-settings:` / `Settings.ACTION_APPLICATION_DETAILS_SETTINGS`) — no such helper exists today; the shipped/existing pattern is textual guidance (`map.locationSettings`/`map.permissionSettings` copy), not a programmatic deep link. Adding one is a reasonable future enhancement but is not required by any E08-02 acceptance criterion and is not implemented here.
- Store publication, App Tracking Transparency, marketing/email/SMS consent, analytics of any kind, account preference sync across devices, full onboarding redesign, backend/database changes.

## 11. Dependencies and related issues

**Required before implementation (already satisfied by existing code — verify only):**
- Onboarding architecture (`onboardingStorage.js`, `OnboardingPage.jsx`) — exists.
- Location permission helper — exists (`locationPermission.js`/`locationService.js`, ISSUE-255).
- Notification permission helper — exists (`nativePushNotifications.js`, ISSUE E04-01/E04-05).
- Push initialization behavior — exists and tested (`e369c02`, E04-05).
- Localization structure — exists (`i18n/index.js`, `locales/{en,he}/common.js`).

**Blocking / must be done as part of E08-02:**
- iOS `NSLocationWhenInUseUsageDescription` (§7, §17).

**Related/adjacent roadmap IDs found in `docs/`:**
- **ISSUE-255** — location-permission service this feature's location step reuses.
- **E04-01 / E04-05** — native push token registration lifecycle this feature's notification step reuses.
- **ISSUE-251** — location usage audit underlying `location-permission-strategy.md`, needs the decision-record addendum from this plan.
- **ISSUE-261 / ISSUE-262** — background-location-is-out-of-scope decision and its regression-test guard; E08-02 must not violate it (it doesn't).
- **ISSUE-267 / ISSUE-272 / ISSUE-273** — deep-link architecture; ISSUE-272 (game deep links) is done and already has a regression test for deep-link-overrides-onboarding (`onboarding-flow.spec.js`, "pending field deep link overrides onboarding location and city handoff"); ISSUE-273 (field deep links) is separately tracked and not blocking here.
- **E07-01** — most recent precedent for native-plugin governance process, useful reference if E08-02 ever needed a new plugin (it doesn't).
- No existing `docs/` file defines an "E08" epic or references "permission priming" — E08-02 is not cross-referenced anywhere else in the repo prior to this plan.

---

## 12. Proposed user flow

**Sequence (already shipped, verified against the brief's suggested ordering):**

1. Language selection (pre-existing, unchanged, precedes everything).
2. Login/authentication (pre-existing, unchanged) — **onboarding requires authentication**, confirmed by `App.jsx`'s render-gate order (§3). Unauthenticated users never see either priming screen.
3. `welcome` — short app introduction (already exists, satisfies the brief's "if one already exists" step 2).
4. `city` — starting-city selection (pre-existing UI, now step 2 of the walkthrough instead of the whole flow).
5. `location` — priming screen with benefits list, "Allow location" primary action **that itself triggers the native/browser permission prompt** (no separate "native prompt" step — the priming screen's own button press *is* the trigger, which is simpler than the brief's suggested 8-step split and is the correct pattern per Apple/Google HIG: don't show a priming screen then immediately auto-fire the OS dialog without a further tap).
6. `notifications` — same pattern for notifications.
7. `guide` — 3-card "how it works" (find/create/join), replaces the brief's generic "onboarding completion" step with actual product education.
8. `ready` — "Open the map" completes onboarding and hands off to `MapPage` with a computed `mapEntryIntent` (§4): if location was granted, centers the map on the user's real coordinates (fetched once, not stored); otherwise centers on the selected city.

This 6-step order is compatible with the current app because: onboarding already only ever renders once a user is authenticated (no need to gate priming behind auth separately — it's structurally guaranteed); `city` must precede `location`/`notifications` because `ready`'s description interpolates the chosen city; `guide` after both permission steps means the priming screens don't compete with product education for attention.

**Resume/interruption behavior (already implemented, tested):**
- App restart mid-onboarding: `currentStep`/`completedSteps` persist in `localStorage`; `onboarding-flow.spec.js` "refresh resumes a skipped location step at notifications" verifies this directly.
- Interrupted native permission prompt (app backgrounded while the OS dialog is visible): the underlying `requestCurrentLocation`/`requestPushPermission` calls are plain `await`s on the Capacitor plugin promise; if the app is killed mid-prompt, `currentStep` was already saved as `'location'`/`'notifications'` before the button press (only advanced on success/skip), so on relaunch the user re-lands on the same priming screen and can re-tap — no stuck/inconsistent state. Not separately tested today; add a test (§18).
- Back navigation: every step has a `back`/secondary button wired to `moveTo(previous step, completedStep='')`, which does **not** re-add the current step to `completedSteps` — i.e., going back and forward again re-runs that step's permission check-on-mount effect, which is idempotent (already-granted short-circuits to the `'granted'` state without re-prompting). Android hardware back / iOS swipe-back are **not** intercepted by any custom handler — they operate on browser history, not on the onboarding step machine (onboarding has no route/URL per step, §3), so a hardware back-gesture exits whatever the underlying page history is, not the onboarding step. This is worth a manual-QA check (§19-20) but is not a code gap — it's consistent with the rest of the app's routing model.
- A skipped permission step is **not** re-shown automatically later in the same onboarding pass (skip advances `currentStep` past it and marks it in `completedSteps`); the user can later grant location via the map's `LocateFixed` button or notifications via the map's Bell icon → `NotificationsModal`, both pre-existing, both already wired through the same shared services (§4-5). This matches the brief's "avoid repeatedly showing priming screens after the user has already made a clear choice" preference.

**Deep links during incomplete onboarding**: `App.jsx` persists a pending deep-link target in `sessionStorage` independent of onboarding state; `MapPage.jsx`'s `initialEntryIntent` effect explicitly checks `deepLinkTarget` first and skips the onboarding-derived intent when one exists ([MapPage.jsx:660](frontend/src/pages/MapPage.jsx): `if (initialEntryAppliedRef.current || deepLinkTarget) return`). Already tested end-to-end (`onboarding-flow.spec.js`, "pending field deep link overrides onboarding location and city handoff") — deep links are **not deferred**, they resolve immediately after onboarding completes, taking priority over the onboarding-selected city/location.

**Push-notification-launch during incomplete onboarding**: not separately tested; because push deep-link handling (`onNotificationTapped` → `applyDeepLinkTarget`, [App.jsx:496-500](frontend/src/App.jsx)) uses the identical `applyDeepLinkTarget`/`sessionStorage` mechanism as URL-based deep links, the same "deep link wins over onboarding intent" behavior applies by construction. Recommend an explicit test for this specific path (§18) since it hasn't been exercised, even though the code path is shared.

**Account-level vs. device-level**: permission *outcomes* (`locationPermission`/`notificationPermission` granted/denied/etc.) are inherently device/OS-level facts and are correctly never treated as anything else. Onboarding *sequence completion* (have you seen `welcome`/`city`/`guide`) is currently device/installation-level only (§3, §14) — this is the one open design question this plan surfaces (§17).

---

## 13. Permission-state model

The shipped model, `PERMISSION_OUTCOMES` in [onboardingSteps.js](frontend/src/onboarding/onboardingSteps.js), is an **application-level, onboarding-scoped outcome tracker**, deliberately smaller than a full platform-permission-state enum:

| App-level outcome | Meaning | Source |
|---|---|---|
| `pending` | Not yet acted on in this onboarding pass | App-level default |
| `granted` | Confirmed granted (via priming action or already-granted check) | Native/browser permission API |
| `denied` | User declined the OS prompt | Native/browser permission API |
| `skipped` | User tapped "Not now" without triggering the OS prompt | App-level only |
| `unavailable` | Platform/browser doesn't support the capability, or the API errored | Native/browser permission API (absence) |

This is intentionally **not** the same as the platform-level state, which is read live and separately whenever needed:
- Location: `checkExistingPermission()` returns `'granted' | 'denied' | 'prompt' | 'unsupported'` (native `checkPermissions()` / web `Permissions.query`) plus a **derived, in-memory-only** `'settings'` state from the denial-count heuristic in `locationPermission.js` (not a real OS state — the OS never reports "permanently denied" reliably on Android or web, hence the heuristic; iOS *can* report a real "restricted"/"denied" distinction via `CLAuthorizationStatus`, not currently surfaced separately).
- Notifications: `checkPushPermission()` returns whatever `@capacitor/push-notifications`' `checkPermissions().receive` reports — `'granted' | 'denied' | 'prompt'` — plus `'unsupported'` when the plugin/API is unavailable.

**The app-level `PERMISSION_OUTCOMES` value is never treated as authoritative for gating real behavior** — every real permission-gated action (fetching a GPS fix, registering a push token) re-checks the live platform API at the point of use (`getCurrentLocation`/`requestCurrentLocation`, `checkPushPermission`/`requestPushPermission`); the stored `onboarding_state` value is only used to decide *onboarding UI flow* (which step to render, whether to auto-advance), never to decide whether to actually attempt a location fetch or push registration. This satisfies the brief's "do not store a local 'granted' value as the source of truth" requirement as shipped.

**Gap**: states like `restricted` (iOS parental-controls case), explicit `service disabled` (device-wide GPS/notifications off), and a distinct `error while checking permission state` are not modeled separately — they currently collapse into `'unavailable'`/`'denied'`. This is a reasonable simplification for a first pass and is not a blocker, but should be called out as a known limitation rather than silently assumed complete (§24).

---

## 14. Storage and persistence decisions

**Existing mechanism**: plain `localStorage`, one key (`onboarding_state`), validated JSON blob, with a `version` field (`ONBOARDING_VERSION = 1`) enabling forward-safe schema migration ([onboardingStorage.js:40-55](frontend/src/onboarding/onboardingStorage.js): unknown versions reset to a fresh state rather than crashing).

This is consistent with the rest of the app's persistence approach (`sessionStorage` for pending deep links, `localStorage` for auth tokens via `sessionStorage.js`, city preference, push-token cache) — **no new persistence mechanism is introduced or needed.** No Capacitor Preferences, no backend user-preferences endpoint, no new table.

**Open decision (device-level vs. account-level)**: `onboarding_state` has no user-id namespace. Per §3/§12, this means:
- Permission *outcomes* staying device-level is correct — matches OS reality, and prevents an unnecessary duplicate OS prompt for a second account on the same device (satisfies acceptance criterion #20 as-is, since a granted OS permission is genuinely already granted regardless of which account is logged in).
- Onboarding *step completion* (specifically `city` and `guide`) staying device-level means a second account on the same device silently inherits the first account's city selection and skips the welcome/guide education screens entirely, without ever being asked. This is a product decision, not obviously a bug, but it should be an explicit decision rather than an accident.

**Recommendation**: keep the storage mechanism as-is (no new persistence layer), but namespace the *existing* `localStorage` key by the authenticated user id (e.g., `onboarding_state:{userId}`, falling back to the legacy unscoped key only for the one-time migration path in §3) so a second account on the same device gets its own onboarding pass, while permission-outcome checks (`checkExistingPermission`/`checkPushPermission`) remain unchanged and continue to read the live, correctly device-scoped OS state. This is a small, mechanical change (§15) that resolves the only real ambiguity in the current design without touching the permission logic at all. If the project owner prefers the simpler current behavior (one onboarding pass per device, ever), that is also defensible — this plan flags it as a decision for the owner (§25) rather than presupposing an answer.

---

## 15. File-by-file change plan

| File | Exists? | Change | Why | Risk |
|---|---|---|---|---|
| `frontend/ios/App/App/Info.plist` | Yes | Add `NSLocationWhenInUseUsageDescription` with an approved, truthful, non-mandatory-sounding description (English only, no localization infra exists). No `Always`/background key added. | Blocking iOS crash risk (§7) for the already-shipped onboarding location step. | Low — additive plist key, no behavior change to existing keys (`NSCalendarsUsageDescription` etc. untouched). |
| `frontend/src/onboarding/onboardingStorage.js` | Yes | *If the account-scoping decision (§14) is approved*: namespace `ONBOARDING_STORAGE_KEY` by user id, add a one-time read fallback to the legacy unscoped key for migration. If not approved, no change. | Resolves the second-account-on-device ambiguity (§14, §24). | Medium — touches the migration path; must not regress the existing legacy-migration tests (`onboarding-storage.test.js`). Needs new tests either way (§18). |
| `frontend/src/App.jsx` | Yes | *Only if* the account-scoping change lands: pass `currentUser.id` into `resolveOnboardingState()`/`saveOnboardingState()` calls (currently called with no args, i.e., anonymous). | Wires the storage-key change through to the actual call sites (`onboardingState` init, `handleOnboardingComplete`). | Low-medium — call-site-only change, same shape as existing `resolveOnboardingState()` usage. |
| `frontend/src/locales/en/common.js`, `frontend/src/locales/he/common.js` | Yes | Fix `onboarding.notifications.deniedMessage` copy: it currently says "enable them later in Settings" but the actual retry surface is the map's Bell icon → Notifications modal, not the `/settings` route ([SettingsPage.jsx](frontend/src/pages/SettingsPage.jsx) has no push/location controls). Reword to reference the correct in-app surface, or add the copy fix alongside a small `SettingsPage.jsx` addition (see next row) — pick one. | Copy accuracy (§9 item 5); avoids sending users to a screen with no matching control. | Low — string-only change if `SettingsPage.jsx` is left alone. |
| `frontend/src/pages/SettingsPage.jsx` | Yes | *Optional, only if the copy-fix-alone approach (previous row) is rejected*: add a small "Permissions" section mirroring the existing "App preferences" section, showing current location/notification status (read live via `checkExistingPermission`/`checkPushPermission`) with a retry button that calls the same shared services already used elsewhere. | Gives the literal `/settings` route a retry entry point, matching users' likely expectation from the copy. | Medium — new UI surface; must not duplicate `NotificationsModal`'s logic (reuse `onEnableNotifications`, `checkExistingPermission`, `checkPushPermission` — do not fork). |
| `frontend/tests/onboarding-flow.spec.js` | Yes | Add tests: (a) location permission denied once → error copy shown, onboarding does not block, city-based `mapEntryIntent` still used; (b) notification permission denied → same; (c) app-relaunch mid-native-prompt resumes correctly; (d) push-notification-tap deep link during incomplete onboarding overrides onboarding intent (mirroring the existing URL-deep-link test). | Closes the denial/interruption/push-launch coverage gaps identified in §12, §18. | Low — additive tests, Playwright already supports denying `geolocation` context permission and stubbing `Notification.requestPermission` to resolve `'denied'`. |
| `frontend/tests/onboarding-storage.test.js` | Yes | *If account-scoping lands*: add tests for per-user key namespacing and legacy-key migration under a namespaced key. | Matches the storage change. | Low. |
| `docs/location-permission-strategy.md` | Yes | Add a decision-record addendum: onboarding priming screens (E08-02) are an approved exception to §4's "Prohibited Times," specifically because the OS prompt is only triggered by an explicit in-onboarding button tap, never on mount/launch — the policy's actual intent (no silent/automatic requests) is preserved. | Reconciles documented policy with shipped, sanctioned behavior (§4, §17). | None — docs-only. |
| `docs/android-location-permission-requirements.md` | Yes | Same addendum against §8's "must never trigger... during onboarding" language. | Same. | None — docs-only. |
| `docs/e08-02-permission-priming-execution-plan.md` | New (this file) | This plan. | Required planning deliverable. | None. |

**No changes proposed to**: `AndroidManifest.xml`, `capacitor.config.ts`, any backend file, `frontend/src/api/locationPermission.js`, `frontend/src/api/locationService.js`, `frontend/src/api/nativePushNotifications.js`, `frontend/src/firebaseMessaging.js`, `frontend/src/onboarding/onboardingSteps.js`, `frontend/src/pages/OnboardingPage.jsx`, `frontend/src/components/onboarding/*`, `frontend/src/pages/MapPage.jsx` — all already correctly implement the required behavior per this audit.

---

## 16. Edge-case matrix

| # | Case | Expected behavior (current or planned) | Status | Test type |
|---|---|---|---|---|
| 1 | Location already granted before onboarding | `checkExistingPermission` on mount sets `'granted'` silently, primary button becomes "Continue," no re-prompt | Implemented | Automated (exists: "already granted... not prompted again") |
| 2 | Notification already granted before onboarding | Same pattern via `checkPushPermission` | Implemented | Automated (needs explicit test — currently only location's already-granted case is covered) |
| 3 | Location denied once | `deniedMessage` shown, onboarding continues, `locationPermission:'denied'` persisted | Implemented, undertest | Automated (to add) |
| 4 | Location permanently denied | In-memory denial-count heuristic escalates messaging on the *map's* re-request; onboarding step itself doesn't surface a distinct "permanently denied" message today (only generic `deniedMessage`) | Partial gap | Manual QA + note as known limitation (§13) |
| 5 | Notification denied | `deniedMessage` shown, onboarding continues | Implemented, undertest | Automated (to add) |
| 6 | Notification cannot be requested again (OS-level) | `checkPushPermission` returns `'denied'`; app cannot distinguish "can prompt again" from "blocked" on any platform (OS limitation, not app bug) — same heuristic gap as location | Known platform limitation | Manual QA |
| 7 | User skips location priming | `locationPermission:'skipped'`, advances to `notifications` | Implemented | Automated (exists) |
| 8 | User skips notification priming | `notificationPermission:'skipped'`, advances to `guide` | Implemented | Automated (exists) |
| 9 | User closes app during priming (before tapping primary) | State already saved as `currentStep:'location'`/`'notifications'` from the previous step transition; relaunch resumes at the same step | Implemented | Manual QA (Android/iOS) |
| 10 | User closes app while native prompt visible | Same as #9 — no state transition happens until the promise resolves, so nothing is lost; relaunch re-shows the same priming screen | Implemented by construction | Manual QA |
| 11 | Permission changed in device settings while app closed | Next mount's `checkExistingPermission`/`checkPushPermission` re-reads live state; onboarding step (if not yet completed) picks up the new state; **map/settings do not proactively re-check after onboarding is done** except on next mount of the relevant screen | Mostly implemented | Manual QA |
| 12 | Permission changed while app backgrounded | `App.jsx`'s `appStateChange`/`visibilitychange` handlers re-validate the *session*, not permissions; permission re-check only happens on next mount of a permission-consuming screen, not on resume | Acceptable gap (matches existing map behavior, not new to E08-02) | Manual QA |
| 13 | Location services disabled globally | Surfaces as `'unavailable'` via the existing error classification (`unavailableMessage`) | Implemented | Manual QA |
| 14 | Notifications disabled globally (OS-level) | Surfaces as `'denied'` via `checkPushPermission` | Implemented | Manual QA |
| 15 | Native permission API throws | Caught, falls back to `'unavailable'`/`'denied'` (try/catch around every plugin call in both services) | Implemented | Automated (unit-level, exists for storage; add for permission services) |
| 16 | Capacitor plugin unavailable | `loadPlugin()`/`Capacitor.isPluginAvailable` guards return `null`/`'unsupported'` | Implemented | Automated (exists indirectly via web-mode tests) |
| 17 | Runs in normal browser | Web fallback paths for both location and notifications | Implemented | Automated (exists) |
| 18 | Browser doesn't support Notifications | `'unavailable'` outcome, `unavailableMessage` copy | Implemented | Automated (add explicit test) |
| 19 | Request not from a user gesture | N/A — every request already originates from a button `onClick` | Implemented by construction | Code review (done in this audit) |
| 20 | User not authenticated | Onboarding never renders pre-login (§3) | Implemented by construction | Automated (implicit in `App.jsx` gate order; add explicit assertion) |
| 21 | Second account logs in on same device | Permission outcomes correctly device-scoped; onboarding *sequence* is currently also device-scoped (inherits first account's completion) — open decision, §14/§17 | **Gap — decision required** | Automated (add after decision) |
| 22 | App reinstalled | `localStorage` cleared with the app — fresh onboarding, correct | Implemented | Manual QA |
| 23 | App storage cleared | Same as #22 | Implemented | Manual QA |
| 24 | Deep link during incomplete onboarding | Deep link wins, onboarding-derived intent skipped | Implemented | Automated (exists) |
| 25 | Push-notification launch during incomplete onboarding | Same mechanism as #24 by construction, not separately tested | Implemented, undertest | Automated (to add, §15) |
| 26 | Existing user upgrade (no priming previously) | Legacy migration marks `completed`/`skipped`, no forced walkthrough | Implemented | Automated (exists) |
| 27 | Existing user already denied permissions pre-feature | Same migration path; live re-check on next map/notifications interaction reflects real OS state regardless of migrated `onboarding_state` value | Implemented | Automated (exists, indirectly) |
| 28 | Permission state `prompt`/`denied`/`granted`/`restricted`/platform-specific | `restricted` not distinctly modeled (§13) | Partial gap | Manual QA (iOS restricted case specifically) |
| 29 | Approximate location granted (iOS/Android) | Accepted as `'granted'`; no accuracy-tier differentiation in onboarding (matches `locationPermission.js`'s explicit "does not differentiate rendering" comment, ISSUE-255 scope) | Implemented, by design | Manual QA |
| 30 | Location request succeeds, coordinates retrieval fails | Falls to `'unavailable'`/`unavailableMessage` via existing error mapping | Implemented | Manual QA |
| 31 | Push permission granted, token registration fails | `onTokenError` callback fires, logged; onboarding still treats permission-grant outcome as `'granted'` (token delivery is a separate concern handled by `createPushTokenSync`'s retry/backoff) | Implemented | Manual QA + existing token-sync tests |
| 32 | Network unavailable | Neither priming screen makes a network call directly (permission APIs are local); push token upload retries via existing backoff | Implemented | Manual QA |
| 33 | RTL layout on small screens | `OnboardingLayout`/`.onboarding-*` CSS already has safe-area + `100dvh`-based responsive rules and a `@media` breakpoint (`App.css:650-667`) | Implemented | Manual QA (physical small device) |
| 34 | Android hardware back button | Not intercepted by onboarding (no per-step route); operates on whatever page history exists beneath it | Needs verification, not a known gap | Manual QA |
| 35 | iOS swipe-back gesture | Same as #34 | Needs verification | Manual QA |
| 36 | Rapid repeated taps on permission button | `actionPendingRef` guards both `handleLocationPermission` and `handleNotificationPermission` against re-entry | Implemented | Automated (add a rapid-tap unit/component test) |
| 37 | Permission result returns after unmount | Effects use an `active`/`isMounted` flag before calling `setState` (`useEffect` in `OnboardingPage.jsx:49-69`); action handlers don't have an unmount guard around their `await` (a resolved promise after unmount would still call `setState` on an unmounted component in React) | **Minor gap** in the action handlers (mount-effect path is guarded, click-handler path is not) | Automated (add regression test + small guard) |
| 38 | Onboarding completion inconsistent with actual permission state | Not possible for completion itself (schema-validated on every write), but `locationPermission`/`notificationPermission` values can go stale relative to live OS state after completion — by design, since live checks are always re-done at point of use (§13) | Implemented, by design | Code review (done) |

---

## 17. Security and privacy review

- Permission explanations (§6 onboarding copy, already-shipped) are truthful and specific (map position, nearby fields/games, navigation; game updates, changes, reminders) — no misleading "mandatory" framing; both steps have a genuine, unblocking skip.
- No location data is collected merely by displaying the priming screen — `checkExistingPermission()` is a passive OS query, not a location fetch; an actual coordinate fetch only happens after the user taps "Allow location" (or, separately, once at `ready`-step completion if already granted, to compute the map entry point — still user-initiated by virtue of having tapped "Allow" earlier in the same session).
- The OS prompt is triggered only from explicit button presses — verified in code (§4-5) and by the dedicated regression test ("login state alone never requests browser notification permission").
- Skipping does not trigger the prompt later in the same pass (§12) — verified.
- Existing location-privacy behavior (`docs/location-permission-strategy.md`'s point-of-need pattern for the *map's* own re-request) is unchanged by this plan; only the documentation needs a decision-record addendum (§15), not a behavior change.
- Existing push-token handling, per-user isolation, and logout cleanup (E04-01/E04-05) are unchanged; account-switch token hygiene already tested and unaffected by anything in this plan.
- Permission state is never treated as authentication/authorization anywhere in the codebase (confirmed — no route/API gate reads `onboarding_state`).
- No permission state is sent to the backend — `onboarding_state` is `localStorage`-only; the backend's `notification_preferences` table stores user-chosen notification *preferences* (radius/city/fields), not raw OS permission status.
- No new analytics/tracking introduced by this plan.
- No background location requested or proposed anywhere in this plan (§10).
- The one open decision in this plan (§14, account-scoping) does not introduce any new privacy surface — it only changes *which onboarding UI a user sees*, not what data is collected or where it's sent.

---

## 18. Automated testing plan

**Unit tests** (`frontend/tests/onboarding-storage.test.js`, extend):
- Per-user key namespacing and migration, if §14's account-scoping is approved.
- Permission-outcome value normalization already covered; add explicit `restricted`/error-during-check paths if §13's model is extended.

**Component/integration tests** (`frontend/tests/onboarding-flow.spec.js`, extend — this file is already a hybrid component+integration Playwright suite exercising real DOM + mocked network):
- Location permission denied once → correct copy, non-blocking continuation.
- Notification permission denied once → correct copy, non-blocking continuation.
- Notifications already granted before onboarding → step auto-shows "Continue," no duplicate prompt (mirrors the existing location test).
- Browser without Notifications API → `unavailableMessage` shown, non-blocking.
- Rapid double-tap on a priming primary button → only one permission request fires (`actionPendingRef` guard, currently untested).
- Component unmounts mid-request (navigate away/refresh during the async permission call) → no React "set state on unmounted component" warning/crash (§16 item 37; may require a small `isMounted`-style guard added to `handleLocationPermission`/`handleNotificationPermission` alongside the test).
- Push-notification-tap deep link arriving during incomplete onboarding → same override behavior as the existing URL-deep-link test.
- Second account login on same device → behavior matches whichever decision is made in §14 (either "own onboarding pass" or "inherits device state," but asserted explicitly either way).
- Not-authenticated state never renders either priming screen (explicit assertion, currently only implicit).

**End-to-end scenarios** (already-covered baseline + additions):
- New installation, no permissions → both steps show priming, both grantable. *(exists)*
- Both permissions skipped → completes, city-based entry. *(exists)*
- Location granted via already-active browser permission, notifications skipped → mixed outcome persisted correctly. *(exists, location-granted case; add explicit mixed-outcome variant)*
- Existing user upgrade (legacy `onboarding_done`) → no forced walkthrough. *(exists)*
- Deep-link launch during onboarding → deep link wins. *(exists)*
- Browser execution end-to-end (already the primary test environment — Playwright/Chromium). *(exists)*

**What automated tests cannot cover** (native permission dialogs, Android 13+ system prompt chrome, iOS `CLLocationManager` authorization sheet, "Don't ask again" checkbox behavior, actual APNs token delivery) — these require manual device QA (§19-21) per the brief's explicit instruction not to mark E08-02 complete on mocked tests alone. The existing Playwright suite already uses *real* browser permission contexts (not mocks) for the web tier, which is a meaningfully stronger signal than a unit-level mock, but is still not a substitute for native-device verification.

## 19. Android manual QA plan

- Android versions/API levels: at minimum one API 30-32 device/emulator (pre-notification-permission behavior) and one API 33+ device/emulator (current `targetSdkVersion` 36 baseline).
- Android 13+ notification prompt: verify the system `POST_NOTIFICATIONS` dialog appears exactly once from the onboarding notification step's "Enable notifications" tap, not before.
- Older Android (API < 33) notification behavior: verify no notification permission dialog is shown (none required pre-13) and the step still completes with `'granted'` semantics (Capacitor's `checkPermissions()` should report accordingly — verify, don't assume).
- Location: verify the unified Android 12+ coarse+fine dialog appears on "Allow location" tap; verify an approximate-only grant is accepted (§16 item 29) and does not error.
- Denied and "Don't ask again": verify the app doesn't crash or hang when the OS silently denies future prompts; verify onboarding still completes (skip-equivalent path).
- Settings redirect: confirm current copy (pointing users to device Settings manually) is accurate on real Android chrome/wording for this OS version.
- Fresh install vs. upgrade install (from a build predating `7672b82`): verify migration path (§3) — no forced walkthrough for upgraded users.
- Relaunch after interruption (kill app mid-prompt): verify resume behavior (§16 items 9-10).
- RTL layout + safe areas on at least one small physical Android device.
- Physical-device verification required — emulator-only is not sufficient per Definition of Done (§23).

## 20. iOS manual QA plan

- **Prerequisite**: the `Info.plist` fix (§7, §15) must land before any of this QA can run without crashing.
- Supported iOS version range: match whatever the project's existing iOS QA docs (`docs/ios-development-environment.md`) specify; verify against at least one current-generation iOS version.
- Location "Allow Once" vs "Allow While Using App": verify both are treated as `'granted'` by `checkExistingPermission`/`requestCurrentLocation` (Capacitor's Geolocation plugin should normalize this, but must be confirmed on-device — this repo has never exercised real iOS location permission end-to-end before, per §7).
- Location denial, and approximate location acceptance (§16 item 29).
- Notification allow/deny via the real `UNUserNotificationCenter` sheet.
- Settings redirect copy accuracy for iOS wording specifically ("Settings > yesh_mishak" path differs from Android's).
- Fresh install and relaunch-after-interruption (§16 items 9-10, 22).
- Physical iPhone verification required, not simulator-only, per Definition of Done (§23) — simulators do not reliably exercise the real location/notification permission chrome.
- Safe-area and swipe-back behavior on at least one large iPhone (notch/Dynamic Island safe-area) and confirm `App.css`'s `env(safe-area-inset-*)` rules render correctly.
- **If physical-device access is unavailable to whoever implements this**, the Definition of Done (§23) requires an explicit project-owner-approved exception recorded with evidence and reason — do not silently skip.

## 21. Web manual QA plan

- Chrome desktop: geolocation allow/deny via the browser's native permission chip; Notifications allow/deny via the native browser prompt.
- Safari desktop: same, noting Safari's stricter secure-context and user-gesture enforcement (already satisfied per §8).
- A mobile browser where available (e.g., Chrome Android or Mobile Safari, outside the Capacitor shell) — confirms the web-fallback code paths (§8) work outside the native app entirely, which is a distinct code path from "Android/iOS native QA" above.
- Unsupported Notifications API (simulate via an older/uncommon browser or `delete window.Notification`) → confirm graceful `unavailableMessage`, no crash.
- Confirm the permission prompt is genuinely tied to the button click in each tested browser (not just asserted in Playwright — a manual click-through confirms real browser gesture-detection heuristics accept it).

---

## 22. Acceptance criteria

Mapped against the brief's 30 required criteria, with current status:

1. Location priming screen exists, follows design/localization systems — **Done** (shipped).
2. Notification priming screen exists, follows design/localization systems — **Done** (shipped).
3. Hebrew RTL + English support — **Done** (shipped, verified copy in both locale files, RTL CSS).
4. OS prompts occur only after explicit primary-action tap — **Done** (verified in code and by regression test).
5. Skipping does not block continuation — **Done**.
6. Skipping does not trigger the OS prompt — **Done** (tested).
7. Already-granted permissions don't duplicate-prompt — **Done** (tested for location; add explicit notification-side test, §18).
8. Existing users handled without forced restart — **Done** (migration logic, tested).
9. Existing location behavior remains functional — **Done** (no fork/duplication introduced, §4).
10. Existing notification/push behavior remains functional — **Done** (shared `handleEnableNotifications`, §5).
11. Permission status read from platform API, not inferred from local flags — **Done** (§13).
12. Denied/permanently-denied states produce guidance — **Partial**: denied is handled; a distinct "permanently denied" message inside onboarding itself is not surfaced (only the map's separate re-request flow has escalating settings guidance) — close as part of §9 item 2 or explicitly accept as a known limitation (§24).
13. Retry / open-settings entry point exists — **Done, but copy-accuracy gap** (§9 item 5, §15) — either fix copy or add the `SettingsPage.jsx` affordance.
14. Android 13+ notification permission handled correctly — **Implemented, needs manual QA sign-off** (§19).
15. Older Android versions don't show an invalid flow — **Implemented, needs manual QA sign-off** (§19).
16. iOS location/notification flows use correct APIs and usage descriptions — **Blocked** until the `Info.plist` fix lands (§7, §15).
17. Web degrades safely — **Done** (§8).
18. Duplicate rapid-tap protection — **Done in code** (`actionPendingRef`), **needs an explicit test** (§18).
19. Interrupted onboarding resumes predictably — **Done** (§12, §16).
20. Second account on same device doesn't cause unnecessary OS prompts — **Done** for the OS-prompt half; onboarding-sequence half is an open decision (§14, §17).
21. No background location introduced — **Confirmed, none exists** (§6, §10).
22. No new tracking/analytics — **Confirmed** (§17).
23. No backend/DB change unless justified — **Confirmed: none needed, none proposed**.
24. Relevant automated tests pass — pending §18's additions being written and run.
25. Android manual verification passes — pending, not yet performed (§19).
26. iOS manual verification passes or is explicitly marked pending with reason — pending, blocked on §7's fix (§20).
27. Web manual verification passes — pending, not yet performed (§21).
28. No regression in auth/onboarding/map/location/games/notifications/deep-links/startup — no regression identified in this audit; existing test suites for those areas (`push-token-logout.spec.js`, deep-link tests, background-location-policy.spec.js) were checked and are consistent with the shipped onboarding changes.
29. Implementation occurs on a dedicated branch — **this plan already establishes `codex/e08-02-permission-priming-plan`**; the *implementation* itself should occur on the separately-recommended `codex/e08-02-permission-priming` branch (§26), not on this planning branch, and not on `main`.
30. No automatic merge into `main` — **confirmed not done as part of this planning task** (§28).

## 23. Definition of Done

Unchanged from the brief, restated with this plan's specifics:
- This approved plan followed.
- Implementation work happens on `codex/e08-02-permission-priming` (a new branch off `main`, not this planning branch).
- All file-by-file changes in §15 documented (as changes land).
- Automated tests from §18 all passing.
- Android physical-device verification (§19) completed with recorded evidence.
- iOS physical-device verification (§20) completed with recorded evidence, or an explicit project-owner-approved exception with evidence and reason if physical iOS hardware is genuinely unavailable.
- Web verification (§21) completed.
- Existing location functionality (map re-request, distance-based notification preference) re-verified, not just onboarding's new usage of it.
- Existing notification/push functionality (settings toggle, token lifecycle, logout cleanup) re-verified.
- Fresh-install onboarding verified end-to-end on a real or emulated device per platform.
- Existing-user upgrade path verified (no forced walkthrough).
- Skip/denied/granted/permanently-denied flows verified across all three platforms.
- No regression found in the areas listed in acceptance criterion #28.
- No secrets, generated artifacts (e.g., `frontend/ios/App/App/capacitor.config.json`, which the iOS audit confirmed is git-ignored/generated), signing files, or `.env` files committed — note the pre-existing local `frontend/.env` modification (§2) must specifically **not** be swept up in any implementation commit.
- No merge into `main` occurs automatically as part of any of this work.
- Completion evidence (test output, QA screenshots/notes) provided alongside the PR.

---

## 24. Risks and unresolved questions

1. **iOS crash risk is real, not theoretical** (§7) — any attempt to run the *already-shipped* onboarding location step on an iOS build today will crash on first native geolocation call. This should be treated as a P0 fix regardless of how the rest of E08-02 is sequenced, since it affects already-merged `main` code, not just planned work.
2. **Documentation/code conflict** (§4, §15) — `location-permission-strategy.md` and `android-location-permission-requirements.md` currently forbid, in explicit language, exactly what the shipped onboarding does. This plan's recommendation (add a decision-record addendum treating explicit-user-tap-during-onboarding as compliant with the policy's actual intent) requires project-owner sign-off — it is a policy interpretation, not a pure engineering call (§25).
3. **Device-vs-account onboarding scoping is genuinely undecided** (§14) — this plan lays out both options with a recommendation but defers the final call to the project owner, since it's a product/UX decision (does a second family member sharing a phone deserve their own city-selection/education pass, or is one device-wide pass acceptable?) not something the code audit alone can resolve.
4. **In-memory-only denial-count heuristic** (§4, §13) means "permanently denied" guidance does not survive an app restart — a user who was denied twice, closed the app, and reopens it will see a plain "denied" message again rather than settings-redirect guidance, even though the OS may still be silently blocking future prompts. This is a pre-existing limitation of `locationPermission.js` (not introduced by this plan) worth flagging for a future, separate hardening pass rather than blocking E08-02 on it.
5. **iOS push token delivery is unverified end-to-end** (§7) — the notification priming screen's OS permission prompt will work on iOS, but nothing in this repo confirms an actual push notification has ever been delivered to a real iOS device via APNs. This is a pre-existing gap unrelated to onboarding UI and is explicitly out of scope (§10), but the project owner should be aware that "notification priming works on iOS" and "push notifications work on iOS" are not the same claim.
6. **Component-unmount race in the two permission-action handlers** (§16 item 37) is a minor, low-probability React correctness gap, not a functional regression today (React logs a console warning at worst in dev; production builds are unaffected in practice), but should be closed alongside the other test additions in §18 for cleanliness.

## 25. Manual actions required from the project owner

1. Approve or reject the account-scoping decision in §14 (own onboarding pass per account vs. current device-wide behavior).
2. Approve the documentation decision-record addendum language in §17/§15 reconciling `location-permission-strategy.md`/`android-location-permission-requirements.md` with the shipped onboarding-priming pattern (or provide alternative language).
3. Approve the exact English wording for the new iOS `NSLocationWhenInUseUsageDescription` string (App Store review-sensitive; should be reviewed by whoever owns App Store submission copy).
4. Decide between the two options in §15's `SettingsPage.jsx`/copy-fix row (add a retry UI to the dedicated Settings page, or just correct the copy to point at the map's existing controls).
5. Provide or arrange access to a physical iOS device and a physical Android device for §19-20's manual QA, or explicitly approve a recorded exception per §23 if iOS hardware is unavailable.
6. Confirm whether `frontend/.env`'s currently-uncommitted local changes (§2) are intentional/should be handled separately — unrelated to this plan, flagged only so it isn't accidentally swept into an implementation commit.

## 26. Recommended implementation order

1. iOS `Info.plist` fix (§7, §15) — small, isolated, unblocks all subsequent iOS work. Do first.
2. Documentation decision-record addenda (§15, pending §25 sign-off) — can happen in parallel with #1, no code dependency.
3. Account-scoping decision + implementation if approved (§14-15) — do before writing the denial-path tests in #4, since it affects `onboardingStorage.js`'s public surface.
4. Automated test additions (§18) — denial paths, unmount-race guard, rapid-tap test, push-launch-during-onboarding test, second-account test.
5. `SettingsPage.jsx`/copy decision implementation (§15, pending §25 sign-off).
6. Android manual QA (§19) — can start as soon as #3-4 land, does not depend on iOS work.
7. iOS manual QA (§20) — depends on #1 landing.
8. Web manual QA (§21) — can happen any time after #4, lowest risk/dependency.
9. Final regression pass across auth/onboarding/map/notifications/deep-links (acceptance criterion #28) before requesting review.

## 27. Estimated complexity by area

| Area | Complexity | Why |
|---|---|---|
| iOS `Info.plist` fix | Trivial | One new plist key, no logic change. |
| Documentation addenda | Trivial | Docs-only. |
| Account-scoping implementation (if approved) | Small-Medium | Touches a well-tested, well-isolated module (`onboardingStorage.js`) plus two call sites in `App.jsx`; needs careful migration-path testing to avoid breaking the existing legacy-user migration. |
| Copy/Settings-page decision | Small | Either a string change or a small, reused-logic UI addition. |
| Automated test additions | Small-Medium | Playwright already has the right fixtures (`browser.newContext({permissions})`, `Notification` stubbing); mostly new test cases following existing patterns, plus one small production-code guard for the unmount race. |
| Android manual QA | Medium | Requires physical device(s) across two API-level tiers; no code changes expected, but real testing time. |
| iOS manual QA | Medium-Large | Requires physical device; this is the *first* real iOS location/notification permission exercise this repo has ever done, so expect to find additional issues beyond the one already identified. |
| Web manual QA | Small | Lowest-risk tier; Playwright already covers most of this with real (non-mocked) browser permission contexts. |

## 28. Final readiness decision

**READY WITH BLOCKERS.**

The core priming-screen feature required by E08-02 is already built, already reasonably tested at the web/component tier, and architecturally sound (single shared location/notification services, no duplicated permission logic, correct opt-in/no-auto-prompt behavior, correct existing-user migration). It is not "not ready" — most of the brief's required behavior already exists and works.

It is not "ready for implementation" as a green light to merge/ship, because of concrete, identified blockers:
- A real iOS crash risk in already-merged code (§7, §24 item 1) — must be fixed before any iOS testing or release.
- A live documentation/policy contradiction that needs an explicit, owner-approved resolution rather than being silently left inconsistent (§24 item 2).
- An undecided product question (device- vs. account-scoped onboarding) that affects a concrete, testable behavior (§14, §24 item 3) and should not be implicitly decided by omission.
- Zero native manual QA evidence exists for this feature on either platform (§19-20) — required by the brief's Definition of Done and by this plan's acceptance criteria before E08-02 can be marked complete.

None of these blockers require large engineering effort (§27 estimates trivial-to-medium for all code-level items); they require decisions and verification work, which is exactly what "ready with blockers" is meant to capture — proceed to implementation on the `codex/e08-02-permission-priming` branch once §25's owner decisions are made, following the order in §26.

---

*Implementation was not started as part of this planning task. No files outside this document and the branch-creation itself were modified. `main` was not modified or merged into.*

---

## 29. Implementation Status Addendum (2026-07-17, Android-first phase, branch `codex/e08-02-permission-priming`)

This section records what the Android-first implementation phase actually did, without rewriting the planning sections above (§1-28 remain the original planning analysis; treat this addendum as the current status layered on top of it).

**Closed from §15's file-by-file plan:**
- Permission-state normalization documented and a real bug fixed: Android's "device location services disabled" native error (`@capacitor/geolocation`'s `LOCATION_DISABLED`, code `OS-PLUG-GLOC-0007`) was being silently folded into a plain permission denial in `frontend/src/api/locationPermission.js`, incrementing the repeat-denial counter and showing "location was denied" copy when the real issue was device GPS being off. Fixed at the source; `frontend/src/api/locationService.js` and every downstream consumer (map, onboarding) now correctly show non-denial "unavailable" guidance instead, with no changes needed in the consumers themselves.
- A second real bug fixed: `frontend/src/App.jsx`'s `handleEnableNotifications()` was reporting a post-grant native token-registration failure (`initNativePush`'s `'registration-failed'` outcome) as a permission *denial*. Since that outcome only occurs after the OS permission check already passed, it now maps to `'granted'`; token delivery continues to retry through the existing registration/registrationError listeners and `createPushTokenSync`, unchanged.
- Lifecycle races closed in `frontend/src/pages/OnboardingPage.jsx`: both permission-action handlers now guard against updating state after unmount and against an in-flight result landing after the user has already navigated to a different onboarding step (a live `stepRef`, not a closure-captured value, is compared post-`await`).
- Settings-guidance copy corrected in both locales: the notification denial message no longer says ambiguous "in Settings" (there is no in-app settings control for it); it now names device settings explicitly. A new `onboarding.location.deniedSettingsMessage` key surfaces the shared location service's existing repeat-denial ("needs settings") signal inside onboarding, which was previously computed but silently discarded there. No settings-opening button was added anywhere — no verified, working native capability for one exists in the currently installed plugin set (`@capacitor/app`, `@capacitor/app-launcher`); adding one is recommended as follow-up work (§20 of the final report), not done here, per this task's explicit "do not render a broken button" instruction.
- City/account-scoping resolved per the approved product decision (a distinct, narrower decision than this document's original §14 recommendation, which proposed scoping the whole onboarding pass by account — the approved decision instead keeps onboarding completion and priming-shown/skipped flags device-scoped and separates out only the city): `frontend/src/onboarding/onboardingStorage.js` gained `getAccountCity`/`setAccountCity`/`resolveAccountCity`, namespaced by authenticated user id, with a one-time best-effort migration for devices that already had a city before this shipped. `App.jsx` re-derives the correct city for the current account on every login; `OnboardingPage.jsx` and `SettingsPage.jsx` write to the account-scoped key wherever they already wrote the device-scoped one.
- `docs/location-permission-strategy.md` and `docs/android-location-permission-requirements.md` updated with dated decision-record addenda distinguishing "forbidden: automatic prompt on launch/mount" from "allowed: explicit tap on the onboarding priming screen," per this task's explicit instruction not to weaken the automatic-request prohibition.

**Explicitly not done (iOS), per this task's scope boundary — see §30 below for the full deferred list.**

**Not done as part of this Android-first pass (documented, not silently skipped):**
- The `SettingsPage.jsx` "add a working retry UI" option from §15's table was not taken; the copy-fix option was, as the smaller, safer change (see above).
- No new automated test file for `locationPermission.js`'s services-disabled distinction existed before this pass; one was added (§14 of the final completion report lists it).

**A real regression was found and fixed during this pass's own verification, not by inspection alone**: the initial `isMountedRef`/`stepRef` implementation used `useEffect(() => () => { isMountedRef.current = false }, [])`, which is broken under React 18 StrictMode's dev-mode mount→cleanup→remount double-invoke — the ref never got reset back to `true`, permanently wedging every guarded state update (onboarding got stuck showing "Saving…" forever, and denial/error copy never rendered) even though the component was genuinely still mounted. This was caught by running the full Playwright suite, not by code review, and is exactly why this task's Definition of Done requires running the suites rather than trusting static analysis alone. Fixed by explicitly resetting the ref to `true` in the effect's mount phase.

Two `eslint-plugin-react-hooks` errors (`react-hooks/refs`, `react-hooks/set-state-in-effect`) were also found and fixed by running lint against the changed files — `App.jsx`'s new city-correction effect now defers its `setState` calls by a tick via `window.setTimeout(..., 0)`, matching this file's own existing deep-link effects' established idiom for the same constraint; `OnboardingPage.jsx`'s `stepRef` mirror moved from a render-time ref write into a `useEffect`.

---

## 30. iOS — Deferred Requirements (Android-First Implementation Phase)

No native iOS implementation work was performed in this phase, per explicit task scope. No `Info.plist`, Xcode project file, or APNs configuration was touched. The following remain **deferred to the iOS implementation phase**:

1. **`Info.plist` location usage description** — `NSLocationWhenInUseUsageDescription` is still absent from `frontend/ios/App/App/Info.plist` (§7 of this document). Until it is added, any native iOS build that reaches the onboarding location-priming step's "Allow location" action, or the map's existing "Center on my location" button, will crash on the first native geolocation call.
2. **Native location permission verification** — no physical-iPhone or simulator verification has ever been performed for `CLLocationManager`'s "Allow Once" / "Allow While Using App" / denial / approximate-location behavior in this app.
3. **Native notification authorization verification** — no physical-iPhone or simulator verification has been performed for `UNUserNotificationCenter`'s authorization prompt/allow/deny flow in this app.
4. **Settings redirection verification** — no iOS-specific verification of the "open device Settings" guidance copy's accuracy (wording, path) for iOS has been performed.
5. **Physical-iPhone QA** — not performed; explicitly out of scope for this phase.
6. **Safe-area and swipe-back QA** — the onboarding CSS already has `env(safe-area-inset-*)`-based rules (verified in source, §16 item 33 of this document), but has never been visually verified on a physical iPhone (notch/Dynamic Island) or exercised against the iOS swipe-back gesture.
7. **Permission denial and recovery QA** — no iOS-specific denial/re-prompt/settings-recovery verification has been performed.
8. **APNs and token-registration verification** — `frontend/ios/App/` has no `GoogleService-Info.plist`, no Firebase iOS SDK, and no `Podfile` (§7 of this document); end-to-end push delivery via APNs has never been demonstrated on this project. The notification-priming screen's OS permission prompt itself should work on iOS (it only needs `@capacitor/push-notifications`, already installed), but actual token delivery is unverified and is a materially larger, separate piece of work than this task's scope.

---

## 31. Follow-up Fix — Account City Isolation (branch `codex/e08-02-permission-priming`, second pass)

**Confirmed Android manual QA finding**: after §29's fix shipped, logging into a second account on an already-onboarded device correctly showed a blank starting city in Settings, but the map still silently centered on the *first* account's city.

**Root cause**: `App.jsx`'s `mapEntryIntent` (passed to `MapPage` as `initialEntryIntent`) was corrected for the new account by a `useEffect` keyed on `currentUser`, deferred one tick via `window.setTimeout`. `MapPage` consumes `initialEntryIntent` synchronously in its own mount effect and immediately marks it applied (`initialEntryAppliedRef.current = true`). Because passive (child) effects run before a parent's own effect in the same commit, and `App.jsx`'s correction was additionally deferred, `MapPage` mounted and permanently locked in the *stale* (previous account's) entry intent before the parent's correction could ever land — a real, reproducible race, not a hypothetical one.

**Fix**: replaced "correct after the fact" with "don't render until correct." `App.jsx` now tracks which `userId` its resolved city actually belongs to (`cityResolution.forUserId`) and derives `resolvedAccountCity` by comparing it against the live `currentUser.id` on every render — so a stale value can never satisfy the check for a newly-logged-in account. Every account-specific route (map, settings, my-games, my-reports) is gated behind this value being resolved. When an authenticated account has device onboarding already complete but no city of its own, it renders a new, minimal `AccountCityStep` component (`frontend/src/components/onboarding/AccountCityStep.jsx`) — reusing the existing `OnboardingLayout`/`CityAutocomplete` primitives, not a second onboarding system — instead of the map, with no permission-priming replay and no native permission API calls. `SettingsPage.jsx` was also changed to read the account-scoped city directly (`getAccountCity(userId)`) rather than the device-scoped blob, so Settings and the map are structurally guaranteed to agree, not just usually consistent by timing.

The existing one-shot legacy-city migration (`resolveAccountCity`'s `CITY_MIGRATION_FLAG_KEY` guard) was already correct and required no changes — the bug was entirely in how the *result* was consumed and rendered, not in the migration logic itself.

**Test-suite-wide consequence**: ~30 unrelated Playwright spec files across the app seeded a "device onboarding complete" state without ever seeding a city (a state the real app flow cannot actually produce, since the six-step wizard's own city step is mandatory). Before this fix, that gap was invisible because the old code never gated map access on having a city at all. After this fix, correctly, it does — so those files' seed data needed a one-line city seed added (either the legacy `userCity` key, migrated automatically, or a direct `starting_city:{userId}` seed for multi-account files) to keep testing what they were actually meant to test. This is documented in full in the completion report for this fix, including which failures were confirmed pre-existing (reproduced independently on the unmodified pre-fix commit) versus caused by this change.

No claim of iOS completion, iOS test coverage, or iOS QA is made anywhere in this implementation's completion report.

---

## 32. Android Physical-Device QA Result — PASSED (final status update)

Android manual QA for E08-02 (§19 of this document, exercising the account-city-isolation fix from §31) was performed on a physical Android device and **passed**. Confirmed behavior:

- Device onboarding did not restart unnecessarily for a second account on the same device.
- Location and notification permission priming did not replay for the second account — no six-step walkthrough, no native permission prompts.
- The second account was shown only the dedicated city-selection step (`AccountCityStep`), nothing else.
- The second account did not inherit the first account's city.
- The map did not use the first account's city before the second account selected its own.
- The second account's selected city appeared correctly in Settings and was used by the app (map entry) after selection.
- Logging back into the first account restored its original city correctly, in both Settings and on the map.
- No regression was found in the tested onboarding flow.

This satisfies the Android-side manual-QA requirement that was the sole open blocker in §28's original "READY WITH BLOCKERS" / the Android-first implementation phase's "ANDROID IMPLEMENTATION COMPLETE WITH BLOCKERS" status. That blocker is now closed.

**Final status: `ANDROID IMPLEMENTATION COMPLETE — IOS DEFERRED`.**

This status applies to the Android-first implementation phase only. It does **not** claim iOS completion, iOS test coverage, or iOS QA of any kind — every item in §30 ("iOS — Deferred Requirements") remains open and deferred to a dedicated future iOS implementation phase; no native iOS file (`Info.plist`, Xcode project, APNs/`GoogleService-Info.plist` configuration) has been modified at any point across this task's Android-first work. §28's "READY WITH BLOCKERS" verdict and §29's "ANDROID IMPLEMENTATION COMPLETE WITH BLOCKERS — IOS DEFERRED" verdict are both superseded by this section for the Android platform; they remain accurate historical records of the state at the time they were written and are left unmodified above.
