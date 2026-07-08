# Location and GPS QA Plan

**Issue:** ISSUE-263
**Date:** 2026-07-08
**Status:** QA plan only — no implementation, no code changes

---

## 1. Purpose

GPS and location behavior is a core product dependency for the yesh_mishak application. Location data drives the user marker, nearby field discovery, navigation launch, and future proximity-based features. Because GPS depends on hardware sensors, operating system permissions, network conditions, and physical environment, it is inherently unreliable and must be validated across multiple failure modes.

This document defines a complete QA plan covering permissions, accuracy, failure scenarios, Android validation, iOS requirements, and regression coverage for all location-related behavior.

---

## 2. Scope

This QA plan covers:

- **User Marker** — displaying the user's position on the map
- **Nearby Fields** — viewport-based field loading behavior
- **Location Refresh** — cache and fresh acquisition behavior
- **Navigation Launch** — external app deep links (Waze/Google Maps)
- **Permission flows** — grant, deny, revoke, permanent denial, settings guidance
- **Accuracy handling** — high/medium/low thresholds per `docs/gps-accuracy-requirements.md`
- **Failure handling** — GPS disabled, timeout, no signal, malformed, stale cache per `docs/location-failure-handling-strategy.md`
- **Foreground-only policy** — background location is NOT used per `docs/background-location-requirements.md`
- **Android validation** — real device testing on Samsung SM-S928B (Android 16) or equivalent
- **iOS requirements** — defined scenarios for future validation when iOS build path is available

This is a **QA plan only**. No code changes, no test implementation, no production release approval.

---

## 3. Out of Scope

- No implementation of any feature or fix
- No permission changes
- No backend changes
- No Android native changes
- No iOS changes
- No automated test implementation (test guidance is documented, not executed)
- No production release approval
- No background location implementation

---

## 4. QA Environments

### Android

| Environment | Description |
|:---|:---|
| Real device — fresh install | `adb install` after `adb uninstall`; no prior permissions or cached data |
| Real device — existing install | Upgrade path via `adb install -r`; existing permissions and cache preserved |
| Permission denied | Deny location at OS prompt or revoke via Settings > Apps > Location |
| Permission granted | Grant "While using the app" or "Only this time" at OS prompt |
| GPS disabled | Settings > Location > toggle off system-wide |
| Poor signal / indoor | Test indoors or in environments with degraded GPS signal |
| Network offline | Airplane mode or Wi-Fi off (affects network-assisted location) |

**Device baseline:** Samsung SM-S928B, Android 16. Package: `com.yeshmishak.app`.

### iOS

| Environment | Description |
|:---|:---|
| Real device | iPhone required for final validation |
| Simulator | Limited UI/fallback checks only; GPS simulation via Xcode scheme |
| Permission states | While In Use, Denied, Not Determined |

> **iOS scenarios are defined but execution is blocked until an iOS device, build, and signing path are available.** Do not claim iOS PASS without actual device validation.

### Web / Local Development

| Environment | Description |
|:---|:---|
| Browser geolocation allowed | Chrome/Firefox with location permission granted |
| Browser geolocation denied | Permission denied via browser prompt or site settings |
| Mocked geolocation | Playwright `addInitScript` mocks for deterministic test runs |

---

## 5. Permissions QA Matrix

| # | Scenario | Platform | Precondition | Steps | Expected Result | Status |
|:---:|:---|:---|:---|:---|:---|:---:|
| P1 | First launch, permission not requested | Android | Fresh install | Launch app, wait for map | Map loads at default center. No permission prompt appears. No location marker. | |
| P2 | User grants location | Android | P1 state | Tap "My Location" → tap "While using the app" | Permission dialog appears. After grant, user marker renders at real position with accuracy circle. Map flies to location. | |
| P3 | User denies location | Android | Fresh install | Tap "My Location" → tap "Don't allow" | Hebrew denied notice appears. No marker. Map remains usable at default center. Button remains available. | |
| P4 | User denies permanently | Android | Prior denial exists | Tap "My Location" → tap "Never" (לא, אף פעם) | Hebrew settings guidance notice appears. No native dialog shown. Map remains usable. | |
| P5 | Permission revoked from OS settings | Android | Previously granted | Settings > Apps > yesh_mishak > Permissions > Location > Deny → return to app | App detects revocation on resume. User marker removed. Revocation notice shown. Next tap triggers fresh permission dialog. | |
| P6 | App reopened after permission change | Android | Permission was revoked | Force-stop app → relaunch | App starts at default center. Tap "My Location" triggers permission dialog. | |
| P7 | Permission granted after previous denial | Android | Previously denied | Settings > Apps > Permissions > Location > Allow → return to app | Next "My Location" tap acquires location without re-prompting. | |
| P8 | Location permission unavailable | Web | `navigator.geolocation` undefined | Mock geolocation as undefined → tap "My Location" | "Location is unavailable" notice. Map usable. No crash. | |
| P9 | Browser geolocation denied | Web | Browser permission denied | Tap "My Location" | Denied notice appears. Map usable at default center. | |
| P10 | Native plugin failure | Android | Plugin bridge error | Simulate plugin timeout/error | Timeout or unsupported result. Non-blocking notice. Map usable. | |
| P11 | iOS While In Use grant | iOS | Fresh install | Tap "My Location" → grant While In Use | Marker appears. Map flies to position. | Blocked |
| P12 | iOS denial | iOS | Fresh install | Tap "My Location" → deny | Denied notice. Map usable. | Blocked |
| P13 | iOS revocation from Settings | iOS | Previously granted | Settings > Privacy > Location > yesh_mishak > Never | App detects on resume. Marker removed. | Blocked |

---

## 6. Accuracy QA Matrix

Reference: `docs/gps-accuracy-requirements.md`

| # | Scenario | Accuracy | Use Case | Expected Behavior | Status |
|:---:|:---|:---|:---|:---|:---:|
| A1 | Ideal accuracy | <= 50m | User Marker | Marker at precise position. Small accuracy circle. | |
| A2 | Target accuracy | <= 100m | User Marker | Marker at position. Accuracy circle visible. | |
| A3 | Acceptable accuracy | 100m–500m | User Marker | Approximate marker shown. Large accuracy circle. | |
| A4 | Poor accuracy | > 500m | User Marker | Approximate marker or fallback per future implementation. | |
| A5 | Missing accuracy | `null` or `undefined` | User Marker | Marker without accuracy circle. No crash. | |
| A6 | Invalid accuracy | Negative or `NaN` | User Marker | Treated as missing. No crash. No broken circle. | |
| A7 | Target accuracy | <= 100m | Nearby Fields | Fields load from viewport bounds (accuracy does not affect field loading). | |
| A8 | Poor accuracy | > 500m | Nearby Fields | Fields still load from viewport. Future: expand radius or show warning. | |
| A9 | Any accuracy | <= 2000m | Navigation Launch | Navigation launches. External app resolves own location. | |
| A10 | Very poor accuracy | > 2000m | Navigation Launch | Navigation still launches (destination-only deep link). | |
| A11 | Target accuracy | <= 50m | Proximity Validation (future) | Action permitted. | |
| A12 | Poor accuracy | > 100m | Proximity Validation (future) | Action blocked. User asked to refresh. | |

---

## 7. Failure Scenario QA Matrix

Reference: `docs/location-failure-handling-strategy.md`

| # | Scenario | Cause | Expected Behavior | Verify | Status |
|:---:|:---|:---|:---|:---|:---:|
| F1 | GPS disabled | System location services off | Default center used. Non-blocking Hebrew notice. Map interactive. Fields load. | Map renders. No crash. No spinner. | |
| F2 | No signal | Indoor / underground | Timeout or low accuracy. Cached location used if fresh (< 60s). Otherwise default center. | No infinite spinner. Notice shown. | |
| F3 | Timeout | Satellites unreachable | Loading stops. Cached location if fresh, else default center. Retry available via button. | Spinner clears. Notice shown. | |
| F4 | Permission missing | User denied | Denied notice. Map usable. No repeated prompts. | No prompt spam. Button available. | |
| F5 | Stale cached location | Cache > 60s old | Not silently treated as current. Fresh acquisition required for accuracy-dependent actions. | Cache expiry triggers new native call. | |
| F6 | Unsupported plugin | Missing native bridge or browser API | Generic fallback notice. Map usable at default center. | No crash. No broken marker. | |
| F7 | Malformed response | `NaN` coords, out-of-range lat/lng | Location rejected entirely. Default center used. No broken marker rendered. | Map renders correctly. | |
| F8 | Unknown failure | Unexpected error type | Generic unavailable notice. Map remains usable. | No crash. Error does not propagate to UI. | |

**Universal invariants for all failure scenarios:**
- Map always renders
- App never crashes
- No infinite spinner
- Fallback center (30.9872, 34.9314) is used when needed
- Manual map browsing remains usable
- User receives non-blocking message
- Broken user marker is never rendered

---

## 8. Android QA Plan

### 8.1 Permission Flow

| # | Check | Steps | Expected |
|:---:|:---|:---|:---|
| AD1 | Fresh install permission flow | `adb uninstall` → `adb install` → launch → tap "My Location" | Native dialog appears with accuracy options + Allow/Deny |
| AD2 | Grant → marker appears | Tap "While using the app" | Marker + accuracy circle + fly-to |
| AD3 | Deny → notice appears | Tap "Never" (לא, אף פעם) | Hebrew denied notice. No marker. |
| AD4 | Second denial → settings guidance | Dismiss notice → tap "My Location" again | Settings guidance notice (no native dialog) |
| AD5 | App restart after grant | Force-stop → relaunch → tap "My Location" | Location acquired without re-prompting |
| AD6 | App restart after denial | Force-stop → relaunch → tap "My Location" | Permission dialog re-appears (or settings guidance if permanently denied) |
| AD7 | OS settings revoke | Grant → Settings > revoke → return to app | Marker removed. Revocation notice on resume. |

### 8.2 Location Service

| # | Check | Steps | Expected |
|:---:|:---|:---|:---|
| AD8 | Real coordinates received | Grant permission → tap "My Location" | Marker at real device position (not default center) |
| AD9 | Accuracy circle rendered | Same as AD8 | SVG circle path visible around marker |
| AD10 | Cached second tap | Tap "My Location" twice within 60s | Second tap instant (< 1s). No new native call. |
| AD11 | Refresh after cache expiry | Wait > 60s or clear cache → tap "My Location" | Fresh native call made (slower response). New timestamp. |
| AD12 | Add Field location | Open Add Field → tap "Use Current Location" | Pin placed at real coordinates |

### 8.3 Failure and Fallback

| # | Check | Steps | Expected |
|:---:|:---|:---|:---|
| AD13 | GPS disabled | Settings > Location > Off → tap "My Location" | Non-blocking notice. Map at default center. Fields load. |
| AD14 | Airplane mode | Enable airplane mode → tap "My Location" | Timeout or unavailable notice. Map usable. |
| AD15 | Navigation launch | Open field details → tap Navigate | External app opens with destination coordinates |
| AD16 | No background location | `adb shell dumpsys package com.yeshmishak.app \| grep BACKGROUND_LOCATION` | Permission not listed |

### 8.4 Diagnostic Commands

```bash
# Check device connection
adb devices -l

# Check installed permissions
adb shell dumpsys package com.yeshmishak.app | grep permission

# Check location permission state
adb shell dumpsys package com.yeshmishak.app | grep -i "location"

# Check for background location
adb shell dumpsys package com.yeshmishak.app | grep BACKGROUND

# Monitor location-related logcat
adb logcat -s Capacitor:* Geolocation:* CapacitorGeolocation:*

# Force-stop app
adb shell am force-stop com.yeshmishak.app

# Clear app data (full reset)
adb shell pm clear com.yeshmishak.app

# Revoke location permissions
adb shell pm revoke com.yeshmishak.app android.permission.ACCESS_FINE_LOCATION
adb shell pm revoke com.yeshmishak.app android.permission.ACCESS_COARSE_LOCATION
```

---

## 9. iOS QA Plan

> **iOS scenarios are defined but execution is blocked until an iOS device, build, and signing path are available.** Do not claim iOS PASS without actual device validation.

### 9.1 Permission Flow

| # | Check | Steps | Expected | Status |
|:---:|:---|:---|:---|:---:|
| IO1 | iOS permission prompt | Launch → tap "My Location" | "While Using the App" / "Don't Allow" prompt | Blocked |
| IO2 | While In Use grant | Tap "Allow While Using App" | Marker appears. Map flies to position. | Blocked |
| IO3 | Denied permission | Tap "Don't Allow" | Denied notice. Map usable. | Blocked |
| IO4 | Permission revoked from Settings | Settings > Privacy > Location Services > yesh_mishak > Never | Marker removed on resume. Notice shown. | Blocked |
| IO5 | App reopen after permission change | Change permission in Settings → return to app | App detects change. Behavior matches new state. | Blocked |
| IO6 | No Always Location request | Inspect permission prompt | Only "While Using" and "Don't Allow" options. No "Always" option. | Blocked |
| IO7 | No background location mode | Inspect Info.plist | No `UIBackgroundModes` with `location` key. | Blocked |

### 9.2 Location and Navigation

| # | Check | Steps | Expected | Status |
|:---:|:---|:---|:---|:---:|
| IO8 | Real coordinates | Grant → tap "My Location" | Marker at real position | Blocked |
| IO9 | Navigation launch | Field details → Navigate | External app opens with destination | Blocked |
| IO10 | App usability without GPS | Deny all location → browse map | Map loads. Fields load. Manual panning works. | Blocked |

---

## 10. Regression Coverage from Previous Issues

| Issue | Area | What Must Be Regression-Tested |
|:---|:---|:---|
| **ISSUE-256** | Location service / refresh / cache | `getCurrentLocation` serves from cache within 60s. `refreshLocation` bypasses cache. Normalized location object includes all fields (lat, lng, accuracyMeters, altitude, heading, speed, timestamp, source, permissionState, ageMs, isFresh). Cache cleared on `clearLocationCache`. |
| **ISSUE-257** | Accuracy requirements | User Marker uses Medium accuracy (target <= 100m, max <= 500m). Navigation Launch uses Low accuracy (target <= 500m, max <= 2000m). Nearby Fields uses viewport bounds (not user accuracy). Future Proximity Validation uses High accuracy (target <= 50m, max <= 100m). |
| **ISSUE-258** | Accuracy handling | Accuracy warning banners display when accuracy exceeds thresholds. Coordinate shape preserved even with poor accuracy. No crash on missing or invalid accuracy values. |
| **ISSUE-259** | Failure strategy | All 7 failure types documented. Hebrew user messages defined. No blocking failures — app always remains usable. Retry policy: manual only (no automatic retry loops). |
| **ISSUE-260** | Failure handling | Failure utility correctly maps error types. Fallback behavior implemented per strategy. Loading indicators clear on failure. |
| **ISSUE-261** | Background location requirements | Background location NOT required. All use cases verified as foreground-only. Decision policy and future triggers documented. |
| **ISSUE-262** | Background location policy enforcement | Guard test verifies no `ACCESS_BACKGROUND_LOCATION` in manifest, no Always Location in Info.plist, no background plugins, no `watchPosition`. Policy implementation document exists. |

---

## 11. Manual QA Checklist

### Android Manual Checklist

- [ ] Install APK on real device (`adb install`)
- [ ] Launch app and verify map loads at default center
- [ ] Verify no permission prompt on first launch
- [ ] Tap "My Location" → verify native permission dialog appears
- [ ] Grant permission → verify marker + accuracy circle + fly-to
- [ ] Tap "My Location" again → verify cached response (instant)
- [ ] Deny permission (fresh install) → verify Hebrew denied notice
- [ ] Deny permanently → verify settings guidance notice on next tap
- [ ] Disable GPS → tap "My Location" → verify non-blocking notice
- [ ] Test location refresh (wait > 60s or cache clear) → verify new native call
- [ ] Open Add Field → tap "Use Current Location" → verify pin placed
- [ ] Open field details → tap Navigate → verify external app launches
- [ ] Verify no crash in any scenario
- [ ] Check `adb logcat` for location-related errors
- [ ] Verify `ACCESS_BACKGROUND_LOCATION` is NOT in dumpsys output

### iOS Manual Checklist

> Blocked until iOS device/build path is available.

- [ ] Install build on real device
- [ ] Launch app and verify map loads
- [ ] Tap "My Location" → verify While In Use prompt (no Always option)
- [ ] Grant While In Use → verify marker appears
- [ ] Deny permission → verify denied notice
- [ ] Revoke permission from Settings → verify detection on resume
- [ ] Test map fallback without location
- [ ] Test navigation launch
- [ ] Verify no background location prompt appears

### Web / Local Development Checklist

- [ ] Mock permission granted → verify marker + fly-to
- [ ] Mock permission denied → verify denied notice
- [ ] Mock timeout (error code 3) → verify unavailable notice
- [ ] Mock unsupported (no `navigator.geolocation`) → verify unavailable notice
- [ ] Mock malformed coordinates → verify no broken marker
- [ ] Run `npx playwright test tests/user-location.spec.js` → all pass
- [ ] Run `npx playwright test tests/location-service.spec.js` → all pass
- [ ] Run `npx playwright test tests/background-location-policy.spec.js` → all pass

---

## 12. Automated Test Coverage Guidance

The following test areas exist or are recommended. This section documents coverage guidance — no tests are added in ISSUE-263.

| Area | Test File | Status |
|:---|:---|:---|
| User location integration (grant, deny, timeout, unsupported, repeated denial) | `tests/user-location.spec.js` | Exists (5 tests) |
| Location service (normalization, cache, refresh, denied, unsupported, accuracy circle) | `tests/location-service.spec.js` | Exists (6 tests) |
| Background location policy guard | `tests/background-location-policy.spec.js` | Exists (4 tests) |
| Accuracy validation utility | — | Recommended: unit tests for `validateLocationAccuracy` when implemented |
| Failure handling utility | — | Recommended: unit tests for failure mapping when implemented |
| Map fallback rendering | `tests/user-location.spec.js` (partial) | Covered by existing denied/unsupported tests |
| Permission denied rendering | `tests/user-location.spec.js` | Covered |
| Timeout handling | `tests/user-location.spec.js` | Covered |
| Malformed coordinate rejection | — | Recommended: edge-case tests for NaN/out-of-range coords |
| Add Field location flow | `tests/add-field-city-location.spec.js` | Exists (scope TBD) |

---

## 13. Pass/Fail Criteria

### PASS Criteria

All of the following must be true:

- App remains fully usable without GPS (default center, manual browsing, field loading)
- Permission flows are predictable (no prompt spam, no surprise dialogs)
- Accuracy states handled according to `docs/gps-accuracy-requirements.md`
- Failure states handled according to `docs/location-failure-handling-strategy.md`
- No background location requested (per `docs/background-location-requirements.md`)
- Android real-device validation passes all AD* checks
- iOS validation either passes all IO* checks OR is explicitly marked as blocked and documented
- No crashes or infinite spinners in any scenario
- User-facing messages are clear, localized (Hebrew), and non-blocking
- All existing automated tests pass

### FAIL Criteria

Any of the following constitutes a failure:

- App crashes during any location scenario
- Map cannot load or render
- Infinite spinner that never resolves
- Broken or incorrectly positioned marker rendered
- User blocked from using the app due to location failure
- Background location permission requested (`ACCESS_BACKGROUND_LOCATION` or Always Location)
- Permission prompt loop (repeated OS dialogs without user action)
- Navigation flow broken (deep link fails to open external app)
- Silent wrong location behavior (stale cache treated as current, coordinates swapped)
- Hebrew messages missing or displaying raw error codes

---

## 14. Approval Checklist

- [x] Permission scenarios defined (P1–P13)
- [x] Accuracy scenarios defined (A1–A12)
- [x] Failure scenarios defined (F1–F8)
- [x] Android scenarios defined (AD1–AD16)
- [x] iOS scenarios defined (IO1–IO10)
- [x] Regression areas mapped (ISSUE-256 through ISSUE-262)
- [x] Manual QA checklist included (Android, iOS, Web)
- [x] Automated test coverage guidance included
- [x] Pass/fail criteria defined
- [x] Scope confirmed as documentation-only
