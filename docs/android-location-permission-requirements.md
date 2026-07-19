# Android Location Permission Requirements

## 1. Executive Summary
This document specifies the Android-specific location permission requirements for the `yesh_mishak` native application. To comply with modern Android security standards (specifically Android 12+ / API level 31+ permissions changes), the application will implement a flexible permission model that requests both precise and approximate location permissions, respects approximate-only user selections, and operates strictly in the foreground. No background tracking or first-launch permission prompts will be implemented.

---

## 2. Context From ISSUE-251 and ISSUE-252
The current native Android application does not declare location permissions in its manifest, leading to silent geolocation failures. According to the location permission strategy (`docs/location-permission-strategy.md`), the application will enforce a permission-at-point-of-need approach. Users will only see location prompts when triggering specific actions, with the application falling back gracefully to manual input and viewport-bounds field queries if permission is denied.

---

## 3. Android Permission Model
Starting with Android 12 (API level 31), users can choose to grant the app access to either their precise location (Fine Location) or approximate location (Coarse Location) via a unified system dialog.
If an application requests `ACCESS_FINE_LOCATION`, the OS displays a prompt allowing the user to select either "Precise" or "Approximate". To handle this flow correctly, the application must request both coarse and fine permissions simultaneously and adapt its features depending on which level of accuracy the user selects.

---

## 4. Required Manifest Permissions
In future native development, the application must declare the following permissions in `AndroidManifest.xml` (without editing it now):
- `android.permission.ACCESS_COARSE_LOCATION`: Allows access to approximate location derived from network sources.
- `android.permission.ACCESS_FINE_LOCATION`: Allows access to precise location derived from GPS and cell towers.

`android.permission.ACCESS_BACKGROUND_LOCATION` is **not required** and must remain out of scope for the current application.

---

## 5. Fine Location Requirement
Precise location (`ACCESS_FINE_LOCATION`) is needed to:
1. Pinpoint the user's position accurately on the map to show a precise navigation marker.
2. Capture the exact coordinate fix when the user clicks "Use current GPS location" to place a new field's pin.
3. Establish the reference coordinate for distance-based notification radius matching.

Precise location is **not** required for Map loading, field browsing, manual pin placement, deep-linked navigation destination parameters, or city-based notification settings.

---

## 6. Coarse Location Requirement
If a user selects "Approximate" only (granting `ACCESS_COARSE_LOCATION` but denying `ACCESS_FINE_LOCATION`), the application must:
- Center the map on the user's approximate coordinates (typically accurate to within 1.6 kilometers / 1 mile).
- Degrade location marker rendering by displaying a wider, low-opacity accuracy circle without the central precise dot.
- Advise the user in the Add Field dialog that precise GPS is unavailable, forcing them to manually adjust the map pin to guarantee accuracy.
- Save the approximate coordinate for distance-based notifications, warning the user of reduced matching precision.

---

## 7. Foreground / While-In-Use Requirement
The application must only request and retrieve location data while the application is in the foreground (actively in use or running a user-visible foreground process). Continuous background location harvesting is rejected. Geolocation requests are one-shot queries and must terminate when the active component is unmounted.

---

## 8. Permission Request Triggers
Permission queries must never trigger automatically on first app launch or on screen mount. The approved trigger events are:
1. Tapping the "Center on my location" button on the map.
2. Tapping "Use current GPS location" in the Add Field modal.
3. Toggling on "Distance-based notifications" inside settings.
4. **(Added 2026-07-17, E08-02)** Tapping the primary "Allow location" action on the onboarding location-priming screen — approved because it is an explicit, in-context user tap identical in kind to triggers 1-3, not an automatic request; see `docs/location-permission-strategy.md` §4a for the full rationale and the boundary this does *not* cross (the priming screen's own mount, and every other onboarding screen's mount, still never triggers the prompt).

---

## 9. Permission State Matrix

| Permission State | Android System Grant | Expected App Behavior | User Message | Fallback / Degradation |
| :--- | :--- | :--- | :--- | :--- |
| **Not Requested** | None | Geolocation remains idle. | None | Map shows `DEFAULT_CENTER`. |
| **Granted Precise** | Coarse + Fine | Map centers precisely, shows location dot. | None | Full native features available. |
| **Granted Approximate**| Coarse only | Map centers approximately, shows large accuracy circle. | Approximate accepted message. | Block GPS field creation; force manual pin adjustment. |
| **Denied** | Denied once | Silently fails on startup. Shows warning banner on explicit button taps. | Denied message. | Default map center; manual pin placement only. |
| **Permanently Denied** | Denied twice / "Don't ask again" | Geolocation attempts reject immediately. | Settings message. | User must go to Android App Settings to enable. |
| **Unavailable / Error**| GPS disabled / Timeout | Rejects after timeout. | Provider disabled or timeout message. | Use default center or manual entry. |
| **Device Location Services Disabled** *(clarified 2026-07-17, E08-02)* | N/A — rejected before the permission dialog | `checkPermissions()`/`requestPermissions()` reject with `@capacitor/geolocation`'s `LOCATION_DISABLED` (code `OS-PLUG-GLOC-0007`) *before* any permission grant/denial occurs. The app must route this to the same non-denial "unavailable" outcome as GPS/timeout above, never to "Denied" — see `frontend/src/api/locationPermission.js`. | Provider/services disabled message (never a denial message). | Use default center or manual entry; re-check once services are re-enabled. |

---

## 10. Feature Requirement Matrix

| Feature | Requires Android Permission? | Fine Required? | Coarse Acceptable? | Fallback Behavior |
| :--- | :---: | :---: | :---: | :--- |
| **View Map** | No | No | Yes | Renders map at `DEFAULT_CENTER`. |
| **View Fields** | No | No | Yes | Loads fields inside viewport bounds. |
| **Center on User** | Yes | No | Yes | Fallback to `DEFAULT_CENTER` if denied. |
| **Add Field Manually**| No | No | Yes | Drag and drop pin manually on map. |
| **Add Field (GPS)** | Yes | Yes | No | Fallback to manual pin placement. |
| **Join Game** | No | No | Yes | Normal game registration. |
| **Navigate to Field** | No | No | Yes | Opens external Waze/Google Maps links. |
| **Distance Notifications**| Yes | Yes | Yes (degraded) | Warn user of reduced accuracy. |
| **City Notifications** | No | No | Yes | Subscribes to manual city name text. |
| **Field Notifications**| No | No | Yes | Subscribes to field ID. |

---

## 11. UX Copy Requirements
The application must render the following Android-specific Hebrew strings:

- **Pre-Permission Explanation**:
  `כדי להציג את המגרשים סביבך ולעזור לך לנווט אליהם, האפליקציה זקוקה לגישה למיקום המכשיר. נבקש את אישורך כעת.`
- **Approximate-Only Accepted Message**:
  `המיקום המקורב נקלט בהצלחה. חלק מהתכונות יציגו דיוק מוגבל.`
- **Denied Message**:
  `לא ניתן להציג את מיקומך הנוכחי ללא הרשאת מיקום. המפה תמשיך לפעול במיקום ברירת המחדל.`
- **Permanently Denied / Settings Message**:
  `הרשאת המיקום נחסמה לצמיתות. כדי לאפשר אותה, יש להיכנס להגדרות המכשיר ולאפשר גישה למיקום עבור yesh_mishak.`
- **Location Services Disabled Message**:
  `רכיב ה-GPS כבוי במכשירך. יש להפעיל את שירותי המיקום בהגדרות המכשיר.`
- **Timeout / Unavailable Message**:
  `התקבל סיגנל מיקום חלש. המערכת תשתמש במיקום ברירת המחדל.`

---

## 12. Privacy and Data Handling Requirements
- **Strictly Ephemeral**: User coordinates for map centering must exist only in memory. Storing them in persistent local storage or sending them to the backend is prohibited.
- **Log Sanitation**: Coordinates must never be logged to Android Logcat or sent to backend crash logging tools.
- **Consent-Driven Processing**: Coordinates for distance-based notifications are sent to the backend only when the user explicitly clicks "Save".

---

## 13. Testing Requirements For Future Implementation
Future native location work must pass the following manual testing checklist on a physical Android device:
1. **Fresh Install**: First launch must not show a location permission prompt.
2. **On-Demand Prompt**: Tapping "Center on my location" must trigger the Android permission prompt.
3. **Precise Path**: Granting precise location must center the map exactly and render the accuracy dot.
4. **Approximate Path**: Granting approximate-only must display the large accuracy circle and Hebrew warning message.
5. **Denial Recovery**: Denying permission must silently return to the map. Clicking the button again must show the Hebrew explanation before re-prompting.
6. **Permanently Denied Flow**: Dismissing twice (or selecting "Don't ask again") and tapping the button must redirect the user to the Android App Settings screen.
7. **GPS Disabled**: Launching the app with location services toggled off in the Android quick settings panel must trigger the "GPS disabled" message.
8. **App Relaunch**: Restarting the app must not trigger a location permission prompt automatically.

---

## 14. Out Of Scope
The following implementation items are excluded from this requirements document:
- Modifying `AndroidManifest.xml`.
- Installing Capacitor location plugins.
- Implementing the JavaScript permission request wrapper.
- Implementing background location tracking services.
- Defining iOS location guidelines.
- Backend database geospatial migrations.

---

## 15. Decision Record
- **Approved Decision**: Future Android location features must declare and request both `ACCESS_COARSE_LOCATION` and `ACCESS_FINE_LOCATION` to handle approximate-only choices correctly.
- **Approved Decision**: First-launch/automatic-on-mount permission queries are rejected.
- **Approved Decision**: Background location tracking (`ACCESS_BACKGROUND_LOCATION`) is rejected. Remains rejected under E08-02 — no background permission was added.
- **Approved Decision**: Manual navigation and map features must remain fully functional if permissions are denied.
- **Amended 2026-07-17 (E08-02)**: an explicit user tap on the onboarding location-priming screen's primary action is added as a fourth approved trigger (§8, item 4). Automatic/mount-time requests remain rejected without exception.

---

## 16. Definition of Done Checklist
- [x] Fine location requirement documented.
- [x] Coarse location requirement documented.
- [x] Foreground/while-in-use behavior documented.
- [x] Background location excluded.
- [x] Permission triggers documented.
- [x] Permission state matrix included.
- [x] Feature matrix included.
- [x] UX copy included.
- [x] Privacy rules included.
- [x] Future Android testing requirements included.
- [x] No code changes made.
