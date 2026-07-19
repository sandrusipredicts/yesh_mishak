# Location Permission Strategy

## 1. Executive Summary
This document defines the location permission strategy for the `yesh_mishak` application across Web, Android, and iOS targets. To maximize user trust and minimize app-installation drop-offs, the application adopts a **privacy-first, permission-at-point-of-need** strategy.

The application will never request location permission on the first app launch or during onboarding. Instead, the permission flow is gated behind explicit user actions that require geospatial data, accompanied by Hebrew in-app explanations. If a user denies permission, the application remains fully functional by falling back to manual entry, viewport-bounds field queries, and a default map center.

---

## 2. Current Context From ISSUE-251
Based on the location audit (`docs/location-usage-audit-report.md`), the application currently utilizes location data in three specific scenarios:
1. One-shot centering of the map on startup (`MapPage`).
2. Quick pin placement when adding a new field (`AddFieldModal`).
3. Capturing coordinates when saving distance-based notification preferences (`NotificationsModal`).

On the web target, browser geolocation is used via `navigator.geolocation.getCurrentPosition`. On native Android, location permissions are not declared in `AndroidManifest.xml` and no Capacitor location plugin is configured, meaning all geolocation calls on native Android fail silently, taking the fallback paths.

---

## 3. Product Principle
Location data is highly sensitive PII. Requesting location permissions on first launch breeds suspicion and triggers high opt-out rates. The product principle is: **Value First, Permission Second**. The application must prove its utility (displaying nearby fields, allowing map browsing) before requesting access to the device's hardware sensors.

---

## 4. Permission Request Timing
- **Prohibited Times**: Automatically on first app launch or screen mount, on user registration, on login, and during simple map navigation — see §4a for the one narrow, approved exception.
- **Allowed Times**: Only after a user interacts with a feature that cannot function without device-derived location coordinates, or explicitly presses the primary action on the onboarding location-priming screen (§4a).

---

## 4a. E08-02 Addendum — Onboarding Location Priming (2026-07-17)
The six-step onboarding walkthrough (`frontend/src/pages/OnboardingPage.jsx`) includes a dedicated location-priming step. This is an **approved, narrow exception** to §4's original blanket "never during onboarding" rule, not a reversal of it. The rule this document actually protects — *no silent, automatic OS permission prompt on app launch or screen mount* — is fully preserved:

- **Still forbidden, unchanged**: triggering the native/browser permission prompt automatically when a screen (including the onboarding location step) mounts, on first app launch, on login, or on registration. `OnboardingPage.jsx`'s location step calls only `checkExistingPermission()` on mount — a passive, non-prompting read — never `requestCurrentLocation()`.
- **Newly approved**: the OS permission prompt may be triggered from within onboarding **only** when all of the following hold, mirroring the point-of-need principle's actual intent (an explicit, informed, in-context user action — not a launch-time ambush) rather than weakening it:
  1. A dedicated, truthful explanation screen is shown first (not just a bare OS dialog).
  2. The user explicitly presses that screen's primary action button — the prompt is never triggered by any effect, timer, or mount.
  3. A "Not now" / skip action is always available and never itself triggers the prompt.
  4. The application remains fully usable (city-based map fallback, per §9's feature matrix) if the user skips or denies.

This keeps the map's own existing point-of-need re-request (the `LocateFixed` button, unaffected by this addendum) and the new onboarding priming step consistent: both only ever prompt from a direct user tap, never automatically.

**iOS note**: this addendum describes shipped, verified Android/web behavior only. The corresponding iOS `Info.plist` `NSLocationWhenInUseUsageDescription` key required for this same behavior to run safely on iOS has not been added — see §13. **Deferred to iOS implementation phase.**

---

## 5. First Launch Strategy
- **Decision**: Geolocation permissions on first launch are **prohibited**.
- **Rationale**:
  - Violates user trust guidelines.
  - Leads to immediate uninstalls or permanent denials.
  - Map browsing can function using viewport bounds without knowing the user's location.

---

## 6. Point-of-Need Permission Strategy
Permissions must only be triggered by the following specific user actions:
1. **Centering the Map**: The user taps the floating "Center on my location" button.
2. **Adding a Field**: The user clicks the "Use current GPS location" button in the Add Field dialog.
3. **Distance Notifications**: The user toggles on the "Distance-based notifications" option in their settings.

---

## 7. User Explanation Copy
All location permission prompts must be preceded or handled by clear Hebrew UX strings:

- **Pre-Permission Explanation**:
  `כדי להציג את המגרשים סביבך ולעזור לך לנווט אליהם, האפליקציה זקוקה לגישה למיקום המכשיר. נבקש את אישורך כעת.`
- **Permission Denied Message**:
  `לא ניתן להציג את מיקומך הנוכחי ללא הרשאת מיקום. המפה תמשיך לפעול במיקום ברירת המחדל.`
- **Permission Permanently Denied / Settings Message**:
  `הרשאת המיקום נחסמה לצמיתות. כדי לאפשר אותה, יש להיכנס להגדרות המכשיר ולאפשר גישה למיקום עבור yesh_mishak.`
- **Fallback Message**:
  `המיקום אינו זמין. מציג מיקום ברירת מחדל.`

---

## 8. Permission States

- **Unknown / Not Requested**: Geolocation is idle; the map uses `DEFAULT_CENTER` silently. No location marker is rendered.
- **Granted**: The map centers once on the user's location, renders a blue location marker with an accuracy circle, and enables the "Center on my location" button.
- **Denied**: The map falls back to the default center silently. Subsequent taps on "Center on my location" trigger the "Permission Denied" warning banner.
- **Permanently Denied**: Tap triggers on location features display a dialog with the "Settings Message" advising the user to manually enable location permissions in the OS settings.
- **Unavailable / Error / Timeout**: The application treats this as "Denied" and falls back to manual operations.

---

## 9. Feature Behavior Matrix

| Feature | Location Mandatory? | Location Fallback Behavior |
| :--- | :--- | :--- |
| **Viewing Map** | No | Renders at `DEFAULT_CENTER` (`[30.9872, 34.9314]`). |
| **Viewing Fields** | No | Loads fields located inside the map viewport bounds. |
| **Centering on User Location** | Yes | Displays the "Permission Denied" message; map remains on current coordinates. |
| **Adding a Field Manually** | No | User manually pans the map and drags the pin to place a marker. |
| **Joining a Game** | No | Standard join action completes without location checks. |
| **Navigation to Field** | No | Opens Waze/Google Maps links using destination coordinates only. |
| **Distance-Based Notifications** | Yes | Toggling this on requires coordinates. If denied, the toggle resets and warns the user. |
| **City-Based Notifications** | No | Standard subscription to a textual city name (no coordinates needed). |
| **Field-Specific Notifications** | No | Standard subscription to a field ID. |

---

## 10. Fallback Behavior
- **Default Map Coordinates**: `[30.9872, 34.9314]` (Central Israel/Negev).
- **Manual Pin Placement**: Add Field modal forces manual pin drag if location is denied or unavailable.
- **Destination-Only Navigation**: Deep links to Waze and Google Maps only carry destination lat/lng. The native navigation app is responsible for identifying the user's origin.

---

## 11. Privacy Rules
- **Ephemeral in Memory**: User coordinates obtained for map centering must live only in React component state. They must never be written to `localStorage` or `sessionStorage`, and must never be sent to the backend.
- **Log Exclusions**: Geolocation coordinates must never be printed to frontend console logs or backend application logs. Geolocation actions must only log event flags (e.g. `event=location_acquired persisted=false`).
- **Server Persistence Limits**: The only coordinates stored server-side are the latitude/longitude reference points chosen by the user for distance notifications.

---

## 12. Android Native Readiness Notes
Future Android native location implementation must preserve the following:
- Permissions must be declared in the manifest (`ACCESS_COARSE_LOCATION` and `ACCESS_FINE_LOCATION`).
- The app must use the `@capacitor/geolocation` plugin to handle runtime permission dialogues.
- Gating permission calls through the "Pre-Permission Explanation" is mandatory.

---

## 13. iOS Native Readiness Notes
Future iOS native location implementation must preserve the following:
- `NSLocationWhenInUseUsageDescription` must be configured in `Info.plist` with a clear explanation of location usage.
- Geolocation calls must delegate to iOS CoreLocation via the Capacitor Geolocation plugin.
- Only the "When In Use" key is required; do not add `NSLocationAlwaysAndWhenInUseUsageDescription`/`NSLocationAlwaysUsageDescription` — this application never requests "Always" location access.

**Status (2026-07-17, E08-02)**: `NSLocationWhenInUseUsageDescription` is still not present in `frontend/ios/App/App/Info.plist`. The onboarding location-priming step described in §4a is Android/web-verified only; running it natively on iOS today would fail once this key is added and native testing begins. **Deferred to iOS implementation phase** — no `Info.plist` or Xcode configuration changes were made as part of E08-02's Android-first phase.

---

## 14. Out Of Scope
The following implementations are explicitly excluded from this strategy and must not be built yet:
- Native GPS/Capacitor Geolocation plugin installation.
- AndroidManifest permissions configuration.
- iOS plist modifications.
- Push notification proximity filtering on the client.
- Backend geospatial index migrations.
- Dynamic map marker clustering.
- Custom navigation fallback screen implementations.

---

## 15. Decision Record
- **Approved Decision**: Location permission must be requested only after explicit user intent (at the point of need), and must never be requested automatically on first app launch or on any screen mount.
- **Amended 2026-07-17 (E08-02)**: the onboarding location-priming screen's primary-action button is an approved point-of-need trigger for the reasons detailed in §4a — an explicit, in-context user tap, not an automatic launch-time or mount-time request. The prohibition on automatic/silent requests is unchanged.

---

## 16. Definition of Done Checklist
- [x] Permission timing defined.
- [x] First-launch behavior defined.
- [x] Point-of-need triggers defined.
- [x] Denied/fallback behavior defined.
- [x] User explanation Hebrew copy included.
- [x] Feature matrix included.
- [x] Privacy rules included.
- [x] Native Location readiness documented.
- [x] No code changes made.
