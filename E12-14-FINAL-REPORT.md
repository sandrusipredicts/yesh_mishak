# E12-14 Onboarding UX QA Pass — Final Report

Branch: `issue-918-onboarding-ux-qa`
Base: `origin/dev` (`c6d74a1`)
Date: 2026-08-02

---

## A. Scope Items Implemented

### 1. Account-city persistence failure handling
**File:** `frontend/src/components/onboarding/AccountCityStep.jsx`
**Change:** `handleContinue()` now checks the boolean return of `setAccountCity()`. On failure (`false`), it sets an error state with `t('onboarding.cityPersistFailed')`, resets `isBusy`, and blocks `onSelected()` from firing. Retry is automatic — the user clicks Continue again with the city still selected.
**Lines changed:** 7 (added error state, handleCityChange wrapper, failure branch)

### 2. Manual registration validation
**File:** `frontend/src/components/LoginPage.jsx`
**Change:** Added `validateRegistration()` function that checks all six registration fields before any API call. Each field gets an inline `form-field-error` span with `aria-describedby` for accessibility. Fields validated: `full_name` (required), `username` (min 3 chars), `email` (required + regex), `phone_number` (required), `password` (8-128 chars), `password_confirm` (match). `handleRegister` calls `validateRegistration()` first and aborts on failure.
**CSS:** `frontend/src/App.css` — added `scroll-margin-bottom: 16px` on `.login-error` and sticky positioning on `.auth-form .login-error` for short-screen reachability.
**Lines changed:** ~60

### 3. AddField location single-flight protection
**File:** `frontend/src/components/AddFieldModal.jsx`
**Change:** Added `isLocating` state. `useCurrentLocation()` now guards with `if (isLocating) return` at the top and wraps the async body in `try/finally` setting `isLocating` back to `false`. The location button renders `disabled={isLocating || isSubmitting}` and shows `t('addField.locating')` while in flight.
**Lines changed:** ~15

### 4. In-scope localization and safe error mapping
**File:** `frontend/src/api/errors.js`
**Change:** Added `getSafeErrorMessage(error, t, fallbackKey)` — maps known `code` values to translation keys via `KNOWN_ERROR_CODES`, then falls back to HTTP status mapping, then to a network-error check, and finally to a generic fallback. Never exposes raw backend text.
**Files:** `frontend/src/locales/en/common.js`, `frontend/src/locales/he/common.js`
**Change:** Added 21 translation keys each: 5 registration validation messages, 3 legal-link labels, 9 safe-error messages, 1 city-persist failure, 1 locating label.
**Lines changed:** ~70

---

## B. Files Changed

| File | Type |
|---|---|
| `frontend/src/components/onboarding/AccountCityStep.jsx` | Modified |
| `frontend/src/components/LoginPage.jsx` | Modified |
| `frontend/src/components/AddFieldModal.jsx` | Modified |
| `frontend/src/api/errors.js` | Modified |
| `frontend/src/locales/en/common.js` | Modified |
| `frontend/src/locales/he/common.js` | Modified |
| `frontend/src/App.css` | Modified |
| `frontend/tests/onboarding-storage.test.js` | Modified |
| `frontend/tests/safe-errors.test.js` | Created |
| `frontend/tests/e12-14-onboarding-ux-qa.spec.js` | Created |

Total: 185 insertions, 55 deletions (excluding lockfile churn).

---

## C. Tests

### Unit Tests (Node built-in test runner)

| File | Tests | Status |
|---|---|---|
| `frontend/tests/safe-errors.test.js` | 7 | All pass |
| `frontend/tests/onboarding-storage.test.js` | 17 (1 new) | All pass |

**safe-errors.test.js** covers: known code mapping, HTTP status mapping (401, 5xx), network error, generic fallback, custom fallback key, raw-backend-detail blocking.

### E2E Tests (Playwright)

| File | Scenarios | Coverage |
|---|---|---|
| `frontend/tests/e12-14-onboarding-ux-qa.spec.js` | 22 tests | Scenarios 1–19 |

**Scenario mapping:**

1. Account-city persistence failure blocks progression — ✅
2. Account-city retry succeeds — ✅
3. Hebrew registration validation — ✅
4. English registration validation — ✅ (3 tests: all-fields, email format, password mismatch)
5. Registration errors reachable on short viewport — ✅
6. Rapid location taps (AddField) single-flight — ✅ (2 tests: call-count, disabled state)
7. Location recovers after denial — ✅
8–11. Auth flows (password registration validation, server error safe message) — ✅ (2 tests; Google-native flows require on-device QA)
12. Terms failure blocks and retry succeeds — ✅
13. Refresh resumes at persisted step — ✅
14. Unauthenticated → login → onboarding — ✅
15. Location/notification denial doesn't block — ✅
16. Permission regrant (map shows location marker) — ✅
17. Deep link survives onboarding — ✅
18. AddField submission failure recoverable — ✅
19. Rapid submission no duplicates — ✅

**Bonus:** 2 localization tests (legal links EN/HE) + 1 safe-error-mapping E2E test.

---

## D. Lint

ESLint on all four modified source files: **0 errors, 0 warnings**.

---

## E. Security Review

### Touched files — credential scan

Scanned all 10 touched/created files for: passwords, JWTs, Google tokens, authorization headers, cookies, private email addresses, test credentials, API keys.

**Result:** No real credentials found. Test files use only synthetic dummy JWTs (`alg: none`, subject: static UUID), placeholder form values for UI testing, and mock API responses. All match established patterns in the existing spec files.

### getSafeErrorMessage contract

The new `getSafeErrorMessage` function in `errors.js` maps errors to translation keys exclusively. It never passes raw `error.response.data.detail` to the UI. The existing `getApiErrorMessage` (used in LoginPage and AddFieldModal) does return raw detail strings as a design choice, but with safe fallback messages for the common paths. The `getSafeErrorMessage` function is available for future adoption across all API error surfaces.

### Pre-existing security blocker — SEPARATE FOLLOW-UP

**File:** `frontend/src/api/accountLinking.js`
**Lines:** 43, 53, 55, 58
**Issue:** `console.log` statements output passwords, Google tokens, and full request/response payloads to the browser console. This leaks credentials in browser DevTools, Sentry breadcrumbs, and any log-forwarding infrastructure.

**This is NOT fixed under issue #918.** It requires a separate security-focused branch with its own review.

---

## F. Behavioral Preservation

- No changes to auth architecture, session management, or token handling
- No changes to backend API contracts
- No changes to onboarding step sequence, storage schema, or version
- No changes to map, notification, admin, or game functionality
- AddFieldModal: only the location button gained a single-flight guard and locating label; all other behavior unchanged
- LoginPage: registration validation is additive (runs before the existing API call); login flow untouched
- AccountCityStep: only added failure handling; success path identical

---

## G. Out of Scope / Not Changed

- Credential logging in `accountLinking.js` (separate security issue)
- No merge into `main` or `dev`
- No backend changes
- No Android/iOS native code changes
- No changes to existing passing tests
- Google-native auth flows (Credential Manager) — require on-device QA; cannot be fully automated in Playwright
