# ISSUE-137: Mobile Safe Area Support

## Summary

This issue implements CSS-level safe-area adjustments to protect yesh_mishak's responsive layout from clipping and overlaps on modern bezel-less devices (specifically notches, Dynamic Island, and Home Indicators on Apple iOS/iPhone viewports). 

The following UI areas were protected:
1. **Map Overlays & Floating Buttons**: Bell (inbox), settings (preferences), geolocation (my-location), and Add Field floating actions.
2. **Native Map Controls**: Leaflet native controls (zoom, attribution, etc.).
3. **Map Notifications & Messages**: Success/error/loading toast alerts.
4. **Bottom Sheet Panel**: The Field Details panel.
5. **Modals & Dialogs**: Backdrops and dynamic viewport boundaries for the notifications, add-field, and field-report modals.
6. **Admin Panel**: The main admin shell container on mobile devices.
7. **Offline Banner**: Sticky offline notifications at the top viewport edge.

The implementation applies rules from `docs/mobile-design-guide.md` created in ISSUE-136, including setting safe area CSS variables, using viewport-aware dynamic units (`100dvh`), and spacing floating buttons dynamically.

## Files Changed

* `frontend/src/App.css` (Modified: defined Safe Area CSS variables, updated `.floating-button.*`, `.map-error`, `.map-loading`, `.map-success`, `.modal-backdrop`, `.notifications-modal`, `.add-field-modal`, `.field-report-modal`, `.field-details-panel`, and `.admin-page` rules).
* `docs/mobile-safe-area-support.md` (New)

## Safe Area Rules Implemented

* **Top Safe Area**: Shifted `.offline-banner`, `.map-success`/`.map-error`/`.map-loading` alerts, `.floating-button.top`, and `.floating-button.preferences` down by `var(--safe-area-top)` to clear the status bar and notch.
* **Bottom Safe Area**: Shifted `.floating-button.my-location` and `.floating-button.bottom` up by `var(--safe-area-bottom)` to clear OS gesture bars.
* **Left/Right Safe Area**: Shifted side floating controls using logical properties (`var(--safe-area-inline-start)` and `var(--safe-area-inline-end)`) to dynamically adapt left and right bounds across English LTR and Hebrew RTL languages.
* **Floating Controls**: Overrode Leaflet-native top/bottom/left/right container bounds with safe-area variables using `!important` to keep standard Leaflet controls visible.
* **Bottom Panels**: Expanded mobile `.field-details-panel` bottom padding to `calc(20px + var(--safe-area-bottom))` so that bottom-placed actions (Open Game, Navigate, Report) do not collide with home indicators.
* **Modals**:
  * Padded `.modal-backdrop` using safe-areas on all sides.
  * Replaced `100vh` modal height limits in `.notifications-modal`, `.add-field-modal`, and `.field-report-modal` with dynamic `100dvh` minus safe-area top and bottom offsets (`calc(100dvh - 40px - var(--safe-area-top) - var(--safe-area-bottom))`), ensuring modals always scroll before clipping.

## iPhone Validation Matrix

| Device Profile   | Viewport | Areas Checked                                  | Result | Notes |
| ---------------- | -------- | ---------------------------------------------- | ------ | ----- |
| iPhone SE        | 375x667  | Map controls, floating buttons, panels, modals | **PASS** | UI fits cleanly; short height causes no clipping. |
| iPhone 12/13/14  | 390x844  | Map controls, floating buttons, panels, modals | **PASS** | Clear notch bounds; bottom sheets and modals clear home indicator. |
| iPhone 14/15 Pro | 393x852  | Map controls, floating buttons, panels, modals | **PASS** | Top controls clear the Dynamic Island. |
| iPhone Pro Max   | 430x932  | Map controls, floating buttons, panels, modals | **PASS** | Large screen behaves as expected with safe-area spacing. |

*Validation Method*: Manual emulation verification via Chrome/Chromium devtools device emulation profiles with touch enabled and simulated safe area environment variables.

## Known Remaining Issues

The following mobile audit findings (ISSUE-135) are intentionally out of scope for this safe-area support ticket and remain documented for future remediation:

* **Keyboard clipping**: The full height/scroll fix for Create Game modal (`CGMOB-001`) remains open.
* **Touch target sizes**: Buttons under 44px hit height standard (`GDMOB-002`, `NTMOB-002`, `NTMOB-003`, `ADMOB-004`) remain open.
* **Table responsiveness**: Visual horizontal scroll shadows (`ADMOB-002`) remain open.
* **Long Hebrew text wrapping**: Responsive headers for notifications (`NTMOB-001`) remain open.
