# Mobile Field Details Screen Audit

## 1. Purpose

This audit evaluates the Field Details screen/bottom sheet across the required mobile device classes from `docs/mobile-audit-plan.md`.

The Field Details screen provides users with essential information about sports fields, active and upcoming games, and access to core gameplay and reporting actions. This audit documents mobile compatibility issues only. It does not implement fixes or authorize mobile production release.

## 2. Scope

- **Screen audited**: Field Details (implemented as the `.field-details-panel` bottom sheet/side panel which opens upon marker selection on the Map screen).
- **Device classes audited**:
  - Small Android: 360x640 / 360x740
  - Large Android: 412x915 / 430x932
  - Small iPhone: 375x667 / 390x844
  - Large iPhone: 428x926 / 430x932
- **Validation areas audited**:
  - Scrolling
  - Action Buttons
  - Navigation Buttons
  - Report Button
- **Out of scope**:
  - Fixing issues
  - Implementing UI changes
  - Backend/API changes
  - Database/schema/config changes
  - Production mobile release approval

## 3. Gate Status

- `docs/mobile-audit-plan.md` exists and was used as the audit standard: **YES**
- `docs/mobile-map-screen-audit.md` exists and related findings were reviewed: **YES**
- EPIC 02 status remains: **NOT COMPLETE**
- AUTH-001 remains the production blocker: **YES**
- This audit does **not** unblock mobile production work.
- Mobile production release remains **NO** until AUTH-001 is resolved and production readiness is re-reviewed.

## 4. Methodology

### Files Reviewed

- `docs/mobile-audit-plan.md` (Audit Standard)
- `docs/mobile-map-screen-audit.md` (Map Screen Audit)
- `docs/product-decisions.md` (Product Decisions)
- `frontend/src/components/FieldDetailsPanel.jsx` (Component Logic)
- `frontend/src/components/GamePanel.jsx` (Inline Game Controls)
- `frontend/src/components/FieldReportModal.jsx` (Reporting Flow)
- `frontend/src/components/OpenGameModal.jsx` (Game Creation Dialog)
- `frontend/src/App.css` (Visual Styling)
- `frontend/package.json` (Scripts and Dependencies)
- `frontend/playwright.config.js` (E2E Test Configuration)
- `frontend/tests/field-navigation.spec.js` (Existing E2E Navigation Tests)

### Commands Run

- `git branch --show-current`
- `git status --short`
- `git pull origin main`
- `git checkout -b issue-130-field-details-mobile-audit`
- `npm run lint` (Identified existing unrelated lint issues in `MyGamesPage.jsx` and `baseline.spec.js`)
- `npm run build` (Verified that the production bundle successfully compiles)
- `npm run test:e2e` (Ran the E2E test suite to verify baseline functionality)

### Execution Notes

- The app was run locally with Vite.
- Browser/mobile emulation was used with Chromium, mobile viewport sizes, touch enabled, and Hebrew selected in local storage.
- An authenticated user session was seeded in local storage using a local unsigned test JWT.
- Fields, notifications, and game schedules were mocked. No production backend or database was used.
- Toggling the participants list, opening Waze/Google Maps, and submitting simulated field reports were validated.

### Limitations

- Real physical mobile device testing was not performed.
- Geolocation permission popups were simulated in Chromium browser emulation.
- Touch feel, physical keyboards, and Apple/Safari notch safe-area behaviors were evaluated using devtools and emulation, which might have slight visual gaps compared to physical device testing.

## 5. Field Details Flow Description

A user reaches the Field Details screen by tapping a field marker on the Map screen.
The Field Details screen is not a standalone page route; it is rendered as a modal panel/bottom sheet (`.field-details-panel`) that slides over the Map screen.

### Information Displayed

1. **Header**: Field name (or "Unnamed field") and a "Pending Approval" VAR badge if relevant.
2. **Close Button**: An `x` button to dismiss the panel.
3. **Field Details List**: Surface type, Presence of nets, Presence of water cooler, Opening hours, Notes, and Approval Status.
4. **Active Game Summary**: Player counts, times, organizer actions (Join, Leave, Extend, Close), and participants list.
5. **Upcoming Games Section**: List of scheduled games with their respective dates, times, and participant actions.

### Available Actions

- **Open Game**: Launches `OpenGameModal` to schedule or start a game at this field (only shown if no active game is present).
- **Navigate to Field**: Opens a navigation dialog with Waze and Google Maps external options.
- **Report Field**: Launches `FieldReportModal` to report issues (e.g., closed field, wrong location).
- **Game Actions**: Users can join, leave, extend (if organizer), or close (if organizer) active and upcoming games.

## 6. Device Coverage

| Device Class | Viewport | Result | Notes |
| :--- | :---: | :--- | :--- |
| Small Android | 360x640 / 360x740 | **FAIL** | Content length pushes the close button above the viewport (`top < 0`), trapping users. |
| Large Android | 412x915 / 430x932 | **PASS WITH FINDINGS** | Core details flow works. Scrolling and safe-area adjustments are needed. |
| Small iPhone | 375x667 / 390x844 | **FAIL** | Content length pushes the close button above the viewport (`top < 0`), trapping users. |
| Large iPhone | 428x926 / 430x932 | **PASS WITH FINDINGS** | Core details flow works. Scrolling and safe-area adjustments are needed. |

## 7. Validation Results

### Scrolling

**What was checked**
- Viewport fit and layout bounds of `.field-details-panel` under mobile viewports.
- Behaviour when the field details list, active games, and upcoming games are populated.
- Scroll conflicts between the panel container and the Map background.

**Result**
FAIL on small viewports (Small Android and Small iPhone); PASS WITH FINDINGS on large viewports.

**Evidence**
- On screen widths <= 640px, the panel is positioned at the bottom of the viewport (`bottom: 0; width: 100%`) as a bottom sheet.
- Because `.field-details-panel` does not have a `max-height` or `overflow-y` constraint, its height dynamically expands to fit all details.
- Calculated content height with basic field details and action buttons is ~520px. When an active game is present (~150px) or multiple upcoming games exist, the panel height exceeds the viewport height of short devices (640px and 667px).
- This causes the top portion of the panel to project above the screen boundary (`top < 0`), making the header and close button unreachable.
- No scroll container is present, and dragging the sheet drags the map underneath.

**Findings**
- *ML-FIELD-DETAILS-001* (Critical): The panel has no height limit or internal scroll, trapping users on short mobile viewports.
- *ML-FIELD-DETAILS-002*: Lack of event propagation controls causes scroll/drag conflicts with the underlying Leaflet map.

### Action Buttons

**What was checked**
- Usability and reachability of primary buttons: "Open Game", "Navigate to Field", and "Report Field".
- Touch target sizes and alignment.
- Hebrew/RTL copy layout.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Primary buttons are styled using `.primary-panel-button`, which sets `width: 100%` and `padding: 12px 14px`. This yields a touch height of ~46px, which exceeds the 44px mobile minimum.
- Labels are fully translated and correctly aligned for RTL (e.g. "פתיחת משחק", "נווט למגרש", "דווח").
- Join / Leave / Extend / Close Game actions are aligned inside the inline `GamePanel` action grid.
- Toggling the participants list inside the inline `GamePanel` adds dynamic list height, which further pushes buttons downward and makes them harder to reach or hides them on short screens.

**Findings**
- *ML-FIELD-DETAILS-003*: Dynamic expansion of the participants list increases panel height and exacerbates the viewport trap.
- *ML-FIELD-DETAILS-004*: Bottom action buttons lack safe-area padding for notch/gesture-bar devices.

### Navigation Buttons

**What was checked**
- Close button `x` size, alignment, and responsiveness.
- Exit behavior on each device class.

**Result**
FAIL on small mobile viewports; PASS on large viewports.

**Evidence**
- The close button is styled as `.panel-close-button` (`position: absolute; top: 12px; inset-inline-end: 12px; font-size: 20px`).
- On Small Android and Small iPhone, when content height exceeds the viewport, the close button is pushed above the screen viewport (`top = -138` on Small Android, `top = -81` on Small iPhone). Playwright click actions fail because the target is outside the viewport bounds, trapping the user in the Field Details screen.

**Findings**
- *ML-FIELD-DETAILS-001* (Critical): Close button is pushed off-screen on short viewports, trapping the user. Directly relates to `ML-MAP-001`.

### Report Button

**What was checked**
- Report button styling, visibility, and click flow.
- Usability of `FieldReportModal`.

**Result**
PASS WITH FINDINGS.

**Evidence**
- The report button ("דווח") successfully launches the `FieldReportModal` backdrop and dialog.
- The `FieldReportModal` itself is scroll-safe and responsive, constrained by `max-height: min(720px, calc(100vh - 40px))` and `overflow: auto`.
- However, form validation on the report modal utilizes browser-native validation tooltips, which appear in English during Hebrew RTL flows.
- Error messages and success messages render globally at the bottom of the modal instead of inline.

**Findings**
- *ML-FIELD-DETAILS-005*: Non-localized browser-native required tooltips and global error messages on `FieldReportModal` degrade user experience.

---

## 8. Relationship to ISSUE-129

This audit confirms a direct overlap with Map Screen finding **ML-MAP-001**:
- The Field Details screen is implemented as `.field-details-panel` within the Map view.
- The viewport trap identified in `ML-MAP-001` (where the close button goes off-screen on Small Android and Small iPhone) is caused by the CSS layout of `FieldDetailsPanel.jsx`.
- When auditing Field Details as a feature, the lack of container boundaries (`max-height`) and scroll management in `.field-details-panel` is the root cause of this critical issue.

---

## 9. Findings

| Finding ID | Severity | Area | Device(s) | Description | Evidence | Recommendation | Blocking |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **ML-FIELD-DETAILS-001** | P1 | Navigation / Scrolling | Small Android, Small iPhone | Field details panel has no height limit or internal scroll. Taller content pushes the close button above the viewport (`top < 0`), trapping users. | Close button top is negative (-138px on Small Android, -81px on Small iPhone) and cannot be tapped. | Constrain panel height (`max-height: calc(100vh - 40px)`) and add `overflow-y: auto`. Keep header sticky. | **YES** |
| **ML-FIELD-DETAILS-002** | P2 | Scrolling | All | No dedicated scroll control inside the panel. Dragging/scrolling the panel causes conflicts with the Leaflet map underneath. | `.field-details-panel` in `App.css` lacks `overflow` rules; dragging the sheet scrolls the map. | Add scroll event propagation blocks (`L.DomEvent.disableScrollPropagation`) to the panel. | NO |
| **ML-FIELD-DETAILS-003** | P2 | Scrolling / Actions | All | Toggling the participants list inline in the `GamePanel` dynamically increases height, exacerbating overflow. | Opening the participants dropdown expands the list inline, adding to the parent panel height. | Limit participants list height or move the participants list to a separate dialog. | NO |
| **ML-FIELD-DETAILS-004** | P3 | Action Buttons | Small Android, Small iPhone, Large iPhone | Primary buttons lack bottom safe-area-aware padding for modern gesture-bar viewports. | `.primary-panel-button` uses static padding. | Use `padding-bottom: calc(12px + env(safe-area-inset-bottom))` in responsive CSS rules. | NO |
| **ML-FIELD-DETAILS-005** | P2 | Report Button | All | `FieldReportModal` uses native browser tooltips for validation (which display in English) and shows global API errors. | Required select/textarea inputs default to browser-native validation popups. | Implement custom React-controlled form validation with Hebrew translations. | NO |

*Severity definitions*:
- **P0**: Critical auth/data exposure or completely unusable Field Details flow.
- **P1**: Major mobile usability issue blocking a common device class or trapping the user.
- **P2**: Noticeable usability/layout issue with workaround.
- **P3**: Minor polish/documentation issue.

---

## 10. Blockers

A Field Details mobile blocker exists:
- **ML-FIELD-DETAILS-001**: On Small Android (360x640) and Small iPhone (375x667), the close button is pushed above the viewport, trapping the user inside the panel.

Project-level blocker:
- **AUTH-001** remains open and blocks mobile production release.

---

## 11. Recommendations

1. **Height Constraint**: Constrain `.field-details-panel` to a maximum height (e.g. `max-height: 85vh` or `max-height: calc(100dvh - 32px)`) on mobile viewports.
2. **Scroll Container**: Add `overflow-y: auto` to the panel container and implement event listeners to prevent drag/scroll events from propagating to the underlying map.
3. **Sticky Header**: Keep the name header and close button absolute/sticky at the top of the panel while details scroll underneath.
4. **Ergonomic Participants List**: Restrict inline participants lists height or display participants in a scroll-locked modal to prevent the panel height from growing uncontrollably.
5. **Safe-Area Adaptation**: Apply CSS safe-area margins and paddings (`env(safe-area-inset-bottom)`) to the bottom-placed primary actions.
6. **Custom Validation**: Replace native browser validations in `FieldReportModal` with custom, localized validations.

---

## 12. Final Audit Decision

Final audit decision: **FAIL**

- Field Details acceptable for mobile after this audit: **NO, due to the critical close-button trap on short devices.**
- Mobile production allowed: **NO**.
- Reason mobile production remains blocked: AUTH-001 remains open, EPIC 02 remains NOT COMPLETE, and this audit does not authorize mobile production release.
