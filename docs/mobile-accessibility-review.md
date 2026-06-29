# ISSUE-177 — Mobile Accessibility Review (2026-06-29)

## Overview

| Field | Value |
| :--- | :--- |
| Issue | ISSUE-177 |
| Title | Mobile accessibility review |
| Date | 2026-06-29 |
| Status | COMPLETED |
| Scope | Font size, contrast, touch targets, screen reader compatibility |
| Method | Code-level audit of CSS, JSX components, i18n config, and HTML shell |

## Screens Reviewed

1. **LoginPage** — Login form, registration form, Google sign-in, tab switching
2. **OnboardingPage** — Username + city selection with autocomplete
3. **MapPage** — Leaflet map, floating buttons, field markers, field details panel
4. **MyGamesPage** — Game list, organizer filter, error/loading states
5. **AdminPage** — Sidebar nav, fields, games, users, field reports, stats
6. **Modals** — AddFieldModal, OpenGameModal, FieldReportModal, NotificationInboxModal, NotificationsModal, confirm dialogs
7. **Global** — OfflineBanner, ErrorBoundary, LanguageSelectionScreen, LanguageSwitcher

## Validation Baseline

| Check | Result |
| :--- | :--- |
| `npm run build` | PASS |
| `npx eslint src/ --max-warnings 0` | PASS (0 errors) |
| Playwright (91 tests) | 91 pass |

---

## 1. Font Size Audit

**Minimum font size found: 12px.** No text goes below 12px.

| Selector | Size | Context | Risk |
| :--- | :--- | :--- | :--- |
| `.notification-badge` | 12px | Bold 800, notification count badge | Low — decorative badge, info also in aria-label |
| `.game-time-list dt` | 12px | Bold 700, label in game time grid | Low — bold mitigates |
| `.notification-list-item time` | 12px | Timestamp in notification list | **P3** — small secondary text |
| `.my-games-organizer-badge` | 12px | Bold 700, "Organizer" badge | Low — bold mitigates |
| `.admin-action-button` | 0.8rem (~12.8px) | Desktop only; mobile overrides to 14px | OK |

**Mobile input font sizes:** All form inputs are forced to 16px on mobile via `@media (max-width: 640px)`. This correctly prevents iOS Safari's auto-zoom on focus.

**Verdict: PASS.** No text under 12px. All mobile inputs at 16px. Smallest body text is 13px (form hints, labels, secondary info). No font size is reduced below readable thresholds in mobile media queries.

---

## 2. Color Contrast Audit

Contrast ratios calculated per WCAG 2.1 AA: 4.5:1 for normal text (<18px regular / <14px bold), 3:1 for large text.

### Failures

| ID | Selector | Foreground | Background | Ratio | Required | Severity |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| CC-01 | `.admin-action-button.suspend` | #d97706 | #fffbeb | 3.07:1 | 4.5:1 | **P2** |
| CC-02 | `.my-games-status-full` | #d97706 | #ffffff | 3.19:1 | 4.5:1 | **P2** |
| CC-03 | `.city-autocomplete input:disabled` | #94a3b8 | #f1f5f9 | 2.34:1 | N/A (disabled) | **P3** |

### Borderline (4.5–5.0:1, technically passing)

| Selector | Foreground | Background | Ratio | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `.auth-submit` | #ffffff | #0f766e | 4.61:1 | Passes — large button text |
| `#64748b` on white (26 uses) | #64748b | #ffffff | 4.76:1 | Passes — used for secondary text |
| `.notification-badge` | #ffffff | #dc2626 | 4.63:1 | Passes — bold 800, effectively large text |
| `.danger-modal-button` | #ffffff | #dc2626 | 4.63:1 | Passes |

### All other pairs: PASS

Primary text (#172033 on #ffffff = 15.3:1), error text (#b42318 on #ffffff = 5.45:1), active tabs (#ffffff on #172033 = 15.3:1), offline banner (#78350f on #fffbeb = 7.53:1), approval badge (#92400e on #fef3c7 = 6.22:1) — all well above thresholds.

**Verdict: 2 contrast failures (P2), both involve #d97706 amber on light backgrounds.** Fix suggestion: darken to #b45309 (ratio ~4.8:1 on white) or #92400e (ratio ~6.2:1).

---

## 3. Touch Target Audit

WCAG 2.5.8 (Level AAA) recommends 44×44px minimum. Apple HIG requires 44pt. Material Design recommends 48dp.

### Mobile Media Query Coverage

The `@media (max-width: 640px)` rule applies `min-height: 44px` to **22 distinct interactive element selectors**, including:

- Modal/panel close buttons (44×44px grid)
- Auth mode tabs, notification tabs
- Toolbar buttons, admin buttons
- Form selects, admin status selects
- City autocomplete options
- Error retry buttons
- Leaflet zoom controls (44×44px !important)
- Back buttons, filter toggles

### Gaps

| ID | Selector | Desktop Size | Mobile Fix? | Severity |
| :--- | :--- | :--- | :--- | :--- |
| TT-01 | `.city-suggestions button` | padding: 10px 12px (~36px height) | No mobile override | **P2** |
| TT-02 | `.notification-list-item button:first-child` | padding: 0, relies on content height | No mobile override | **P3** — content typically provides sufficient height |
| TT-03 | `.error-boundary-fallback button` | padding: 10px 24px (~40px height) | No mobile override | **P3** — close to 44px |

### Already Compliant

| Element | Size |
| :--- | :--- |
| `.floating-button` (map actions) | 52×52px |
| `.field-marker` (map pins) | 54×54px |
| `.google-login-button` | min-height: 44px |
| `.navigation-option-button` | min-height: 44px |
| `.auth-submit` | padding: 12px 14px (~44px) |
| All primary/secondary/danger buttons | padding: 12px 14px |

**Verdict: PASS with 1 P2 gap.** 22 interactive elements explicitly get 44px on mobile. One element (`.city-suggestions button`) lacks a mobile override. Main action buttons and map controls are all adequately sized.

---

## 4. Screen Reader Compatibility Audit

### 4.1 Error Announcements — P1 (Systemic)

**13 components display error messages without `role="alert"` or `aria-live`.** Screen reader users will not hear errors when they appear.

| Component | Error Element | ARIA | Status |
| :--- | :--- | :--- | :--- |
| LoginPage | `.login-error` | None | **MISSING** |
| AddFieldModal | `.modal-error` | None | **MISSING** |
| FieldReportModal | `.modal-error` | None | **MISSING** |
| GamePanel | `.panel-error` | None | **MISSING** |
| OpenGameModal | `.modal-error` | None | **MISSING** |
| NotificationInboxModal | `.modal-error` | None | **MISSING** |
| NotificationsModal | `.modal-error` | None | **MISSING** |
| MapPage | `.map-error` | None | **MISSING** |
| AdminFields | `.admin-error` | None | **MISSING** |
| AdminGames | `.admin-error` | None | **MISSING** |
| AdminUsers | `.admin-error` | None | **MISSING** |
| AdminFieldReports | `.admin-error` | None | **MISSING** |
| MyGamesPage | `.my-games-error` | None | **MISSING** |

**Positive:** OfflineBanner correctly uses `role="status"` and `aria-live="polite"`. MapPage loading state uses `role="status"` and `aria-live="polite"`.

### 4.2 Modal Focus Management — P1

**Modal.jsx lacks focus trapping.** When a modal opens:
- Focus is not moved into the dialog
- Tab key can escape to background content
- Focus is not restored to the triggering element on close

This violates WCAG 2.4.3 (Focus Order). All 8+ modals in the app inherit this issue.

The modal does:
- Use `role="dialog"` and `aria-labelledby` — correct
- Handle Escape key to close — correct
- Use `inert` on background content (via FieldDetailsPanel) — partially correct

### 4.3 Form Validation Errors — P1

Form validation errors are not programmatically linked to their inputs:

| Component | Error Pattern | `aria-describedby`? |
| :--- | :--- | :--- |
| OpenGameModal | `<span className="form-field-error">` per field | No |
| LoginPage | `<span className="form-field-error">` for password mismatch | No |
| NotificationsModal | `<span className="form-field-error">` for city | No |
| OnboardingPage | `<p className="onboarding-error">` | No |

### 4.4 Tab Widget Semantics — P1

LoginPage uses a tablist pattern (`role="tablist"`) but:
- Tab buttons lack `role="tab"` and `aria-selected`
- Tab panels lack `role="tabpanel"` and `aria-labelledby`
- Arrow key navigation between tabs is not implemented

### 4.5 Duplicate IDs — P1

GamePanel uses `id="game-participants-list"` as a static string. When multiple GamePanels render on the same page (e.g., field with upcoming + active games), the ID is duplicated, breaking `aria-controls` associations.

### 4.6 Unlabeled Interactive Elements — P1

| Component | Element | Issue |
| :--- | :--- | :--- |
| AdminFields | `<select>` for status filter | No `<label>` or `aria-label` |
| AddFieldModal | `<MapContainer>` click-to-place | No keyboard alternative for pin placement |

### 4.7 Autocomplete Accessibility — P1

OnboardingPage city autocomplete:
- Input missing `role="combobox"`
- Missing `aria-activedescendant` for keyboard tracking
- Suggestion list missing `role="listbox"`, items missing `role="option"`

### 4.8 Icon Accessibility — P2

Lucide-react icons in button labels (MapPage: Bell, Settings, LocateFixed; MyGamesPage: ArrowLeft/ArrowRight) lack `aria-hidden="true"`. Screen readers may read SVG content in addition to the button's text/aria-label.

**Exception:** FieldDetailsPanel MapPin icon correctly uses `aria-hidden="true"`. OfflineBanner WifiOff icon correctly uses `aria-hidden="true"`.

### 4.9 Success/Status Announcements — P2

6 components show success or status messages without `role="status"` or `aria-live`:

- FieldReportModal (success message before auto-close)
- GamePanel (success messages)
- NotificationsModal (push test success)
- MapPage (field submission success)
- LoginPage (loading status)
- StatusCard (backend status changes)

### 4.10 Hardcoded English Strings — P2

| Component | String | Issue |
| :--- | :--- | :--- |
| Modal.jsx | Close button `aria-label="Close"` | Not i18n-ized; Hebrew users get English label |
| ErrorBoundary.jsx | "Something went wrong", "Reload" | Props allow override but defaults are English-only |

### 4.11 Missing Semantic HTML — P2/P3

| Component | Issue | Severity |
| :--- | :--- | :--- |
| MyGamesPage | Uses `<div>` instead of `<main>` for page root | P2 |
| MyGamesPage | Filter toggle missing `aria-pressed` | P2 |
| AdminFieldReports/AdminFields | Tab panels missing `role="tabpanel"` | P2 |
| GameSection (MyGamesPage) | Uses `<div>` instead of `<section>` | P3 |
| Admin tables | Missing `<caption>` elements | P3 |

---

## 5. Focus Styles Audit

**No `outline: none` or `outline: 0` found anywhere.** Browser default focus indicators are preserved.

### Custom Focus Styles

| Selector | Style | Visibility |
| :--- | :--- | :--- |
| `.language-selection-option:focus` | `outline: 3px solid rgba(23,32,51,0.12)` | **Weak** — 12% opacity barely visible |
| `.auth-form input:focus` | `border-color: #2563eb; outline: 3px solid rgba(37,99,235,0.18)` | **Weak** outline, but blue border change helps |
| `.city-suggestions button:focus` | `background: #f1f5f9` | OK |
| `.participants-toggle-button:focus` | `box-shadow + translateY(-2px)` | OK |
| Admin buttons (5 selectors) | Border/background color changes | OK |

### Missing Custom Focus Styles (rely on browser defaults)

`.auth-submit`, `.floating-button`, `.primary-panel-button`, `.secondary-panel-button`, `.primary-modal-button`, `.secondary-modal-button`, `.danger-panel-button`, `.danger-modal-button`, `.notifications-tabs button`, `.notification-mark-read-button`, `.notification-list-item button`, `.my-games-back-button`, `.my-games-filter-toggle`, `.error-boundary-fallback button`, form inputs (except auth), all `<select>` elements.

**No `:focus-visible` rules exist.** The app does not distinguish mouse focus from keyboard focus.

**Verdict: P2.** No focus suppression (good). Two custom focus outlines are too faint. Many elements rely on browser defaults, which is acceptable but could be improved.

---

## 6. Motion and Animation Audit

### Animations Found

| Animation | Selector | Type | Duration |
| :--- | :--- | :--- | :--- |
| `field-marker-active-pulse` | `.field-marker--active .field-marker-status` | Infinite pulse (scale + glow) | 1.6s |
| `field-marker-active-ring` | `.field-marker--active .field-marker-status::after` | Infinite ring expansion | 1.6s |
| `map-loading-spin` | `.map-loading-spinner` | Infinite rotation | 800ms |
| Transition | `.participants-toggle-button` | Transform + box-shadow | 160ms |
| Transition | `.participants-toggle-icon` | Transform (rotation) | 160ms |
| Transition | `.my-games-filter-toggle` | Background/color/border | 150ms |

### `prefers-reduced-motion` Support

**Not implemented.** No `@media (prefers-reduced-motion: reduce)` query exists anywhere in the codebase. Users who have requested reduced motion in their OS settings will still see all animations.

**Verdict: P2.** The infinite animations (marker pulse, loading spinner) should respect `prefers-reduced-motion`. The short transitions (150-160ms) are borderline — WCAG doesn't strictly require pausing them, but best practice is to honor the preference.

---

## 7. RTL and Internationalization

| Check | Result |
| :--- | :--- |
| `<html lang="he" dir="rtl">` | PASS — set in index.html |
| Dynamic `lang`/`dir` updates | PASS — `i18n/index.js` updates `document.documentElement.lang`, `document.documentElement.dir`, and `document.body.dir` on language change |
| CSS logical properties | Partial — uses `inset-inline-start` in some places but many `left`/`right` values remain |
| Translation key parity (EN↔HE) | PASS — all keys present in both locales |
| Dedicated a11y translation keys | None — no `aria.*` or `sr.*` namespace in locale files |
| Viewport meta | PASS — `width=device-width, initial-scale=1.0`, no zoom restrictions |

---

## Issue Summary by Severity

### P1 — Serious (7 issues)

| ID | Category | Description | Components Affected |
| :--- | :--- | :--- | :--- |
| A11Y-01 | Screen Reader | Error messages lack `role="alert"` / `aria-live` — dynamic errors invisible to screen readers | 13 components |
| A11Y-02 | Screen Reader | Modal.jsx has no focus trapping — Tab escapes to background | All 8+ modals |
| A11Y-03 | Screen Reader | Form validation errors not linked to inputs via `aria-describedby` | OpenGameModal, LoginPage, NotificationsModal, OnboardingPage |
| A11Y-04 | Screen Reader | LoginPage tab widget missing ARIA tab roles (`role="tab"`, `aria-selected`) | LoginPage |
| A11Y-05 | Screen Reader | GamePanel duplicate `id="game-participants-list"` across instances | GamePanel |
| A11Y-06 | Screen Reader | AdminFields status `<select>` has no accessible label | AdminFields |
| A11Y-07 | Screen Reader | OnboardingPage autocomplete missing `role="combobox"`, `aria-activedescendant`, `role="listbox"` | OnboardingPage |

### P2 — Moderate (10 issues)

| ID | Category | Description |
| :--- | :--- | :--- |
| A11Y-08 | Contrast | `.admin-action-button.suspend` — #d97706 on #fffbeb = 3.07:1 |
| A11Y-09 | Contrast | `.my-games-status-full` — #d97706 on #ffffff = 3.19:1 |
| A11Y-10 | Screen Reader | Success/status messages lack `role="status"` (6 components) |
| A11Y-11 | Screen Reader | Modal close button `aria-label="Close"` hardcoded English |
| A11Y-12 | Screen Reader | Lucide-react icons missing `aria-hidden="true"` in buttons |
| A11Y-13 | Focus | Two custom focus outlines at 12-18% opacity — barely visible |
| A11Y-14 | Motion | No `prefers-reduced-motion` support for 3 infinite animations |
| A11Y-15 | Semantic | MyGamesPage uses `<div>` not `<main>`; filter toggle missing `aria-pressed` |
| A11Y-16 | Semantic | Tab panels in LoginPage, AdminFields, AdminFieldReports missing `role="tabpanel"` |
| A11Y-17 | Touch | `.city-suggestions button` lacks mobile min-height: 44px override |

### P3 — Minor (8 issues)

| ID | Category | Description |
| :--- | :--- | :--- |
| A11Y-18 | Font | `.notification-list-item time` at 12px — small secondary text |
| A11Y-19 | Contrast | Disabled input #94a3b8 on #f1f5f9 = 2.34:1 (WCAG allows but poor UX) |
| A11Y-20 | Touch | `.error-boundary-fallback button` padding 10px 24px (~40px height) |
| A11Y-21 | Screen Reader | Admin tables missing `<caption>` elements |
| A11Y-22 | Screen Reader | ErrorBoundary defaults are English-only (overridable via props) |
| A11Y-23 | Semantic | GameSection uses `<div>` not `<section>` |
| A11Y-24 | Semantic | AdminUsers action buttons missing `type="button"` |
| A11Y-25 | Screen Reader | `.notification-list-item button:first-child` — no mobile min-height |

---

## What's Working Well

1. **Touch targets on mobile:** 22 interactive elements explicitly get `min-height: 44px` via the `@media (max-width: 640px)` query. Map floating buttons are 52×52px. Leaflet zoom controls forced to 44×44px.
2. **No focus suppression:** No `outline: none` anywhere. Browser defaults are always preserved.
3. **OfflineBanner:** Uses `role="status"` and `aria-live="polite"` — the best accessibility pattern in the app.
4. **Map loading state:** Uses `role="status"` and `aria-live="polite"`.
5. **RTL support:** Properly configured via i18n with dynamic `lang`/`dir` on `<html>` and `<body>`.
6. **Viewport:** No zoom restrictions (`user-scalable` not set, no `maximum-scale`).
7. **Font sizes:** No text under 12px. Mobile inputs at 16px prevent iOS zoom.
8. **Color contrast:** Most text pairs pass WCAG AA. Primary text at 15.3:1, error text at 5.45:1.
9. **FieldDetailsPanel:** Good use of `aria-label`, `inert` attribute, `aria-hidden` on icons.
10. **MapPage floating buttons:** All have proper `aria-label` attributes.
11. **Translation parity:** All error messages exist in both English and Hebrew.

---

## Recommended Fix Priority

If addressing these issues in future work:

1. **First:** Add `role="alert"` to error message containers (A11Y-01) — highest impact, smallest change (add one attribute per element across 13 files).
2. **Second:** Implement focus trapping in Modal.jsx (A11Y-02) — single file change, benefits all modals.
3. **Third:** Fix the two amber contrast failures (A11Y-08, A11Y-09) — change #d97706 to #b45309 in two CSS rules.
4. **Fourth:** Add `aria-describedby` linking for form validation errors (A11Y-03).
5. **Fifth:** Add `prefers-reduced-motion` media query (A11Y-14).

---

## Files Changed

- `docs/mobile-accessibility-review.md` (this file)

No application code or test code changed.
