# Background Location Policy Implementation

**Issue:** ISSUE-262
**Depends on:** ISSUE-261 (docs/background-location-requirements.md)
**Date:** 2026-07-08

---

## 1. Approved Policy

ISSUE-261 concluded that **Background Location is NOT required for the current MVP**. All location-dependent features operate entirely in the foreground via explicit user actions. This document verifies that the codebase enforces that decision and defines invariants that guard against accidental regression.

---

## 2. Current Implementation Status

| Area | Status | Evidence |
|:---|:---:|:---|
| Android `ACCESS_BACKGROUND_LOCATION` | **Not present** | `AndroidManifest.xml` declares `ACCESS_COARSE_LOCATION` and `ACCESS_FINE_LOCATION` only |
| iOS `NSLocationAlwaysUsageDescription` | **Not present** | `Info.plist` contains no `NSLocation` keys |
| iOS `NSLocationAlwaysAndWhenInUseUsageDescription` | **Not present** | Same as above |
| iOS background mode `location` | **Not present** | No `UIBackgroundModes` entry in `Info.plist` |
| Native background service / foreground service | **Not present** | No `Service` declarations in `AndroidManifest.xml`; no background task plugins in Capacitor config |
| `watchPosition` usage | **Not present** | All location acquisition is one-shot `getCurrentPosition` |
| Background task plugins | **Not present** | `package.json` contains no `@capacitor/background-runner`, `@capacitor/background-task`, or equivalent |
| Location service behavior | **Foreground-only** | `locationService.js` and `locationPermission.js` use one-shot calls triggered by explicit user actions |

---

## 3. Files Inspected

| File | Relevant Finding |
|:---|:---|
| `frontend/android/app/src/main/AndroidManifest.xml` | `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION` only; no `ACCESS_BACKGROUND_LOCATION`; no `<service>` elements |
| `frontend/ios/App/App/Info.plist` | No `NSLocation*` keys; no `UIBackgroundModes` |
| `frontend/src/api/locationService.js` | One-shot `getCurrentLocation` / `refreshLocation`; no `watchPosition`; no background scheduling |
| `frontend/src/api/locationPermission.js` | One-shot `getCurrentPosition` with explicit user-triggered permission flow; no background listeners |
| `frontend/src/pages/MapPage.jsx` | Location acquired only on "My Location" button tap; app-resume revalidation checks permission state only (no position acquisition) |
| `frontend/src/components/AddFieldModal.jsx` | One-shot location on "Use Current Location" button |
| `frontend/src/components/NotificationsModal.jsx` | One-shot location at save time for distance-notification preferences |
| `frontend/src/components/FieldDetailsPanel.jsx` | Navigation uses destination coordinates only; external app delegation |
| `frontend/capacitor.config.ts` | No background plugins configured |
| `frontend/package.json` | No background-location or background-task dependencies |

---

## 4. Required Invariants

The following invariants must hold unless a new issue with full product/privacy/platform review is approved:

1. **Android must NOT request `ACCESS_BACKGROUND_LOCATION`.** Only `ACCESS_COARSE_LOCATION` and `ACCESS_FINE_LOCATION` are permitted.
2. **iOS must NOT request Always Location authorization.** No `NSLocationAlwaysUsageDescription` or `NSLocationAlwaysAndWhenInUseUsageDescription` in `Info.plist`.
3. **No background modes for location.** iOS `UIBackgroundModes` must not include `location`.
4. **All location acquisition must be user-triggered.** One-shot `getCurrentPosition` only, never `watchPosition` or continuous tracking.
5. **Notifications must rely on saved preferences and server-side matching**, not on background device tracking.
6. **Navigation must delegate to external apps** using destination coordinates only.
7. **No native background services or foreground services** for location tracking.
8. **No background task plugins** (`@capacitor/background-runner`, `@capacitor/background-task`, or equivalent).

---

## 5. Use-Case Verification

| Use Case | Background Location Required? | Current Behavior |
|:---|:---:|:---|
| User Marker | No | Foreground one-shot via "My Location" button |
| Nearby Fields | No | Viewport-bounds-based field loading; no user coordinates involved |
| Navigation Launch | No | Destination-only deep links to Waze/Google Maps |
| Game Creation | No | Field coordinates or foreground pin placement |
| Join Game | No | Direct user action in foreground |
| Notifications | No | Server-side matching against saved preference coordinates |
| Location Refresh | No | Manual "My Location" tap or foreground-resume revalidation |
| Future Proximity Validation | No | Will require fresh foreground fix at action time |

---

## 6. Automated Guard Test

A Playwright test (`frontend/tests/background-location-policy.spec.js`) verifies the invariants automatically:

- Asserts `ACCESS_BACKGROUND_LOCATION` is absent from the Android manifest.
- Asserts `NSLocationAlwaysUsageDescription` and `NSLocationAlwaysAndWhenInUseUsageDescription` are absent from iOS Info.plist.
- Asserts no background-location plugins are declared in `package.json`.
- Asserts `watchPosition` is not used in application source code.

This test runs as part of the standard `npx playwright test` suite and will fail if any invariant is violated.

---

## 7. Future Change Gate

Any future proposal to add background location must:

1. Create a **new issue** with explicit product justification.
2. Complete the **Mandatory Review Checklist** defined in `docs/background-location-requirements.md` (Section 4).
3. Pass **privacy review** including data minimization plan and purge policy.
4. Pass **platform review** for both Android (Play Store declaration) and iOS (App Store background mode review).
5. Include **explicit user opt-in** with rationale screen and easy toggle to disable.
6. Update this document and the automated guard test to reflect the new approved scope.

---

## 8. Out of Scope

- No background location implementation
- No permission escalation
- No native background services or foreground services
- No backend changes
- No Android permission additions
- No iOS permission additions
- No new product features
- No analytics
- No UI redesign
- No enforcement logic beyond documentation and guard tests

---

## 9. Definition of Done Checklist

- [x] Approved policy from ISSUE-261 referenced and summarized.
- [x] Current implementation verified against policy.
- [x] All relevant files inspected and documented.
- [x] Required invariants defined.
- [x] Every current location use case verified as foreground-only.
- [x] Automated guard test added.
- [x] Future change gate documented.
- [x] Scope confirmed as policy enforcement only.
