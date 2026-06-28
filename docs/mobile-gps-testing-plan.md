# Mobile GPS Testing Plan

## A. Purpose

The map is the primary interface of Yesh Mishak. Every core flow — finding fields, joining games, adding fields — begins on the map. The app requests browser geolocation to center the map on the user's real position and to display a user location marker.

If geolocation permission handling, error states, or fallback behavior are broken on mobile, users may see an empty or miscentered map, get trapped in a loading state, or lose access to core actions. GPS/location testing validates that:

- Permission granted produces correct map centering and a visible user location marker.
- Permission denied, revoked, or unavailable states fall back gracefully and never block map usage.
- The "My Location" button and "Use current location" (AddFieldModal) work correctly when geolocation is available and handle failure when it is not.
- Mobile browser differences in permission UI, timing, and error reporting do not break the app.

## B. Scope

This plan covers:

- **Browser geolocation permission behavior** — prompt, grant, deny, revoke, and dismiss across mobile browsers.
- **Map initial loading behavior** — how `MapPage` calls `navigator.geolocation.getCurrentPosition` on mount and falls back to `DEFAULT_CENTER [30.9872, 34.9314]` on failure.
- **User location marker** — the blue dot marker (`.user-location-marker`) and accuracy circle that appear when geolocation succeeds. Hidden when geolocation fails.
- **"My Location" button** — the `LocateFixed` floating button that flies the map back to the user's position. Visible only when `userLocation` is set and no field is selected.
- **AddFieldModal "Use current location"** — a separate `getCurrentPosition` call that sets the field location picker to the user's coordinates. Shows `locationUnavailable` or `locationFailed` error on failure.
- **Permission granted** — map centers on user, marker visible, accuracy circle shown, "My Location" button works.
- **Permission denied** — `userLocation` set to `null`, map stays on default center, no marker, no "My Location" button, map remains usable.
- **Permission revoked** — previously granted permission removed from browser settings; app must not assume stale access.
- **Location unavailable** — device cannot provide coordinates (indoor, airplane mode, broken GPS). Error callback fires with code 2 (`POSITION_UNAVAILABLE`).
- **Slow GPS response / timeout** — `getCurrentPosition` has a 10-second timeout (`timeout: 10000`). If exceeded, error callback fires with code 3 (`TIMEOUT`).
- **Location accuracy** — `coords.accuracy` is stored and rendered as an accuracy circle radius. Non-finite values are treated as `null`.
- **Mobile browser differences** — Chromium and WebKit handle permission prompts, error codes, and timing differently.
- **Manual and automated test coverage** — what Playwright can simulate vs. what requires real-device or manual validation.

### Out of Scope

- Push notifications or background location tracking (the app does not use `watchPosition`).
- GPS accuracy calibration or A-GPS behavior.
- Native app location permissions (this is a web app).

## C. Required Test Environments

| Category | Example device | Viewport | Browser/engine | Required |
| :--- | :--- | :--- | :--- | :--- |
| Android Small | Galaxy A14 | 360x640 | Chrome (Chromium) | Yes |
| Android Large | Pixel 7 | 412x915 | Chrome (Chromium) | Yes |
| iPhone Small | iPhone SE 3 | 375x667 | Safari (WebKit) | Yes |
| iPhone Large | iPhone 14 | 390x844 | Safari (WebKit) | Yes |
| Tablet / iPad | iPad 10th gen | 768x1024 | Safari (WebKit) | Yes |
| Desktop | Any | 1280x800 | Chrome (Chromium) | Yes (sanity check) |
| Chromium simulation | Playwright | Multiple viewports | Playwright Chromium | Yes (automated baseline) |
| WebKit simulation | Playwright | Multiple viewports | Playwright WebKit | Yes (automated baseline) |
| Samsung Internet | Samsung Galaxy | 412x915 | Samsung Internet / Chromium proxy | Yes (Chromium proxy acceptable when direct device unavailable; label proxy honestly) |
| Real device | Physical Android/iOS | Physical viewport | Native browser | Recommended for permission prompt, keyboard, browser chrome validation |

### Browser Geolocation API Coverage

| Browser | Permission prompt | Error codes | Notes |
| :--- | :--- | :--- | :--- |
| Chrome (Android) | System-level prompt or site settings | Standard codes 1/2/3 | Prompt may be suppressed after repeated denials |
| Safari (iOS) | Per-site permission with system-level control | Standard codes 1/2/3 | iOS may report code 2 for timeout in some builds |
| Samsung Internet | Chrome-like prompt | Standard codes | Night mode/content blockers may affect behavior |
| Chrome (Desktop) | Address bar prompt | Standard codes 1/2/3 | Useful for sanity check |

## D. GPS Test Statuses

| Status | Meaning |
| :--- | :--- |
| **Not Tested** | Scenario not evaluated in this cycle. |
| **Pass** | All pass criteria satisfied with evidence. |
| **Pass With Notes** | Pass criteria met with documented non-blocking observations. |
| **Fail** | A pass criterion was not met due to a product defect. |
| **Blocked** | Environment, device, or access constraint prevented execution; reason recorded. |

## E. Scenario 1 — Permission Granted

### Preconditions

- Authenticated user session.
- Browser geolocation permission not previously set (fresh state) or previously granted.
- Device/browser can provide a location.

### Steps

1. Open the app on map screen.
2. When the browser permission prompt appears, grant location access.
3. Observe map centering behavior.
4. Observe user location marker appearance.
5. Observe accuracy circle if accuracy data is available.
6. Verify "My Location" button is visible (bottom-start position, only when no field is selected).
7. Pan the map away from the user location marker.
8. Tap "My Location" button.
9. Observe the map fly back to user position.
10. Open a field details panel and verify "My Location" button hides.
11. Close field details and verify "My Location" button reappears.
12. Open AddFieldModal and tap "Use current location".
13. Verify the location picker updates to user coordinates.
14. Reload the page and verify the map still centers on user location (permission persisted).
15. Check the browser console for errors.

### Expected Result

Map centers on the user's real position. Blue dot marker and accuracy circle are visible. "My Location" button works. AddFieldModal "Use current location" works. Fields load based on the visible map bounds. No controls are hidden by the permission prompt. Map remains fully usable after granting.

### Pass Criteria

- Map centers on user position (not default center) after permission grant.
- `.user-location-marker-icon` is visible on the map.
- Accuracy circle (`.leaflet-interactive` circle) appears if accuracy is finite.
- "My Location" button (`aria-label="My Location"`) is visible when no field is selected.
- Tapping "My Location" after panning flies the map back to user position.
- "My Location" button hides when `FieldDetailsPanel` is open.
- AddFieldModal "Use current location" updates the location picker.
- Fields load correctly in the visible bounds.
- No blocking console errors.
- Map controls (zoom, pan, field markers) remain usable.
- Browser permission prompt does not permanently hide critical controls.
- Behavior persists after page refresh.
- Section J cross-scenario criteria pass.

### Failure Criteria

- Map does not center on user position despite permission grant.
- User location marker does not appear.
- "My Location" button is missing or does not work.
- AddFieldModal "Use current location" fails silently or shows error.
- Permission prompt permanently hides map controls.
- Console errors block map or field usage.
- Map enters an infinite loading state.

## F. Scenario 2 — Permission Denied

### Preconditions

- Authenticated user session.
- Browser geolocation permission not previously set or previously denied.

### Steps

1. Open the app on map screen.
2. When the browser permission prompt appears, deny location access.
3. Observe map behavior — should remain on default center `[30.9872, 34.9314]`.
4. Verify no user location marker is shown.
5. Verify "My Location" button is not shown.
6. Verify no infinite loading spinner or stuck state.
7. Pan and zoom the map.
8. Open a field marker to view field details.
9. Close field details.
10. Open AddFieldModal and tap "Use current location".
11. Observe error message — should display location failed/unavailable message.
12. Verify the user can still manually set a location on the picker map.
13. Check the browser console for errors.

### Expected Result

The app handles denial gracefully. The map loads at the default center (roughly Beersheba area). No user marker, no "My Location" button. The user can browse the map, open fields, join games, and use all core flows. AddFieldModal shows a clear error when "Use current location" is tapped.

### Pass Criteria

- Map loads and is visible at default center.
- No `.user-location-marker-icon` is rendered.
- No "My Location" button is rendered.
- No loading spinner or stuck state.
- Map pan, zoom, and field marker interaction work.
- Field details panel opens and closes normally.
- AddFieldModal shows `locationFailed` or `locationUnavailable` error on "Use current location".
- Manual location selection in AddFieldModal still works.
- No blocking console errors.
- Section J cross-scenario criteria pass.

### Failure Criteria

- Map does not load or stays in loading state.
- App crashes or shows unrecoverable error.
- User cannot interact with the map after denial.
- "Use current location" fails silently without error message.
- Console error blocks map or field usage.
- User is trapped with no way to use the app.

## G. Scenario 3 — Permission Revoked

### Preconditions

- Authenticated user session.
- Browser geolocation permission was previously granted and the map loaded with user location.

### Steps

1. Open the app and confirm user location marker is visible (permission was granted).
2. Without closing the app, go to browser site settings and revoke location permission.
3. Reload the page.
4. Observe map behavior — should fall back to default center.
5. Verify user location marker is gone.
6. Verify "My Location" button is gone.
7. Verify the map is still usable (pan, zoom, open fields).
8. Open AddFieldModal and tap "Use current location".
9. Observe error message.
10. Re-grant permission from browser settings.
11. Reload the page.
12. Verify user location marker and "My Location" button return.
13. Check the browser console for errors.

### Expected Result

The app does not assume stale location access. After revocation, the map falls back to default behavior as if permission was never granted. After re-granting, normal location behavior resumes. No trapped or broken state at any point.

### Pass Criteria

- After revocation + reload, map falls back to default center.
- No user location marker after revocation.
- No "My Location" button after revocation.
- Map remains fully usable after revocation.
- AddFieldModal "Use current location" shows appropriate error.
- After re-granting + reload, user location marker and "My Location" button return.
- No stale position data displayed.
- No blocking console errors.
- Section J cross-scenario criteria pass.

### Failure Criteria

- App shows stale user location after revocation.
- Map crashes or enters infinite loading after revocation.
- User cannot interact with the map after revocation.
- Re-granting permission does not restore location behavior.
- Console error blocks functionality.

### Notes

Permission revocation requires manual browser/site settings interaction. This cannot be fully automated with Playwright. The Playwright geolocation API mock can simulate a "fresh denied" state but not a mid-session revocation.

## H. Scenario 4 — Location Unavailable

### Preconditions

- Authenticated user session.
- Browser geolocation permission is granted but the device cannot provide a location (GPS disabled, airplane mode, indoor with no network location, or API returns `POSITION_UNAVAILABLE`).

### Steps

1. Ensure geolocation will fail (disable device GPS, enable airplane mode, or mock `POSITION_UNAVAILABLE` error code 2).
2. Open the app on map screen.
3. Observe map behavior — should fall back to default center after timeout (up to 10 seconds based on `timeout: 10000` setting).
4. Verify no user location marker.
5. Verify no "My Location" button.
6. Verify no infinite loading spinner.
7. Pan and zoom the map.
8. Open field markers and field details.
9. Open AddFieldModal and tap "Use current location".
10. Observe error message.
11. Re-enable GPS / exit airplane mode.
12. Reload the page and verify location resumes.
13. Check the browser console for errors.

### Expected Result

The map loads at default center after the geolocation call fails. The app does not crash, does not stay in a permanent loading state, and does not display stale location data. All core flows remain usable.

### Pass Criteria

- Map loads at default center within a reasonable time (up to 10-second timeout + render time).
- No user location marker.
- No "My Location" button.
- No permanent loading spinner.
- Map controls and field interactions work.
- AddFieldModal "Use current location" shows appropriate error.
- After GPS is restored and page reloads, location behavior resumes.
- No blocking console errors.
- Section J cross-scenario criteria pass.

### Failure Criteria

- App crashes when location is unavailable.
- Map never loads or stays in infinite loading state.
- Stale or incorrect location is displayed.
- User cannot use the map or open fields.
- Timeout causes the app to freeze.
- Console error blocks map or field usage.

## I. Additional GPS Edge Cases

| # | Edge case | Expected behavior | Can simulate with Playwright? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| I.1 | Slow permission prompt response — user waits before granting/denying | Map should wait for response; no timeout on the permission prompt itself. App timeout is on the geolocation call (10s), not the prompt. | Partially — can delay mock callback | Real-device prompt timing varies |
| I.2 | Permission prompt ignored/dismissed | Browser-dependent: some browsers treat dismiss as deny, others re-prompt. App should not crash. | No — dismiss behavior is browser-native | Manual testing required |
| I.3 | GPS returns low accuracy (accuracy > 1000m) | Accuracy circle renders large. Map centers correctly. No functional impact. | Yes — mock with high accuracy value | Verify circle does not cover entire viewport |
| I.4 | GPS returns stale location (`maximumAge: 60000`) | App accepts cached position up to 60 seconds old. Marker reflects cached position. | Yes — mock with any coordinates | By design; not a defect |
| I.5 | Browser blocks geolocation on insecure origin (HTTP) | `navigator.geolocation` is `undefined` or `getCurrentPosition` fails. App falls back gracefully. | Yes — mock `navigator.geolocation` as undefined | HTTPS is required for production; HTTP fallback is defensive |
| I.6 | App loaded over HTTP vs HTTPS | On HTTP, geolocation API may be unavailable. App should treat this as geolocation unsupported. | Yes | Production should always be HTTPS |
| I.7 | User changes physical location while app is open | App called `getCurrentPosition` (one-shot), not `watchPosition`. Map does not track live movement. Tapping "My Location" re-flies to the initially captured position. | No — requires physical movement | Expected behavior per current code |
| I.8 | App resumes after backgrounding | Permission state persists. If permission was granted, marker should still be visible after foregrounding. No re-request on resume (no `watchPosition`). | No — requires real device | Manual testing recommended |
| I.9 | Page refresh after permission grant | Browser remembers permission. Geolocation should succeed immediately without re-prompting. | Partially — mock simulates instant success | Real-device behavior may differ |
| I.10 | Page refresh after permission deny | Some browsers remember denial; others re-prompt. App must handle both cases. | Partially | Manual testing for re-prompt behavior |
| I.11 | Incognito/private browsing | Some browsers reset geolocation permission in incognito. Permission prompt may re-appear each session. | No — requires real browser | Manual testing recommended |
| I.12 | Browser chrome overlays permission prompt | On mobile, the permission prompt may cover the top of the viewport. App controls should not be permanently hidden. | No — permission prompt is browser-native | Manual testing required |
| I.13 | `coords.accuracy` is non-finite (NaN, Infinity) | Code handles this: `Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null`. Accuracy circle should not render. | Yes — mock with NaN accuracy | Defensive code already in place |

## J. Map Behavior Criteria (Cross-Scenario)

A GPS scenario passes only if all of the following are true:

- Map canvas loads and is visible.
- User is not trapped in any state.
- Field markers are visible and tappable.
- Map controls (zoom +/−, pan) are reachable and functional.
- No unintended horizontal scrolling on the page.
- Permission state is reflected correctly (marker shown ↔ permission granted; no marker ↔ denied/unavailable).
- No blocking console errors occur.
- Fallback behavior is clear and usable when geolocation fails.
- Hebrew (RTL) layout does not overlap or misalign location-related text.
- Mobile keyboard and browser chrome do not permanently hide critical map controls.
- Floating action buttons (add field, notifications) remain accessible regardless of geolocation state.

## K. Failure Criteria (Cross-Scenario)

A GPS scenario fails if any of the following are true:

- App crashes or shows an unrecoverable error.
- Map never loads or enters an infinite loading state.
- User cannot interact with the map (pan, zoom, tap markers).
- Permission denial causes a dead-end with no usable map.
- Location unavailable causes an infinite spinner or frozen UI.
- Critical UI is hidden behind the permission prompt or browser chrome with no recovery.
- Fallback location does not work (map has no center or shows coordinates `[0, 0]`).
- User cannot recover from revoked permission (map stays broken after revocation).
- Console or runtime error blocks map or field usage.
- "My Location" button appears when `userLocation` is `null`.
- User location marker appears when geolocation was denied or failed.

## L. Manual Test Matrix

| Scenario | Device category | Browser/engine | Permission state | Network/location condition | Expected result | Status | Evidence | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Permission Granted | Android Small 360x640 | Chrome (Chromium) | Grant | GPS available | Map centers on user; marker visible; "My Location" works | Not Tested | | |
| Permission Granted | iPhone Large 390x844 | Safari (WebKit) | Grant | GPS available | Map centers on user; marker visible; "My Location" works | Not Tested | | |
| Permission Granted | Tablet/iPad 768x1024 | Safari (WebKit) | Grant | GPS available | Map centers on user; marker visible; "My Location" works | Not Tested | | |
| Permission Granted | Desktop 1280x800 | Chrome (Chromium) | Grant | Location available | Map centers on user; marker visible; "My Location" works | Not Tested | | Sanity check |
| Permission Denied | Android Small 360x640 | Chrome (Chromium) | Deny | N/A | Default center; no marker; map usable | Not Tested | | |
| Permission Denied | iPhone Large 390x844 | Safari (WebKit) | Deny | N/A | Default center; no marker; map usable | Not Tested | | |
| Permission Denied | Android Large 412x915 | Chrome (Chromium) | Deny | N/A | Default center; no marker; map usable | Not Tested | | |
| Permission Revoked | Android Small 360x640 | Chrome (Chromium) | Grant → Revoke → Reload | GPS available | Falls back to default; marker gone; re-grant restores | Not Tested | | Requires manual site settings |
| Permission Revoked | iPhone Large 390x844 | Safari (WebKit) | Grant → Revoke → Reload | GPS available | Falls back to default; marker gone; re-grant restores | Not Tested | | Requires manual site settings |
| Location Unavailable | Android Small 360x640 | Chrome (Chromium) | Grant | GPS disabled / airplane mode | Default center; no marker; map usable; recovers when GPS restored | Not Tested | | |
| Location Unavailable | iPhone Small 375x667 | Safari (WebKit) | Grant | GPS disabled / airplane mode | Default center; no marker; map usable | Not Tested | | |
| Timeout | Android Large 412x915 | Chrome (Chromium) | Grant | Weak/no GPS signal | Default center after ≤10s; no marker; map usable | Not Tested | | 10s timeout per app config |
| AddFieldModal — Use Current Location (granted) | Android Small 360x640 | Chrome (Chromium) | Grant | GPS available | Location picker updates to user coords | Not Tested | | |
| AddFieldModal — Use Current Location (denied) | iPhone Large 390x844 | Safari (WebKit) | Deny | N/A | Error message shown; manual selection still works | Not Tested | | |
| Samsung Internet | Android Large 412x915 | Samsung Internet / Chromium proxy | Grant/Deny | GPS available | Same behavior as Chrome; label proxy honestly | Not Tested | | |

## M. Automated Test Mapping

| GPS scenario | Can simulate with Playwright? | Existing test file | Existing coverage | Manual test still required? | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Permission Granted | Yes — mock `getCurrentPosition` success callback | `user-location.spec.js` | Map centers, marker visible, accuracy circle, "My Location" button, fly-back after pan | Yes — real permission prompt, real GPS | Playwright mocks bypass the real browser permission prompt |
| Permission Denied | Yes — mock error callback with code 1 | `user-location.spec.js` | Map usable, no marker, no "My Location" button | Yes — real denial prompt behavior | Mock simulates instant denial; real prompt has UI interaction |
| Permission Revoked | Partially — can simulate fresh denied state | None | None | Yes — requires manual browser site settings | Playwright cannot revoke a previously granted permission mid-session |
| Location Unavailable (code 2) | Yes — mock error callback with code 2 | None directly; `user-location.spec.js` tests code 3 | Timeout test covers similar fallback path | Yes — real GPS-off behavior | Code 2 and code 3 follow the same error callback in the app |
| Timeout (code 3) | Yes — mock error callback with code 3 | `user-location.spec.js` | Map usable, no marker, no "My Location" button | Yes — real slow-GPS behavior | Mock fires instantly; real timeout takes up to 10s |
| Geolocation Unsupported | Yes — mock `navigator.geolocation` as undefined | `user-location.spec.js` | Map usable, no marker, no "My Location" button | No | Simulates HTTP or old browser |
| Low Accuracy | Yes — mock with high accuracy value | None | None | Recommended — verify large circle rendering | Check accuracy circle does not cover entire map |
| Non-finite Accuracy | Yes — mock with NaN accuracy | None | None | No | Code already handles: `Number.isFinite` check |
| AddFieldModal — Use Current Location (success) | Partially — would need AddFieldModal-specific mock | None | None | Yes | Separate geolocation call in AddFieldModal |
| AddFieldModal — Use Current Location (failure) | Partially — would need AddFieldModal-specific mock | None | None | Yes | Verify error message rendering |

### Simulation Honesty Notes

- Playwright geolocation mocking replaces `navigator.geolocation` with a controlled object. This validates the app's JavaScript logic but does **not** validate real browser permission prompt UI, timing, or system-level GPS behavior.
- Real iOS Safari permission behavior requires real-device or manual testing. WebKit simulation provides engine-level coverage but not permission prompt coverage.
- Permission revocation requires manual browser settings interaction and cannot be automated with Playwright.
- The existing `user-location.spec.js` tests cover the core happy path and two failure paths. They are mock-backed and serve as regression guards, not as evidence that real GPS behavior works on real devices.

## N. Recommended Execution Order

| Order | Phase | Description |
| :--- | :--- | :--- |
| 1 | Desktop/Chromium simulation sanity check | Run `user-location.spec.js` on Chromium and WebKit. Verify all 4 existing tests pass. |
| 2 | Android Chrome — permission granted | Real device or emulator. Grant permission. Verify marker, centering, "My Location" button. |
| 3 | Android Chrome — permission denied | Deny permission. Verify fallback, no marker, map usable. |
| 4 | Android Chrome — permission revoked | Grant → revoke via site settings → reload. Verify fallback. Re-grant → reload. Verify recovery. |
| 5 | Android Chrome — location unavailable | Enable airplane mode or disable GPS. Verify fallback after timeout. |
| 6 | iPhone Safari/WebKit — permission granted | Real device or simulator. Grant permission. Verify marker, centering, "My Location" button. |
| 7 | iPhone Safari/WebKit — permission denied | Deny permission. Verify fallback, no marker, map usable. |
| 8 | iPhone Safari/WebKit — revoked/unavailable | Revoke via Settings → Safari → Location. Verify fallback. Test location unavailable. |
| 9 | Tablet/iPad — map usability | Permission granted and denied. Verify layout, controls, marker positioning on tablet viewport. |
| 10 | AddFieldModal — "Use current location" | Test with permission granted and denied. Verify success and error message. |
| 11 | Edge cases | Incognito, prompt dismissed, slow GPS, low accuracy, page refresh after grant/deny. |
| 12 | Samsung Internet | Real device or Chromium proxy. Label honestly. |
| 13 | Final evidence review | Compile results, verify all scenarios have explicit status, review console logs. |

## O. Evidence Requirements

Every GPS test execution must record:

| Evidence | Required |
| :--- | :--- |
| Date | Yes |
| Tester | Yes |
| Branch/commit | Yes |
| Device (model or simulation viewport) | Yes |
| Browser name and version (if available) | Yes |
| Permission state tested | Yes |
| Screenshot/video of permission prompt | Where possible (browser-native prompt may not be capturable) |
| Screenshot/video of map result | Yes |
| Screenshot of user location marker (or its absence) | Yes |
| Console error log | Required for any Fail; recommended for all |
| Notes for Pass With Notes | Yes — describe observation and confirm non-blocking |
| Linked issue for any Fail | Yes |

Avoid credentials or personal data in evidence. If real coordinates are visible, note that they represent the tester's location and are not production user data.

## P. Release Gate Rules

| Rule | Severity |
| :--- | :--- |
| Permission granted must produce correct map centering and user marker on at least one primary mobile browser (Chrome or Safari) | P0 — blocks release |
| Permission denied must not block map usability | P0 — blocks release |
| Location unavailable must not block map usability | P0 — blocks release |
| Permission revoked must not cause a trapped or broken state | P1 — blocks release |
| "My Location" button must work when geolocation is available | P1 — blocks release |
| AddFieldModal "Use current location" must show error on failure (not fail silently) | P2 — requires approval to ship without |
| Low accuracy rendering issue (circle too large, covers controls) | P2 — requires approval |
| Cosmetic issues (marker animation, circle opacity, prompt timing) | P3 — may ship with documented notes |
| Samsung Internet direct testing not performed | P3 — Chromium proxy acceptable with note |
| Real-device testing not performed for a specific device category | P3 — acceptable with simulation evidence and note |

## Q. Re-run Triggers

GPS testing must be repeated after changes to:

| Trigger | Reason |
| :--- | :--- |
| `MapPage.jsx` — map initialization, `useEffect` geolocation call, `DEFAULT_CENTER`, `USER_LOCATION_ZOOM` | Core geolocation logic |
| `MapPage.jsx` — `UserLocationFlyTo`, `RecenterMap`, `createUserLocationIcon` | Location marker and fly-to behavior |
| `MapPage.jsx` — "My Location" button rendering or click handler | Location button behavior |
| `AddFieldModal.jsx` — `useCurrentLocation` function | AddFieldModal geolocation |
| `App.css` — `.user-location-marker`, `.user-location-marker-icon` | Marker styling |
| Geolocation API timeout/options changes | Timeout or accuracy behavior |
| Map library (Leaflet / react-leaflet) upgrade | Map rendering engine |
| Fallback location coordinates change | Default center behavior |
| Field loading by map bounds logic (`FieldLoader`) | Fields visible after location change |
| Map control positioning or floating button layout | Control reachability |
| Browser compatibility fixes affecting geolocation | Cross-browser behavior |
| Mobile layout changes affecting map viewport | Map canvas size |
| HTTPS/deployment/CORS changes | Geolocation requires secure origin |
| Onboarding or language selection flow changes | Flow before map load |

## R. Open Questions / Assumptions

| # | Question | Current assumption | Needs confirmation? |
| :--- | :--- | :--- | :--- |
| R.1 | What fallback location is expected? | `DEFAULT_CENTER = [30.9872, 34.9314]` (approximately Beersheba, Israel). This is a hardcoded constant in `MapPage.jsx`. | No — confirmed in code. May need product decision if the default should change. |
| R.2 | Is user location marker officially supported? | Yes — `createUserLocationIcon()` renders a blue dot with accuracy circle. The "My Location" fly-to button is exposed. | No — confirmed in code. |
| R.3 | Is GPS required for creating/joining games? | No — GPS is used for map centering only. Game creation requires selecting a field (which is on the map). Game joining is through field details. Neither requires the user's GPS position. | No — confirmed in code. The `AddFieldModal` has an optional "Use current location" for the field location picker, but manual pin placement is always available. |
| R.4 | Is real-device GPS validation required before public release? | Recommended but not strictly required. Playwright simulation covers the JavaScript API behavior. Real-device testing adds coverage for browser permission prompts, real GPS timing, and mobile browser chrome interaction. | Yes — product owner should decide. |
| R.5 | Must Samsung Internet be tested directly or via Chromium proxy? | Chromium proxy is acceptable per ISSUE-164 checklist. Direct Samsung Internet testing is recommended for Samsung-specific features (night mode, content blockers) but these do not directly affect geolocation API behavior. | No — decided in ISSUE-164. Label proxy evidence honestly. |
| R.6 | Does the app use `watchPosition` for live tracking? | No — the app uses `getCurrentPosition` (one-shot). The map does not track live user movement. The "My Location" button re-flies to the initially captured position, not a live position. | No — confirmed in code. |
| R.7 | What happens if geolocation succeeds but returns coordinates far from any fields? | Map centers on user location. `FieldLoader` loads fields within the visible map bounds. If no fields are in the area, the map shows no markers. The user can pan/zoom to find fields. | No — by design. Not a GPS test failure. |
