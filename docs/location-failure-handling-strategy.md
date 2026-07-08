# Location Failure Handling Strategy

## 1. Purpose
Geospatial features are heavily dependent on native device hardware, operating system configurations, and browser permission architectures. Because these dependencies are prone to failure at multiple integration points (e.g. system-level settings, physical environmental blocks, user permission choices), location services cannot be assumed to be always available or reliable. 

To ensure the application remains stable and functional under all circumstances, it must implement predictable, graceful, and user-friendly fallback behaviors instead of failing silently or crashing.

---

## 2. Failure Model
We classify location telemetry failures into distinct categories based on their origin, signals, and resolution paths:

- **Permission Failure**: The user has explicitly denied location permissions for the application (either at the browser level or native operating system level). This requires guidance to prompt the user to enable it manually in settings if they attempt to use location-dependent features.
- **Device/Service Unavailable**: The system-level location services (GPS hardware) are disabled on the device, or the hardware sensor is missing or malfunctioning.
- **Timeout**: The location acquisition request fails to resolve within the allocated window (e.g. 10s for map initialization, 15s for notifications). This requires aborting the spinner and using fallbacks to avoid blocking the user.
- **Low/No GPS Signal**: The device is unable to communicate with GPS satellites due to physical obstructions (urban canyons, indoor usage, underground facilities).
- **Malformed/Empty Location Response**: The geolocation API returns a payload that lacks essential fields (latitude, longitude) or contains invalid values (e.g., non-number coordinates, coordinates outside ±90/±180 ranges, or non-positive accuracy numbers).
- **Stale Cached Location**: A location reading exists in local state or cache but its age exceeds the fresh-allowance window (e.g. 60 seconds).
- **Unsupported Platform / Plugin Failure**: The Capacitor geolocation plugin fails to load on a native platform, native bridge execution hangs, or the browser environment lacks `navigator.geolocation` capabilities.

---

## 3. Failure Scenarios

| Scenario | Example Cause | Detection Signal | User Impact | Expected App Behavior | Suggested User Message | Blocking? |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **GPS Disabled** | System-level location services toggled off. | Geolocation API rejects with `POSITION_UNAVAILABLE` or custom status. | App cannot resolve current coordinates. | Do not crash. Fall back to showing default center. Allow manual map panning/browsing. Allow navigation only if field destination is selected. | "שירותי המיקום כבויים. אפשר להפעיל מיקום במכשיר או להמשיך לעיין במפה ידנית." | **No** |
| **No Signal** | User is indoors or in an underground facility with poor GPS reception. | Geolocation API times out or returns extremely low accuracy (>2000m). | Cannot place exact marker; accuracy circle is huge. | Keep app usable. Serve last known location *only* if fresh enough (< 60s). Otherwise, use default center and show non-blocking warning. | "לא הצלחנו לקבל מיקום מדויק כרגע. ייתכן שאתה במקום עם קליטת GPS חלשה." | **No** |
| **Timeout** | Satellites are out of reach, causing the device to hang during coordinate resolution. | Location request duration exceeds the timeout threshold (e.g., 10s/15s limit). | Long loading spinner. | Stop waiting immediately. Clear/dismiss infinite loading indicators. Serve cached location if fresh enough; otherwise serve default center. Show retry button. | "לא הצלחנו לקבל מיקום בזמן. אפשר לנסות שוב או להמשיך להשתמש במפה." | **No** |
| **Permission Missing** | User denied browser prompt or native permission dialog. | Geolocation API rejects with `PERMISSION_DENIED`. | User location marker cannot be displayed. | Do not repeatedly spam OS prompts. Show localized explanation banner. Allow map usage via default center. Provide manual retry or direct settings redirection link. | "אין הרשאת מיקום. אפשר לאשר מיקום כדי לראות מגרשים קרובים אליך." | **No** |
| **Stale Cached Location** | App held a location in memory, but the user has traveled or time has passed (>60s). | Captured timestamp compared to current time (`ageMs > 60000`). | Coordinates do not reflect user's real location. | Do not silently treat it as current location. Use only for approximate fallback. Require fresh acquisition (refresh) for proximity-dependent actions. | "מציגים מיקום ברירת מחדל עד שנצליח לקבל את המיקום שלך." (if cached data is discarded) | **No** |
| **Unsupported Plugin / Native Failure** | Capacitor native bridge fails to load, or browser does not support `navigator.geolocation`. | `navigator.geolocation` is undefined, or plugin invocation rejects immediately. | Unable to query hardware sensors. | Keep app fully functional. Log diagnostic logs for development. Show generic fallback message to the user. | "המיקום אינו זמין במכשיר זה. המפה תפעל במצב ברירת מחדל." | **No** |
| **Malformed Location Response** | API returned `NaN` coordinates, invalid bounding box coordinates, or <= 0 accuracy. | Coordinates fail bounds validation (lat < -90 or > 90, lng < -180 or > 180) or types checks. | UI errors or rendering issues. | Reject the location payload entirely as unusable. Avoid rendering broken markers or centering map on invalid coordinates. Revert to fallback. | "התקבלה קריאת מיקום לא תקינה מהמכשיר. מציג מיקום ברירת מחדל." | **No** |

---

## 4. Use-Case Behavior Mapping

| Use Case | Failure Behavior |
| :--- | :--- |
| **User Marker** | Hide the marker and accuracy circle cleanly; do not display broken indicators. The map must not block and must remain fully interactive. |
| **Nearby Fields** | Load fields based on the default map center or current viewport bounds. Allow the user to browse fields manually by panning the map. |
| **Navigation Launch** | Allow launching navigation deep links (Waze/Google Maps) using the target field's destination coordinates only; do not require user GPS origin. |
| **Refresh Location** | If location refresh fails, display a non-blocking toast/banner notice. Dismiss all loading indicators immediately to avoid infinite spinners. |
| **Future Proximity Validation** | Block the proximity-sensitive action (e.g. check-in) completely until a fresh, valid location fix meeting high accuracy standards is acquired. |

---

## 5. User Messaging Standards (Hebrew Copy)
The application must present user-facing feedback in clear, friendly Hebrew copy based on the specific failure scenario encountered:

* **GPS Disabled**:
  `"שירותי המיקום כבויים. אפשר להפעיל מיקום במכשיר או להמשיך לעיין במפה ידנית."`
* **Permission Missing**:
  `"אין הרשאת מיקום. אפשר לאשר מיקום כדי לראות מגרשים קרובים אליך."`
* **Timeout**:
  `"לא הצלחנו לקבל מיקום בזמן. אפשר לנסות שוב או להמשיך להשתמש במפה."`
* **No Signal**:
  `"לא הצלחנו לקבל מיקום מדויק כרגע. ייתכן שאתה במקום עם קליטת GPS חלשה."`
* **Fallback / Stale Cache Reset**:
  `"מציגים מיקום ברירת מחדל עד שנצליח לקבל את המיקום שלך."`

---

## 6. Retry Policy
To balance battery usage, system resources, and user experience, location requests must follow a strict retry policy:

- **When Retry is Allowed**: A retry is permitted when the user triggers an explicit location-based action (e.g., clicking "My Location" or "Use Current GPS Location" buttons).
- **When Retry Should Be Manual**: Automatic retries should not occur after timeouts, user-denials, or service-unavailable statuses. The user must manually tap the location trigger button to initiate a new request.
- **When Automatic Retry is Acceptable**: An automatic retry is allowed only when the app returns to the foreground, and *only* if the app previously held a valid location permission that might have been changed in settings.
- **When Not to Keep Retrying (Anti-Patterns)**:
  - Do not loop requests on timeout; abort the attempt immediately.
  - Do not spawn permission dialogs repeatedly. If permission is denied, keep it blocked until the user takes action.
  - Do not use cached data if it is stale and a feature requires high precision.

---

## 7. Logging and Diagnostics
To aid debugging and troubleshooting, location failures should be logged in development/debug modes with the following properties:

- **Failure Type**: The mapped error string (e.g. `'permission_denied'`, `'unavailable'`, `'timeout'`, `'malformed'`).
- **Stage**: The execution step where it failed (e.g., checking permissions, requesting permissions, getting current coordinates).
- **Timeout Duration**: The timeout limit set for the call (e.g. 10000ms).
- **Cache Status**: Whether a cached coordinate was used as a fallback and its age in milliseconds.
- **Platform Path**: Whether it was executed via Capacitor native plugins or the browser Web API.
- **Permission State**: Current permission status (e.g. `'granted'`, `'denied'`, `'prompt'`, `'settings'`).

*CRITICAL PRIVACY STANDARD*: Exact user coordinate values (latitude, longitude) must **never** be logged in production telemetry or system logs.

---

## 8. Relationship to Previous Issues
The location strategy is built incrementally across the following issues:
* **ISSUE-256**: Defined the memory caching lifetime, maximum age limits (`maxAge`), and refresh behavior.
* **ISSUE-257**: Defined GPS accuracy requirements (High, Medium, Low levels) in meters.
* **ISSUE-258**: Implemented accuracy checking, warning banners on the map screen, and coordinate shape preservation.
* **ISSUE-259**: Defines failure behavior and user-facing fallback strategies when location data cannot be resolved or verified.

---

## 9. Out of Scope
The current task (ISSUE-259) is strictly a documentation task. The following items are out of scope:
- No frontend implementation or UI layout changes.
- No backend code changes or API contract modifications.
- No Android native code changes or native manifest permission requests.
- No iOS changes.
- No permission-flow implementation adjustments.
- No new automated unit, integration, or E2E tests.
- No UI changes or new styling.
- No production analytics integration.

---

## 10. Definition of Done Checklist
- [x] GPS Disabled failure scenario defined.
- [x] No Signal failure scenario defined.
- [x] Timeout failure scenario defined.
- [x] Permission Missing failure scenario defined.
- [x] Stale cache behavior defined.
- [x] Unsupported plugin/native failure scenario defined.
- [x] Malformed response scenario defined.
- [x] Current location use cases mapped to failure behavior.
- [x] User-facing message standards defined.
- [x] Retry policy defined.
- [x] Scope confirmed as documentation-only.
