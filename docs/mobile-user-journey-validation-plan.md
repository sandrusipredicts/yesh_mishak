# Mobile User Journey Validation Plan

## A. Purpose

Feature regression proves that individual controls and states work. Journey validation proves that a mobile user can move across those features and complete a real goal without losing authentication, context, navigation, or state.

A journey passes only when its complete user goal is completed on mobile from the stated starting condition through final confirmation. Isolated, mocked, or layout test passes are supporting evidence, not a journey pass.

## B. Scope

This plan includes the new user, returning user, logged-out viewer, player joining, game organizer, field reporter/add field, notification recipient, scheduled/future game, admin/moderator, and mobile navigation journeys. Admin is included because an authenticated admin page exists. Scheduled games are included because future creation and upcoming state are supported.

The journeys group the authentication, game, field, navigation, notification, scheduled-game, and admin checks from ISSUE-166 and ISSUE-167 into complete user goals. This document defines future validation; it does not claim that these complete journeys have passed.

## C. User Types Covered

| User type | Definition | Journeys |
| :--- | :--- | :--- |
| Logged-out visitor | User without an authenticated session who may view the map and encounter protected actions. | J-04, J-09 |
| New registered user | User who creates an account, authenticates, and uses the app for the first time. | J-01 |
| Returning authenticated player | Existing player who signs in and resumes normal use. | J-02 |
| Game organizer | Authenticated user who creates and manages a game. | J-03, J-07 |
| Non-organizer participant | Player who joins another user's game and must not receive organizer controls. | J-01, J-02, J-07 |
| Field reporter | Authenticated user who submits a field addition/report request. | J-05 |
| Notification recipient | Authenticated user with seeded or legitimately triggered notifications. | J-06 |
| Admin/moderator | Authorized administrator who views admin data and, with safe data, moderates pending fields. | J-08 |

One account may represent multiple types, but evidence must identify the type and permissions exercised.

## D. Required Mobile Environments

| Category | Baseline | Browser/engine | Requirement |
| :--- | :--- | :--- | :--- |
| Android Small | 360x640 / Galaxy A14 class | Chromium | Required |
| Android Large | 412x915 / Pixel 7 class | Chromium | Required |
| iPhone Small | 375x667 / iPhone SE class | WebKit/Safari | Required |
| iPhone Large | 390x844 / iPhone 14 class | WebKit/Safari | Required |
| Tablet / iPad | 768x1024 / iPad class | WebKit/Safari | Required |
| Samsung Internet | 412x915 / Samsung Galaxy class | Direct Samsung Internet; Chromium proxy when unavailable | Required, with proxy limitation recorded |

Chromium and WebKit/Safari coverage are required. Simulation supplies engine evidence, but real devices are required for conclusive keyboard, browser-chrome, safe-area, touch, permission, and Samsung-specific behavior. Chromium proxy evidence must not be called direct Samsung Internet coverage.

## E. Journey Statuses

| Status | Meaning |
| :--- | :--- |
| **Not Tested** | Complete journey not executed in this cycle. |
| **Pass** | Complete goal and every pass criterion satisfied with evidence. |
| **Pass With Notes** | Goal completed with only documented, non-blocking P3 observations. |
| **Fail** | Goal or required criterion prevented by a product defect. |
| **Blocked** | Access, data, device, environment, or supported behavior prevented execution; reason recorded. Blocked is never Pass. |

## F. Journey Template

| Field | Required content |
| :--- | :--- |
| Journey ID | Stable plan ID |
| Journey name | User goal |
| User type | Role and permission exercised |
| Starting condition | Authentication, screen, and state before step 1 |
| Preconditions / test data | Accounts, fields, games, notifications, and cleanup data |
| Steps | Numbered uninterrupted actions |
| Expected result | End-to-end outcome |
| Mobile risks | Journey-specific mobile failure modes |
| Pass criteria | Observable conditions required for Pass |
| Failure criteria | Observable conditions producing Fail |
| Evidence required | Execution metadata and journey-specific proof |
| Related automated tests | Existing tests only; supporting coverage is not a journey result |
| Manual validation required? | Yes/No and reason |

## G. Journey 1 — New User Joins a Game

| Field | Definition |
| :--- | :--- |
| Journey ID | J-01 |
| Journey name | New User Joins a Game |
| User type | New registered user; non-organizer participant |
| Starting condition | Logged out; an available game exists at a known field; unique registration data is available. |
| Preconditions / test data | Disposable account data; known field and non-full active game created by another user; credential login available. |
| Steps | 1. Register. 2. Login. 3. Open Map. 4. Open Field. 5. Join Game. 6. Confirm joined and participant state. 7. If configured and applicable, inspect notification/badge behavior. 8. Logout. |
| Expected result | New user can complete onboarding/auth and join an available game on mobile. |
| Mobile risks | Keyboard covers fields/submit; auth controls clip; marker is hard to tap; field/join control is unreachable; joined state is stale; badge overlaps; logout is hidden. |
| Pass criteria | Registration and login succeed; map/field remain usable; join succeeds once; joined state is visible; logout clears session; Section P passes. Optional notification behavior is evaluated only when configured. |
| Failure criteria | Registration/login, navigation, join, state confirmation, or logout fails; session is lost; Section Q applies. Missing environment capability is Blocked. |
| Evidence required | Execution record; registration-complete, authenticated-field, joined-state, and logged-out screenshots/video; participant/API evidence where available; linked issue for failure. |
| Related automated tests | `small-android-layout.spec.js`, `ipad-layout.spec.js`, `game-close.spec.js`, `mobile-regression-flows.spec.js`, `floating-buttons.spec.js` |
| Manual validation required? | Yes — no test executes real registration/login through join and logout as one journey; real auth and keyboard remain manual. |

## H. Journey 2 — Returning Player Joins and Leaves Game

| Field | Definition |
| :--- | :--- |
| Journey ID | J-02 |
| Journey name | Returning Player Joins and Leaves Game |
| User type | Returning authenticated player; non-organizer participant |
| Starting condition | Logged out; existing credentials and a joinable game created by another user exist. |
| Preconditions / test data | Existing player; known field; game below capacity; organizer/fixture available to verify participants. |
| Steps | 1. Login. 2. Open Map. 3. Open Field. 4. Join Game. 5. Confirm game/player state. 6. Leave Game. 7. Confirm state updates. 8. Logout. |
| Expected result | Returning player can join and leave without layout or state problems. |
| Mobile risks | Join/leave control clips; duplicate taps; participant list is stale; panel scrolling traps user; logout is unreachable. |
| Pass criteria | Login, join, leave, both state transitions, and logout complete; organizer controls never appear; no duplicate membership; Section P passes. |
| Failure criteria | Any action/state update fails; organizer controls appear; auth breaks; user is trapped; Section Q applies. |
| Evidence required | Execution record; before/joined/left screenshots/video; participant evidence; logged-out end state; linked issue for failure. |
| Related automated tests | `game-close.spec.js`, `mobile-regression-flows.spec.js`, `field-navigation.spec.js`, `modal-usability.spec.js` |
| Manual validation required? | Yes — join, leave, refresh, and logout are covered separately, not in one real session. |

## I. Journey 3 — Game Organizer Lifecycle

| Field | Definition |
| :--- | :--- |
| Journey ID | J-03 |
| Journey name | Game Organizer Lifecycle |
| User type | Game organizer |
| Starting condition | Logged out; organizer/participant accounts exist; target field has no conflicting active game. |
| Preconditions / test data | Safe field; two accounts or supported participant fixture; valid game values; cleanup permission. |
| Steps | 1. Login. 2. Open Map. 3. Open Field. 4. Create Game. 5. Wait for or simulate player join with a supported fixture. 6. Confirm organizer sees participant state. 7. Extend Game. 8. Confirm extended state. 9. Close Game. 10. Confirm active state clears. |
| Expected result | Organizer can manage full game lifecycle on mobile. |
| Mobile risks | Form/submit hidden by keyboard; selectors unusable; participant refresh stale; organizer controls clip; repeat taps duplicate requests; state confirmation unreachable. |
| Pass criteria | One game is created; another player joins; participant is shown; extend and close succeed and refresh state; Section P passes. |
| Failure criteria | Create, join visibility, extend, close, or refresh fails; unauthorized controls appear; wrong game changes; Section Q applies. |
| Evidence required | Execution record; video preferred; created, joined, extended, and closed states; request/state evidence; test-user roles; linked issue for failure. |
| Related automated tests | `mobile-regression-flows.spec.js`, `game-close.spec.js`, `modal-usability.spec.js`, `notification-matching.spec.js` |
| Manual validation required? | Yes — mocked tests validate parts, not the uninterrupted multi-user lifecycle. |

## J. Journey 4 — Logged-Out Visitor Attempts Protected Action

| Field | Definition |
| :--- | :--- |
| Journey ID | J-04 |
| Journey name | Logged-Out Visitor Attempts Protected Action |
| User type | Logged-out visitor, then returning player |
| Starting condition | Session/storage cleared; app opened logged out. |
| Preconditions / test data | Field with joinable game or Create Game availability; valid player credentials. |
| Steps | 1. Open app logged out. 2. Open Map. 3. Open Field. 4. Attempt Join Game or Create Game. 5. Confirm authentication requirement and no mutation. 6. Login. 7. Continue the intended action if supported; otherwise return through the supported route and complete it, recording the path. |
| Expected result | Protected actions are unavailable without authentication and user is guided correctly. |
| Mobile risks | Prompt is off-screen; modal layering traps user; request fires before auth; login loses context without guidance; keyboard hides submit. |
| Pass criteria | No logged-out mutation; clear auth guidance; login succeeds; supported path back is usable; Section P passes. Automatic continuation is not required unless the product provides it. |
| Failure criteria | Protected mutation is allowed; guidance is missing; auth breaks; user cannot return through a supported path; Section Q applies. |
| Evidence required | Execution record; cleared-auth proof; attempted-action/auth-guidance/authenticated-completion screenshots/video; linked issue for failure. |
| Related automated tests | `admin-panel.spec.js`, `mobile-regression-flows.spec.js`, `small-android-layout.spec.js` |
| Manual validation required? | Yes — Join/Create interception and supported post-login routing need journey validation. |

## K. Journey 5 — Field Report / Add Field Journey

| Field | Definition |
| :--- | :--- |
| Journey ID | J-05 |
| Journey name | Field Report / Add Field |
| User type | Field reporter |
| Starting condition | Logged out or at login; safe reporter account and non-production data exist. |
| Preconditions / test data | Valid account; unique field/report data; known coordinates; safe submission and cleanup/moderation path. |
| Steps | 1. Login. 2. Open Map. 3. Open Add/Report Field modal. 4. Fill field form. 5. Trigger and inspect required-field validation. 6. Correct form. 7. Submit request/report. 8. Confirm success message. 9. Close modal. |
| Expected result | User can report/add a field on mobile and is not trapped in modal scrolling. |
| Mobile risks | Keyboard/location map consumes viewport; validation overlaps; close/submit is lost after scroll; location selection is hard; success is below fold; nested modal traps user. |
| Pass criteria | Validation is readable; valid inputs/location submit once; success is visible; modal closes to a usable map; Section P passes. |
| Failure criteria | Invalid form submits; valid form cannot; duplicate request; success absent; close/submit unreachable; user trapped; Section Q applies. |
| Evidence required | Execution record; validation, completed form (no sensitive data), success, and closed-modal screenshots/video; record ID if available; linked issue for failure. |
| Related automated tests | `modal-usability.spec.js`, `ipad-layout.spec.js`, `small-android-layout.spec.js`, `field-navigation.spec.js`, `mobile-scrolling.spec.js` |
| Manual validation required? | Yes — keyboard, real map interaction, explicit validation/success, and safe submission are not one automated journey. |

## L. Journey 6 — Notification Recipient Journey

| Field | Definition |
| :--- | :--- |
| Journey ID | J-06 |
| Journey name | Notification Recipient |
| User type | Notification recipient |
| Starting condition | Logged out; account has at least two unread in-app notifications or a supported trigger can create them. |
| Preconditions / test data | Recipient; deterministic fixture/trigger; known unread count. Push delivery is excluded unless configured on a real device. |
| Steps | 1. Login. 2. Trigger or simulate notification. 3. Confirm badge. 4. Open inbox/modal. 5. Read one notification. 6. Confirm unread count updates. 7. Read all. 8. Confirm zero unread and empty/read state. 9. Close/reopen to confirm consistency. |
| Expected result | Notification state stays consistent across badge, inbox, read, and read-all actions. |
| Mobile risks | Badge overlaps; close blocked by toolbar; content cannot scroll; update race; badge/list disagree; empty state clips. |
| Pass criteria | Initial count is correct; single read decrements once; read-all clears unread; reopen stays consistent; modal scrolls/closes; Section P passes. |
| Failure criteria | Counts disagree/revert; read-all leaves unread; modal cannot close; item cannot be read; Section Q applies. |
| Evidence required | Execution record; before/single-read/read-all/reopen screenshots/video; fixture description; linked issue for failure. |
| Related automated tests | `notifications.spec.js`, `notification-matching.spec.js`, `ipad-layout.spec.js`, `small-android-layout.spec.js` |
| Manual validation required? | Yes — full touch/modal sequence is manual; real push requires separate real-device evidence if claimed. |

## M. Journey 7 — Scheduled/Future Game Journey

| Field | Definition |
| :--- | :--- |
| Journey ID | J-07 |
| Journey name | Scheduled/Future Game |
| User type | Game organizer and non-organizer participant |
| Starting condition | Organizer authenticated; field supports future-game creation; second account exists. |
| Preconditions / test data | Safe field; future date/time; two users; scheduled-game behavior enabled. |
| Steps | 1. Login. 2. Open Field. 3. Create Future Game. 4. Confirm scheduled time/upcoming state. 5. Use participant session. 6. Open same Field. 7. Join Future Game if the UI supports it. 8. Leave Future Game if supported. 9. Confirm each state. |
| Expected result | Future game behavior works separately from active games. |
| Mobile risks | Date/time controls unusable; locale/time zone ambiguous; active/upcoming controls confused; time clips; state stale. |
| Pass criteria | Future creation succeeds; displayed time matches submitted local intent; upcoming differs from active; exposed join/leave actions update state; active-only controls stay hidden; Section P passes. |
| Failure criteria | Wrong time/state; active controls on upcoming game; displayed join/leave action fails; Section Q applies. Unsupported join/leave is Blocked with observed reason, not Pass. |
| Evidence required | Execution record; submitted/displayed date/time and zone; upcoming and participant-state screenshots/video; linked issue for failure. |
| Related automated tests | `mobile-regression-flows.spec.js`, `game-close.spec.js`, `notifications.spec.js` |
| Manual validation required? | Yes — supported future join/leave and time-zone presentation are unconfirmed. |

## N. Journey 8 — Admin/Moderator Mobile Journey

| Field | Definition |
| :--- | :--- |
| Journey ID | J-08 |
| Journey name | Admin/Moderator Mobile |
| User type | Admin/moderator |
| Starting condition | Logged out; authorized admin account exists. |
| Preconditions / test data | Admin credentials; pending-field fixture; explicit permission to approve/reject it. |
| Steps | 1. Login as admin. 2. Open admin page. 3. View pending fields. 4. Approve/reject only if safe test data and authorization exist. 5. View users, stats, and games tabs. |
| Expected result | Admin can complete basic moderation/admin flow on mobile. |
| Mobile risks | Wide tables create unusable page scrolling; tabs/actions clip; target is ambiguous; redirects loop; loading covers controls. |
| Pass criteria | Page and named tabs load; authorized safe action updates once; tables use supported local scrolling without trapping navigation; Section P passes. |
| Failure criteria | Required view/action fails; wrong record changes; controls unreachable; Section Q applies. Without account, safe data, or permission, mark Blocked, never Pass. |
| Evidence required | Redacted execution record; page/tab/moderation screenshots/video; test record ID; permission or blocker note; linked issue for failure. |
| Related automated tests | `admin-panel.spec.js`, `mobile-scrolling.spec.js`, `i18n-rtl-ltr.spec.js` |
| Manual validation required? | Yes — tests cover auth/tab loading, not real moderation or tablet touch/table usability. |

## O. Journey 9 — Mobile Navigation Resilience Journey

| Field | Definition |
| :--- | :--- |
| Journey ID | J-09 |
| Journey name | Mobile Navigation Resilience |
| User type | Logged-out visitor and authenticated user; admin segment when available |
| Starting condition | Clean app load on each required environment. |
| Preconditions / test data | Standard user; field details; notifications; admin where available; rotatable viewport/device. |
| Steps | 1. Open app. 2. Navigate among map, field details, child dialogs/modals, notifications, and admin if available. 3. Close every modal using its visible supported control. 4. Reopen surfaces to prove recovery. 5. Rotate where applicable. 6. Recheck critical close/navigation actions. 7. Confirm no page horizontal scrolling. 8. Confirm map remains usable and no trapped state. |
| Expected result | User can move through the app and recover from every screen/modal. |
| Mobile risks | Layering blocks close; scroll lock persists; floating buttons overlap; rotation loses state; browser chrome hides actions; RTL misaligns; admin overflow leaks. |
| Pass criteria | Every entered surface can be exited; map recovers; rotation keeps critical controls; no unintended page horizontal scrolling (local admin-table scrolling is allowed); no trap/runtime error; Section P passes. |
| Failure criteria | Surface cannot close; stale backdrop/lock; critical action clips; map unusable; normal use requires page horizontal scrolling; user trapped; Section Q applies. |
| Evidence required | Execution record; navigation/rotation video preferred; layout screenshots; orientation sequence; error console log; linked issue for failure. |
| Related automated tests | `field-navigation.spec.js`, `modal-usability.spec.js`, `floating-buttons.spec.js`, `small-android-layout.spec.js`, `mobile-scrolling.spec.js`, `ipad-layout.spec.js`, `i18n-rtl-ltr.spec.js`, `admin-panel.spec.js` |
| Manual validation required? | Yes — real rotation, browser chrome, touch recovery, and complete cross-surface sequence are not fully simulated. |

## P. Cross-Journey Pass Criteria

A journey passes only if:

- The user goal is completed end-to-end.
- No critical button is hidden or clipped.
- No modal traps the user.
- Forms are usable with the mobile keyboard.
- Map remains usable.
- State updates correctly after actions.
- Hebrew/RTL layout remains readable.
- No blocking console/runtime errors occur.
- Browser chrome does not hide critical actions.

## Q. Journey Failure Criteria

A journey fails if:

- User cannot complete the goal.
- Authentication state breaks.
- Join/create/extend/close actions fail.
- Notification read state becomes inconsistent.
- Modal cannot be closed.
- Submit button becomes unreachable.
- Horizontal scrolling is required.
- User gets trapped.
- Critical text overlaps or becomes unreadable.

Environment/access limitations are Blocked. Unsupported optional behavior is not invented; notes must distinguish unsupported/not exposed from a defect.

## R. Automated Test Mapping

| Journey | Related existing test files | Coverage | Manual? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| J-01 New User | `small-android-layout.spec.js`, `ipad-layout.spec.js`, `game-close.spec.js`, `mobile-regression-flows.spec.js` | Partial | Yes | Registration reachability, join, logout separate/mock-backed; no real-auth chain. |
| J-02 Returning Player | `game-close.spec.js`, `mobile-regression-flows.spec.js`, `field-navigation.spec.js` | Partial | Yes | Join/leave refresh and logout are separate. |
| J-03 Organizer | `mobile-regression-flows.spec.js`, `game-close.spec.js`, `notification-matching.spec.js` | Partial | Yes | Parts covered; no two-user lifecycle. |
| J-04 Logged-Out Visitor | `admin-panel.spec.js`, `mobile-regression-flows.spec.js` | Partial | Yes | Admin redirect/logout protection covered; Join/Create recovery path is not. |
| J-05 Field Report/Add | `modal-usability.spec.js`, `ipad-layout.spec.js`, `small-android-layout.spec.js`, `field-navigation.spec.js`, `mobile-scrolling.spec.js` | Partial | Yes | Strong modal/report coverage; validation, success, keyboard, real submission remain. |
| J-06 Notifications | `notifications.spec.js`, `notification-matching.spec.js`, `ipad-layout.spec.js` | Partial | Yes | State checks strong; full mobile sequence/real push not covered. |
| J-07 Scheduled Game | `mobile-regression-flows.spec.js`, `game-close.spec.js`, `notifications.spec.js` | Partial | Yes | Creation/upcoming/reminder covered; future join/leave unconfirmed. |
| J-08 Admin | `admin-panel.spec.js`, `mobile-scrolling.spec.js`, `i18n-rtl-ltr.spec.js` | Partial | Yes | Auth/tabs covered; real safe moderation remains. |
| J-09 Navigation | `field-navigation.spec.js`, `modal-usability.spec.js`, `floating-buttons.spec.js`, `small-android-layout.spec.js`, `mobile-scrolling.spec.js`, `ipad-layout.spec.js`, `i18n-rtl-ltr.spec.js`, `admin-panel.spec.js` | Partial | Yes | Surfaces covered separately; real chrome/rotation/recovery remain. |

No existing test provides Full end-to-end coverage for a journey. No new tests are required by ISSUE-168.

## S. Manual Validation Matrix

| Journey | User type | Device category | Browser/engine | Orientation | Status | Evidence | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| J-04 | Logged-out visitor → player | Android Small | Chromium | Portrait | Not Tested | — | Auth/protection smoke |
| J-01 | New user | iPhone Small | WebKit/Safari | Portrait | Not Tested | — | Real keyboard preferred |
| J-02 | Returning non-organizer | Android Large | Chromium | Portrait | Not Tested | — | Verify both transitions |
| J-03 | Organizer | iPhone Large | WebKit/Safari | Portrait | Not Tested | — | Needs second player |
| J-05 | Field reporter | Android Small | Chromium | Portrait | Not Tested | — | Keyboard/location touch |
| J-06 | Notification recipient | iPhone Large | WebKit/Safari | Portrait | Not Tested | — | In-app; push only if configured |
| J-07 | Organizer + participant | Android Large | Chromium | Portrait | Not Tested | — | Record zone/support |
| J-08 | Admin/moderator | Tablet / iPad | WebKit/Safari | Portrait + Landscape | Not Tested | — | Block without safe access/data |
| J-09 | Visitor + authenticated user | Tablet / iPad | WebKit/Safari | Portrait + Landscape | Not Tested | — | Rotation and all surfaces |
| J-09 | Visitor + authenticated user | Samsung Internet / Android Large proxy | Samsung Internet / Chromium proxy | Portrait + Landscape | Not Tested | — | Label proxy honestly |

Every Section D environment must appear in a completed row and every journey needs a current status. P0/P1-risk journeys should be spot-checked in Chromium and WebKit.

## T. Execution Order

1. Logged-out visitor
2. New user
3. Returning player
4. Game organizer
5. Field report/add field
6. Notification recipient
7. Scheduled/future game
8. Admin/moderator
9. Navigation resilience

Stop and preserve evidence when a P0/P1 failure is found.

## U. Evidence Requirements

Every execution records:

- Date
- Tester
- Branch/commit
- Device/viewport
- Browser/engine
- Test user type
- Journey ID and status
- Starting condition and test-data identifiers
- Screenshots/videos for failures
- Notes for Pass With Notes
- Linked issue for any failure

Avoid credentials/personal data. Include automated output/CI links when cited. Blocked records state the blocker, affected steps, and unblocking need.

## V. Release Gate Rules

- P0/P1 journey failure blocks release.
- P2 requires explicit approval.
- P3 may ship with documented notes.
- Missing journey coverage is Blocked or Not Tested.
- Every supported user type has at least one defined journey.
- Isolated feature tests cannot confer a journey Pass.
- Required Blocked/Not Tested journeys need explicit release approval; P0/P1-risk missing coverage blocks.
- Admin is Blocked, not Pass, without access or safe data.

## W. Re-run Triggers

Repeat journey validation after changes to:

- Authentication
- Game lifecycle
- Field details/add/report flow
- Notifications
- Navigation
- Mobile layout/modals
- Map interactions
- Admin/moderation
- Scheduled games
- Browser compatibility fixes

Re-run affected journeys plus J-09. Re-run all journeys when shared authentication, navigation, layout, or browser changes may cross user types.
