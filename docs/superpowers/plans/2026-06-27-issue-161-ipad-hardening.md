# ISSUE-161 iPad Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden modal close-button stacking and AddFieldModal tablet-landscape usability while preserving existing phone layouts.

**Architecture:** Keep the existing named z-index scale, where primary modal backdrops sit above the auth toolbar and below confirmation dialogs. Strengthen viewport-specific behavior only in the existing tablet-landscape media query, and use Playwright assertions against real interaction and rendered geometry.

**Tech Stack:** React, CSS media queries, Playwright, Vite, ESLint.

---

### Task 1: Strengthen iPad and phone regression coverage

**Files:**
- Modify: `frontend/tests/ipad-layout.spec.js`

- [ ] **Step 1: Replace passive close-button hit tests with failing interaction tests**

For notifications and AddFieldModal at 1024x768 and 1180x820, assert that the close button is visible, its center resolves to the button rather than `.auth-toolbar`, click it, and assert that the modal is detached.

- [ ] **Step 2: Add failing AddFieldModal geometry assertions**

At tablet-landscape viewports, assert that the location map has a positive height no greater than 160px, the action group is visible, both cancel and submit controls are inside the modal and viewport bounds, and the modal has no horizontal overflow.

- [ ] **Step 3: Add a phone regression test**

At 390x844, assert that AddFieldModal retains the phone layout: the map is no taller than 160px, the action group uses a single-column grid, and submit remains reachable by scrolling.

- [ ] **Step 4: Run tests to verify meaningful failures**

Run: `npx playwright test tests/ipad-layout.spec.js`

Expected: new interaction and geometry assertions expose any insufficient implementation or pass only where the existing implementation already satisfies the hardened contract.

### Task 2: Apply the minimum responsive fix

**Files:**
- Modify if required: `frontend/src/App.css`
- Test: `frontend/tests/ipad-layout.spec.js`

- [ ] **Step 1: Preserve the named modal layer**

Keep `--z-modal-backdrop` above `--z-auth-toolbar` and below `--z-confirm-modal-backdrop`; avoid unrelated global stacking changes.

- [ ] **Step 2: Adjust tablet-landscape AddFieldModal styles only if tests require it**

Limit changes to `@media (min-width: 641px) and (max-height: 820px)`. Keep the location picker capped at 160px and ensure the sticky action group remains fully within the modal and viewport.

- [ ] **Step 3: Run targeted iPad and phone tests**

Run: `npx playwright test tests/ipad-layout.spec.js`

Expected: all hardened iPad and phone regression cases pass.

### Task 3: Validate and document

**Files:**
- Modify: `docs/product-decisions.md`

- [ ] **Step 1: Run relevant layout suites**

Run: `npx playwright test tests/ipad-layout.spec.js tests/modal-usability.spec.js tests/small-android.spec.js tests/mobile-scrolling.spec.js`

Expected: all selected layout tests pass.

- [ ] **Step 2: Run lint and build**

Run: `npm run lint`

Run: `npm run build`

Expected: build passes; lint results are recorded exactly, including any baseline failures.

- [ ] **Step 3: Update the decision record**

Append the hardening decision, changed files, exact commands, results, branch synchronization note, and intentionally deferred items to `docs/product-decisions.md`.

- [ ] **Step 4: Verify the final diff**

Run: `git diff --check`

Run: `git status --short --branch`

Expected: no whitespace errors; only intended files are modified.
