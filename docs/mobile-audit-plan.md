# Mobile Audit Plan

## 1. Purpose

This document defines the complete mobile audit scope for the yesh_mishak web application before mobile remediation begins. It specifies which screens must be audited, which device classes must be covered, what checks must be performed, and how findings should be reported.

This is a planning document only. It does not execute the audit or implement fixes.

## 2. Current Gate Status

| Field | Value |
| :--- | :--- |
| EPIC 02 status | NOT COMPLETE |
| Production blocker | AUTH-001 — Google OAuth account-takeover via email-only linking |
| Production readiness | NO-GO (per ISSUE-122) |
| Mobile production release allowed | **NO** |

**Important**:
- AUTH-001 remains the current production blocker.
- This audit plan does not unblock mobile production work.
- Mobile remediation must not proceed to production until the critical auth risk is fixed and production readiness is re-reviewed (ISSUE-122 re-executed with GO result).
- Creating this audit plan is a preparatory step only.

## 3. Audit Principles

1. **Test real user flows, not isolated screens only.** Follow complete task paths (e.g., login -> map -> field -> create game -> see game in list).
2. **Test both authenticated and unauthenticated states.** Verify behavior when logged in, logged out, and when session expires.
3. **Test loading, empty, error, and success states.** Every screen has multiple visual states beyond the happy path.
4. **Test touch usability.** All interactive elements must be reachable and tappable with a finger, not just a mouse pointer.
5. **Test Hebrew / RTL layout.** The application serves Hebrew-speaking users. All text, alignment, and directional UI must render correctly in RTL mode.
6. **Test small and large mobile screens.** Layout must not break on the smallest practical device or waste space on the largest.
7. **Test safe behavior under bad network conditions.** The app should handle slow connections, timeouts, and offline states without crashing or showing broken UI.
8. **Test permissions such as location and notifications.** The app requests geolocation and push notification permissions. All permission states (granted, denied, default, unsupported) must be handled gracefully.
9. **Test that admin screens are not exposed to normal users.** Admin routes must return 403 or redirect for non-admin users on all device sizes.

## 4. Device Matrix

| Device Class | Example Viewport | OS | Browser | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| Small Android | 360x640 / 360x740 | Android | Chrome | Minimum practical Android layout |
| Large Android | 412x915 / 430x932 | Android | Chrome | Common modern Android layout |
| Small iPhone | 375x667 / 390x844 | iOS | Safari | Small iPhone layout (iPhone SE / iPhone 13 mini) |
| Large iPhone | 428x926 / 430x932 | iOS | Safari | Large iPhone layout (iPhone 14 Pro Max / iPhone 15 Plus) |

**Additional rules**:
- **Portrait mode is required** for all audit checks.
- **Landscape mode is optional** unless the app explicitly supports landscape-specific layouts.
- **Browser-based testing is acceptable** for the web app. Native app testing applies only if/when native app work begins.
- **Emulator/simulator testing is acceptable** for initial audit. Device testing is recommended for touch usability and permission behavior verification.

## 5. Screen Audit Matrix

| Screen | User State | Required Checks | Mobile Risks | Device Coverage | Pass Criteria |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Login | Unauthenticated | Google login button visible, tappable, loading state, error state, redirect flow | Button too small, hidden behind keyboard, overflow on small screens | All 4 device classes | Login completes successfully on all devices, no layout breaks |
| Register | First-time user (post-Google auth) | Profile completion fields, validation, keyboard behavior, submit button | Keyboard hides submit, fields overflow, validation not visible | All 4 device classes | Registration completes, all fields accessible, errors visible |
| Map | Authenticated | Map loads, pins visible and tappable, controls reachable, location permission | Map controls overlap, pins untappable, permission dialog behavior | All 4 device classes | Map renders with pins, controls usable, permission states handled |
| Field Details | Authenticated | Field info visible, games listed, create/join actions reachable, back navigation | Long names overflow, action buttons hidden, empty state missing | All 4 device classes | All field info readable, actions reachable, back works |
| Create Game | Authenticated | Sport selection, player count, date/time, validation, submit, duplicate conflict | Date picker unusable on mobile, keyboard overlap, small touch targets | All 4 device classes | Game created successfully, all inputs usable, errors visible |
| Game Details | Authenticated | Status, participants, join/leave, close/extend for organizer, permissions | Buttons too close, long participant lists overflow, permission errors unclear | All 4 device classes | All game info visible, all actions work, authorization enforced |
| Notifications | Authenticated | List renders, unread badge, mark read, preferences, push permission states | List items too small, preferences overflow, city autocomplete unusable | All 4 device classes | Notifications readable, preferences usable, push states handled |
| Admin | Authenticated (admin role) | Stats, fields moderation, games, users, blocked for non-admin | Tables overflow, cards not responsive, non-admin access possible | All 4 device classes | Admin functions usable, non-admin blocked, tables/cards responsive |

## 6. Login Audit

### Checks

- [ ] Google login button is visible without scrolling on all device classes
- [ ] Google login button is large enough to tap (minimum 44x44px touch target)
- [ ] Button text/icon is readable on small screens
- [ ] Tapping the button initiates Google OAuth flow
- [ ] Loading state is visible while authentication is in progress
- [ ] Error state is visible if authentication fails (network error, token error)
- [ ] After successful login, user lands in the correct app state (map view)
- [ ] Redirect/callback flow completes without getting stuck
- [ ] No horizontal overflow on any device class
- [ ] No text is hidden or cut off due to viewport size
- [ ] Hebrew/RTL copy is readable and properly aligned
- [ ] Login page works correctly when already logged in (redirect to app)
- [ ] Login page works after session expiry (re-authentication flow)

## 7. Register Audit

Registration in yesh_mishak is handled via Google OAuth (first-time login creates account). If a profile completion step exists, the following must be checked:

### Checks

- [ ] First-time user flow is clear — user understands they are creating an account
- [ ] Required fields (if any) are clearly marked
- [ ] Validation errors are visible and positioned near the relevant field
- [ ] Keyboard does not hide required fields or the submit button
- [ ] Submit button remains visible and reachable when keyboard is open
- [ ] Form works on small screens without horizontal scrolling
- [ ] Long input values do not break layout
- [ ] Success state confirms account creation
- [ ] User is redirected to the correct post-registration screen
- [ ] Hebrew/RTL input works correctly in all text fields
- [ ] If no separate registration screen exists, document this as "Registration is part of Google login flow — no separate screen"

## 8. Map Audit

### Checks

- [ ] Map loads and renders tiles correctly on all device classes
- [ ] Field pins/markers are visible on the map
- [ ] Field pins are tappable (minimum 44x44px touch target or equivalent)
- [ ] Tapping a pin opens field details or a preview
- [ ] User location permission is requested appropriately
- [ ] Permission granted: user location is shown on map
- [ ] Permission denied: map still loads with a fallback location or message
- [ ] Permission default (not yet asked): prompt is shown clearly
- [ ] "Add field" button is reachable and not hidden behind other controls
- [ ] Notifications button/icon is reachable and not hidden
- [ ] Bottom controls do not overlap with map content or each other
- [ ] Top controls (if any) do not overlap with device status bar or notch
- [ ] Map zoom and pan work with touch gestures (pinch, drag)
- [ ] No broken scroll/zoom behavior (page scroll vs. map scroll conflict)
- [ ] Map works on small screens (360x640) without controls overlapping
- [ ] Loading state is visible while map tiles or field data loads
- [ ] Error state is visible if map or field data fails to load
- [ ] Hebrew/RTL UI elements around the map are properly aligned

## 9. Field Details Audit

### Checks

- [ ] Field name is visible and not truncated on small screens
- [ ] Long field names wrap properly without horizontal overflow
- [ ] Sport type is visible (football, basketball, both)
- [ ] Field status information is visible (approved, pending, etc.)
- [ ] Active game information is visible if a game is currently active
- [ ] Upcoming game information is visible if supported
- [ ] "Create Game" or "Join Game" action buttons are reachable and tappable
- [ ] Back/close navigation works (back button, swipe, or close icon)
- [ ] Empty state is handled when no games exist for the field
- [ ] Field location/address information is visible
- [ ] Surface type and amenities (nets, etc.) are visible if available
- [ ] Field reports section is accessible if supported
- [ ] Content is scrollable if it exceeds viewport height
- [ ] Hebrew/RTL text renders correctly
- [ ] No horizontal overflow on any device class

## 10. Create Game Audit

### Checks

- [ ] Sport selection is usable on mobile (dropdown, buttons, or radio)
- [ ] Max players input is usable (number input or stepper)
- [ ] Instant game ("now") flow works if supported
- [ ] Scheduled game ("future") flow works if supported
- [ ] Date picker is usable on mobile (native date input or custom picker)
- [ ] Time picker is usable on mobile
- [ ] Validation errors are visible and positioned near the relevant field
- [ ] Required fields are clearly marked
- [ ] Submit button is visible and reachable when keyboard is open
- [ ] Loading state is visible during game creation
- [ ] Success state confirms game was created
- [ ] Duplicate game conflict state is visible (e.g., "A game already exists at this field")
- [ ] Rate limiting error is visible if triggered
- [ ] Keyboard does not hide important buttons or fields
- [ ] All touch targets are large enough (minimum 44x44px)
- [ ] Form works on small screens (360x640)
- [ ] Hebrew/RTL labels and inputs work correctly

## 11. Game Details Audit

### Checks

- [ ] Game status is visible (active, scheduled, closed, cancelled)
- [ ] Participant count is visible (current / max)
- [ ] Participant list is visible and scrollable if long
- [ ] "Join" button is visible and tappable for eligible users
- [ ] "Leave" button is visible and tappable for participants
- [ ] "Close Game" is available for the organizer
- [ ] "Extend Game" is available for the organizer
- [ ] Authorization is enforced — non-organizers cannot close/extend
- [ ] Full game state is handled (join button disabled or hidden when game is full)
- [ ] Scheduled/future game displays correctly with date/time
- [ ] Error states are visible (network error, permission error)
- [ ] Back/close navigation works
- [ ] No horizontal overflow on any device class
- [ ] Hebrew/RTL text renders correctly
- [ ] Touch targets are large enough for all action buttons

## 12. Notifications Audit

### Checks

- [ ] Notification modal/page opens from the main screen
- [ ] Unread badge/count is visible on the notification icon
- [ ] Notification list items are readable on small screens
- [ ] Each notification shows relevant information (game, field, time)
- [ ] "Mark as read" works for individual notifications
- [ ] "Mark all as read" works
- [ ] Notification preferences screen is accessible
- [ ] City autocomplete input works on mobile (keyboard, suggestions visible)
- [ ] Distance/radius slider is usable with touch
- [ ] Specific fields selection works on mobile
- [ ] Push notification permission states handled:
  - [ ] Default (not yet asked): prompt shown clearly
  - [ ] Granted: push notifications work
  - [ ] Denied: clear message, no repeated prompts
  - [ ] Unsupported (browser/device): clear message
- [ ] Small screen usability — all preference controls are reachable
- [ ] Long notification text wraps properly
- [ ] Empty state is handled (no notifications message)
- [ ] Hebrew/RTL layout works for notification text and preferences

## 13. Admin Audit

### Checks

- [ ] Admin routes are hidden or blocked for non-admin users (403 or redirect)
- [ ] Non-admin users cannot see admin navigation links
- [ ] Admin users can access the admin area
- [ ] Stats/dashboard screen is usable on mobile
- [ ] Fields moderation screen is usable (approve/reject actions reachable)
- [ ] Games management view is usable
- [ ] Users management view is usable (ban/suspend/unban actions)
- [ ] Data tables are responsive — either scroll horizontally, use cards, or collapse columns
- [ ] No desktop-only layout assumptions (no tiny text, no unreachable buttons)
- [ ] Dangerous actions (ban, reject, close) require clear UI feedback or confirmation
- [ ] Admin actions produce visible success/error feedback
- [ ] Hebrew/RTL layout works for admin content
- [ ] Admin area works on small screens (360x640)

## 14. Cross-Cutting Mobile Checks

These checks apply to every screen and must be verified across all device classes:

### Layout and Text
- [ ] RTL/Hebrew layout renders correctly on all screens
- [ ] Font size is readable without zooming (minimum 14px body text)
- [ ] No horizontal scrolling on any screen
- [ ] No text is cut off or hidden
- [ ] Long text wraps properly

### Touch and Interaction
- [ ] All tap targets are at least 44x44px
- [ ] Buttons are not too close together (minimum 8px spacing)
- [ ] Sticky/fixed buttons do not overlap with content
- [ ] Modals do not overflow the viewport
- [ ] Modals can be closed (close button, backdrop tap, or back button)

### Viewport and Device
- [ ] iPhone safe-area (notch, home indicator) is handled — content not hidden behind
- [ ] Viewport height is correct — no 100vh issues on mobile browsers (address bar)
- [ ] Keyboard opening does not break layout or hide critical buttons
- [ ] Scroll locking works correctly (background does not scroll when modal is open)

### States
- [ ] Loading states are visible on all screens
- [ ] Empty states are handled on all screens
- [ ] Error states are visible and informative
- [ ] Network failure produces a visible message (not a blank screen)
- [ ] Slow connection does not cause the app to appear frozen

### Navigation
- [ ] Browser back button works correctly on all screens
- [ ] App does not get stuck in a broken navigation state
- [ ] Deep links work (if supported)

### Accessibility Basics
- [ ] Sufficient color contrast for text and interactive elements
- [ ] Focus indicators are visible for keyboard/assistive technology users
- [ ] Images have alt text where meaningful
- [ ] Form inputs have associated labels

## 15. Audit Execution Checklist

Copy this checklist for each device class during audit execution:

### Small Android (360x640 / 360x740)

| Screen | Status | Finding Count | Blocker? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Login | | | | |
| Register | | | | |
| Map | | | | |
| Field Details | | | | |
| Create Game | | | | |
| Game Details | | | | |
| Notifications | | | | |
| Admin | | | | |
| Cross-Cutting | | | | |

### Large Android (412x915 / 430x932)

| Screen | Status | Finding Count | Blocker? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Login | | | | |
| Register | | | | |
| Map | | | | |
| Field Details | | | | |
| Create Game | | | | |
| Game Details | | | | |
| Notifications | | | | |
| Admin | | | | |
| Cross-Cutting | | | | |

### Small iPhone (375x667 / 390x844)

| Screen | Status | Finding Count | Blocker? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Login | | | | |
| Register | | | | |
| Map | | | | |
| Field Details | | | | |
| Create Game | | | | |
| Game Details | | | | |
| Notifications | | | | |
| Admin | | | | |
| Cross-Cutting | | | | |

### Large iPhone (428x926 / 430x932)

| Screen | Status | Finding Count | Blocker? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Login | | | | |
| Register | | | | |
| Map | | | | |
| Field Details | | | | |
| Create Game | | | | |
| Game Details | | | | |
| Notifications | | | | |
| Admin | | | | |
| Cross-Cutting | | | | |

## 16. Pass / Fail Rules

| Status | Definition |
| :--- | :--- |
| PASS | Screen works correctly on the device class. No critical or high-severity findings. |
| FAIL | Screen has one or more critical or high-severity findings that must be fixed. |
| BLOCKED | Screen cannot be tested due to a prerequisite failure (e.g., login broken, AUTH-001 unresolved). |
| NOT APPLICABLE | Screen does not exist or is not relevant for this device class. |

**Blocking rule**: Any finding in the following categories is a blocker that must be fixed before mobile production release:
- Critical auth vulnerability (e.g., AUTH-001)
- Data exposure to unauthorized users
- Broken core user flow (cannot login, cannot create game, cannot join game)
- Completely unusable screen on any required device class (content hidden, buttons unreachable, app crashes)
- Admin functionality exposed to non-admin users

## 17. Output Format For Future Audit

When the mobile audit is executed, findings should be documented using this template:

| Field | Description |
| :--- | :--- |
| **Device** | Device class (e.g., Small Android 360x640) |
| **Screen** | Screen name (e.g., Create Game) |
| **Finding ID** | Sequential ID (e.g., MA-001) |
| **Severity** | Critical / High / Medium / Low |
| **Evidence** | Screenshot or description of what was observed |
| **Steps to Reproduce** | Step-by-step instructions to reproduce the finding |
| **Expected Behavior** | What should happen |
| **Actual Behavior** | What actually happens |
| **Recommendation** | Suggested fix |
| **Blocking Decision** | YES (blocks release) / NO (can ship with known issue) |

### Severity Definitions for Mobile Findings

| Severity | Definition |
| :--- | :--- |
| Critical | App crashes, data loss, security vulnerability, or core flow completely broken |
| High | Major usability issue — screen is functional but very difficult to use on the device class |
| Medium | Noticeable issue — layout problem, minor overflow, suboptimal spacing |
| Low | Cosmetic — minor alignment, spacing, or visual polish issue |

## 18. Final Decision

- This issue creates the mobile audit plan only.
- Mobile audit execution is a separate future issue.
- Mobile remediation (fixing findings) is separate from audit planning and audit execution.
- **Production mobile release remains blocked** until:
  1. AUTH-001 is resolved (ISSUE-111: Harden Google OAuth account linking)
  2. Production readiness review (ISSUE-122) is re-executed with GO result
  3. Mobile audit is executed and critical/high findings are remediated
