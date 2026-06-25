# Mobile Create Game Screen Audit

## 1. Purpose

This audit evaluates the Create Game flow/modal across the required mobile device classes from `docs/mobile-audit-plan.md`.

The Create Game flow is a core transaction in the yesh_mishak application. This audit documents mobile usability, layout, input pickers, and keyboard handling issues. It does not implement fixes or authorize mobile production release.

## 2. Scope

- **Screen audited**: Create Game (implemented as `OpenGameModal.jsx` which is launched from the Field Details panel).
- **Device classes audited**:
  - Small Android: 360x640 / 360x740
  - Large Android: 412x915 / 430x932
  - Small iPhone: 375x667 / 390x844
  - Large iPhone: 428x926 / 430x932
- **Validation areas audited**:
  - Form Fields
  - Date Selection
  - Time Selection
  - Participant Count
  - Keyboard Handling
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
- EPIC 02 status remains: **NOT COMPLETE**
- AUTH-001 remains the production blocker: **YES**
- This audit does **not** unblock mobile production work.
- Mobile production release remains **NO** until AUTH-001 is resolved and production readiness is re-reviewed.

## 4. Methodology

### Files Reviewed

- `docs/mobile-audit-plan.md` (Audit Standard)
- `docs/product-decisions.md` (Product Decisions Ledger)
- `frontend/src/components/OpenGameModal.jsx` (Form Implementation)
- `frontend/src/components/FieldDetailsPanel.jsx` (Trigger Context)
- `frontend/src/api/games.js` (API Client)
- `frontend/src/App.css` (Visual Styling)
- `frontend/package.json` (Scripts and Dependencies)
- `frontend/tests/game-close.spec.js` (E2E Game Management Tests)

### Commands Run

- `git branch --show-current`
- `git status --short`
- `npm run lint` (Identified existing linter exceptions in `MyGamesPage.jsx` and `baseline.spec.js`)
- `npm run build` (Verified compiling success)

### Execution Notes

- The app was run locally with Vite.
- Browser/mobile emulation was used with Chromium, mobile viewport sizes, touch enabled, and Hebrew selected in local storage.
- An authenticated user session was seeded.
- Selecting a field on the map, opening the details panel, tapping "Open Game" ("פתיחת משחק"), switching between "Now" and "Future" options, inputting values, and focusing fields to trigger keyboard emulation were validated.

### Limitations

- Real physical mobile device testing was not performed.
- Virtual keyboard height (~250px-300px) and viewport resizing dynamics were simulated via browser devtools and emulation, which might differ slightly from native webview layout resizing on physical devices.
- Apple Safari specific input behaviors (like date/time picker layout bugs) were evaluated theoretically and via emulation.

## 5. Create Game Flow Description

A user reaches the Create Game flow by selecting an approved field marker on the Map, opening the Field Details panel, and clicking the "Open Game" ("פתיחת משחק") button (this button is shown only if there is no active game currently at the field).

This opens `OpenGameModal` which is centered as a dialog overlay.

### Information / Fields Displayed

1. **Title**: "פתיחת משחק" (Create Game).
2. **Timing Toggle**: Radio options for "משחק עכשיו" (Now) and "משחק עתידי" (Future).
3. **Date and Time Inputs**: Shown dynamically if "Future" is selected.
4. **Sport Selection**: A dropdown to choose "כדורגל" (Football) or "כדורסל" (Basketball) (automatically pre-selected if the field only supports one sport; displayed as a chooser if the field supports "both").
5. **Players Present**: Numeric input representing the current player count.
6. **Max Players**: Numeric input representing the maximum capacity.
7. **Age Note**: Text input for age restrictions (e.g. "18+").
8. **Submit Button**: "פתיחת משחק" (Create Game) with active loading spinner.

---

## 6. Device Coverage

| Device Class | Viewport | Result | Notes |
| :--- | :---: | :--- | :--- |
| Small Android | 360x640 / 360x740 | **FAIL** | Virtual keyboard or dynamic "Future" fields push buttons off-screen without scrolling, trapping users. |
| Large Android | 412x915 / 430x932 | **PASS WITH FINDINGS** | Form fits and works on portrait, but keyboard triggers scroll boundaries close to viewport edges. |
| Small iPhone | 375x667 / 390x844 | **FAIL** | Virtual keyboard or dynamic "Future" fields push buttons off-screen without scrolling, trapping users. |
| Large iPhone | 428x926 / 430x932 | **PASS WITH FINDINGS** | Form fits and works on portrait, but suffers from input auto-zooming on iOS Safari. |

---

## 7. Validation Results

### Form Fields

**What was checked**
- Input layouts, spacing, and label alignment in RTL Hebrew mode.
- Usability of sport selection dropdown and text inputs.
- Spacing between labels and touch target dimensions.
- Location of validation error messages.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Dropdowns and input fields align correctly for RTL Hebrew.
- Spacing is defined by `display: grid; gap: 14px;` in `.open-game-form`, which separates inputs sufficiently.
- However, form inputs and select elements have `padding: 10px 12px` and `font: inherit` inside `App.css`. Since their label has `font-size: 14px`, the inputs inherit a `14px` font size. This is below the `16px` iOS Safari threshold and triggers automatic screen zoom on focus.
- Target heights for fields are ~38px, which is below the 44px minimum touch target standard.
- Form error messages render globally at the bottom of the modal as `<p className="modal-error">{error}</p>`. If the user submits invalid fields, they have to scroll down to view the error text.

**Findings**
- *CGMOB-002*: Input font size is 14px, causing iOS Safari auto-zoom on focus.
- *CGMOB-003*: Target height of inputs/selects (~38px) is below 44px.
- *CGMOB-004*: Error messages display globally at the bottom instead of inline.

### Date Selection

**What was checked**
- Dynamics of the dynamic date selector when "Future" is selected.
- Compatibility of `type="date"` with mobile native calendars.
- Past-date validation handling.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Selecting "משחק עתידי" shows the date field. Stacking is handled vertically on viewports <= 640px.
- Using `type="date"` invokes native mobile calendar widgets, which is optimal for accessibility.
- Submitting a date in the past correctly halts execution and displays the local error message ("אי אפשר לקבוע משחק בזמן שעבר.").
- The Javascript parser merges date and time strings locally (`new Date(${scheduledDate}T${scheduledTime})`), converting to UTC ISO strings for API transfer. This cleanly avoids timezone/local offsets conflicts.

**Findings**
- No major date-specific functionality failures, but stacking layout adds ~60px of height, increasing modal scroll risks.

### Time Selection

**What was checked**
- Time picker visibility and usability.
- native time-wheel interaction.
- Timezone handling.

**Result**
PASS WITH FINDINGS.

**Evidence**
- `type="time"` correctly invokes mobile native time widgets.
- Time format is localized by browser/device settings.
- Timezone conversions are consistent.

**Findings**
- No time-specific errors.

### Participant Count

**What was checked**
- Numeric inputs for `playersPresent` and `maxPlayers`.
- Keyboard type triggered on mobile.
- Capacity validations (`max_players >= players_present`).

**Result**
PASS WITH FINDINGS.

**Evidence**
- `playersPresent` and `maxPlayers` are set as `type="number"`.
- Validations prevent submitting a game where max players is less than players present, showing "מקסימום השחקנים חייב להיות גדול או שווה לשחקנים כרגע."
- However, `type="number"` without `inputmode="numeric"` causes standard mobile keyboards to display letters, decimal points, and minus signs. For integer participant counts, a clean numeric keypad should be enforced.

**Findings**
- *CGMOB-005*: Missing `inputmode="numeric"` results in suboptimal mobile keyboard layout (displays characters/signs).

### Keyboard Handling

**What was checked**
- Visual clipping when focusing inputs and typing.
- Visibility of the "Create Game" submit button when keyboard is active.
- Modal sizing and scroll accessibility.

**Result**
**FAIL** on small viewports (Small Android and Small iPhone).

**Evidence**
- The modal is styled as `.open-game-modal`. In `App.css`, it has **no** `max-height` or `overflow` rules.
- Content height is ~410px (for "Now" games) and ~528px (for "Future" games, since fields stack vertically under 640px).
- When a virtual keyboard opens, it occupies ~250px-300px of height. On a 640px tall screen, this leaves only ~340px-390px of visible viewport.
- Because the modal is not scrollable, the bottom half (including the submit button and inputs like `ageNote` or `maxPlayers`) is pushed off-screen and cannot be reached.
- The close button at the top can also be pushed out of view depending on browser webview resizing. The user is trapped.

**Findings**
- *CGMOB-001* (Critical): Modal lacks height limits and scrolling, causing form actions to be covered by the keyboard and trapping users on small devices.

---

## 8. Detailed Findings

### CGMOB-001: Modal has no height constraint or scroll, trapping users when keyboard is open
- **Severity**: P0 (Blocker)
- **Area**: Keyboard Handling / Scrolling
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.open-game-modal` (line 900)
  - Code/Behavior: Lack of `max-height` and `overflow: auto` (unlike `.field-report-modal` or `.notifications-modal` which have `max-height: min(720px, calc(100vh - 40px))` and `overflow: auto`).
- **Mobile Impact**: On short screens (e.g. 360x640) or when focusing inputs, the virtual keyboard pushes inputs and the submit button off-screen. Users cannot scroll to reach them.
- **User Impact**: Users cannot fill out the form or submit it, completely blocking game creation.
- **Recommendation**: Apply `max-height: min(600px, calc(100vh - 40px))` and `overflow-y: auto` to `.open-game-modal` in CSS.
- **Suggested Follow-up Issue**: Constrain `open-game-modal` height and enable scroll on mobile.

### CGMOB-002: Input font-size is 14px, triggering iOS Safari zoom on focus
- **Severity**: P1
- **Area**: Form Fields
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.open-game-form label` (line 1350) setting `font-size: 14px`, inherited by inputs via `font: inherit` (line 16).
- **Mobile Impact**: When focusing an input, iOS Safari automatically zooms in to fit the field.
- **User Impact**: Screen zooms in automatically on focus, forcing the user to manually pinch-zoom out to see the rest of the modal or submit button.
- **Recommendation**: Set `font-size: 16px` on all text inputs, selects, and textareas on mobile viewports.
- **Suggested Follow-up Issue**: Set input font-size to 16px to prevent iOS Safari auto-zoom.

### CGMOB-003: Form input height and close button hit target are below 44px
- **Severity**: P2
- **Area**: Form Fields / Navigation
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.open-game-form input`, `.open-game-form select` (padding `10px 12px`, total height ~38px); `.modal-close-button` (top: 12px, inset-inline-end: 12px, font-size 20px, total size ~20x20px).
- **Mobile Impact**: Hit targets are small and close together, making precision tapping difficult.
- **User Impact**: Users might miss-tap inputs or struggle to tap the close button, leading to accidental submissions or closures.
- **Recommendation**: Increase vertical padding of inputs to `12px` (making height >= 44px) and add `padding: 10px` or `min-width: 44px; min-height: 44px;` to the close button.
- **Suggested Follow-up Issue**: Increase mobile touch targets for create game form inputs and close button.

### CGMOB-004: Global error messages are displayed at the bottom of the form
- **Severity**: P2
- **Area**: Form Fields
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/OpenGameModal.jsx`
  - Code: `{error ? <p className="modal-error">{error}</p> : null}` (line 216) located below all inputs.
- **Mobile Impact**: Validation errors are hidden below the viewport when the keyboard is open or when screens are small.
- **User Impact**: Users submit the form, nothing happens, and they must scroll down to find the error message.
- **Recommendation**: Show inline errors near respective fields (e.g. max players warning next to the capacity field) or scroll the error message into view automatically.
- **Suggested Follow-up Issue**: Implement inline form field validation errors.

### CGMOB-005: Numeric fields display alpha keyboard on mobile
- **Severity**: P2
- **Area**: Participant Count
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/OpenGameModal.jsx`
  - Code: `<input type="number">` (lines 187, 198) lacks `inputmode` and `pattern` attributes.
- **Mobile Impact**: Mobile keyboards display alphabet and symbol keys alongside numbers instead of a clean numeric keypad.
- **User Impact**: Users can type invalid characters (e.g. minus, dot, 'e') and experience annoying input switching.
- **Recommendation**: Add `inputmode="numeric"` and `pattern="[0-9]*"` to integer inputs.
- **Suggested Follow-up Issue**: Optimize numeric keypads for player counts.

---

## 9. Positive Findings

- **RTL Alignment**: The layout handles Hebrew translations and right-to-left layout gracefully. No layout breaks or overlapping text were observed in RTL mode.
- **Date/Time Parsing**: Merging date/time strings locally and sending UTC ISO to the API prevents timezone discrepancies.
- **Clean Timing Switch**: Toggling between "Now" and "Future" options dynamically updates fields smoothly.

---

## 10. Risks Not Fully Verified

- **iOS Safari Native wheels**: Native date/time picker wheels can behave unpredictably inside absolute/fixed containers on older iOS versions.
- **Webview resizing on Android**: Some Android browsers resize the window height when the keyboard opens (`window.innerHeight`), while others overlay it. Viewport overflow must be tested on both webview models.

---

## 11. Recommended Follow-up Issues

1. **[P0] Blocker Fix**: Add `max-height` and `overflow-y: auto` to `.open-game-modal` to ensure scroll safety when virtual keyboards open.
2. **[P1] Usability Fix**: Increase input font-size to `16px` on mobile viewports to stop iOS Safari auto-zoom.
3. **[P2] Polish**: Increase vertical padding of inputs to `12px` and close button tap size to `44px`.
4. **[P2] Polish**: Add `inputmode="numeric"` and `pattern="[0-9]*"` to players inputs.
5. **[P2] Polish**: Support inline field-specific validation errors.

---

## 12. Final Verdict

Final audit verdict: **NOT READY**

The Create Game mobile experience is **not ready** due to the critical virtual keyboard clipping blocker (**CGMOB-001**). Remediation is required before epic completion.
