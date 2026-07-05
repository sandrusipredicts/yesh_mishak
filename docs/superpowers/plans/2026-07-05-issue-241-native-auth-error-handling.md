# ISSUE-241 Native Authentication Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe, centralized error classification and cleanup to native Google authentication without changing its successful path.

**Architecture:** A focused mapper converts provider and API failures into a stable UI contract. `LoginPage` consumes that contract, clears failed native sessions, renders translated severity-appropriate feedback, and retains `finally`-based loading cleanup.

**Tech Stack:** React, i18next, Axios error objects, Capacitor Social Login, Playwright.

---

### Task 1: Central error mapping

**Files:**
- Create: `frontend/src/api/authErrorMapping.js`
- Create: `frontend/tests/auth-error-mapping.spec.js`
- Modify: `frontend/src/api/nativeGoogleAuth.js`

- [ ] Write tests that import `mapNativeAuthError` and assert the complete
  `{ kind, messageKey, severity, shouldClearSession }` object for cancellation,
  Axios network/timeout failures, 400/401/403, 5xx, provider failure, missing ID
  token, and unknown errors.
- [ ] Run `npx playwright test tests/auth-error-mapping.spec.js` from
  `frontend`; expect failure because the mapper does not exist.
- [ ] Implement the mapper and a stable missing-ID-token error code in the
  provider adapter.
- [ ] Re-run the focused mapping test; expect all cases to pass.

### Task 2: Native login UI and cleanup

**Files:**
- Modify: `frontend/tests/native-google-login.spec.js`
- Modify: `frontend/src/components/LoginPage.jsx`
- Modify: `frontend/src/locales/en/common.js`
- Modify: `frontend/src/locales/he/common.js`
- Modify: `frontend/src/App.css`

- [ ] Extend the native mock with provider failure and missing-token modes,
  network aborts, stale secure/in-memory metadata, and controllable HTTP status.
- [ ] Add UI tests for neutral cancellation, retry-friendly network failure,
  400/401/403 verification failure, 5xx temporary server failure, provider
  failure, missing ID token, session cleanup, and button re-enablement.
- [ ] Run `npx playwright test tests/native-google-login.spec.js`; expect the
  new assertions to fail against the current behavior.
- [ ] Add translation keys and update `LoginPage` to map, clear, render by
  severity, and reset loading in `finally`.
- [ ] Re-run the native login suite; expect all tests to pass, including the
  existing successful persistence and logout cases.

### Task 3: Regression verification and handoff

**Files:**
- Review all changed files; do not commit before user review.

- [ ] Run `npm run lint`.
- [ ] Run `npm run test:e2e`.
- [ ] Run `npm run build`.
- [ ] Run `npm run build:android`.
- [ ] Confirm `git diff --name-only` contains only ISSUE-241 auth/tests/docs
  plus the two pre-existing generated Android worktree entries.
- [ ] Report the changed files, exact commands/results, scenario matrix, scope
  confirmations, and the pending iPhone validation gate.
