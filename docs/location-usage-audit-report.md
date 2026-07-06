# Location Usage Audit Report

**Issue:** ISSUE-251 (#340)
**Status:** Documentation-only audit — no behavior was modified, no Native GPS was added.
**Date:** 2026-07-06
**Code audited at:** main `e67e666`

## 1. Executive Summary

Location today is **browser-geolocation only** (`navigator.geolocation.getCurrentPosition`), used in exactly three places: centering the map once on startup (MapPage), placing a new field's pin (AddFieldModal), and capturing a reference point when saving distance-based notification preferences (NotificationsModal). There is no `watchPosition`, no Capacitor geolocation plugin, and — critically — **the Android manifest declares no location permission**, so on the native Android app every geolocation call fails silently and the app always runs its fallback paths (fixed default map center, manual pin placement, distance-notifications save error). Field loading is driven by **map viewport bounds**, not by user coordinates. Navigation to a field exists (Waze / Google Maps deep links) and uses **destination coordinates only** — the user's location is never embedded in links. User coordinates are held in React state only, except notification distance preferences, where a fresh fix is sent to the backend and persisted.

## 2. Source Files Reviewed

| File | Responsibility | Location-related behavior |
|---|---|---|
| `frontend/src/pages/MapPage.jsx` | Map screen | One-shot geolocation on mount; map center state; user-location marker + accuracy circle; My Location fly-to button; bounds-based field loading |
| `frontend/src/components/AddFieldModal.jsx` | Create field | Optional geolocation for pin placement; manual pin fallback; submits chosen lat/lng as field data |
| `frontend/src/components/NotificationsModal.jsx` | Notification preferences | Fresh geolocation at save time when distance notifications are enabled; sends `distance_lat`/`distance_lng` to backend |
| `frontend/src/components/FieldDetailsPanel.jsx` | Field details | "Navigate to field" modal → Waze / Google Maps deep links (destination-only); coordinate validation |
| `frontend/src/pages/OnboardingPage.jsx` | Onboarding | Manual city selection → `localStorage.userCity` (coarse location proxy, no geolocation) |
| `frontend/src/api/fields.js` | Fields API client | Sends viewport bounds (`north/south/east/west`) as query params; in-flight dedupe keyed by rounded bounds |
| `backend/app/routers/fields.py` | Fields API | Validates bounds ranges and ordering; Supabase box filter `lat/lng` between bounds; returns field `lat`/`lng` |
| `backend/app/routers/notifications.py` (+ services) | Notification prefs & matching | Persists radius preference (`radius_km`, `lat`, `lng`); backend-side radius matching |
| `backend/app/services/duplicate_detection.py` | Admin/duplicate detection | Haversine distance between **field** coordinates (no user location involved) |
| `frontend/tests/user-location.spec.js` | Tests | Mocks `navigator.geolocation`; covers success/denied/timeout/unsupported |
| `frontend/android/app/src/main/AndroidManifest.xml` | Android config | **No location permissions declared** (INTERNET, POST_NOTIFICATIONS only) |

## 3. Current Location Flow

1. App starts → authenticated → `MapPage` mounts with `center = DEFAULT_CENTER` (`[30.9872, 34.9314]`, zoom 14).
2. A mount effect checks `navigator.geolocation`; if absent, it returns silently (fallback center stands).
3. Otherwise it calls `getCurrentPosition` with `{ enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }`.
4. **Granted + fix:** `userLocation` state is set (`position`, `accuracy`), and `setCenter(position)` re-centers the map once via the `RecenterMap` child (`map.setView`). The user-location marker and accuracy circle render. A "My Location" floating button appears; pressing it increments a request id that triggers `UserLocationFlyTo` → `map.flyTo(position, zoom 16)`.
5. **Denied / error / timeout:** the error callback sets `userLocation = null`; no message is shown; the map remains fully usable at the default center (regression-tested).
6. The map's field data is loaded from viewport bounds on every settled pan/zoom — user location plays no role in field loading.
7. On the native Android app, step 3 always takes the error path (see §9), so steps 5–6 are the effective production behavior on device.

## 4. Browser Geolocation Usage

All three call sites use the one-shot `navigator.geolocation.getCurrentPosition`; `watchPosition` is never used; the `permissions` API is never queried.

| Call site | Options | Success | Failure |
|---|---|---|---|
| MapPage.jsx:387 (mount) | `enableHighAccuracy: true, timeout: 10000, maximumAge: 60000` | Set `userLocation` + center map (guarded by `isMounted`) | `setUserLocation(null)` — silent |
| AddFieldModal.jsx:114 (button) | library defaults (no options) | Pin position set, `locationSource='gps'` | Error text shown; any existing manual pin is deliberately left untouched |
| NotificationsModal.jsx:182 (save) | `enableHighAccuracy: false, timeout: 15000, maximumAge: 0` | Resolves `{lat, lng}` for the save payload | Rejects after a 1200ms grace timer (`GEOLOCATION_ERROR_GRACE_MS`, lets a late success win); mapped to translated messages per error code (`getGeolocationErrorDetails`) |

There is no fallback *location* anywhere — fallbacks are behavioral (default center, manual pin, disabled distance notifications), never a substitute coordinate. AddFieldModal explicitly documents that a fallback coordinate must never pre-fill the pin.

## 5. Map Centering Behavior

- Initial center: hardcoded `DEFAULT_CENTER = [30.9872, 34.9314]` (central Israel/Negev), `DEFAULT_ZOOM = 14` — used always, immediately.
- On the single successful fix: `center` state changes once → `RecenterMap` runs `map.setView(center)`. There is no continuous following: position changes after the first fix are never observed (no `watchPosition`), so the center never updates again from location.
- "My Location" button (rendered only when `userLocation` exists and no field panel is open): `map.flyTo(userLocation.position, 16)` per press.
- User panning is otherwise sovereign — nothing re-centers behind the user's back.
- Owners: `MapPage` (state), `RecenterMap` and `UserLocationFlyTo` (map-side effects, both in MapPage.jsx).

## 6. Nearby Fields Behavior

"Nearby" is **viewport-based, not user-location-based**:
- `FieldLoader` (MapPage.jsx) fires on `moveend` (debounced 250ms) and calls `GET /fields/` with `north/south/east/west` from `map.getBounds()`.
- Backend (`fields.py:102-145`) validates ranges (±90/±180), rejects inverted bounds (antimeridian crossing unsupported — irrelevant for Israel), and applies a Supabase box filter (`lat`/`lng` gte/lte). **No distance computation, no radius, no ordering by proximity** — a plain bounding-box query.
- Responses are merged by `field.id` into existing state (Map Fixing 2), with stale-response guards (Map Fixing 3), and cached in `localStorage.cached_fields`.
- User coordinates are never sent to `/fields/`. Distance math exists in the backend only for (a) duplicate-field detection (haversine between *field* coordinates) and (b) radius *notification* matching against the saved preference point.

## 7. Navigation Features

Implemented in `FieldDetailsPanel.jsx` ("Navigate to field" modal, two options):
- **Waze:** `https://waze.com/ul?ll=<lat>,<lng>&navigate=yes`
- **Google Maps:** `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>`
- Opened with `window.open(url, '_blank', 'noopener,noreferrer')`; the modal closes after.
- **Destination-only:** links carry the *field's* coordinates exclusively; the user's location is never included (the target app resolves origin itself). Coordinates are validated first (finite, within ±90/±180 — `getNavigationCoordinates`); with invalid coordinates the modal simply closes and no link opens.
- Placeholder/future work (open issues, not in code): ISSUE-274 external-navigation strategy, ISSUE-276 Google Maps integration, ISSUE-277 Apple Maps, ISSUE-278 fallback handling. Nothing in the current code handles "navigation app not installed" — `window.open` fires unconditionally.

## 8. Location Marker Behavior

- Rendered by `MapPage` directly (no dedicated component): when `userLocation` is truthy, a `<Circle>` (accuracy radius, blue `#2563eb/#3b82f6`, low opacity) plus a `<Marker>` with a `user-location-marker` divIcon (28×28, anchored center), `interactive={false}`, `keyboard={false}`, `zIndexOffset={1000}` so it floats above field markers.
- Appears only after a successful fix; never appears on denial/failure; disappears only if `userLocation` becomes null (in practice: never after success, since nothing re-queries).
- **Position never updates** after the first fix (single-shot). The accuracy circle renders only when `coords.accuracy` is a finite number.

## 9. Permission / Error / Fallback Behavior

| Condition | Behavior |
|---|---|
| Granted (web browser) | Center once, marker + circle, My Location button |
| Denied | Silent; default center; map fully usable (test: "keeps the map usable when location permission is denied") |
| Timeout (10s map / 15s notifications) | Same silent fallback (tested); notifications save shows a translated timeout message |
| Unsupported (`navigator.geolocation` missing) | Guarded at all three sites; map silent, modals show "location unavailable" |
| **Native Android app** | **Geolocation can never succeed:** the manifest declares no `ACCESS_FINE_LOCATION`/`ACCESS_COARSE_LOCATION`, and no Capacitor geolocation plugin is installed, so the WebView's permission request cannot be granted. Every call takes the error path. The app behaves as "denied" everywhere: default map center, manual pin only, distance-notification saves fail with the location error. |
| Re-request | No UI exists to retry a denied/failed map fix (the My Location button only renders after success); AddFieldModal/NotificationsModal retry implicitly on each button press/save |

## 10. Storage / Privacy Notes

- **Map user location:** React state only (`userLocation`, `center`). Never written to localStorage/sessionStorage, never sent to the backend, never logged.
- **Notification distance preference:** the only place user coordinates leave the device — a fresh fix (`maximumAge: 0`) is sent on save and **persisted server-side** as `distance_lat`/`distance_lng` with `radius_km` for backend radius matching. Saved coordinates go stale until the user saves again (documented gap, §11).
- **Field creation:** the chosen pin (GPS or manual) becomes the field's public `lat`/`lng` — intentional public data, not personal location (though a GPS-placed pin equals the reporter's position at that moment).
- **`localStorage.userCity`:** manually chosen city name from onboarding — coarse, user-declared, not derived from geolocation.
- No coordinates appear in frontend or backend logs (log lines carry event names/booleans; geolocation errors are logged as translated messages without coordinates).

## 11. Known Gaps / Risks (before Native Location work)

1. **Native Android geolocation is entirely non-functional** (no manifest permission, no plugin, no WebView geolocation-prompt handling). All device users silently get fallback behavior; browser-only users get the full experience. This is the single biggest gap Native Location must close.
2. **Single-shot fix, no `watchPosition`:** the marker and center go stale the moment the user moves; My Location re-flies to the *old* fix.
3. **`maximumAge: 60000` on the map fix:** a cached position up to a minute old may be presented as current.
4. **Silent denial UX:** no rationale, no retry affordance, no settings deep-link on the map screen.
5. **Stale notification reference point:** distance notifications match against coordinates captured at the last save, which can be arbitrarily old.
6. **Fixed default center** (`[30.9872, 34.9314]`): users far from it start on an empty area (bounded by `userCity` being unused for centering — the stored city is never fed into the map).
7. **Navigation fallback missing:** no handling for uninstalled Waze/absent maps app (tracked as ISSUE-278; `window.open` of a Waze universal link on a device without Waze lands in the browser).
8. **`enableHighAccuracy: true` at map startup:** slowest/most battery-hungry mode on the critical path (moot on Android today given gap 1, relevant once native lands).
9. Permission state is never inspected (`navigator.permissions.query`), so denied-forever vs. transient failure are indistinguishable.

## 12. Native Location Readiness Notes (do not implement — preserve list)

Future Native Location work must preserve:
- **Fail-open UX:** the map must remain fully usable with a default center on denial/failure (regression-tested today in user-location.spec.js).
- **No fallback coordinates as data:** AddFieldModal's rule that a pin is only user-provided (GPS or manual) — never a default/display coordinate.
- **One-time centering semantics:** auto-center happens once; user panning is never overridden; My Location is an explicit action (flyTo zoom 16).
- **Destination-only navigation links** (no user-origin leakage in URLs).
- **Save-time capture semantics** for notification preferences (`maximumAge: 0`, fresh consent-adjacent fix per save; payload shape `distance_lat`/`distance_lng`/`distance_radius_km`).
- **Privacy posture:** map coordinates stay in memory; only the notification preference point is persisted server-side.
- **Bounds-driven field loading** — do not switch to user-radius loading as a side effect; the merge/stale-guard pipeline (Map Fixing 2/3) assumes bounds semantics.
- **Test seams:** current specs mock `navigator.geolocation` via `Object.defineProperty`; a Capacitor plugin will need an equivalent mock strategy (the established `window.Capacitor.nativePromise` pattern used by the secure-storage/social-login mocks is available).
- Android manifest changes (location permissions) will be required and must go through the release checklist; iOS remains excluded per project policy.

## 13. Definition of Done Checklist

- [x] User location acquisition mapped (3 call sites, exact APIs and options) — §4
- [x] Permission granted / denied / error / timeout / unsupported behavior documented — §4, §9
- [x] Fallback behavior documented (behavioral fallbacks, no substitute coordinates) — §4, §9
- [x] Storage locations documented (React state / localStorage / backend / logs) — §10
- [x] Map centering: initial, fallback, updates, owning components — §5
- [x] Nearby fields: bounds-driven loading, query params, backend filtering, distance-calc locations — §6
- [x] Navigation features: Waze/Google Maps links, destination-only, missing fallback behavior — §7
- [x] Location marker: renderer, lifecycle, update behavior, styling — §8
- [x] All required search terms executed repo-wide (navigator.geolocation, geolocation, location, userLocation, currentLocation, mapCenter, latitude, longitude, lat, lng, bounds, nearby, distance, directions, navigate, open maps, Google Maps, Waze) — §2 table lists every file with hits relevant to app behavior
- [x] Known gaps/risks before Native Location — §11
- [x] Native Location readiness/preserve list (no implementation) — §12
- [x] No frontend/backend/Android/iOS code modified — documentation-only diff
