# Mobile User Journey Testing Results

## A. Purpose

This document records execution of the mobile user journey validation plan created by ISSUE-168. It distinguishes complete journey validation from supporting feature, mocked-route, layout, and browser-engine tests.

No journey is marked Pass unless the complete goal was actually validated against all applicable plan criteria.

## B. Dependency

| Item | Result |
| :--- | :--- |
| ISSUE-168 merged to `main` | Yes — commit `206a80f` |
| Journey plan | `docs/mobile-user-journey-validation-plan.md` |
| ISSUE-168 decision record | Present in `docs/product-decisions.md` |
| Plan used as source of truth | Yes |

## C. Test Date / Branch / Commit

| Field | Value |
| :--- | :--- |
| Date | 2026-06-28 |
| Branch | `issue-169-execute-mobile-user-journey-testing` |
| Commit tested | `206a80fe2ebca06107f055b4cf88e748e728081e` (`main`, including ISSUE-168) |
| Tester | Codex execution environment on Windows |
| Notes | Documentation/execution only. No application code or test files changed. |

## D. Test Environment

| Component | Value |
| :--- | :--- |
| Automated frontend | Local Vite server started by Playwright at `http://127.0.0.1:5173` |
| Visual frontend | Local Vite server at `http://127.0.0.1:5174` |
| Backend | Not started or authenticated; journey tests used mocked routes and localStorage identities |
| Auth/test accounts | No real new-user, returning-player, organizer, participant, notification-recipient, or admin credentials supplied |
| Safe mutable data | No approved field/game/admin moderation records supplied |
| Browser engines | Playwright Chromium and Playwright WebKit simulation |
| Automated viewports | 320px iPhone SE width; 360x640 Android Small; 390x844 iPhone Large; 667x375 landscape; 768x1024 iPad portrait; 1024x768 and 1180x820 iPad landscape; 1366x1024 iPad Pro landscape; other per-test defaults |
| Direct visual viewports | 360x640 Android Small and 768x1024 Tablet/iPad |
| Real devices | None |
| Samsung Internet | Not directly tested; Chromium engine evidence only |
| Data method | Existing Playwright tests mock authentication, API responses, fields, games, notifications, and admin data |

The live local login and registration screens were visually inspected. Google Sign-In returned 403 because `http://127.0.0.1:5174` is not an allowed origin for the configured client. No credential-based test account or working local backend was available to continue into authenticated journeys.

## E. Journey Status Summary

| Journey ID | Journey name | User type | Status | Blocking issue? | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| J-01 | New User Joins a Game | New user / non-organizer | **Blocked** | Yes | Registration UI and mocked join/logout pass, but no real backend/account/game or real-device validation. |
| J-02 | Returning Player Joins and Leaves Game | Returning player / non-organizer | **Blocked** | Yes | Mocked join/leave/logout pass; no real credentials, organizer/game data, or physical device. |
| J-03 | Game Organizer Lifecycle | Organizer | **Blocked** | Yes | Mocked create/extend/close pieces pass; no two-user environment or safe game lifecycle data. |
| J-04 | Logged-Out Visitor Attempts Protected Action | Logged-out visitor → player | **Blocked** | Yes | Local app shows authentication before map access; no valid login was available to validate the supported recovery path. |
| J-05 | Field Report / Add Field | Field reporter | **Blocked** | Yes | Mocked modal/report checks pass; no authenticated backend, safe submission data, or real keyboard/location interaction. |
| J-06 | Notification Recipient | Notification recipient | **Blocked** | Yes | Mocked badge/read/read-all checks pass; no real recipient/session or complete touch journey. |
| J-07 | Scheduled/Future Game | Organizer + participant | **Blocked** | Yes | Future controls/upcoming state pass in mocks; real creation, time-zone display, and future join/leave could not be completed. |
| J-08 | Admin/Moderator Mobile | Admin/moderator | **Blocked** | Yes | Mocked admin access/tabs pass; no real admin account, approved safe moderation record, or physical iPad. |
| J-09 | Mobile Navigation Resilience | Visitor + authenticated/admin | **Blocked** | Yes | Simulated surfaces/layout pass, but authenticated/admin traversal, real rotation/browser chrome, and Samsung Internet were unavailable. |

## F. Journey 1 — New User Joins a Game

**Status: Blocked**

| Step | Result | Evidence/notes |
| :--- | :--- | :--- |
| Register | Partial | Registration form opened and rendered cleanly at 360x640 and 768x1024. Submit reachability passed automated layout tests. No real backend account was created. |
| Login | Blocked | No credential test account/backend. Google Sign-In rejected localhost origin with 403. |
| Open Map / Field | Blocked | Local app remained at authentication; mocked map/field tests passed separately. |
| Join / confirm joined | Blocked | Mocked join and participant refresh passed, but no real new-user session/game existed. |
| Logout | Supporting test Pass | Existing logout test cleared mocked auth at 360x640 and 390x844. Not reached through a real new-user journey. |

Expected result was not fully validated. J-01 cannot be marked Pass.

## G. Journey 2 — Returning Player Joins and Leaves Game

**Status: Blocked**

Existing tests validated mocked join, participant refresh, leave, refreshed state, and logout in Chromium and WebKit. The complete sequence could not be executed because no returning-player credentials, real backend, joinable game, organizer session, or physical device was available.

Expected result was not fully validated. J-02 cannot be marked Pass.

## H. Journey 3 — Game Organizer Lifecycle

**Status: Blocked**

Existing tests validated mocked create-game form behavior, active-game refresh, participant visibility, organizer-only extend/close controls, extend request, close request, and cleared active state. A complete lifecycle was not executed because no organizer and participant accounts, backend, safe field, or mutable game data were available.

Expected result was not fully validated. J-03 cannot be marked Pass.

## I. Journey 4 — Logged-Out Visitor Attempts Protected Action

**Status: Blocked**

The local application was opened with clean browser state. Language selection led to the authentication screen, whose text states that sign-in is required to open and join games. The map/field therefore could not be reached while logged out in this environment, and no valid login was available to test the supported continuation/return path.

Automated admin-route tests confirmed unauthenticated users see login and regular users cannot access admin. They do not prove the full Join/Create protected-action journey.

Expected result was only partially validated. J-04 cannot be marked Pass.

## J. Journey 5 — Field Report / Add Field Journey

**Status: Blocked**

Mocked tests validated field-details navigation, report submit/cancel, Add Field modal opening, scrolling, close behavior, location-map layout, and submit reachability. Explicit real required-field validation, backend success confirmation, safe record creation, physical keyboard, and touch location selection could not be executed.

Expected result was not fully validated. J-05 cannot be marked Pass.

## K. Journey 6 — Notification Recipient Journey

**Status: Blocked**

Mocked tests validated unread badge, single read, badge decrement, read-all, legacy read state, preferences, notification matching, and scheduled reminders. No real recipient account or authenticated journey was available, and push delivery was not configured or claimed.

Expected result was not fully validated. J-06 cannot be marked Pass.

## L. Journey 7 — Scheduled/Future Game Journey

**Status: Blocked**

Mocked tests validated future-game form controls, upcoming-state rendering, absence of active controls, and scheduled reminder display. No real organizer/participant accounts or backend existed to create a future game, verify the displayed local time, join it, and leave it.

Expected result was not fully validated. J-07 cannot be marked Pass.

## M. Journey 8 — Admin/Moderator Mobile Journey

**Status: Blocked**

Mocked tests validated admin authorization, regular-user rejection, stats, fields, games, users, and field-report queue rendering. No real admin credentials, safe pending-field record, mutation authorization, or physical iPad was available. No approve/reject action was performed.

Per the ISSUE-168 rule, unavailable admin access/test data must be Blocked, not Pass.

## N. Journey 9 — Mobile Navigation Resilience Journey

**Status: Blocked**

Automated simulation validated map and field surfaces, modal close controls, nested scrolling, portrait/landscape layouts, no horizontal overflow, floating controls, RTL/LTR, notifications, and admin layout. Direct visual inspection showed clean login/register rendering at 360x640 and 768x1024.

The complete navigation journey could not be performed because authenticated and admin access were unavailable. Physical rotation, real browser chrome, soft keyboard, and direct Samsung Internet behavior were also unavailable. J-09 cannot be marked Pass.

## O. Automated Test Execution

| Command | Engine | Result | Count | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `npx playwright test tests/mobile-regression-flows.spec.js tests/game-close.spec.js tests/field-navigation.spec.js tests/notifications.spec.js tests/notification-matching.spec.js tests/admin-panel.spec.js tests/modal-usability.spec.js tests/small-android-layout.spec.js tests/ipad-layout.spec.js tests/mobile-scrolling.spec.js tests/floating-buttons.spec.js tests/i18n-rtl-ltr.spec.js --project=chromium --reporter=line` | Chromium | Pass | 86 passed, 0 failed | Existing mock-backed journey support suite. |
| Same 12 files with temporary WebKit runner config | WebKit | Pass With Notes | 84 passed, 2 failed | Failures reproduce known P3 test limitations COMPAT-002 and WEBKIT-TIMING-001. Temporary config removed. |
| `npx playwright test tests/field-navigation.spec.js:269 tests/mobile-scrolling.spec.js:140 --config=playwright.webkit.issue169.config.js --workers=1 --reporter=line` | WebKit | Expected known failures reproduced | 0 passed, 2 failed | Serial confirmation of the same known failure signatures; no new product defect inferred. |

An initial Chromium command using `--browser=chromium` executed zero tests because the repository config defines projects; it was corrected to `--project=chromium` and is not counted as a test result.

## P. Manual / Visual Validation Matrix

| Journey | User type | Device category | Browser/engine | Orientation | Status | Evidence/notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| J-04 auth entry | Logged-out visitor | Android Small 360x640 | Chromium | Portrait | Pass With Notes | Language choice and login screen rendered; no clipping/overflow. Map is unavailable before auth. |
| J-01 registration entry | New user | Android Small 360x640 | Chromium | Portrait | Pass With Notes | Registration fields and Create Account control present/reachable; submission blocked by unavailable backend/account setup. |
| J-01 registration entry | New user | Tablet/iPad 768x1024 | Chromium | Portrait | Pass With Notes | Registration form visually readable and fully visible. |
| J-01 through J-08 complete authenticated journeys | All authenticated types | Required mobile categories | Chromium/WebKit | Portrait/landscape | Blocked | No real credentials/backend/safe data. |
| J-08 admin moderation | Admin/moderator | Tablet/iPad | WebKit/Safari | Portrait/landscape | Blocked | No admin account, safe moderation data, or physical iPad. |
| J-09 real-device resilience | Visitor/authenticated/admin | iPhone/iPad/Android/Samsung | Safari/Chrome/Samsung Internet | Portrait/landscape | Blocked | No physical devices; browser chrome, keyboard, real rotation, and direct Samsung Internet not validated. |

Playwright screenshots were inspected during execution and removed afterward; no failure screenshot claims are made for product behavior that was not reached.

## Q. Issues Found

| ID | Severity | Journey | Description | Reproduction steps | Status | Blocking? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| JOURNEY-SETUP-001 | P1 coverage blocker | J-01–J-09 | No working backend plus role-specific test credentials and safe mutable game/field/notification/admin data were available. | Start local frontend; select language; attempt to proceed beyond authentication. | Open setup blocker | Yes |
| JOURNEY-DEVICE-001 | P1 coverage blocker | J-01, J-05, J-08, J-09 and cross-journey criteria | No physical iOS/Android/Samsung devices were available for keyboard, browser chrome, touch, rotation, safe-area, or direct Samsung Internet checks required by the plan. | Compare available environment with plan Sections D and P. | Open coverage blocker | Yes |
| JOURNEY-AUTH-001 | P2 environment | J-01, J-04 | Google Sign-In rejects local visual-test origin with HTTP 403 / origin-not-allowed. | Open `http://127.0.0.1:5174`, choose language, observe Google identity console errors. | Open environment limitation | Yes for Google-auth path |
| COMPAT-002 | P3 known test limitation | J-05, J-09 | WebKit reports empty computed `overscroll-behavior` shorthand although the property is known to work functionally. | Run `mobile-scrolling.spec.js:140` in WebKit. | Previously documented; unchanged | No |
| WEBKIT-TIMING-001 | P3 known test limitation | J-02, J-03, J-09 | Cached-field heading is not visible within the WebKit test's 5-second expectation. | Run `field-navigation.spec.js:269` in WebKit. | Previously documented; unchanged | No |

No new P0/P1 product defect was demonstrated. The P1 entries are required coverage/setup blockers, not application defect findings.

## R. Blocker Status

**Blockers remain and ISSUE-169 cannot be closed.**

Required setup/access prevents complete execution:

- real backend and role-specific accounts;
- deterministic, safe game/field/notification/admin data;
- approved cleanup/mutation path;
- physical iOS, Android, iPad, and Samsung coverage for required real-device criteria.

## S. Final Journey Decision

**BLOCKED**

All nine required journeys are present, but all nine remain Blocked. Supporting automation cannot confer journey Pass under ISSUE-168.

## T. Release Gate Decision

**Mobile user journey gate: Blocked**

Reason: no complete required journey passed against the plan's real authentication, safe data, end-to-end state, and real-device criteria. Chromium automation passed 86/86 and WebKit passed 84/86 with two known non-blocking P3 test limitations, but that evidence is partial.

ISSUE-169 is not ready to close until the blockers in Section R are resolved and all nine journeys are re-executed.
