# Mobile Notifications Screen Audit

## 1. Purpose

This audit evaluates the Notifications center and preferences modal across the required mobile device classes from `docs/mobile-audit-plan.md`.

The Notifications center provides users with updates about active/upcoming games, player counts, and configuration preferences. This audit documents mobile compatibility issues only. It does not implement fixes or authorize mobile production release.

## 2. Scope

- **Screen audited**: Notifications (implemented as `NotificationInboxModal.jsx` for the inbox list and `NotificationsModal.jsx` for notification settings).
- **Device classes audited**:
  - Small Android: 360x640 / 360x740
  - Large Android: 412x915 / 430x932
  - Small iPhone: 375x667 / 390x844
  - Large iPhone: 428x926 / 430x932
- **Validation areas audited**:
  - Notification List
  - Read Actions
  - Read All
  - Long Notifications
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
- `docs/mobile-game-details-screen-audit.md` exists and related findings were reviewed: **YES**
- EPIC 02 status remains: **NOT COMPLETE**
- AUTH-001 remains the production blocker: **YES**
- This audit does **not** unblock mobile production work.
- Mobile production release remains **NO** until AUTH-001 is resolved and production readiness is re-reviewed.

## 4. Methodology

### Files Reviewed

- `docs/mobile-audit-plan.md` (Audit Standard)
- `docs/product-decisions.md` (Product Decisions Ledger)
- `frontend/src/components/NotificationInboxModal.jsx` (Inbox Component)
- `frontend/src/components/NotificationsModal.jsx` (Settings Component)
- `frontend/src/components/CityAutocomplete.jsx` (City Selection)
- `frontend/src/api/notifications.js` (Notifications API client)
- `frontend/src/firebaseMessaging.js` (FCM Integration logic)
- `frontend/src/App.css` (Visual Styling)
- `frontend/package.json` (Scripts and Dependencies)
- `frontend/tests/notifications.spec.js` (E2E Notification Center Tests)

### Commands Run

- `git branch --show-current`
- `git status --short`
- `npm run lint` (Checked baseline linter results)
- `npm run build` (Verified compiling success)

### Execution Notes

- The app was run locally with Vite.
- Browser/mobile emulation was used with Chromium, mobile viewport sizes, touch enabled, and Hebrew selected in local storage.
- A list of mocked unread and read notifications (join game reminders, location-matching, game creation notifications) was loaded.
- Action triggers: marking single items read, marking all read, opening notification click links, changing distance sliders, and searching cities via the Israel cities catalog were simulated.

### Limitations

- Real physical mobile device testing was not performed.
- Firebase push notification delivery and browser permission popup behaviors (blocking, enabling) were simulated inside the browser-emulation layer.

## 5. Notifications Flow Description

A user accesses notifications from floating map controls:
1. **Inbox bell button**: Displays unread notification count badge and opens `NotificationInboxModal` to view alerts list.
2. **Settings gear button**: Opens `NotificationsModal` to toggle distance radius, city settings, specific fields checkboxes, and browser push permissions.

### Actions Available

- **Read Single**: Tapping a notification card marks it read and centers map / opens details. Tapping "סימון כנקרא" marks it read inline.
- **Read All**: Clears all unread notifications in one click.
- **Enable/Disable Push**: Subscribes/unsubscribes Firebase cloud tokens.
- **Save Settings**: Persists distance, city, and field-specific preferences.

---

## 6. Device Coverage

| Device Class | Viewport | Result | Notes |
| :--- | :---: | :--- | :--- |
| Small Android | 360x640 / 360x740 | **PASS WITH FINDINGS** | Layout and lists fit well. Small targets and header squashing identified. |
| Large Android | 412x915 / 430x932 | **PASS WITH FINDINGS** | Core inbox and preferences functions work. Polish targets identified. |
| Small iPhone | 375x667 / 390x844 | **PASS WITH FINDINGS** | Layout and lists fit well. Safari click-outside handler should be hardened. |
| Large iPhone | 428x926 / 430x932 | **PASS WITH FINDINGS** | Core inbox and preferences functions work. Polish targets identified. |

---

## 7. Validation Results

### Notification List

**What was checked**
- Layout fit, spacing, and vertical scrolling bounds.
- Visually clear read vs unread indicators.
- Handling of loading, empty, and error feedback states.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Renders list dynamically in `.notifications-list` (`max-height: 420px; overflow: auto; display: grid; gap: 8px;`). The list container scrolls internally, fitting viewport boundaries safely.
- Unread notifications receive `.unread` class which applies a light blue background (`#eff6ff`) and border (`#93c5fd`), contrasting clearly with white read items.
- Empty state displays "אין התראות עדיין." (No notifications yet) correctly.
- However, unread items show unread text indicators ("לא נקראה") and timestamp details vertically stacked inside a grid on the main button wrapper. This makes each item tall (~120px), reducing screen density on small screens.

**Findings**
- No blockers found. Polishing density and spacing is recommended.

### Read Actions

**What was checked**
- Tapping a card to mark it read and trigger its deep link action.
- Tapping the inline "סימון כנקרא" (Mark as read) button.
- Verification of unread badge updates.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Tapping a notification item successfully executes the API call `markNotificationRead` and updates both the unread badge and list.
- Inline read actions are accessible via `.notification-mark-read-button`.
- However, this inline button has a height of only ~30px (`padding: 7px 9px`, `font-size: 13px`), which is below the 44px mobile touch target standard, presenting a hit target risk.

**Findings**
- *NTMOB-002*: Inline mark-read touch target height (~30px) is below 44px.

### Read All

**What was checked**
- Visibility and reachability of the "Mark all as read" header action.
- Badge reset performance.
- Stacking on small screen viewports.

**Result**
PASS WITH FINDINGS.

**Evidence**
- Header button triggers `markAllNotificationsRead`, resetting the badge immediately.
- However, `.notifications-list-header` is configured as a flex row with `justify-content: space-between`. On narrow devices (e.g. 320px or 360px), the unread count text (e.g., "12 התראות שלא נקראו") and button ("סימון הכל כנקרא") can squash together or wrap awkwardly, causing layout clutter.
- The "Mark all as read" button has height ~34px, which is below the 44px touch target.

**Findings**
- *NTMOB-001*: Flex header squashes count text and button on narrow screens.
- *NTMOB-003*: Mark-all button height (~34px) is below 44px.

### Long Notifications

**What was checked**
- Wrapping of long Hebrew notification titles and bodies.
- Visual alignment of metadata timestamps.

**Result**
PASS.

**Evidence**
- No `white-space: nowrap` constraints exist on titles (`span`) or bodies (`small`). Texts wrap normally inside the grid boundaries.
- Timestamps and read indicators are placed on separate rows, preventing clipping or overflow.

**Findings**
- No wrap or text overflow failures.

---

## 8. Detailed Findings

### NTMOB-001: Header flex row squashes count and button on narrow mobile viewports
- **Severity**: P1
- **Area**: Read All
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.notifications-list-header` (line 1085) styled as `display: flex; justify-content: space-between;`.
- **Mobile Impact**: On viewports with width <= 360px, the combined size of the unread count label and the "Mark all as read" button exceeds the modal container's inner width (after subtracting 44px padding). This forces text wrapping and squashes buttons.
- **User Impact**: Visual clutter and poor layout alignment.
- **Recommendation**: Stack items vertically (`flex-direction: column; align-items: stretch;`) on screens <= 400px.
- **Suggested Follow-up Issue**: Make notifications header responsive on narrow viewports.

### NTMOB-002: Inline mark-as-read touch target height (~30px) is below 44px
- **Severity**: P2
- **Area**: Read Actions
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.notification-mark-read-button` (line 1196) with `padding: 7px 9px` and `font-size: 13px`.
- **Mobile Impact**: Touch target is too small for standard fingers, increasing tap miss rates.
- **User Impact**: Friction when trying to mark notifications read without opening them.
- **Recommendation**: Increase padding to `11px 13px` to achieve a hit target height of >= 44px.
- **Suggested Follow-up Issue**: Increase touch target height of inline mark-read button.

### NTMOB-003: Mark All as Read button height (~34px) is below 44px
- **Severity**: P2
- **Area**: Read All
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.notifications-list-header button` (line 1099) with `padding: 8px 10px`.
- **Mobile Impact**: Small hit target.
- **User Impact**: Missed taps when trying to clear notifications.
- **Recommendation**: Increase padding to `12px 14px` on mobile viewports.
- **Suggested Follow-up Issue**: Increase touch target height of Mark All as Read button.

### NTMOB-004: CityAutocomplete click-outside handler uses mousedown instead of touchstart
- **Severity**: P2
- **Area**: Notification List / Preferences
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/CityAutocomplete.jsx`
  - Code: `document.addEventListener('mousedown', handleClickOutside)` (line 56).
- **Mobile Impact**: Mobile touch devices do not fire `mousedown` reliably on simple taps, making outside clicks to dismiss the autocomplete dropdown fail.
- **User Impact**: The suggestions dropdown remains open when tapping elsewhere on the modal.
- **Recommendation**: Add a `touchstart` event listener in addition to `mousedown`.
- **Suggested Follow-up Issue**: Support touch events for autocomplete click-outside dismissal.

### NTMOB-005: Autocomplete suggestions dropdown clipped by virtual keyboard on short screens
- **Severity**: P2
- **Area**: Notification List / Preferences
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/App.css`
  - Component: `.city-autocomplete-suggestions` (line 1310) having `position: absolute; z-index: 20; max-height: 220px;`.
- **Mobile Impact**: Tapping the city input triggers the soft keyboard (~250px). With a remaining viewport height of ~350px, the 220px dropdown overlaps or overflows the modal boundary.
- **User Impact**: Suggestions are cut off by the keyboard, forcing users to type blindly or dismiss the keyboard to select a city.
- **Recommendation**: Constrain dropdown max-height or scroll the autocomplete container into view when focused.
- **Suggested Follow-up Issue**: Adjust suggestions dropdown bounds when keyboard is active.

### NTMOB-006: Radius slider range input is difficult to control precisely
- **Severity**: P2
- **Area**: Notification List / Preferences
- **Status**: Open
- **Evidence**:
  - File: `frontend/src/components/NotificationsModal.jsx` (line 429) using `<input type="range">`.
- **Mobile Impact**: Thumb dragging is difficult on small mobile screens.
- **User Impact**: Users struggle to set precise radius numbers (e.g. exactly 5km vs 6km).
- **Recommendation**: Add a text indicator display or numerical increment/decrement steppers next to the range slider.
- **Suggested Follow-up Issue**: Add precise numerical controls to distance radius setting.

---

## 9. Positive Findings

- **Roster Bounds**: The unread vs read visual boundaries are distinct and clean.
- **Scroll Limits**: Restricting the notifications list height to 420px prevents modal overflow.
- **RTL Language Compliance**: Hebrew text wraps and aligns correctly under flex and grid layouts.

---

## 10. Risks Not Fully Verified

- **FCM Web Push in iOS Safari**: iOS Safari has strict installation requirements (PWA addition to Home Screen) for web push notifications, which could not be verified in local emulation.
- **Background Sync**: Real-time notifications count synchronization when the app is suspended in background tabs.

---

## 11. Recommended Follow-up Issues

1. **[P1] Layout**: Stack notifications header items vertically on viewports <= 400px wide.
2. **[P2] Polish**: Increase padding to reach 44px height targets for the inline Mark Read and Mark All buttons.
3. **[P2] Polish**: Add `touchstart` listener to `CityAutocomplete` outside tap handlers.
4. **[P2] Polish**: Improve suggestions picker layout and height when keyboard is focused.
5. **[P2] Polish**: Add manual steppers to distance radius range inputs.

---

## 12. Final Verdict

Final audit verdict: **READY WITH FINDINGS**

The Notifications experience is **ready with findings**. The notification list and settings screens are fully functional, scroll-safe, and responsive. Remediation is recommended for touch targets and header layout, but no P0 blocker exists.
