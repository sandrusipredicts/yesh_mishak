# ISSUE-139: Keyboard Handling Improvements

## Summary

This issue implements the keyboard interaction improvements defined in `docs/mobile-keyboard-interaction-spec.md` (ISSUE-138). The changes ensure all mobile form fields remain accessible when the virtual keyboard opens, modals scroll internally, submit/cancel actions remain reachable, and iOS Safari auto-zoom is prevented.

The implementation covers:
- Full-page form scroll safety (Login/Registration)
- Modal internal scrolling with bounded height (Create Game — resolves CGMOB-001)
- iOS Safari 16px input font-size enforcement across all form inputs on mobile
- Numeric keypad optimization for player count fields
- Touch-safe autocomplete outside-click dismissal
- Viewport-aware autocomplete suggestion list height

## Files Changed

### Frontend CSS
- `frontend/src/App.css`
  - Changed `.login-page` from `min-height: 100vh` to `min-height: 100dvh` and added `overflow-y: auto` for keyboard-safe scrolling
  - Added `max-height`, `overflow-y: auto`, and safe-area-aware `padding-bottom` to `.open-game-modal` (resolves CGMOB-001)
  - Added `align-content: safe center` to `.login-page` on mobile to prevent content clipping above viewport when keyboard opens
  - Added `font-size: 16px` on mobile (max-width: 640px) for all form inputs, selects, and textareas across auth forms, open game form, add field form, field report form, notifications form, admin search, and city autocomplete (resolves CGMOB-002, ADMOB-003)
  - Added viewport-aware `max-height: min(220px, 40dvh)` to `.city-autocomplete-suggestions` on mobile (addresses NTMOB-005)

### Frontend Components
- `frontend/src/components/OpenGameModal.jsx`
  - Added `inputMode="numeric"` and `pattern="[0-9]*"` to players present and max players inputs (resolves CGMOB-005)

- `frontend/src/components/CityAutocomplete.jsx`
  - Added `touchstart` event listener alongside existing `mousedown` for outside-click dismissal (addresses NTMOB-004)

### Documentation
- `docs/mobile-keyboard-handling-implementation.md` (this file)
- `docs/product-decisions.md` (decision record appended)

## Keyboard Rules Implemented

### Full-Page Form Scrolling
- `.login-page` uses `min-height: 100dvh` instead of `100vh` to account for dynamic viewport changes when the keyboard opens on iOS Safari
- Added `overflow-y: auto` so the page can scroll when form content exceeds the visible viewport
- Added `align-content: safe center` on mobile so the centered grid does not clip content above the viewport when the keyboard reduces available height

### Modal Internal Scrolling
- `.open-game-modal` now has `max-height: min(600px, calc(100dvh - 40px - var(--safe-area-top) - var(--safe-area-bottom)))` and `overflow-y: auto`
- This matches the pattern already applied to `.notifications-modal`, `.add-field-modal`, and `.field-report-modal` in ISSUE-137
- Bottom padding includes safe-area offset: `padding-bottom: calc(22px + var(--safe-area-bottom))`
- This directly resolves CGMOB-001 (Critical): the Create Game modal keyboard trap

### Bottom Sheet/Panel Behavior
- `FieldDetailsPanel` contains no form inputs — no keyboard changes needed
- The panel already has height constraints and safe-area padding from ISSUE-137

### Autocomplete/Dropdown Behavior
- CityAutocomplete now listens for both `mousedown` and `touchstart` for outside-click dismissal
- Suggestion list max-height is viewport-aware on mobile: `min(220px, 40dvh)` prevents suggestions from extending behind the keyboard

### Submit/Cancel Reachability
- All modal forms now have bounded height with internal scroll, so submit buttons are always reachable by scrolling
- Login/Registration page scroll is enabled, so submit buttons below the keyboard can be reached by scrolling

### Error Reachability
- Modal errors remain inside the scrollable content area, so they are reachable by scrolling
- Login/Registration errors are at the bottom of the panel and reachable via page scroll

### Numeric Keyboard Handling
- Player count inputs (`playersPresent`, `maxPlayers`) in OpenGameModal use `inputMode="numeric"` and `pattern="[0-9]*"` to display a numeric keypad on mobile

## Findings Addressed

| Finding ID | Severity | Screen | Resolution |
| :--- | :--- | :--- | :--- |
| `CGMOB-001` | Critical | Create Game | Resolved — modal now has max-height and overflow-y: auto |
| `CGMOB-002` | High | Create Game | Resolved — input font-size set to 16px on mobile |
| `CGMOB-005` | Medium | Create Game | Resolved — numeric inputs use inputMode="numeric" |
| `ADMOB-003` | High | Admin Panel | Resolved — admin search/select font-size set to 16px on mobile |
| `NTMOB-004` | Medium | Notifications | Addressed — touchstart listener added to CityAutocomplete |
| `NTMOB-005` | Medium | Notifications | Addressed — suggestions max-height is viewport-aware on mobile |
| `ML-LOGIN-001` | Medium | Login | Addressed — login page uses 100dvh, overflow-y: auto, safe center |
| `ML-REGISTER-001` | Medium | Registration | Addressed — same login page improvements apply to register mode |

## Forms Reviewed Matrix

| Form/Screen | Component/File | Keyboard Risk | Change Made | Result |
| :--- | :--- | :--- | :--- | :--- |
| Login | LoginPage.jsx / App.css | Submit hidden behind keyboard on short screens | 100dvh, overflow-y: auto, safe center, 16px inputs | PASS |
| Registration | LoginPage.jsx / App.css | 6-field form overflows viewport with keyboard | Same as Login (shared component) | PASS |
| Create Game | OpenGameModal.jsx / App.css | Modal has no height limit; keyboard covers submit (CGMOB-001) | max-height, overflow-y: auto, safe-area padding, 16px inputs, numeric keypad | PASS |
| Add Field | AddFieldModal.jsx / App.css | Already has max-height and overflow from ISSUE-137 | 16px inputs added on mobile | PASS |
| Field Report | FieldReportModal.jsx / App.css | Already has max-height and overflow from ISSUE-137 | 16px inputs added on mobile | PASS |
| Notifications Preferences | NotificationsModal.jsx / App.css | Already has max-height and overflow from ISSUE-137 | 16px inputs added on mobile | PASS |
| City Autocomplete | CityAutocomplete.jsx / App.css | Suggestions hidden behind keyboard; mousedown-only dismissal | Viewport-aware max-height, touchstart listener | PASS |
| Admin Filters | AdminUsers.jsx / App.css | Search input triggers iOS zoom | 16px font-size on mobile | PASS |

## Manual Validation Matrix

All validation performed via code review against the keyboard interaction specification (ISSUE-138). CSS changes are scoped to mobile via `@media (max-width: 640px)` and do not affect desktop layout.

| Viewport | Forms Checked | Result | Notes |
| :--- | :--- | :--- | :--- |
| 375x667 | Login, Register, Create Game, Add Field, Field Report, Notifications, Admin Filters | PASS | All forms scrollable; modals bounded; inputs 16px; numeric keypad applied |
| 390x844 | Login, Register, Create Game, Add Field, Field Report, Notifications, Admin Filters | PASS | Same CSS rules apply; more viewport height reduces keyboard risk |
| 393x852 | Login, Register, Create Game, Add Field, Field Report, Notifications, Admin Filters | PASS | Same CSS rules apply |
| 430x932 | Login, Register, Create Game, Add Field, Field Report, Notifications, Admin Filters | PASS | Largest viewport; keyboard impact minimal |

## Known Remaining Issues

The following are intentionally not fixed in this issue:

- **Touch target sizing below 44px** (`GDMOB-002`, `NTMOB-002`, `NTMOB-003`, `ADMOB-004`, `ADMOB-005`, `ADMOB-006`, `ML-LOGIN-002`): Requires padding increases on many components. Separate issue.
- **Admin native prompt replacement** (`ADMOB-001`): Replacing `window.prompt` with a custom React modal is a component redesign, not a keyboard CSS fix. Separate issue.
- **Notification header wrapping** (`NTMOB-001`): Layout flex squashing on narrow screens. Separate issue.
- **Table/card redesign** (`ADMOB-002`): Horizontal scroll shadows for admin tables. Separate issue.
- **CGMOB-004 (inline validation errors)**: Implementing inline validation requires a validation architecture change. Errors remain visible via scroll. Documented as remaining work.
- **CGMOB-003 (touch targets in Create Game form)**: Input and close button height below 44px. Separate touch-target issue.
- **Native confirm replacement** (`GDMOB-003`): Close game uses `window.confirm`. Separate issue.
