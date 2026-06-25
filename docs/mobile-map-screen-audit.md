# Mobile Map Screen Audit

## 1. Purpose

This audit evaluates the central Map screen across the required mobile device classes from `docs/mobile-audit-plan.md`.

The Map screen is the core authenticated app surface. This audit documents mobile compatibility issues only. It does not implement fixes or authorize mobile production release.

## 2. Scope

- Screen audited: Map
- Device classes audited:
  - Small Android: 360x640
  - Large Android: 412x915
  - Small iPhone: 375x667
  - Large iPhone: 428x926
- Validation areas audited:
  - Map Controls
  - Zoom Controls
  - Marker Selection
  - Field Selection
  - Bottom Sheets
  - Location Button
- Out of scope:
  - Fixing issues
  - Implementing UI changes
  - Backend/API changes
  - Database/schema/config changes
  - Production mobile release

## 3. Gate Status

- ISSUE-126 mobile audit plan exists and was used as the audit standard.
- ISSUE-127 Login audit exists and was reviewed for audit format consistency.
- ISSUE-128 Registration audit exists and was reviewed for audit format consistency.
- EPIC 02 remains **NOT COMPLETE**.
- AUTH-001 remains the production blocker.
- This audit does **not** unblock mobile production work.
- Mobile production release remains **NO** until AUTH-001 is resolved and production readiness is re-reviewed.

## 4. Methodology

### Files Reviewed

- `docs/mobile-audit-plan.md`
- `docs/mobile-login-screen-audit.md`
- `docs/mobile-registration-screen-audit.md`
- `docs/product-decisions.md`
- `frontend/src/pages/MapPage.jsx`
- `frontend/src/components/FieldDetailsPanel.jsx`
- `frontend/src/components/GamePanel.jsx`
- `frontend/src/components/AddFieldModal.jsx`
- `frontend/src/components/NotificationInboxModal.jsx`
- `frontend/src/components/NotificationsModal.jsx`
- `frontend/src/api/fields.js`
- `frontend/src/App.css`
- `frontend/src/index.css`
- `frontend/package.json`
- `frontend/playwright.config.js`
- `frontend/tests/field-navigation.spec.js`

### Commands Run

- `git branch --show-current`
- `git status --short`
- `git pull origin main`
- `git checkout -b issue-129-map-screen-mobile-audit`
- `Test-Path docs\mobile-audit-plan.md`
- `Test-Path docs\mobile-login-screen-audit.md; Test-Path docs\mobile-registration-screen-audit.md`
- `rg -n "ISSUE-126: Create Complete Mobile Audit Plan|ISSUE-127: Perform Login Screen Mobile Audit|ISSUE-128: Perform Registration Screen Mobile Audit|AUTH-001|EPIC 02" ...`
- `rg --files frontend | rg "(Map|Field|GamePanel|Notification|Location|map|field|marker|\.css$|package\.json|playwright|spec|test|i18n|locales)"`
- `Get-Content frontend\src\pages\MapPage.jsx`
- `Get-Content frontend\src\components\FieldDetailsPanel.jsx`
- `Get-Content frontend\src\components\GamePanel.jsx`
- `Get-Content frontend\src\api\fields.js`
- `Get-Content frontend\src\App.css`
- `Get-Content frontend\tests\field-navigation.spec.js`
- Browser-emulation audit using Playwright's Chromium package from `frontend/node_modules/playwright`

### Execution Notes

- The app was run locally with Vite.
- Browser/mobile emulation was used with Chromium, mobile viewport sizes, touch enabled, and Hebrew selected in local storage.
- An authenticated user session was seeded in local storage using a local unsigned test JWT.
- Fields, notifications, unread count, and OpenStreetMap tile requests were mocked locally. No production backend or database was used.
- Geolocation success and geolocation denial were simulated.

### Limitations

- Real mobile device testing was not performed.
- Real map tiles were blocked in the audit harness to avoid external dependency noise, so tile visual fidelity was not validated.
- Browser emulation cannot fully validate native permission prompts, pinch-zoom feel, or iPhone safe-area behavior.
- Marker density was tested with a small mocked field set, not a production-scale dense field cluster.

## 5. Map Flow Description

A user reaches the Map screen after authentication and onboarding completion. The Map screen is not available unauthenticated; unauthenticated users see the Login screen first.

Controls present on the Map screen:

- Notification inbox floating button.
- Notification preferences floating button.
- Location floating button, shown only after geolocation succeeds.
- Add field floating button.
- Leaflet zoom in / zoom out controls.
- Field markers rendered with custom stadium icons.
- Field details bottom sheet/panel after selecting a field.
- Add field modal after tapping the add button.

Fields are loaded through `getFields()` and rendered as Leaflet markers. Selecting a marker sets `selectedField` and opens `FieldDetailsPanel`.

Location handling:

- On mount, `navigator.geolocation.getCurrentPosition()` is called if available.
- Success sets user location, recenters the map, shows the user marker, and displays the location button.
- Failure sets `userLocation` to `null`; no user-facing map error is shown and the location button is hidden.

## 6. Device Coverage

| Device Class | Viewport | Result | Notes |
|---|---:|---|---|
| Small Android | 360x640 | FAIL | Map renders, controls render, markers are tappable, but field-details bottom sheet close button is above the viewport and normal tap fails. |
| Large Android | 412x915 | PASS WITH FINDINGS | Core map flow works; zoom controls are small and dense markers can overlap. |
| Small iPhone | 375x667 | FAIL | Map renders, controls render, markers are tappable, but field-details bottom sheet close button is above the viewport and normal tap fails. |
| Large iPhone | 428x926 | PASS WITH FINDINGS | Core map flow works; zoom controls are small and dense markers can overlap. |

## 7. Validation Results

### Map Controls

**What was checked**

- Map canvas rendering on all device classes.
- Floating notification, preferences, add-field, and location controls.
- Control overlap and viewport fit.
- Loading/error state positioning.
- RTL behavior.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Map canvas matched each viewport:
  - 360x640: map `360x640`
  - 412x915: map `412x915`
  - 375x667: map `375x667`
  - 428x926: map `428x926`
- Floating buttons measured `52x52`, meeting touch target expectations.
- No page-level horizontal overflow was detected on any device.
- In Hebrew/RTL, top controls appeared on the right side and the add button centered at the bottom.
- On small devices, the add and location buttons sit at the bottom (`bottom=616` on 360x640, `bottom=643` on 375x667), close to mobile browser/safe-area regions.

**Findings**

- Bottom floating controls may need explicit safe-area padding on iPhone and mobile browsers.

### Zoom Controls

**What was checked**

- Leaflet zoom buttons visibility and tap behavior.
- Map usability after zoom in/out.
- Whether zoom controls create layout overflow or block markers.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Zoom controls were visible and clickable in browser emulation.
- After zoom in/out, marker count remained `2` and horizontal overflow remained absent.
- Leaflet zoom controls measured `30x30` on all audited devices.

**Findings**

- Visible zoom controls are below the 44x44 mobile touch target target.
- Pinch-zoom was not validated on a real device.

### Marker Selection

**What was checked**

- Field marker visibility.
- Marker tap target size.
- Marker selection behavior.
- Selected marker state clarity.
- Dense marker behavior.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Field markers measured `54x54`, meeting touch target expectations.
- Markers were visible on all four audited viewports.
- Selecting a marker opened field details.
- Active marker uses animated green status styling; inactive marker uses red status styling.
- The two mocked nearby markers visibly overlapped:
  - Small Android active marker `x=150..204`, inactive marker `x=162..216`
  - Small iPhone active marker `x=158..212`, inactive marker `x=170..224`

**Findings**

- Dense/nearby markers overlap and can be hard to select precisely on mobile.
- Selected marker state is primarily represented by opening the field details panel; the marker itself does not get a persistent selected visual state.

### Field Selection

**What was checked**

- Selecting a field opens the field details experience.
- Field information readability.
- Long field names.
- Ability to close/back out.
- Whether selected field traps the user.

**Result**

FAIL on small mobile viewports; PASS WITH FINDINGS on large mobile viewports.

**Evidence**

- Selecting a marker opened `.field-details-panel`.
- Long Hebrew field name wrapped without horizontal overflow.
- Large Android and Large iPhone allowed normal close button tapping.
- Small Android field-details panel measured `top=-150`, `bottom=640`; close button measured `top=-138`, `bottom=-109`.
- Small iPhone field-details panel measured `top=-93`, `bottom=667`; close button measured `top=-81`, `bottom=-52`.
- Normal Playwright tap failed on the close button for Small Android and Small iPhone because the element was outside the viewport.

**Findings**

- The field-details panel can exceed short viewport height, placing the close button above the visible viewport and trapping the user.

### Bottom Sheets

**What was checked**

- Field details bottom sheet/panel opening.
- Add field modal opening.
- Sheet/modal viewport fit.
- Scroll behavior.
- Close behavior.
- Background interaction behavior.

**Result**

FAIL for field-details bottom sheet on short viewports; PASS WITH FINDINGS for add-field modal.

**Evidence**

- Field details panel:
  - Small Android: panel `top=-150`, close button above viewport.
  - Small iPhone: panel `top=-93`, close button above viewport.
  - Large Android: panel `top=155`, close visible.
  - Large iPhone: panel `top=166`, close visible.
- Add field modal:
  - Small Android: modal `top=20`, `bottom=620`, `clientHeight=600`, `scrollHeight=943`.
  - Small iPhone: modal `top=20`, `bottom=647`, `clientHeight=627`, `scrollHeight=943`.
  - Large devices: modal max height `760`, scrollable.

**Findings**

- Field details panel is not constrained to the viewport and has no internal scroll when its content is taller than short screens.
- Add field modal is scrollable and usable, but relies on `100vh` rather than `100dvh` or explicit safe-area padding.

### Location Button

**What was checked**

- Location button visibility when geolocation succeeds.
- Button tap behavior.
- User location marker visibility.
- Permission denied fallback behavior.
- Whether denial traps the user.

**Result**

PASS WITH FINDINGS.

**Evidence**

- With geolocation success, location button rendered as `52x52` and user marker rendered.
- Tapping location button completed without layout overflow and user marker remained present.
- With simulated geolocation denial on Small Android:
  - `locationButtonExists=false`
  - `userMarkerExists=false`
  - `mapErrorText=""`
  - field marker still rendered (`markerCount=1`)

**Findings**

- Permission denied/unavailable location has no user-facing message.
- Once denied, there is no visible in-map recovery action or explanation; the location button is hidden.

## 8. Findings

| Finding ID | Severity | Area | Device(s) | Description | Evidence | Recommendation | Blocking |
|---|---|---|---|---|---|---|---|
| ML-MAP-001 | P1 | Field Selection / Bottom Sheets | Small Android, Small iPhone | Field details panel can be taller than the viewport and positions the close button above the visible screen, trapping users on short mobile screens. | Small Android panel `top=-150`, close `top=-138..-109`; Small iPhone panel `top=-93`, close `top=-81..-52`; normal tap failed because close button was outside viewport. | Constrain field details to viewport height, add internal scrolling, and keep the close/action header sticky and visible. | YES |
| ML-MAP-002 | P2 | Zoom Controls | All device classes | Leaflet zoom controls are visible but only `30x30`, below the 44x44 mobile touch target target. | Zoom in/out controls measured `30x30` on all viewports. | Increase mobile zoom control touch area or provide larger custom mobile controls. | NO |
| ML-MAP-003 | P2 | Location Button | All device classes | Geolocation denied/unavailable state hides the location button and shows no user-facing message or recovery path. | Simulated denial produced no `.map-error`, no location button, no user marker, while map and fields still rendered. | Show a clear non-blocking message and provide a retry/help action for denied or unavailable location. | NO |
| ML-MAP-004 | P2 | Marker Selection | All device classes | Nearby markers overlap, making precise selection difficult on mobile. | Mocked nearby markers overlapped by roughly 42px horizontally on small viewports. | Add a mobile strategy for dense marker areas, such as clustering, spreading, or selected-marker disambiguation in a future issue. | NO |
| ML-MAP-005 | P3 | Marker Selection / Field Selection | All device classes | Selected marker state is not visibly persistent on the marker itself; selection is mainly indicated by the details panel. | After marker selection, panel opens, but marker icon does not receive a distinct selected style. | Add a selected-marker visual state if it can be done without cluttering the map. | NO |
| ML-MAP-006 | P3 | Map Controls / Bottom Sheets | Small Android, Small iPhone, Large iPhone | Bottom controls and modals rely on `100vh`/fixed offsets and do not show explicit safe-area padding. | Bottom buttons ended at `616/640`, `643/667`, and `902/926`; add-field modal starts/ends at fixed `20px` offsets. | Add safe-area-aware spacing with `env(safe-area-inset-*)` and prefer dynamic viewport units where appropriate. | NO |

## 9. Blockers

A Map screen mobile blocker exists.

Blocking finding:

- `ML-MAP-001`: On Small Android and Small iPhone, the field-details bottom sheet can trap the user because the close button is above the viewport and normal tapping fails.

Project-level blocker still outside this Map UI audit:

- AUTH-001 remains a P0 production blocker.

## 10. Recommendations

- Fix the field details panel before mobile production: constrain height, add internal scroll, and keep close/action header visible.
- Increase Leaflet zoom controls or replace with mobile-sized custom controls.
- Add geolocation denied/unavailable messaging and retry guidance.
- Add a strategy for dense marker selection on mobile.
- Add selected-marker styling if it improves clarity without adding clutter.
- Add safe-area-aware spacing for bottom floating controls and modal/bottom-sheet layouts.
- Re-test Map screen on real Android and iPhone devices after fixes, including native pinch zoom and permission prompts.

## 11. Final Audit Decision

Final audit decision: **FAIL**.

- Map screen acceptable for mobile after this audit: **NO, because a bottom-sheet trap exists on short mobile viewports**.
- Mobile production allowed: **NO**.
- Reason mobile production remains blocked: AUTH-001 remains open, EPIC 02 remains NOT COMPLETE, and this audit does not authorize mobile production release.
