# Mobile Regression Testing Plan

## A. Purpose

This plan defines the repeatable regression testing process for mobile and responsive layout changes in the Yesh Mishak web application. It protects core user flows from being broken by mobile/layout/auth/game/notification/map changes.

This plan must be executed:
- Before any release that includes mobile or layout changes
- After any change listed in the re-run triggers (Section Q)
- As part of the release gate process

It complements the ISSUE-164 device compatibility certification checklist by focusing on functional regression of core flows rather than initial device certification.

## B. Scope

This plan covers regression testing for:

- **Authentication** — Login, logout, registration
- **Games** — Create, join, leave, extend, close
- **Fields** — Open field details, report field, add field
- **Navigation** — Map, controls, back/close flows, portrait/landscape
- **Notifications** — Open inbox, read, read all, preferences, badge
- **Mobile layout and compatibility risks** — Viewport clipping, keyboard behavior, modal scrolling, touch targets, map usability, navigation reachability, Hebrew RTL layout, browser chrome issues

## C. Required Test Environments

| Category | Example Device | Viewport | Engine | Required |
| :--- | :--- | :--- | :--- | :--- |
| Android Small | Galaxy A14 | 360x640 | Chromium | Yes |
| Android Large | Pixel 7 | 412x915 | Chromium | Yes |
| iPhone Small | iPhone SE 3 | 375x667 | WebKit | Yes |
| iPhone Large | iPhone 14 | 390x844 | WebKit | Yes |
| Tablet / iPad | iPad 10th gen | 768x1024 | WebKit | Yes |
| Desktop | Any | 1280x800 | Chromium | Yes (sanity check) |
| Samsung Internet | Samsung Galaxy | 412x915 | Chromium proxy | Where direct device testing is unavailable, Chromium proxy is acceptable |

### Browser Coverage

| Browser | Engine | Method |
| :--- | :--- | :--- |
| Chrome | Chromium / Blink | Playwright Chromium (direct) |
| Safari | WebKit | Playwright WebKit (simulation) |
| Edge | Chromium / Blink | Chromium proxy |
| Samsung Internet | Chromium / Blink | Chromium proxy; real device recommended |

## D. Regression Statuses

| Status | Meaning |
| :--- | :--- |
| **Not Tested** | Flow has not been evaluated in this regression cycle. |
| **Pass** | Flow works correctly. No issues found. |
| **Pass With Notes** | Flow works, but a minor non-blocking issue was observed. Notes describe the issue. |
| **Fail** | Flow is broken. A blocking issue prevents normal use. Must be fixed before release. |
| **Blocked** | Testing could not be completed due to environment, tooling, or access constraints. |

## E. Authentication Regression Checklist

| # | Check | Status | Notes |
| :--- | :--- | :--- | :--- |
| E.1 | Registration screen opens correctly on mobile | | |
| E.2 | User can register (form fields fillable, submit reachable) | | |
| E.3 | Validation messages are readable and do not overlap | | |
| E.4 | Password/input fields remain reachable when keyboard opens | | |
| E.5 | Login screen renders correctly (panel centered, no overflow) | | |
| E.6 | Login with valid credentials succeeds | | |
| E.7 | Login error states display correctly (invalid credentials, network error) | | |
| E.8 | Logout button is visible and works | | |
| E.9 | After logout, protected actions require authentication again | | |
| E.10 | No auth buttons are clipped or hidden on any viewport | | |
| E.11 | Auth mode tabs (Login/Register) are tappable on mobile (min 44px touch target) | | |
| E.12 | Google login button is visible and reachable (may be below fold on short viewports) | | |

## F. Games Regression Checklist

| # | Check | Status | Notes |
| :--- | :--- | :--- | :--- |
| F.1 | Create game flow opens | | |
| F.2 | Field/sport/max players/time selectors are usable on mobile | | |
| F.3 | Submit create game works | | |
| F.4 | Created game appears correctly in field details | | |
| F.5 | Join game button is visible and tappable | | |
| F.6 | Join game succeeds and participant list updates | | |
| F.7 | Leave game button is visible (for participants) | | |
| F.8 | Leave game succeeds and field refreshes | | |
| F.9 | Extend game controls are visible where available | | |
| F.10 | Close game button is visible for organizer only | | |
| F.11 | Close game sends request and field refreshes to no active game | | |
| F.12 | Non-organizer cannot see or trigger close game | | |
| F.13 | Full game (max participants reached) behaves correctly | | |
| F.14 | Future/scheduled game shows upcoming state without active controls | | |
| F.15 | Game-related modals/forms can scroll and close on mobile | | |
| F.16 | Game action buttons remain tappable on all mobile viewports | | |

## G. Fields Regression Checklist

| # | Check | Status | Notes |
| :--- | :--- | :--- | :--- |
| G.1 | Tap field marker to open field details | | |
| G.2 | Field details panel layout is readable on mobile | | |
| G.3 | Active/upcoming games display correctly in field details | | |
| G.4 | Field details panel is scrollable if content overflows | | |
| G.5 | AddFieldModal opens from floating action button | | |
| G.6 | AddFieldModal form fields are all fillable | | |
| G.7 | AddFieldModal location picker map is visible | | |
| G.8 | AddFieldModal form validation works (required fields, error messages) | | |
| G.9 | AddFieldModal submit request works | | |
| G.10 | AddFieldModal close button (X) remains visible and clickable after scrolling (COMPAT-001 regression) | | |
| G.11 | AddFieldModal cancel button is reachable | | |
| G.12 | Report field flow opens from field details | | |
| G.13 | Report field form can be submitted | | |
| G.14 | Report field modal can be cancelled/closed | | |
| G.15 | Success/error messages are visible after field submission | | |
| G.16 | Map pin interaction works (tap to open details) | | |
| G.17 | Stadium markers display correctly for active and inactive fields | | |

## H. Navigation Regression Checklist

| # | Check | Status | Notes |
| :--- | :--- | :--- | :--- |
| H.1 | Main map loads and fills viewport | | |
| H.2 | Map zoom controls (+/−) are visible and functional | | |
| H.3 | Floating action buttons (add field, notifications, preferences) are visible | | |
| H.4 | Auth toolbar fits within viewport width (no overflow) | | |
| H.5 | Back/close flows work (modals, panels, dialogs) | | |
| H.6 | No screen traps user inside a modal (Escape, backdrop click, or X always available) | | |
| H.7 | Portrait orientation layout is correct | | |
| H.8 | Landscape orientation layout is functional | | |
| H.9 | No horizontal scrolling on any screen | | |
| H.10 | Hebrew RTL layout does not overlap or misalign | | |
| H.11 | English LTR layout renders correctly | | |
| H.12 | Mobile browser chrome (address bar, navigation bar) does not hide critical actions | | |
| H.13 | Navigation dialog (Waze/Google Maps) is usable on mobile viewport | | |
| H.14 | Bottom floating buttons are hidden when FieldDetailsPanel is open | | |

## I. Notifications Regression Checklist

| # | Check | Status | Notes |
| :--- | :--- | :--- | :--- |
| I.1 | Open notification modal/inbox via bell button | | |
| I.2 | Notification badge shows unread count | | |
| I.3 | Read single notification (click marks as read) | | |
| I.4 | Read all notifications (mark all as read) | | |
| I.5 | Unread count updates after reading | | |
| I.6 | Empty state displays correctly (no notifications) | | |
| I.7 | Notification preferences screen opens | | |
| I.8 | Notification preferences can be saved | | |
| I.9 | Scheduled game reminders surface in notification center | | |
| I.10 | Notification modal remains scrollable and closable | | |
| I.11 | Notification close button is not blocked by auth toolbar (z-index) | | |
| I.12 | Legacy notification read state is handled correctly | | |

## J. Cross-Flow Regression Scenarios

These end-to-end scenarios test realistic mobile usage across multiple features.

| # | Scenario | Steps | Expected Result | Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| J.1 | Unauthenticated user attempts protected action | View map → tap add field or join game | Redirected to login or shown auth prompt | | |
| J.2 | Login → field → create game → close modal | Login → tap field marker → create game → fill form → submit → close modal | Game created, modal closes, field shows active game | | |
| J.3 | Second user joins game, notification sent | User B logs in → opens same field → taps join → User A checks notifications | Join succeeds, notification appears for User A | | |
| J.4 | Read notification, count updates | Open notifications → tap notification → verify unread count decreases | Notification marked read, badge updates | | |
| J.5 | Organizer extends/closes game | Organizer opens field → extends or closes game → field refreshes | Game state updates correctly | | |
| J.6 | Add field flow | User opens AddFieldModal → fills form → picks location → submits | Field submission succeeds, confirmation visible | | |
| J.7 | Logout and protection check | User logs out → attempts to access protected route or action | Protected actions are unavailable, user sees login | | |

## K. Mobile-Specific Failure Criteria

A regression **fails** if any of the following are true:

- Core action cannot be completed (login, create game, join game, add field, read notification)
- Button is hidden, clipped, or unreachable on any required viewport
- Modal cannot be closed (no working close mechanism: X button, Escape, or backdrop click)
- Keyboard hides required submit/action button with no way to scroll to it
- Map controls are unusable (hidden, unresponsive, or overlapped)
- User gets trapped in a screen with no way to navigate away
- Text overlaps or becomes unreadable
- Horizontal scrolling is required for normal usage (admin tables excluded)
- Browser-specific runtime error blocks a core flow
- Notification state becomes inconsistent (unread count doesn't update, read state doesn't persist)
- Auth state leaks (protected actions available after logout)

## L. Automated Test Mapping

| Core Flow | Test File | Covered? | Manual Test Still Required? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Login screen layout | `small-android-layout.spec.js`, `mobile-scrolling.spec.js` | Yes | Yes — keyboard interaction | Layout tested at 360x640 and short viewports |
| Registration form reachable | `ipad-layout.spec.js` (IPAD-002), `small-android-layout.spec.js` | Yes | Yes — keyboard, real device | Submit reachable via scroll |
| Logout | — | No | Yes | No automated logout regression test |
| Create game | `game-close.spec.js` (line 640) | Partial | Yes | Tests game open flow, not full create form |
| Join game | `game-close.spec.js` (lines 397, 421, 514) | Yes | Yes — mobile touch | Join + participant list refresh |
| Leave game | `game-close.spec.js` (lines 237, 468) | Yes | Yes — mobile touch | Leave + field/participant refresh |
| Close game | `game-close.spec.js` (lines 191, 208, 609) | Yes | No | Organizer close, auth check, field refresh |
| Extend game | — | No | Yes | No automated extend test |
| Open field details | `field-navigation.spec.js` (line 107) | Yes | No | Field marker tap + details panel |
| Report field | `field-navigation.spec.js` (lines 147, 184) | Yes | No | Submit and cancel flows |
| Add field modal | `modal-usability.spec.js`, `ipad-layout.spec.js` | Yes | Yes — keyboard, real device | Open, scroll, close, submit reachable |
| AddFieldModal close after scroll | `ipad-layout.spec.js` (COMPAT-001) | Yes | No | Sticky close button validated |
| Field markers | `field-navigation.spec.js` (line 216) | Yes | No | Stadium markers for active/inactive |
| Map loads | `small-android-layout.spec.js`, `floating-buttons.spec.js` | Yes | No | Map + toolbar + no overflow |
| Navigation dialog | `field-navigation.spec.js` (lines 107, 136, 302) | Yes | No | Waze/Google Maps links, mobile viewport |
| Floating buttons layout | `floating-buttons.spec.js` | Yes | No | Position, overlap, panel-hide behavior |
| No horizontal overflow | `small-android-layout.spec.js`, `mobile-scrolling.spec.js` | Yes | No | Tested at 320px and 360px |
| Notification read | `notifications.spec.js` (line 57) | Yes | No | Click marks read, badge updates |
| Notification read all | `notifications.spec.js` (line 118) | Yes | No | Mark all as read, count clears |
| Notification preferences | `notifications.spec.js` (line 213), `notification-matching.spec.js` (line 470) | Yes | No | Load, save, persist |
| Notification matching | `notification-matching.spec.js` | Yes | No | Field/city matching, organizer exclusion |
| Scheduled reminders | `notifications.spec.js` (line 269) | Yes | No | Reminder surfaces and can be read |
| RTL/LTR layout | `i18n-rtl-ltr.spec.js` | Yes | No | Direction and persistence |
| Modal scroll/close | `modal-usability.spec.js` | Yes | Yes — real device touch | 320x568 and 375x667 viewports |
| Overscroll containment | `mobile-scrolling.spec.js` | Partial | Yes | WebKit computed style quirk (COMPAT-002) |
| iPad modal layout | `ipad-layout.spec.js` | Yes | No | 14 tests across tablet viewports |
| Admin panel | `admin-panel.spec.js` | Yes | Yes — tablet horizontal scroll | 8 tests, auth + tab loading |
| User location | `user-location.spec.js` | Yes | Yes — real geolocation permission | Mock-based, 4 tests |
| Landscape smoke | `small-android-layout.spec.js` (line 163) | Yes | No | Map + login at 667x375 |

### Coverage Summary

| Category | Automated | Manual Only | Not Covered |
| :--- | :--- | :--- | :--- |
| Authentication | Login layout, registration reachable | Logout, keyboard interaction, error states | — |
| Games | Join, leave, close, participant list, scheduled | Create form, extend | — |
| Fields | Open details, report, add modal, markers | Keyboard during add field | — |
| Navigation | Map, controls, floating buttons, RTL/LTR | Browser chrome, landscape (partial) | — |
| Notifications | Read, read all, preferences, matching, reminders | Push notification controls | — |

## M. Manual Test Matrix

| Flow | Device Category | Browser/Engine | Orientation | Status | Evidence | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Auth (E.1–E.12) | Android Small | Chromium | Portrait | | | |
| Auth (E.1–E.12) | iPhone Large | WebKit | Portrait | | | |
| Auth (E.1–E.12) | Desktop | Chromium | Landscape | | | |
| Games (F.1–F.16) | Android Small | Chromium | Portrait | | | |
| Games (F.1–F.16) | iPhone Large | WebKit | Portrait | | | |
| Games (F.1–F.16) | Tablet / iPad | WebKit | Landscape | | | |
| Fields (G.1–G.17) | Android Small | Chromium | Portrait | | | |
| Fields (G.1–G.17) | iPhone Small | WebKit | Portrait | | | |
| Fields (G.1–G.17) | iPhone Large | WebKit | Portrait | | | |
| Navigation (H.1–H.14) | Android Small | Chromium | Portrait + Landscape | | | |
| Navigation (H.1–H.14) | iPhone Large | WebKit | Portrait + Landscape | | | |
| Navigation (H.1–H.14) | Tablet / iPad | WebKit | Portrait + Landscape | | | |
| Notifications (I.1–I.12) | Android Large | Chromium | Portrait | | | |
| Notifications (I.1–I.12) | iPhone Large | WebKit | Portrait | | | |
| Cross-flows (J.1–J.7) | iPhone Large | WebKit | Portrait | | | |
| Cross-flows (J.1–J.7) | Android Small | Chromium | Portrait | | | |

## N. Regression Execution Order

Execute regression testing in this order. Stop and report if a P0/P1 failure is found at any step.

| Order | Phase | Description |
| :--- | :--- | :--- |
| 1 | **Smoke load** | App loads on all required device categories. Map renders. No console errors. |
| 2 | **Authentication** | Login, register, logout. Auth state transitions work. |
| 3 | **Map / Navigation** | Map fills viewport, controls usable, no overflow, RTL/LTR correct. |
| 4 | **Fields** | Open field details, add field, report field. Modal scroll/close works. |
| 5 | **Games** | Create, join, leave, extend, close. Organizer-only protection. |
| 6 | **Notifications** | Open, read, read all, preferences. Badge updates. |
| 7 | **Cross-flow scenarios** | End-to-end flows from Section J. |
| 8 | **Browser/device spot checks** | WebKit validation, landscape orientation, small/large viewport edge cases. |
| 9 | **Final decision** | Review all results. Mark pass/fail per Section P rules. |

## O. Evidence Requirements

Before marking a regression cycle as complete, the following evidence must be recorded:

| Evidence | Required |
| :--- | :--- |
| Date tested | Yes |
| Tester name or initials | Yes |
| Branch and commit hash | Yes |
| Device/viewport tested | Yes |
| Browser name and engine | Yes |
| Automated test command output | Yes (for automated phases) |
| Screenshots/videos | Required for any Fail or Pass With Notes |
| Console error log | Required for any Fail |
| Notes for Pass With Notes | Yes — describe issue and confirm non-blocking |

## P. Release Gate Rules

| Severity | Rule |
| :--- | :--- |
| **P0 regression** | Blocks release. Must be fixed before shipping. |
| **P1 regression** | Blocks release. Must be fixed before shipping. |
| **P2 regression** | Requires explicit approval from project lead to ship. Must be documented. |
| **P3 regression** | May ship with notes. Must be documented in release notes. |
| **Missing coverage** | Must be documented. Missing coverage for a core flow (auth, games, fields, notifications) blocks release unless explicitly approved. |
| **Any auth failure** | Blocks release. |
| **Any game flow failure** | Blocks release. |
| **Any notification state failure** | Blocks release. |

## Q. Re-run Triggers

This regression plan must be re-executed after changes to any of the following:

| Trigger | Affected Sections |
| :--- | :--- |
| Auth UI or auth logic | E (Auth), J (Cross-flows) |
| Game create/join/leave/extend/close logic | F (Games), J (Cross-flows) |
| Field details/add/report field flows | G (Fields), J (Cross-flows) |
| Notifications inbox/preferences/badge/push | I (Notifications), J (Cross-flows) |
| Modal CSS (positioning, sizing, overflow, z-index) | E, F, G, I (all modal flows) |
| Map layout or controls | H (Navigation), G (Fields) |
| Navigation/routing changes | H (Navigation), J (Cross-flows) |
| Mobile viewport/layout CSS (media queries, breakpoints) | All sections |
| Browser compatibility fixes | All sections |
| Touch target size changes | E, F, G, I (all interactive elements) |
| New form fields added to any modal | G (Fields), F (Games) |
| i18n/RTL changes | H (Navigation) |
