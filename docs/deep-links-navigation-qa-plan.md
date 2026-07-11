# Deep Links and Navigation QA Plan

**Issue:** ISSUE-279 (#374)
**Date:** 2026-07-11
**Status:** QA plan only — no implementation, no test execution, no code changes
**Dependencies:** ISSUE-274, ISSUE-275, ISSUE-276, planned ISSUE-277, ISSUE-267, ISSUE-268, ISSUE-270

---

## 1. Purpose

Deep links and external navigation cross the web application, native operating systems, domain verification, authentication, backend resource resolution, and third-party navigation apps. A successful unit or browser test cannot by itself prove that an installed mobile application receives a verified link or that a provider handoff works on a physical device.

This document defines the complete QA strategy for Android App Links, future iOS Universal Links, field and game routes, and Waze, Google Maps, and Apple Maps handoff. It is the release-facing source of truth for scenario coverage. It does not claim that any scenario has been executed.

---

## 2. Source Documents and Implementation Baseline

| Source | QA contract used by this plan |
|:---|:---|
| `docs/deep-link-architecture.md` (ISSUE-267) | Canonical field/game routes, UUID validation, auth-intent resume, resource states, web/Android/iOS handoff, network fallback |
| `docs/android-app-links-strategy.md` (ISSUE-268 / ISSUE-270 notes) | Verified HTTPS App Links, domain association, `singleTask`, `appUrlOpen`, supported routes, ADB verification |
| `docs/external-navigation-strategy.md` (ISSUE-274) | Destination-only privacy, provider availability, HTTPS fallback, failure ownership, platform coverage |
| ISSUE-275 implementation | Waze native capability check, native launch, HTTPS fallback, invalid-coordinate rejection, clean failure result |
| ISSUE-276 implementation | Google Maps universal HTTPS launch, encoded destination, invalid-coordinate rejection, clean failure result |
| ISSUE-277 (planned) | Apple Maps provider implementation and executable iOS provider validation |
| `docs/navigation-sharing-entry-points-audit.md` | Existing map/field/game entry points and known backend/frontend gaps |

Current readiness assumptions must be re-checked at execution time:

- Android App Link configuration exists, but verification depends on the deployed domain, valid `assetlinks.json`, and the certificate that signed the installed build.
- Field resolution uses `GET /fields/{field_id}`.
- Game deep-link execution depends on a direct, reliable game-to-field resolution path.
- iOS Universal Links require Associated Domains, an AASA file, a signed iOS build, macOS/Xcode, and a physical-device validation path.
- Apple Maps execution remains pending ISSUE-277.

---

## 3. Scope

This plan covers:

- HTTPS entry from browser, messaging application, ADB, and operating-system link dispatch.
- Cold-start and warm-start link delivery.
- Android verified App Links with installed and uninstalled app behavior.
- Future iOS Universal Links, retained as blocked scenarios until their dependencies exist.
- Field and game path parsing, authentication gates, resource resolution, and failure states.
- Waze, Google Maps, and future Apple Maps provider handoff.
- Offline, invalid-input, missing-resource, and network-failure behavior.
- Cross-platform regression protection for Android, iOS, and web.

---

## 4. Out of Scope

- Implementing or fixing deep links, App Links, Universal Links, provider launch, or backend endpoints.
- Adding automated tests in this issue.
- Provisioning a domain, signing certificate, Apple Developer account, or physical device.
- Approving a production release based only on this document.
- Marketing-link behavior under `/m/{slug}` beyond confirming it does not break supported routes.
- Analytics, attribution, tracking parameters, or provider-preference persistence.

---

## 5. Status Legend and Execution Rules

| Status | Meaning |
|:---|:---|
| **Pending** | Scenario is fully specified but has not been executed |
| **Blocked — ISSUE-277 / macOS testing** | Scenario must remain in the plan; execution requires ISSUE-277 and/or macOS/Xcode/iOS hardware |
| **Blocked — dependency** | Execution requires a missing domain, backend, signing, deployment, or environment dependency |
| **Pass** | Executed with retained evidence and all expected results met |
| **Fail** | Executed and at least one expected result was not met; release is blocked according to §15 |

Rules:

1. Do not convert a scenario to Pass from source inspection alone when it requires OS dispatch, domain verification, or a third-party application.
2. Retain evidence for every execution: build SHA, app version, platform/OS, device/browser, URL, timestamp, result, screenshots or screen recording, and relevant sanitized logs.
3. Use test UUIDs and accounts only. Never place tokens, user identifiers, or private data in shared links or evidence.
4. Re-run all applicable regression scenarios after any deep-link resolver, route, auth, provider, manifest, entitlement, domain-association, or signing change.

---

## 6. Environments, Tools, and Test Data

### 6.1 Required Environments

| Platform | Required environment |
|:---|:---|
| Android | Physical Android 11+ device; fresh-install and upgrade-install builds; ADB; Chrome; Waze installed/uninstalled states; Google Maps installed/disabled states |
| iOS | macOS, Xcode, signed physical iPhone build, Safari, Waze/Google Maps installed states; **execution blocked by ISSUE-277 / macOS testing** |
| Web | Current Chrome, Safari, and Firefox; desktop and mobile viewport; online/offline network controls; clean and authenticated sessions |

### 6.2 Required Test Data

- One approved/open field with valid coordinates.
- One deleted/missing field UUID.
- One pending or rejected field UUID and one closed/renovation field.
- One active joinable game, one finished game, and one deleted/missing game UUID.
- One syntactically valid UUID that resolves to no resource.
- Invalid identifiers: `not-a-uuid`, empty identifier, truncated UUID, and extra path segment.
- A future private-game fixture when private games are implemented.
- Logged-in and logged-out test accounts.
- A known verified canonical host and a deliberately invalid host.

### 6.3 Android Verification Commands

```powershell
adb shell pm get-app-links com.yeshmishak.app
adb shell pm verify-app-links --re-verify com.yeshmishak.app
adb shell am start -W -a android.intent.action.VIEW -d "https://<canonical-host>/field/<field-uuid>"
adb shell am start -W -a android.intent.action.VIEW -d "https://<canonical-host>/game/<game-uuid>"
```

Record the domain verification state before interpreting any App Link result.

---

## 7. Android App Links Matrix

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| AL-01 | Android | App installed; cold-start a valid verified field link | Android opens yesh_mishak directly, delivers the URL once, resolves the field, and opens field details | Pending |
| AL-02 | Android | App not installed; open a valid canonical link | Link opens the web application in the browser; no custom-scheme error or store redirect loop | Pending |
| AL-03 | Android | Verified App Link with matching host, package, and signing fingerprint | Link opens the app without a disambiguation prompt; `pm get-app-links` reports verified association | Pending |
| AL-04 | Android | Valid path on an invalid/unassociated host | yesh_mishak does not intercept the URL; browser handles it safely | Pending |
| AL-05 | Android | Canonical host with invalid/unsupported path | App or web resolver shows the safe unsupported-link fallback with a return-to-map action; no crash | Pending |
| AL-06 | Android | Valid App Link while device is offline | Installed app opens; resolver shows offline/network failure with retry and keeps navigation usable | Pending |
| AL-07 | Android | Valid App Link while user is logged out | Intent is retained through login/onboarding and resumed exactly once after authentication | Pending |
| AL-08 | Android | Link to existing active game | Resolver opens the correct field/game state; no unrelated game is shown | Blocked — dependency |
| AL-09 | Android | Link to missing/deleted game | Resolver shows “Game not found” and a safe return action; no retry loop | Blocked — dependency |
| AL-10 | Android | Link to existing approved field | Map centers on the target and opens the correct `FieldDetailsPanel` | Pending |
| AL-11 | Android | Link to missing/deleted field | Resolver shows “Field not found”; map/app remains usable | Pending |
| AL-12 | Android | App already running; open verified link (`singleTask`) | Existing task is foregrounded, URL is handled once, and back navigation remains coherent | Pending |

Android route execution must cover both the singular architecture paths (`/field/{id}`, `/game/{id}`) and any supported plural compatibility paths (`/fields/{id}`, `/games/{id}`). The resolver must normalize them to one internal target.

---

## 8. iOS Universal Links Matrix

> **All scenarios in this section are Blocked — ISSUE-277 / macOS testing. They are mandatory and must not be removed when implementation is pending.**

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| UL-01 | iOS | App installed; cold-start a valid Universal Link | iOS opens yesh_mishak directly and resolves the target once | Blocked — ISSUE-277 / macOS testing |
| UL-02 | iOS | App not installed; open canonical HTTPS link | Safari opens the web application and resolves the same target | Blocked — ISSUE-277 / macOS testing |
| UL-03 | iOS | Valid Associated Domain and matching AASA details | Universal Link opens the app rather than Safari; no confirmation loop | Blocked — ISSUE-277 / macOS testing |
| UL-04 | iOS | Valid path on invalid/unassociated host | Safari handles the URL; yesh_mishak is not opened | Blocked — ISSUE-277 / macOS testing |
| UL-05 | iOS | Canonical host with invalid/unsupported path | Safe unsupported-link fallback appears; no crash or blank screen | Blocked — ISSUE-277 / macOS testing |
| UL-06 | iOS | Valid Universal Link while offline | App opens and presents offline/retry behavior without losing the target intent | Blocked — ISSUE-277 / macOS testing |
| UL-07 | iOS | Valid Universal Link while logged out | Target survives language/auth/onboarding and resumes exactly once | Blocked — ISSUE-277 / macOS testing |
| UL-08 | iOS | Existing active game link | Correct field/game UI opens | Blocked — ISSUE-277 / macOS testing |
| UL-09 | iOS | Missing/deleted game link | “Game not found” fallback appears | Blocked — ISSUE-277 / macOS testing |
| UL-10 | iOS | Existing approved field link | Correct field opens and map centers on it | Blocked — ISSUE-277 / macOS testing |
| UL-11 | iOS | Missing/deleted field link | “Field not found” fallback appears | Blocked — ISSUE-277 / macOS testing |
| UL-12 | iOS | App already running; open Universal Link | Existing scene/app is foregrounded, handles the target once, and preserves back behavior | Blocked — ISSUE-277 / macOS testing |

Execution prerequisites include an `applinks:` Associated Domains entitlement, reachable AASA file with correct Team ID/bundle ID/path rules, signed physical-device build, macOS/Xcode, and retained device-console evidence.

---

## 9. Game Links Matrix

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| GL-01 | Android / iOS / Web | Active game with capacity via `/game/{uuid}` | Correct field and active game details open; join remains available | Blocked — dependency |
| GL-02 | Android / iOS / Web | Active game via `/game/{uuid}/join` | Correct game opens and join intent is presented once; no automatic duplicate join | Blocked — dependency |
| GL-03 | Android / iOS / Web | Finished game | Field/game context remains visible with “game has ended”; join is unavailable | Blocked — dependency |
| GL-04 | Android / iOS / Web | Deleted/missing game | “Game not found” fallback and return-to-map action; no stale cached game | Blocked — dependency |
| GL-05 | Android / iOS / Web | Invalid game UUID | Client rejects before resource fetch and shows “Invalid link” | Blocked — dependency |
| GL-06 | Android / iOS / Web | Private game (future) opened by authorized user | Authorized user sees the game without exposing private metadata in the URL | Blocked — dependency |
| GL-07 | Android / iOS / Web | Private game (future) opened by unauthorized user | Neutral not-found/access-denied behavior; no existence or participant leakage | Blocked — dependency |
| GL-08 | Android / iOS / Web | Game fetch timeout/network failure | Recoverable network message and retry; target intent is retained; no incorrect not-found result | Blocked — dependency |

The private-game scenarios are future-facing acceptance protection. They must remain in the plan even while the product has no private-game state.

---

## 10. Field Links Matrix

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| FL-01 | Android / iOS / Web | Existing approved/open field | Map centers on correct coordinates and opens the correct field details | Pending |
| FL-02 | Android / iOS / Web | Deleted/missing field | “Field not found” fallback appears; no stale cached field opens | Pending |
| FL-03 | Android / iOS / Web | Invalid field UUID | Client rejects before fetch and shows “Invalid link” | Pending |
| FL-04 | Android / iOS / Web | Existing field while GPS is unavailable or denied | Field still resolves and opens from destination data; no location permission is required | Pending |
| FL-05 | Android / iOS / Web | Existing field while offline | Offline/retry state appears and retains the target; app/map remains usable | Pending |
| FL-06 | Android / iOS / Web | Pending or rejected field | Neutral “Field not found” behavior; hidden field data is not disclosed | Pending |
| FL-07 | Android / iOS / Web | Closed or renovation field | “Field temporarily unavailable” state; no navigation/join action incorrectly presented | Pending |

---

## 11. Navigation Provider Matrix

### 11.1 Waze

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| NP-W01 | Android | Waze installed and native scheme available | Capability check succeeds; Waze opens natively at destination and receives no origin/user data | Pending |
| NP-W02 | iOS | Waze installed and native scheme available | Waze opens natively at destination and receives no origin/user data | Blocked — ISSUE-277 / macOS testing |
| NP-W03 | Android | Waze not installed | Native capability check fails; supported Waze HTTPS URL opens without crash | Pending |
| NP-W04 | Web | Waze selected in browser | HTTPS Waze URL opens in a secure new target with only destination coordinates | Pending |
| NP-W05 | Android / iOS / Web | Invalid, missing, blank, or out-of-range coordinates | Launch is rejected; no native/HTTPS call occurs; navigation flow remains usable | Pending |
| NP-W06 | Android | Native Waze launch returns failure | Waze HTTPS fallback is attempted once; final failure returns cleanly to navigation flow | Pending |

### 11.2 Google Maps

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| NP-G01 | Android | Google Maps installed | Universal Maps URL opens the installed app with encoded destination only | Pending |
| NP-G02 | iOS | Google Maps installed | Universal Maps URL opens Google Maps with encoded destination only | Blocked — ISSUE-277 / macOS testing |
| NP-G03 | Android | Google Maps missing or disabled | Universal URL opens the supported browser Maps experience | Pending |
| NP-G04 | Web | Google Maps selected | Browser opens `maps/dir/?api=1&destination=...`; no origin, identity, or auth data | Pending |
| NP-G05 | Android / iOS / Web | Invalid, missing, blank, or out-of-range coordinates | Launch is rejected and navigation flow remains usable | Pending |
| NP-G06 | Web | Browser launch throws/fails | Failure is contained; navigation flow stays open for future coordinator handling | Pending |

### 11.3 Apple Maps

> **Execution is pending until ISSUE-277. All Apple Maps rows are Blocked — ISSUE-277 / macOS testing and must remain in the checklist.**

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| NP-A01 | iOS | Apple Maps available; valid destination | Apple Maps opens directly with destination coordinates only | Blocked — ISSUE-277 / macOS testing |
| NP-A02 | iOS | Valid Apple Maps HTTPS/native handoff | Supported Apple Maps mechanism is used once; no chooser loop | Blocked — ISSUE-277 / macOS testing |
| NP-A03 | iOS | Invalid, missing, blank, or out-of-range coordinates | Launch is rejected and navigation flow remains usable | Blocked — ISSUE-277 / macOS testing |
| NP-A04 | iOS | Apple Maps launch reports failure | Failure returns cleanly for future coordinator handling; app does not crash | Blocked — ISSUE-277 / macOS testing |
| NP-A05 | Web (Apple platform) | Apple Maps HTTPS experience selected | Supported `maps.apple.com` destination opens; current page remains safe | Blocked — ISSUE-277 / macOS testing |
| NP-A06 | iOS / Web | Inspect Apple Maps request privacy | Only destination lat/lng is present; no origin, user ID, token, or field metadata | Blocked — ISSUE-277 / macOS testing |

---

## 12. Regression Matrix

| ID | Platform | Scenario | Expected Result | Status |
|:---|:---|:---|:---|:---|
| RG-01 | Web | Existing website navigation (`/`, `/my-games`, back/forward) | Existing routes and browser history continue to work | Pending |
| RG-02 | Android / iOS / Web | Open field from existing map marker or notification inbox | Same field panel opens without URL-related regression | Pending |
| RG-03 | Android / iOS / Web | Open existing active/upcoming game from field UI | Existing game display, join, leave, and close behavior remain unchanged | Pending |
| RG-04 | Web | Open canonical link in external browser with app unavailable | Browser resolves the web route; no blank page, forced install, or custom-scheme error | Pending |
| RG-05 | Android | Normal app launch, resume, and back navigation after App Link changes | Android application starts normally and App Link handling does not duplicate activities | Pending |
| RG-06 | iOS | Future normal launch, resume, Safari handoff, and back navigation | Future iOS application behavior remains stable | Blocked — ISSUE-277 / macOS testing |

---

## 13. Cross-Platform Test Matrix Summary

Sections 7–12 are the authoritative matrix: every row contains Platform, Scenario, Expected Result, and Status. Coverage totals are:

| Platform | Scenario participation | Primary coverage |
|:---|---:|:---|
| Android | 37 | App Links, game/field resolution, Waze, Google Maps, regression |
| iOS | 39 | Universal Links, game/field resolution, all providers, regression; most execution blocked |
| Web | 26 | Browser deep links, game/field resolution, provider HTTPS behavior, regression |

Platform participation counts overlap because one scenario may require execution on Android, iOS, and web. The authoritative number of unique scenario IDs is **63**.

Category totals:

| Category | Scenario count |
|:---|---:|
| Android App Links | 12 |
| iOS Universal Links | 12 |
| Game links | 8 |
| Field links | 7 |
| Navigation providers | 18 |
| Regression | 6 |
| **Total unique scenarios** | **63** |

---

## 14. Acceptance Criteria Mapping

| ISSUE-279 acceptance requirement | QA scenarios |
|:---|:---|
| Android App Links included | AL-01–AL-12 |
| App installed / not installed | AL-01, AL-02 |
| Verified App Link | AL-03 |
| Invalid host / invalid path | AL-04, AL-05 |
| Offline and logged-out behavior | AL-06, AL-07 |
| Existing/missing games and fields on Android | AL-08–AL-11 |
| iOS Universal Links retained while pending | UL-01–UL-12 |
| iOS blocked status clearly marked | UL-01–UL-12, NP-W02, NP-G02, NP-A01–NP-A06, RG-06 |
| Active, finished, deleted, invalid, private, and network-failed game links | GL-01–GL-08 |
| Existing, deleted, invalid, GPS-unavailable, and offline field links | FL-01–FL-05 |
| Hidden/unavailable field states | FL-06, FL-07 |
| Waze installed, unavailable, native, HTTPS, invalid, and failure behavior | NP-W01–NP-W06 |
| Google Maps installed, browser fallback, invalid, and failure behavior | NP-G01–NP-G06 |
| Complete Apple Maps checklist pending ISSUE-277 | NP-A01–NP-A06 |
| Existing website navigation regression | RG-01 |
| Existing field/game opening regression | RG-02, RG-03 |
| External browser behavior | RG-04 |
| Android and future iOS application regression | RG-05, RG-06 |
| Platform / Scenario / Expected Result / Status matrix | All 63 rows in §§7–12 |
| QA plan approved and all scenarios covered | §15 exit criteria plus the complete scenario inventory |

---

## 15. Entry, Exit, and Release-Blocking Criteria

### 15.1 Entry Criteria

- Target build and commit SHA recorded.
- Canonical host and supported path contract confirmed.
- Required backend endpoints and test fixtures available for the category being executed.
- Domain association files are reachable without redirects and match the build signing identity.
- Test accounts contain no production-sensitive data.
- Provider installed/uninstalled states can be reproduced.

### 15.2 Exit Criteria

- Every applicable, unblocked scenario is Pass with retained evidence.
- Every blocked scenario remains listed with owner, dependency, and follow-up issue.
- No P0/P1 failure remains open.
- Privacy inspection confirms destination-only provider requests.
- Android verification is performed on a physical device and real signed build.
- iOS is not declared complete until ISSUE-277/macOS physical-device execution is unblocked and all applicable UL/NP/RG rows pass.
- Regression rows pass after the final candidate build.

### 15.3 Release Blockers

- Verified canonical link opens the wrong application, wrong resource, or an untrusted host.
- Auth intent is lost, duplicated, or resumed for the wrong user/resource.
- Missing/private resources disclose restricted data.
- Provider link includes origin coordinates, identity, token, or tracking data not approved by strategy.
- Invalid link crashes, loops, or leaves a blank screen.
- Installed-app and browser fallback behavior both fail for a required provider.
- Existing web or native navigation regresses.

---

## 16. Evidence Template

For each executed scenario, retain:

```text
Scenario ID:
Build / commit SHA:
App version:
Platform / OS / device or browser:
Install state:
Authentication state:
Input URL or provider destination:
Domain verification state:
Expected result:
Actual result:
Status: Pass / Fail / Blocked
Evidence links:
Sanitized logs:
Tester / timestamp:
Follow-up issue:
```

URLs in evidence must redact or avoid any token, user identifier, private resource, or unapproved tracking parameter.

---

## 17. Definition of Done Checklist

- [x] Android App Links scenarios defined, including installed/uninstalled, verification, invalid input, offline, auth, game, and field states.
- [x] iOS Universal Links scenarios retained and explicitly marked Blocked — ISSUE-277 / macOS testing.
- [x] Game-link active, finished, deleted, invalid UUID, private future, and network-failure scenarios defined.
- [x] Field-link existing, deleted, invalid, GPS-unavailable, offline, and restricted-state scenarios defined.
- [x] Waze, Google Maps, and complete pending Apple Maps checklists defined.
- [x] Existing web, field, game, external-browser, Android, and future iOS regression coverage defined.
- [x] Cross-platform Platform / Scenario / Expected Result / Status matrix provided.
- [x] Every ISSUE-279 acceptance requirement mapped to scenario IDs.
- [x] Exactly 63 unique QA scenarios documented.
- [x] No application code, native configuration, dependencies, or runtime behavior changed.
