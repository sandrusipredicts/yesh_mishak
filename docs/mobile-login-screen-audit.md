# Mobile Login Screen Audit

## 1. Purpose

This audit evaluates the Login screen across the required mobile device classes from `docs/mobile-audit-plan.md`.

The goal is to document mobile issues for the Login screen only. This issue does not implement fixes or authorize production mobile release.

## 2. Scope

- Screen audited: Login
- Device classes audited:
  - Small Android: 360x640
  - Large Android: 412x915
  - Small iPhone: 375x667
  - Large iPhone: 428x926
- Validation areas audited:
  - Layout
  - Keyboard
  - Overflow
  - Button Accessibility
  - Error Messages
- Out of scope:
  - Fixing Login UI issues
  - Implementing UI changes
  - Backend/auth changes
  - Production mobile release
  - Full Register, Map, Game, Notification, or Admin mobile audits

## 3. Gate Status

- ISSUE-126 mobile audit plan exists and was used as the audit standard.
- EPIC 02 remains **NOT COMPLETE**.
- AUTH-001 remains the production blocker.
- This audit does **not** unblock mobile production work.
- Mobile production release remains **NO** until AUTH-001 is resolved and production readiness is re-reviewed.

## 4. Methodology

### Files Reviewed

- `docs/mobile-audit-plan.md`
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
- `git switch issue-127-login-screen-mobile-audit`
- `Test-Path docs\mobile-audit-plan.md`
- `rg -n "ISSUE-126: Create Complete Mobile Audit Plan|AUTH-001|EPIC 02|mobile" docs\product-decisions.md docs\mobile-audit-plan.md`
- `rg --files frontend | rg "(Login|Auth|Register|auth|login|router|routes|App|\.css$|\.scss$|package\.json|playwright|spec|test)"`
- `Get-Content frontend\package.json`
- `Get-Content frontend\src\components\LoginPage.jsx`
- `Get-Content frontend\src\App.jsx`
- `Get-Content frontend\src\App.css`
- `Get-Content frontend\src\index.css`
- `Get-Content frontend\playwright.config.js`
- `Get-Content frontend\src\i18n\index.js`
- `Get-Content frontend\src\locales\en\common.js -TotalCount 80`
- `Get-Content frontend\src\locales\he\common.js -TotalCount 80`
- `npm run dev -- --host 127.0.0.1 --port 5173`
- Browser-emulation audit using Playwright's Chromium package from `frontend/node_modules/playwright`

### Execution Notes

- The app was run locally with Vite.
- Browser/mobile emulation was used with Chromium, mobile viewport sizes, touch enabled, and Hebrew selected in local storage.
- The audit inspected both Login and Register modes because `LoginPage.jsx` includes username/password login and password registration forms in addition to Google login.
- No production service, database, or backend endpoint was required for layout inspection.
- API error-state layout was tested by intercepting `POST /auth/login` locally and returning a 401 response.

### Limitations

- Real mobile device testing was not performed.
- The browser run does not open a real mobile virtual keyboard, so keyboard findings are based on focus and viewport reachability measurements rather than native keyboard screenshots.
- The external Google Identity script did not load during local browser audit, so the fully rendered Google-provided button could not be verified. The local error message for that failure was visible and readable.

## 5. Device Coverage

| Device Class | Viewport | Result | Notes |
|---|---:|---|---|
| Small Android | 360x640 | PASS WITH FINDINGS | Login form fits without horizontal overflow. Register submit is below the viewport when the first register field is focused. |
| Large Android | 412x915 | PASS | Login and register controls fit in the viewport during focus checks. Google script load failed locally, but error was visible. |
| Small iPhone | 375x667 | PASS WITH FINDINGS | Login form fits without horizontal overflow. Register submit is below the viewport when the first register field is focused. |
| Large iPhone | 428x926 | PASS | Login and register controls fit in the viewport during focus checks. Google script load failed locally, but error was visible. |

## 6. Validation Results

### Layout

**What was checked**

- Login screen renders after language selection is satisfied.
- Login panel fits required mobile widths.
- Hebrew / RTL layout is readable.
- Important login content is visible.
- Safe-area and viewport-height risks are identifiable.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Small Android 360x640: login panel measured `312x520`, positioned from `y=60` to `y=580`.
- Small iPhone 375x667: login panel measured `327x555`, positioned from `y=56` to `y=611`.
- Large Android 412x915 and Large iPhone 428x926 had the login panel fully visible with vertical centering.
- `document.documentElement.dir` was `rtl` during Hebrew audit.

**Findings**

- No layout blocker was found for Login mode.
- Register mode exceeds the viewport height on Small Android and Small iPhone. This is documented because the current Login screen includes Register mode, but the audit target remains the Login screen surface.

### Keyboard

**What was checked**

- Text inputs exist and can receive focus.
- Login submit remains reachable when the username field is focused.
- Register submit reachability was checked because the screen includes Register mode.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Login mode: focusing username kept the Sign in button visible on all four viewports.
- Small Android: Sign in button bottom was `459` in a `640` viewport.
- Small iPhone: Sign in button bottom was `455` in a `667` viewport.
- Small Android Register mode: Create account button bottom was `735` in a `640` viewport after focusing the first field.
- Small iPhone Register mode: Create account button bottom was `735` in a `667` viewport after focusing the first field.

**Findings**

- Register mode on short screens has a keyboard reachability risk: the submit button starts below the viewport when the first field is focused. A user can likely scroll, but native keyboard behavior still needs real-device confirmation.

### Overflow

**What was checked**

- Horizontal scrolling.
- Clipped content.
- Error text wrapping.
- Hidden bottom buttons.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Login mode horizontal scroll width equaled viewport width on all devices:
  - 360x640: `scrollWidth=360`, `viewportWidth=360`
  - 412x915: `scrollWidth=412`, `viewportWidth=412`
  - 375x667: `scrollWidth=375`, `viewportWidth=375`
  - 428x926: `scrollWidth=428`, `viewportWidth=428`
- 401 login error on Small Android and Small iPhone did not create horizontal overflow.
- Register mode vertical scroll was present on small devices:
  - Small Android: `scrollHeight=880`, `viewportHeight=640`
  - Small iPhone: `scrollHeight=880`, `viewportHeight=667`

**Findings**

- No horizontal overflow was found.
- Register mode requires vertical scrolling on short screens.

### Button Accessibility

**What was checked**

- Login tabs are visible and tappable.
- Password Sign in button is visible and large enough.
- Google login button container is present.
- Touch targets are at least approximately 44px tall.

**Result**

PASS WITH FINDINGS.

**Evidence**

- Login tabs measured 41px tall. This is slightly below the 44px target from the audit plan.
- Sign in button measured 45px tall on all measured viewports.
- Google button container measured at least 44px tall.
- The actual Google-rendered button could not be verified because the Google Identity script did not load in the local audit run.

**Findings**

- Login/Register tab buttons are slightly below the 44px touch target target.
- Real Google button rendering/tap behavior remains unverified in this local audit environment.

### Error Messages

**What was checked**

- Google script failure error visibility.
- Password login API failure error visibility.
- Error text layout on small screens.
- Error text overflow.

**Result**

PASS.

**Evidence**

- Google script failure showed readable Hebrew copy: `לא ניתן לטעון התחברות Google.`
- Simulated password login failure showed readable Hebrew copy: `שם משתמש או סיסמה שגויים. נסו שוב.`
- Small Android 401 error bounds: width `256`, height `19`, bottom `570` inside the panel.
- Small iPhone 401 error bounds: width `271`, height `19`, bottom `583` inside the panel.
- Error state did not create horizontal scrolling.

**Findings**

- No error-message layout findings were identified.

## 7. Findings

| Finding ID | Severity | Area | Device(s) | Description | Evidence | Recommendation | Blocking |
|---|---|---|---|---|---|---|---|
| ML-LOGIN-001 | P2 | Keyboard / Layout | Small Android, Small iPhone | Register mode on the Login screen places the Create account button below the viewport when the first field is focused. | Small Android: submit bottom `735` vs viewport `640`; Small iPhone: submit bottom `735` vs viewport `667`. | In a future fix issue, improve small-screen register layout, reduce vertical spacing, or ensure submit remains reachable with keyboard open. Verify on real mobile keyboards. | NO |
| ML-LOGIN-002 | P3 | Button Accessibility | All device classes | Login/Register tab buttons are slightly shorter than the 44px mobile touch target target. | Tabs measured 41px tall in mobile emulation. | Increase tab button min-height to at least 44px in a future mobile UI fix. | NO |
| ML-LOGIN-003 | P3 | Button Accessibility / Testability | All device classes | Actual Google-rendered button could not be verified in local browser audit because the Google Identity script did not load. | Local audit showed readable Google load failure error; `.google-login-button` container was present and 44px tall, but provider-rendered content was unavailable. | Add a test strategy or mock for Google button rendering, and perform one real environment/mobile-device OAuth smoke test. | NO |

## 8. Blockers

No Login screen mobile blocker was identified during this audit.

The following project-level blocker remains outside this Login UI audit:

- AUTH-001 remains a P0 production blocker.

## 9. Recommendations

- Verify the Login screen on at least one real Android device and one real iPhone with native keyboards.
- Improve Register mode small-screen keyboard ergonomics in a separate fix issue.
- Increase Login/Register tab touch target height to at least 44px.
- Add a controlled Google login button test/mocking path so audits do not depend on the external Google Identity script.
- Run one staging OAuth smoke test after AUTH-001 is remediated and staging auth is available.

## 10. Final Audit Decision

Final audit decision: **PASS WITH FINDINGS**.

- Login screen acceptable for mobile after this audit: **YES, with documented non-blocking findings**.
- Mobile production allowed: **NO**.
- Reason mobile production remains blocked: AUTH-001 remains open, EPIC 02 remains NOT COMPLETE, and this audit does not authorize mobile production release.
