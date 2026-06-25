# Mobile Registration Screen Audit

## 1. Purpose

This audit evaluates the registration screen across the required mobile device classes from `docs/mobile-audit-plan.md`.

The product does not currently expose a separate registration route. Registration is implemented as a mode inside the Login/Auth UI, so this audit treats the Login page's Register mode as the Registration screen.

This issue documents findings only. It does not implement fixes or authorize mobile production release.

## 2. Scope

- Screen audited: Registration
- Implementation shape: Register mode inside `frontend/src/components/LoginPage.jsx`
- Device classes audited:
  - Small Android: 360x640
  - Large Android: 412x915
  - Small iPhone: 375x667
  - Large iPhone: 428x926
- Validation areas audited:
  - Form Layout
  - Validation Messages
  - Keyboard Behavior
  - Scroll Behavior
- Out of scope:
  - Fixing issues
  - Implementing UI changes
  - Backend/auth changes
  - Production mobile release
  - Full Login, Map, Game, Notification, or Admin audits

## 3. Gate Status

- ISSUE-126 mobile audit plan exists and was used as the audit standard.
- ISSUE-127 Login audit exists and related registration findings were reviewed.
- EPIC 02 remains **NOT COMPLETE**.
- AUTH-001 remains the production blocker.
- This audit does **not** unblock mobile production work.
- Mobile production release remains **NO** until AUTH-001 is resolved and production readiness is re-reviewed.

## 4. Methodology

### Files Reviewed

- `docs/mobile-audit-plan.md`
- `docs/mobile-login-screen-audit.md`
- `docs/product-decisions.md`
- `frontend/src/components/LoginPage.jsx`
- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `frontend/src/index.css`
- `frontend/src/api/auth.js`
- `frontend/src/i18n/index.js`
- `frontend/src/locales/en/common.js`
- `frontend/src/locales/he/common.js`
- `frontend/package.json`
- `frontend/playwright.config.js`

### Commands Run

- `git branch --show-current`
- `git status --short`
- `git switch main`
- `git pull origin main`
- `git checkout -b issue-128-registration-screen-mobile-audit`
- `Test-Path docs\mobile-audit-plan.md`
- `Test-Path docs\mobile-login-screen-audit.md`
- `rg -n "ISSUE-126: Create Complete Mobile Audit Plan|ISSUE-127: Perform Login Screen Mobile Audit|ML-LOGIN-001|ML-LOGIN-002|ML-LOGIN-003|AUTH-001|EPIC 02" docs\product-decisions.md docs\mobile-audit-plan.md docs\mobile-login-screen-audit.md`
- `rg --files frontend | rg "(Login|Register|Auth|auth|login|register|router|routes|App|\.css$|\.scss$|package\.json|playwright|spec|test|i18n|locales)"`
- `Get-Content frontend\package.json`
- `Get-Content frontend\src\components\LoginPage.jsx`
- `Get-Content frontend\src\App.jsx`
- `Get-Content frontend\src\App.css | Select-Object -First 280`
- `Get-Content frontend\src\index.css`
- `Get-Content frontend\playwright.config.js`
- Browser-emulation audit using Playwright's Chromium package from `frontend/node_modules/playwright`

### Execution Notes

- The app was run locally with Vite.
- Browser/mobile emulation was used with Chromium, mobile viewport sizes, touch enabled, and Hebrew selected in local storage.
- The audit switched the auth UI into Register mode and inspected form layout, focus behavior, scroll behavior, native validation state, and a simulated server-side registration error.
- API error-state layout was tested by intercepting `POST /auth/register` locally and returning a 422 response.

### Limitations

- Real mobile device testing was not performed.
- Browser emulation does not display a real native mobile keyboard, so keyboard findings are based on focus and viewport reachability measurements.
- Browser-native validation bubbles cannot be fully inspected in headless mode; validation was documented through field validity and `validationMessage` values.
- The external Google Identity script is still outside this registration-mode audit, except where the shared auth panel affects layout.

## 5. Registration Flow Description

A user reaches registration by opening the unauthenticated auth screen and tapping the `הרשמה` / Register tab.

Registration is not a standalone route. It is a local form in `LoginPage.jsx` that submits to `registerWithPassword()`, which calls `POST /auth/register`.

Fields present:

| Field | Input name | Type | Required | Other source-visible validation |
| :--- | :--- | :--- | :--- | :--- |
| Full name | `full_name` | `text` | YES | `autoComplete="name"` |
| Username | `username` | `text` | YES | `minLength={3}`, `autoComplete="username"` |
| Email | `email` | `email` | YES | `autoComplete="email"` |
| Phone number | `phone_number` | `tel` | YES | `autoComplete="tel"` |
| Password | `password` | `password` | YES | `minLength={8}`, `maxLength={128}`, `autoComplete="new-password"` |
| Confirm password | `password_confirm` | `password` | YES | `minLength={8}`, `maxLength={128}`, `autoComplete="new-password"` |

Assumptions and limitations:

- Browser-native HTML validation is used for required fields, email format, and min/max length.
- Server/API validation errors are rendered as a single global auth error below the form/auth divider area.
- Password confirmation matching is not visibly validated inline before submit from the reviewed frontend source.

## 6. Device Coverage

| Device Class | Viewport | Result | Notes |
|---|---:|---|---|
| Small Android | 360x640 | PASS WITH FINDINGS | All fields are reachable, but the form is taller than the viewport; submit starts below the viewport and requires scrolling. |
| Large Android | 412x915 | PASS WITH FINDINGS | Form fits in the viewport; validation relies on native/global messages rather than inline field messages. |
| Small iPhone | 375x667 | PASS WITH FINDINGS | All fields are reachable, but the form is taller than the viewport; submit starts below the viewport and requires scrolling. |
| Large iPhone | 428x926 | PASS WITH FINDINGS | Form fits in the viewport; validation relies on native/global messages rather than inline field messages. |

## 7. Validation Results

### Form Layout

**What was checked**

- Registration form visibility on all required device classes.
- Required field visibility and reachability.
- Label readability in Hebrew / RTL.
- Submit button reachability.
- Whether the form visually collapses or horizontally overflows.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Register mode rendered with `dir="rtl"` during Hebrew audit.
- All six fields rendered on all device classes.
- No horizontal overflow was found:
  - Small Android: `scrollWidth=360`, `viewportWidth=360`
  - Large Android: `scrollWidth=412`, `viewportWidth=412`
  - Small iPhone: `scrollWidth=375`, `viewportWidth=375`
  - Large iPhone: `scrollWidth=428`, `viewportWidth=428`
- Short devices required vertical scroll:
  - Small Android: `scrollHeight=880`, `viewportHeight=640`
  - Small iPhone: `scrollHeight=880`, `viewportHeight=667`
- Submit button initial position:
  - Small Android: bottom `735` in a `640` viewport
  - Small iPhone: bottom `735` in a `667` viewport
  - Large Android: bottom `753` in a `915` viewport
  - Large iPhone: bottom `748` in a `926` viewport

**Findings**

- Short devices require scrolling before the user can reach the submit button.
- The issue overlaps with ISSUE-127 finding `ML-LOGIN-001`, but is documented here as a registration-specific form layout/scroll finding.

### Validation Messages

**What was checked**

- Required-field validation.
- Invalid input validation as represented by browser validity state.
- Server/API error message layout.
- Whether error messages remain readable on small screens.
- Whether validation tells the user what to fix.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Empty required fields reported `valid=false`.
- Browser-native validation messages were available, but in the local Chromium run they were English strings such as `Please fill out this field.` even while the app was in Hebrew/RTL mode.
- A simulated 422 response from `POST /auth/register` rendered the Hebrew message `שם המשתמש קצר מדי. בחרו לפחות 3 תווים.`
- Simulated API error did not create horizontal overflow.
- On Small Android, the API error bottom measured `642` in a `640` viewport after submit, meaning the bottom edge was slightly clipped without additional scroll.
- On Small iPhone, the API error bottom measured `650` in a `667` viewport and remained visible.

**Findings**

- Validation relies partly on browser-native messages that are not controlled by the app's i18n copy.
- API errors appear as one global message below the form/shared auth area, not inline near the field that needs correction.
- On the shortest audited viewport, the global API error can sit at the bottom edge and may require small scroll adjustment.

### Keyboard Behavior

**What was checked**

- Each registration input can receive focus.
- Field types and autocomplete attributes are appropriate.
- Whether focusing fields leaves the submit button visible.
- Whether the user can move through fields in source/render order.

**Result**

PASS WITH FINDINGS.

**Evidence**

- All six inputs accepted focus in browser emulation.
- Input types are mobile-appropriate from source:
  - Email uses `type="email"`.
  - Phone uses `type="tel"`.
  - Password fields use `type="password"`.
- On Large Android and Large iPhone, the submit button remained visible while focusing each field.
- On Small Android and Small iPhone, the submit button was not visible while focusing each field before manual scrolling.

**Findings**

- Native keyboard testing is still needed on real devices because browser emulation does not display the keyboard.
- The measured focus behavior indicates a keyboard reachability risk on short devices.

### Scroll Behavior

**What was checked**

- Vertical scrolling on short devices.
- Horizontal scrolling.
- Scroll trap risk.
- Submit button recovery after scrolling.
- Error message reachability.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Manual scroll recovery worked on short devices:
  - Small Android after scrolling to page bottom: submit top `450`, bottom `495`, visible in `640` viewport.
  - Small iPhone after scrolling to page bottom: submit top `477`, bottom `522`, visible in `667` viewport.
- No horizontal scrolling was detected on any audited device class.
- No scroll trap was observed in browser emulation.
- API error remained reachable but may require scroll adjustment on the shortest viewport.

**Findings**

- Short devices depend on vertical scrolling to complete registration.
- No blocker was found because the submit button can be reached after scrolling.

## 8. Findings

| Finding ID | Severity | Area | Device(s) | Description | Evidence | Recommendation | Blocking |
|---|---|---|---|---|---|---|---|
| ML-REGISTER-001 | P2 | Form Layout / Scroll Behavior / Keyboard Behavior | Small Android, Small iPhone | Registration form is taller than the short mobile viewport; submit starts below the viewport and remains out of view while fields are focused before manual scrolling. | Small Android: submit bottom `735` vs viewport `640`; Small iPhone: submit bottom `735` vs viewport `667`; focus checks kept submit invisible on short devices. | In a future fix issue, reduce vertical height, improve spacing, or keep submit/action recovery clearer on short screens. Verify with native keyboards. | NO |
| ML-REGISTER-002 | P2 | Validation Messages | All device classes | Field validation relies partly on browser-native validation messages, which are not controlled by app i18n and appeared in English during Hebrew/RTL audit. | Empty required fields returned validation messages such as `Please fill out this field.` while the app direction was `rtl` and labels were Hebrew. | Add app-controlled, localized validation messages near fields in a future registration UX fix. | NO |
| ML-REGISTER-003 | P2 | Validation Messages / Scroll Behavior | Small Android, Small iPhone | Server/API registration errors render as a single global message below the form/shared auth area, not near the affected field; on the shortest viewport the error can sit at the viewport edge. | Simulated 422 error rendered below the shared auth area. Small Android error bottom was `642` in a `640` viewport. | Render field-specific errors inline where possible, keep global errors near the submit action, and verify short-screen scrolling. | NO |
| ML-REGISTER-004 | P3 | Form Layout / Touch Target | All device classes | Register tab shares the auth tabs from the Login screen; tab height is slightly below the 44px mobile touch target target. | Related ISSUE-127 finding `ML-LOGIN-002`; tab buttons measured 41px tall. | Increase auth tab min-height to at least 44px in a future mobile UI fix. | NO |

Relationship to ISSUE-127:

- `ML-REGISTER-001` is the registration-specific version of the ISSUE-127 registration-related observation `ML-LOGIN-001`.
- `ML-REGISTER-004` references the shared tab touch-target finding from `ML-LOGIN-002`.
- `ML-LOGIN-003` is not duplicated as a registration finding because the actual Google-rendered button is not part of completing the local registration form, although it shares the same auth panel.

## 9. Blockers

No Registration screen mobile blocker was identified during this audit.

Reasoning:

- All required fields are visible or reachable by scrolling.
- Submit is inaccessible at first on short screens but becomes reachable after vertical scroll.
- No horizontal overflow or scroll trap was observed.
- Validation messages are imperfect but readable/recoverable.
- No critical auth/data exposure was found in the mobile UI audit itself.

The following project-level blocker remains outside this Registration UI audit:

- AUTH-001 remains a P0 production blocker.

## 10. Recommendations

- Verify Register mode on at least one real Android device and one real iPhone with native keyboards.
- Improve short-screen registration layout so the submit action is easier to recover after keyboard focus.
- Add localized, app-controlled validation messages instead of relying only on browser-native validation bubbles.
- Prefer field-level validation messages for username, email, phone, password, and password confirmation errors.
- Keep the global API error close to the submit action or provide a summary that links users back to the relevant field.
- Increase auth tab touch targets to at least 44px.

## 11. Final Audit Decision

Final audit decision: **PASS WITH FINDINGS**.

- Registration screen acceptable for mobile after this audit: **YES, with documented non-blocking findings**.
- Mobile production allowed: **NO**.
- Reason mobile production remains blocked: AUTH-001 remains open, EPIC 02 remains NOT COMPLETE, and this audit does not authorize mobile production release.
