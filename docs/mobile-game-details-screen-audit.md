# Mobile Game Details Screen Audit

## 1. Purpose

This audit evaluates the Game Details flow/view across the required mobile device classes from `docs/mobile-audit-plan.md`.

The Game Details screen provides players with game status, timing, organizer controls, and lists of participants. In the yesh_mishak application, game details are rendered inline as the `GamePanel` component inside the Field Details panel. This audit documents mobile compatibility issues only. It does not implement fixes or authorize mobile production release.

## 2. Scope

- **Screen audited**: Game Details (implemented as `GamePanel.jsx` nested within the `.field-details-panel` bottom sheet/side panel).
- **Device classes audited**:
  - Small Android: 360x640 / 360x740
  - Large Android: 412x915 / 430x932
  - Small iPhone: 375x667 / 390x844
  - Large iPhone: 428x926 / 430x932
- **Validation areas audited**:
  - Participant List
  - Close Game Button
  - Extend Game Button
  - Time Display
  - Notifications
- **Out of scope**:
  - Fixing issues
  - Implementing UI changes
  - Backend/API changes
  - Database/schema/config changes
  - Production mobile release approval

## 3. Gate Status

- `docs/mobile-audit-plan.md` exists and was used as the audit standard: **YES**
- `docs/mobile-map-screen-audit.md` exists and related findings were reviewed: **YES**
- `docs/mobile-field-details-screen-audit.md` exists and related findings were reviewed: **YES**
- `docs/mobile-create-game-screen-audit.md` exists and related findings were reviewed: **YES**
- EPIC 02 status remains: **NOT COMPLETE**
- AUTH-001 remains the production blocker: **YES**
- This audit does **not** unblock mobile production work.
- Mobile production release remains **NO** until AUTH-001 is resolved and production readiness is re-reviewed.

## 4. Methodology

### Files Reviewed

- `docs/mobile-audit-plan.md` (Audit Standard)
- `docs/product-decisions.md` (Product Decisions Ledger)
- `frontend/src/components/GamePanel.jsx` (Component Logic)
- `frontend/src/components/FieldDetailsPanel.jsx` (Parent Container)
- `frontend/src/api/games.js` (API Requests)
- `frontend/src/App.css` (Visual Styling)
- `frontend/package.json` (Scripts and Dependencies)
- `frontend/tests/game-close.spec.js` (E2E Game Close/Leave/Join Tests)

### Commands Run

- `git branch --show-current`
- `git status --short`
- `npm run lint` (Checked baseline linter results)
- `npm run build` (Verified compiling success)

### Execution Notes

- The app was run locally with Vite.
- Browser/mobile emulation was used with Chromium, mobile viewport sizes, touch enabled, and Hebrew selected in local storage.
- An authenticated organizer session was simulated to test creator controls (Close, Extend). A separate regular player session was simulated to test Join/Leave actions.
- Toggling the participants dropdown list and verifying Hebrew RTL layout wrap limits were tested.

### Limitations

- Real physical mobile device testing was not performed.
- Soft keyboard activation height was simulated in emulation.
- Dynamic network latency or WebSocket reconnections were not validated.

## 5. Game Details Flow Description

Game details are rendered dynamically as a card widget (`GamePanel`) inside the `FieldDetailsPanel` bottom sheet. It handles three distinct game states:
1. **Active Game**: Displays Start Time, End Time, Ends In countdown, Join/Leave actions, and Creator controls (Extend, Close).
2. **Upcoming Game**: Displays Scheduled Date/Time and Join/Leave actions.
3. **Ended Game**: Displays "המשחק הסתיים" (The game has ended) without actions.

### Information Displayed

1. **Player Count**: Displays `{{current}} / {{max}} שחקנים` (e.g. "4 / 10 שחקנים").
2. **Time Details Grid**:
   - Active: "התחלה" (Start), "סיום" (End), "מסתיים בעוד" (Ends in).
   - Scheduled: "מתוכנן" (Scheduled At).
3. **Age Note**: Optional restrictions (e.g., "18+").
4. **Participants Accordion**: Collapsible dropdown displaying list of player names.

### Actions Available

- **Join** ("אני בא"): Join the game (if not full and not already participating).
- **Leave** ("עזיבה"): Leave the game (if participating).
- **Extend** ("עוד סיבוב"): Organizers can extend the active duration.
- **Close Game** ("סגירת משחק"): Organizers can end the game immediately.

---

## 6. Device Coverage

| Device Class | Viewport | Result | Notes |
| :--- | :---: | :--- | :--- |
| Small Android | 360x640 / 360x740 | **FAIL** | Toggling the participants list open pushes parent sheet close actions off-screen (`top < 0`), trapping users. |
| Large Android | 412x915 / 430x932 | **PASS WITH FINDINGS** | Layout works portrait, but participant text wrap and toggle target dimensions need adjustments. |
| Small iPhone | 375x667 / 390x844 | **FAIL** | Toggling the participants list open pushes parent sheet close actions off-screen (`top < 0`), trapping users. |
| Large iPhone | 428x926 / 430x932 | **PASS WITH FINDINGS** | Layout works portrait, but Safari confirmation modals block custom webview flows. |

---

## 7. Validation Results

### Participant List

**What was checked**
- Readability and alignment of list text.
- Scrolling limits for large player count rosters.
- Overflow and wrapping for long Hebrew usernames.
- Touch target of the participants accordion toggle.

**Result**
PASS WITH FINDINGS.

**Evidence**
- The toggle header correctly shows participants count (e.g. "משתתפים (4)").
- The participant roster is styled with `.participants-list` in `App.css`, which sets `max-height: 180px; overflow: auto;`. This successfully limits container growth and enables internal scrolling when there are many players.
- Roster item names wrap normally without causing horizontal viewport breaks.
- However, the `.participants-toggle-button` header has a height of only ~24px (font-size 13px, padding `4px 0`). This is significantly below the 44px mobile touch target standard, making it hard to toggle open on mobile.
- Additionally, opening the list dynamically increases sheet height by up to 180px, contributing to parent viewport trap risks.

**Findings**
- *GDMOB-002*: Accordion toggle button height (~24px) is below the 44px touch target.
- *GDMOB-001* (Critical): Roster expansion adds vertical height, exacerbating the parent sheet viewport trap.

### Close Game Button

**What was checked**
- Authorization bounds (only creators see Close button).
- Touch target and visual accessibility.
- Confirmation dialog behavior.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Non-creators do not see the Close button (`danger-panel-button`). Creators see it rendered with a bright red background.
- It uses vertical padding `12px 14px`, achieving a hit target of ~46px (exceeding the 44px minimum).
- However, tapping the Close button triggers a native browser dialog via `window.confirm(t('game.closeConfirm'))`. In mobile Webviews, native confirm boxes halt JS execution, block user gesture detection, and provide suboptimal UX styling.

**Findings**
- *GDMOB-003*: Reliance on browser-native `window.confirm` degrades mobile ergonomics.

### Extend Game Button

**What was checked**
- Visibility logic (creators only).
- Touch target and visual distinction from Close button.
- User clarity regarding duration meaning.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Toggles correctly for active game organizers.
- Hit target is ~46px. Visual hierarchy is maintained using a subtle grey border and white background, contrasting well with the red Close button.
- However, the label "עוד סיבוב" (Extend) offers no information about the extension length. Users do not know if the game will be extended by 15, 30, or 60 minutes.

**Findings**
- *GDMOB-004*: Ambiguity in duration of the Extend Game action.

### Time Display

**What was checked**
- Format of times for active and scheduled games.
- Localized language formatting.
- Layout responsiveness on narrow widths.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Active games display start, end, and Ends In countdowns. Scheduled games display the start date/time.
- Localizations are resolved using browser locales (`Intl.DateTimeFormat(locale, ...)`), avoiding time offset issues.
- However, `.game-time-list` is configured with `grid-template-columns: repeat(3, minmax(0, 1fr))` on all screen widths. On narrow viewports (e.g. 320px or 360px), splitting the space into 3 equal columns causes text wrapping (e.g., "10 דקות" wraps into two lines, or Hebrew labels overlap), harming readability.

**Findings**
- *GDMOB-005*: 3-column time grid causes text wrapping and label overlap on small screens.

### Notifications

**What was checked**
- Actions (Join/Leave) triggers and their relationship to map state updates.
- Visibility of API and network validation errors.

**Result**
PASS.

**Evidence**
- Tapping Join or Leave dispatches API actions and reloads field and game states successfully.
- Errors (e.g. join failed) render as `<p className="panel-error">{error}</p>` below the action list. The text uses a clear contrast red color and is legible on mobile screen sizes.

---

## 8. Detailed Findings

### GDMOB-001: Inline participants list expansion pushes parent panel close actions off-screen
- **Severity**: P1 (Relates directly to `ML-FIELD-DETAILS-001` blocker)
- **Area**: Participant List / Scrolling
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/GamePanel.jsx` (line 297)
  - Component: `.participants-list` container inside `.field-details-panel`.
- **Mobile Impact**: On short screens (e.g. 360x640), expanding the roster adds up to 180px of vertical height. This pushes the parent panel's close button `x` further above the screen viewport, trapping the user.
- **User Impact**: User gets trapped on the map/field details view, forcing a page reload to exit.
- **Recommendation**: Constrain the parent panel height and make its header/close action sticky.
- **Suggested Follow-up Issue**: Remediate Field Details Panel height boundaries (`ML-FIELD-DETAILS-001`).

### GDMOB-002: Participants list accordion toggle height is below 44px
- **Severity**: P2
- **Area**: Participant List
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.participants-toggle-button` (line 814) having `padding: 4px 0` and `font-size: 13px`.
- **Mobile Impact**: Total hit height is ~24px, which is below the 44px mobile touch target standard.
- **User Impact**: Users might struggle or miss-tap when attempting to open or close the participant list.
- **Recommendation**: Increase padding on the toggle button to at least `10px 0` and size the chevron icon to increase touch target area.
- **Suggested Follow-up Issue**: Increase touch target area of the participants toggle header.

### GDMOB-003: Destructive Close Game confirmation uses native window.confirm
- **Severity**: P2
- **Area**: Close Game Button
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/GamePanel.jsx`
  - Code: `window.confirm(t('game.closeConfirm'))` (line 211).
- **Mobile Impact**: Native browser dialogs freeze the thread, offer no style customizability, and have poor visual alignment on mobile browsers/webviews.
- **User Impact**: Suboptimal pop-up design and potential for accidental confirmations due to native dialog button placement.
- **Recommendation**: Replace native `window.confirm` with a custom React-controlled modal or overlay dialog.
- **Suggested Follow-up Issue**: Replace native window confirm dialog with custom modal.

### GDMOB-004: Extend Game button lacks explanation of extension duration
- **Severity**: P2
- **Area**: Extend Game Button
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/GamePanel.jsx`
  - Code: `{t('game.extend')}` (renders as "עוד סיבוב" / "Extend").
- **Mobile Impact**: The button does not specify the duration of the time extension.
- **User Impact**: Users are hesitant to press it because they do not know if the game will extend by 10, 30, or 60 minutes.
- **Recommendation**: Explicitly state the duration on the button or tooltip (e.g. "עוד סיבוב (+30 דק')").
- **Suggested Follow-up Issue**: Add extension duration info to Extend Game button.

### GDMOB-005: 3-column time display grid causes text wrap and overlap on narrow screens
- **Severity**: P2
- **Area**: Time Display
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.game-time-list` (line 755) setting `grid-template-columns: repeat(3, minmax(0, 1fr))`.
- **Mobile Impact**: On viewports with width <= 360px, splitting 320px into 3 columns (with gaps) leaves ~95px per column. Active time countdowns and Hebrew labels ("מסתיים בעוד") wrap awkwardly into 2-3 lines or overflow.
- **User Impact**: Poor readability and visual clutter in the game timing grid.
- **Recommendation**: Use a responsive grid layout that changes to 1 column or 2 columns on screens <= 360px.
- **Suggested Follow-up Issue**: Make game time list grid responsive on narrow devices.

---

## 9. Positive Findings

- **Roster Scrolling Limit**: Limiting roster height to 180px and adding `overflow: auto` is an excellent mobile design pattern that prevents unchecked container growth.
- **Visual Hierarchy**: The primary, secondary, and danger button themes provide clear visual cues for actions (Join vs Leave vs Close).
- **Date/Time Localization**: Local datetime formatting adjusts dynamically to user selected locale.

---

## 10. Risks Not Fully Verified

- **Safari Confirmation Prompts**: Intermittent rendering issues of native confirm prompts in iOS Webviews.
- **High-Latency Updates**: The Ends In countdown relies on `setInterval` which can lag or suspend when mobile browsers put tabs in sleep/background states.

---

## 11. Recommended Follow-up Issues

1. **[P1] Integration**: Ensure parent Field Details height constraint fixes prevent participants list expansion from clipping navigation actions (`GDMOB-001`).
2. **[P2] Polish**: Increase participants toggle button height padding to reach at least 44px.
3. **[P2] Polish**: Use a responsive grid (1 or 2 columns) for game timing on viewports <= 360px.
4. **[P2] Polish**: Replace native browser `window.confirm` with custom modal.
5. **[P2] Polish**: Specify time extension details on the organizer action button (e.g. `+30m`).

---

## 12. Final Verdict

Final audit verdict: **CONDITIONALLY READY**

The Game Details mobile component (`GamePanel`) is **conditionally ready**. The component is responsive and limits list expansions, but its final usability depends on fixing the parent container height limits (**ML-FIELD-DETAILS-001**) to prevent viewport trapping.
