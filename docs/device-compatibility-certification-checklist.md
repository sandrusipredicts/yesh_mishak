# Device Compatibility Certification Checklist

## A. Purpose

This checklist defines the process for certifying that the Yesh Mishak web application is usable on a specific device/browser combination. Certification means the application's core user flows work correctly, controls are reachable, and no blocking layout or runtime issues exist on the tested combination.

Passing certification does **not** mean every possible device in the world was tested. It means the tested device/browser combination meets the pass criteria defined in this document and can be recommended for end users.

## B. Certification Statuses

| Status | Meaning |
| :--- | :--- |
| **Not Tested** | This device/browser combination has not been evaluated. |
| **Pass** | All core screens and flows meet the universal pass criteria. No blocking issues found. |
| **Pass With Notes** | All core flows work, but minor cosmetic or non-blocking issues were observed. Notes describe the issues and any workarounds. |
| **Fail** | One or more core flows do not work. A blocking issue prevents normal use. A follow-up issue must be opened. |
| **Blocked** | Testing could not be completed due to environment, tooling, or access constraints. Reason must be documented. |

## C. Required Device Categories

| Category | Example Devices | Representative Viewport | Orientation |
| :--- | :--- | :--- | :--- |
| **Android Small** | Galaxy A series, Pixel 4a, older budget Android phones | 360x640 | Portrait + Landscape |
| **Android Large** | Galaxy S series, Pixel 7/8, OnePlus | 412x915 | Portrait + Landscape |
| **iPhone Small** | iPhone SE (2nd/3rd gen), iPhone 13 mini | 375x667 | Portrait + Landscape |
| **iPhone Large** | iPhone 14/15/16, iPhone Pro Max | 390x844, 430x932 | Portrait + Landscape |
| **Tablet / iPad** | iPad (10th gen), iPad Air, iPad Pro | 768x1024, 1024x768, 1180x820, 1366x1024 | Portrait + Landscape |
| **Desktop Browser** | Any desktop with Chrome, Safari, Edge, or Firefox | 1280x800 minimum | Landscape (standard) |

Each category must have at least one device/viewport tested before the category can be certified.

## D. Required Browser Coverage

| Browser | Engine | Coverage Rationale | Required |
| :--- | :--- | :--- | :--- |
| **Chrome** | Chromium / Blink | Primary Android and desktop browser. Direct Playwright coverage via Chromium engine. | Yes |
| **Safari** | WebKit | Primary iOS/macOS browser. Playwright WebKit simulation provides engine-level coverage. Real-device testing recommended for rubber-banding, address bar collapse, and safe-area insets. | Yes |
| **Edge** | Chromium / Blink | Uses the same Blink engine as Chrome. Chromium testing provides high-confidence proxy coverage. | Yes |
| **Samsung Internet** | Chromium / Blink | Uses the same Blink engine as Chrome. Chromium testing provides partial proxy. Samsung-specific features (night mode, content blockers) require real-device testing. | Yes |
| **Firefox** | Gecko | Optional. Include if project policy requires it. Playwright supports Firefox via its Gecko integration. | Optional |

### Known Browser Quirks

| Browser | Quirk | Reference |
| :--- | :--- | :--- |
| Safari / WebKit | `CSS.supports('overscroll-behavior', 'contain')` returns false, but the property works. Use `overscroll-behavior-y` longhand in test assertions. | COMPAT-002 (ISSUE-162) |

## E. Core Screens To Certify

Every device/browser combination must be tested against these screens:

| # | Screen | Key Elements to Verify |
| :--- | :--- | :--- |
| 1 | **Login** | Form visible, fields fillable, submit button reachable, panel centered |
| 2 | **Register** | All fields present, submit reachable via scroll if needed |
| 3 | **Map** | Map canvas fills viewport (>80% height), zoom controls usable, field markers visible |
| 4 | **Field Details** | Panel opens, content scrollable, close/back works, report button accessible |
| 5 | **Add Field Modal** | Opens, all form fields fillable, location picker map visible, close button visible after scroll, submit button reachable |
| 6 | **Create Game** | Form opens, date/time pickers usable, submit reachable |
| 7 | **Join / Leave Game** | Action buttons visible and tappable, confirmation works |
| 8 | **Close / Extend Game** | Controls visible where available, confirmation modal works |
| 9 | **Notifications Modal** | Opens, scrollable, close button clickable, tabs switchable |
| 10 | **Admin Screens** | If admin role is available: admin panel loads, tables scrollable (horizontal scroll acceptable per ISSUE-151 policy) |

## F. Universal Pass Criteria

A device/browser combination passes only if **all** of the following are true:

- [ ] No critical controls are clipped or hidden
- [ ] Buttons are reachable and tappable (minimum 44x44px touch targets on mobile)
- [ ] Modals can be opened, scrolled, submitted, and closed
- [ ] Modal close button remains visible and clickable at all scroll positions
- [ ] Map controls (zoom, pan) remain usable
- [ ] Text is readable without horizontal scrolling
- [ ] Forms can be completed (all fields reachable, keyboard does not permanently hide submit)
- [ ] Primary flows work without browser-specific failure
- [ ] No blocking console or runtime errors appear
- [ ] Layout works in both portrait and landscape where applicable
- [ ] Browser chrome and mobile viewport behavior (address bar, navigation bar) does not hide key actions
- [ ] Keyboard opening does not make required form actions permanently unreachable
- [ ] RTL Hebrew and LTR English layouts render correctly
- [ ] No z-index stacking issues between modals and toolbars

## G. Failure Criteria

A device/browser combination **fails** if **any** of the following are true:

- User cannot complete a core flow (login, add field, create game, join game)
- Close, submit, join, or create buttons become unreachable
- Modal cannot be closed (no working close mechanism: button, Escape, or backdrop click)
- Map cannot be used (controls hidden, canvas does not render, interactions blocked)
- Screen requires horizontal scrolling for normal use (admin tables excluded per ISSUE-151)
- Important Hebrew text becomes unreadable or overlaps
- Auth flow breaks (cannot login or register)
- Console errors block functionality (network errors on required API calls, unhandled exceptions that freeze UI)

## H. Device Test Matrix

| Category | Example Device | Viewport | Browser Engine | Orientation | Required Screens | Status | Evidence Link | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Android Small | Galaxy A14 | 360x640 | Chromium | Portrait | All (E.1–E.10) | Not Tested | | |
| Android Small | Galaxy A14 | 640x360 | Chromium | Landscape | All (E.1–E.10) | Not Tested | | |
| Android Large | Pixel 7 | 412x915 | Chromium | Portrait | All (E.1–E.10) | Not Tested | | |
| Android Large | Pixel 7 | 915x412 | Chromium | Landscape | All (E.1–E.10) | Not Tested | | |
| iPhone Small | iPhone SE 3 | 375x667 | WebKit | Portrait | All (E.1–E.10) | Not Tested | | |
| iPhone Small | iPhone SE 3 | 667x375 | WebKit | Landscape | All (E.1–E.10) | Not Tested | | |
| iPhone Large | iPhone 14 | 390x844 | WebKit | Portrait | All (E.1–E.10) | Not Tested | | |
| iPhone Large | iPhone 14 | 844x390 | WebKit | Landscape | All (E.1–E.10) | Not Tested | | |
| iPhone Large | iPhone Pro Max | 430x932 | WebKit | Portrait | All (E.1–E.10) | Not Tested | | |
| iPhone Large | iPhone Pro Max | 932x430 | WebKit | Landscape | All (E.1–E.10) | Not Tested | | |
| Tablet / iPad | iPad 10th gen | 768x1024 | WebKit | Portrait | All (E.1–E.10) | Not Tested | | |
| Tablet / iPad | iPad 10th gen | 1024x768 | WebKit | Landscape | All (E.1–E.10) | Not Tested | | |
| Tablet / iPad | iPad Air | 1180x820 | WebKit | Landscape | All (E.1–E.10) | Not Tested | | |
| Tablet / iPad | iPad Pro | 1366x1024 | WebKit | Landscape | All (E.1–E.10) | Not Tested | | |
| Desktop | Any | 1280x800+ | Chromium | Landscape | All (E.1–E.10) | Not Tested | | |

## I. Browser Test Matrix

| Browser | Engine | Platform | Required Test Scope | Status | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Chrome | Chromium / Blink | Android, Desktop | All device categories using Chromium engine | Not Tested | Primary browser. Playwright Chromium provides direct coverage. |
| Safari | WebKit | iOS, macOS | All iPhone and iPad categories | Not Tested | Playwright WebKit provides engine coverage. Real-device test recommended for address bar, safe-area, keyboard. |
| Edge | Chromium / Blink | Android, Desktop | At least one Android + one Desktop viewport | Not Tested | Same engine as Chrome. Low risk. |
| Samsung Internet | Chromium / Blink | Samsung Android devices | At least one Android Large viewport | Not Tested | Same engine as Chrome. Night mode and content blockers not testable via simulation. |
| Firefox | Gecko | Android, Desktop | Optional. At least one viewport per platform if tested. | Not Tested | Only required if project policy includes Firefox support. |

## J. Manual Certification Steps

Follow this checklist for each device/browser combination being certified. Start each test from a clean state (clear storage or use incognito/private mode).

### Setup
- [ ] Record: device name, viewport size, browser name and version, date, tester initials
- [ ] Clear browser storage or open incognito/private window
- [ ] Load the application URL

### Authentication
- [ ] Login screen renders correctly (panel centered, no overflow)
- [ ] Login form fields are fillable
- [ ] Login submit button is visible and tappable
- [ ] Switch to Register tab
- [ ] Register form fields are all reachable (scroll if needed)
- [ ] Register submit button is visible and tappable
- [ ] Complete login with valid credentials

### Map Screen
- [ ] Map canvas fills the viewport (no large blank areas)
- [ ] Zoom controls (+/−) are visible and functional
- [ ] Field markers are visible on the map
- [ ] Auth toolbar fits within viewport width (no horizontal overflow)
- [ ] Floating action buttons are visible and tappable

### Field Details
- [ ] Tap a field marker to open field details
- [ ] Field details panel opens and content is readable
- [ ] Panel content is scrollable if it overflows
- [ ] Close/back button works

### Add Field Modal
- [ ] Tap the add field button
- [ ] AddFieldModal opens
- [ ] All form fields are visible and fillable
- [ ] Location picker map is visible
- [ ] Scroll to the bottom of the modal
- [ ] **Close button (X) remains visible and clickable after scrolling** (COMPAT-001 regression check)
- [ ] Submit button is reachable
- [ ] Cancel button is reachable
- [ ] Close the modal (X button, Escape, or backdrop click)

### Create Game
- [ ] Open the create game flow
- [ ] Form fields are fillable
- [ ] Date/time pickers are usable
- [ ] Submit button is reachable

### Join / Leave Game
- [ ] Join button is visible and tappable
- [ ] Confirmation dialog works
- [ ] Leave button is visible (if applicable)

### Close / Extend Game
- [ ] Controls are visible where available
- [ ] Confirmation modal opens and is usable

### Notifications Modal
- [ ] Open notifications modal via the bell/preferences button
- [ ] Modal opens
- [ ] Close button is clickable
- [ ] Content is scrollable if it overflows
- [ ] Tabs are switchable (if multiple tabs exist)
- [ ] Close the modal

### Orientation (if applicable)
- [ ] Rotate to landscape
- [ ] Repeat key checks: map fills viewport, modal opens/closes, no horizontal overflow
- [ ] Rotate back to portrait
- [ ] Verify layout recovers correctly

### Final Checks
- [ ] No horizontal scrolling required on any screen (admin tables excluded)
- [ ] RTL Hebrew text displays correctly (if language is set to Hebrew)
- [ ] No blocking console errors visible in developer tools
- [ ] Record final status: Pass / Pass With Notes / Fail / Blocked

## K. Automated Validation Mapping

The following Playwright test files provide automated coverage for certification items. Items marked "Manual test still required" need real-device verification for behaviors that simulation cannot reproduce (keyboard interaction, address bar collapse, touch gestures).

| Certification Item | Automated Test File | Manual Test Still Required? | Notes |
| :--- | :--- | :--- | :--- |
| Modal close button not blocked by toolbar | `ipad-layout.spec.js` (IPAD-001) | No | Hit-test validated on iPad and iPad Air landscape viewports |
| AddFieldModal close button visible after scroll | `ipad-layout.spec.js` (COMPAT-001) | Yes — real device keyboard interaction | Automated on 390x844 and 768x1024. Real-device keyboard may affect scroll position. |
| AddFieldModal submit button reachable | `ipad-layout.spec.js` (IPAD-003) | No | Tested on iPad portrait, landscape, Air, and Pro viewports |
| AddFieldModal tablet landscape layout | `ipad-layout.spec.js` (IPAD-003/IPAD-004) | No | Map height, actions visibility, no horizontal overflow |
| Phone compact layout | `ipad-layout.spec.js` (Phone regression) | Yes — real device touch targets | Map height and action columns validated |
| Register form reachable on tablet | `ipad-layout.spec.js` (IPAD-002) | No | Submit button visible after scroll on iPad landscape |
| Modal open/scroll/close on small mobile | `modal-usability.spec.js` | Yes — soft keyboard, address bar | 320x568 and 375x667 viewports |
| Field details panel scrollable | `modal-usability.spec.js` | No | Panel and child modal stack tested on 375x667 |
| RTL/LTR layout | `i18n-rtl-ltr.spec.js` | No | Hebrew and English direction verified |
| Mobile scroll locking | `mobile-scrolling.spec.js` | Yes — real device overscroll | Body scroll lock when modal is open |
| Small Android layout | `small-android-layout.spec.js` | Yes — real Android device | Layout on small Android viewports |
| Floating buttons visibility | `floating-buttons.spec.js` | No | Button positions and visibility |
| Admin panel | `admin-panel.spec.js` | Yes — horizontal scroll on real tablet | Table rendering, horizontal scroll acceptable |
| Notifications | `notifications.spec.js` | No | Notification list and matching |
| Field navigation | `field-navigation.spec.js` | No | Map marker interaction and navigation |
| Game close flow | `game-close.spec.js` | No | Close game confirmation flow |
| User location | `user-location.spec.js` | Yes — real geolocation permission | Geolocation mocked in tests |

## L. Evidence Requirements

Before a device/browser combination can be marked as **Pass** or **Pass With Notes**, the following evidence must be attached or referenced:

| Evidence | Required For | Format |
| :--- | :--- | :--- |
| Browser name and version | All statuses | Text (e.g., "Chrome 126.0.6478.182") |
| Device name or viewport dimensions | All statuses | Text (e.g., "iPhone 14, 390x844") |
| Screenshot or video | Fail and Pass With Notes | Image (PNG/JPEG) or video (MP4/WebM) |
| Playwright test command output | Automated validation | Terminal output or CI log link |
| Date tested | All statuses | ISO date (YYYY-MM-DD) |
| Tester name or initials | All statuses | Text |
| Console error log | Fail | Browser console screenshot or text export |
| Description of issue and workaround | Pass With Notes | Text in the Notes column |

## M. Approval Rules

### Who can mark a device as Pass
Any team member who performed or witnessed the testing may mark a certification status. For release-gate decisions, at least one certification per required device category must be reviewed by the project lead or QA lead.

### When Pass With Notes is allowed
A device may be marked **Pass With Notes** when:
- All core flows work, but a minor cosmetic issue exists (e.g., slight misalignment, extra whitespace)
- A non-blocking browser quirk was observed (e.g., COMPAT-002 WebKit CSS.supports quirk)
- A known limitation exists that does not affect usability (e.g., admin table horizontal scroll on tablet, per ISSUE-151)

The notes must describe the issue and confirm it does not block any core flow.

### When a new issue must be opened
A new issue must be opened when:
- A device is marked **Fail**
- A **Pass With Notes** issue has user-facing impact beyond cosmetic
- A previously passing device begins failing after a code change

The issue must reference the certification checklist, the device/browser combination, and include evidence (screenshot/video).

### When certification must be repeated
See Section N (Re-certification Triggers).

## N. Re-certification Triggers

Certification must be repeated for all affected device categories when any of the following changes are merged to `main`:

| Trigger | Affected Categories | Rationale |
| :--- | :--- | :--- |
| Modal or layout CSS changes | All | Modal sizing, overflow, and positioning affect all viewports |
| Map layout changes | All | Map fill, controls, and marker visibility are viewport-dependent |
| Navigation or routing changes | All | Screen transitions and URL handling affect all devices |
| Auth flow changes | All | Login/register layout affects all viewports |
| Notification UI changes | All | Modal sizing and close button behavior |
| New browser/device bug fix | Affected device category + regression on others | Fix may introduce new issues on other viewports |
| Major responsive design changes | All | Media query or breakpoint changes affect all categories |
| Z-index or stacking context changes | All | Modal/toolbar layering (ref: IPAD-001 / ISSUE-161) |
| Touch target size changes | Mobile categories (Android, iPhone) | 44px minimum touch target compliance |
| New form fields added to modals | All mobile categories | May increase scroll depth, affecting close button visibility (ref: COMPAT-001 / ISSUE-163) |

Re-certification is **not** required for:
- Backend-only changes (API, database, server logic)
- Translation/i18n text changes (unless they significantly change text length)
- Test file changes that do not modify application code
- Documentation changes
