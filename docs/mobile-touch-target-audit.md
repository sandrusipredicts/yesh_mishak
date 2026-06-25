# ISSUE-140: Mobile Touch Target Size Audit

## Summary

This audit catalogs every interactive element in the frontend whose touch target height falls below the 44x44px minimum established in `docs/mobile-design-guide.md` (ISSUE-136). It covers all screens: Login, Map, Field Details, Game Details, Create Game, Notifications, Admin Panel, and My Games. No CSS or component changes are made — this is a documentation-only audit that identifies violations and provides a structured remediation plan.

**Total findings**: 18
- **Critical**: 0
- **High**: 0
- **Medium**: 14
- **Low**: 4
- **Overall touch target compliance**: **NOT COMPLIANT**

The majority of violations are in the Admin Panel (6 findings) and modal close/action buttons (5 findings). Most violations can be resolved by increasing vertical padding in mobile-scoped CSS rules without changing component structure.

## Dependency Verification

| Dependency | Document | Status | Relevant Standard |
| :--- | :--- | :--- | :--- |
| ISSUE-136 | `docs/mobile-design-guide.md` | Verified | 44x44px minimum touch target; 48px preferred for primary actions; 8px minimum gap between adjacent targets |
| ISSUE-135 | `docs/mobile-audit-consolidated-report.md` | Verified | 10 touch-target findings already identified (cross-referenced below) |
| ISSUE-137 | `docs/mobile-safe-area-support.md` | Verified | Safe-area padding applied to modals and panels |
| ISSUE-139 | `docs/mobile-keyboard-handling-implementation.md` | Verified | Notes touch target sizing as "intentionally not fixed" in that issue |

## Audit Scope

### Screens Reviewed

| Screen | Primary Component | CSS File | Touch Elements Audited |
| :--- | :--- | :--- | :--- |
| Login / Registration | `LoginPage.jsx` | `App.css` | Auth mode tabs, password toggle, Google button, form submit |
| Map | `MapPage.jsx` | `App.css` | Floating action buttons, field markers, Leaflet zoom controls |
| Field Details Panel | `FieldDetailsPanel.jsx` | `App.css` | Panel close button, navigation/report/open-game buttons, participants toggle |
| Game Details | `GamePanel.jsx` | `App.css` | Join/leave/extend/close buttons, participants toggle |
| Create Game Modal | `OpenGameModal.jsx` | `App.css` | Modal close button, form inputs, radio labels, submit button |
| Add Field Modal | `AddFieldModal.jsx` | `App.css` | Modal close button, location picker button, form inputs, submit/cancel buttons |
| Notifications Inbox | `NotificationInboxModal.jsx` | `App.css` | Modal close button, mark-read buttons, mark-all button, notification items |
| Notifications Preferences | `NotificationsModal.jsx` | `App.css` | Modal close button, tab buttons, city autocomplete options, save button |
| Field Report Modal | `FieldReportModal.jsx` | `App.css` | Modal close button, submit/cancel buttons |
| Navigation Modal | (inline in FieldDetailsPanel) | `App.css` | Navigation option buttons, cancel button |
| Admin Panel | `AdminPage.jsx`, `AdminUsers.jsx`, `AdminFields.jsx`, `AdminGames.jsx`, `AdminFieldReports.jsx` | `App.css` | Sidebar buttons, tab filter buttons, table action buttons, user moderation buttons, status select |
| My Games | `MyGamesPage.jsx` | `App.css` | Back button, filter toggle, error retry button |
| Global | `LanguageSwitcher.jsx`, `App.jsx` | `App.css` | Language switcher select, auth toolbar logout button |

### Touch Target Standard

From `docs/mobile-design-guide.md`:
- **Minimum**: 44x44px (width and height)
- **Preferred**: 48x48px for primary actions
- **Icon-only buttons**: Must achieve 44px hit diameter via padding
- **Adjacent destructive buttons**: Must have spacing separation
- **Minimum gap**: 8px between adjacent interactive targets

### Measurement Method

Touch target height is calculated as: `font-size × line-height + padding-top + padding-bottom + border-top + border-bottom`. The base font-size is 16px (browser default). Buttons with `font: inherit` inherit 16px. Line-height defaults to browser `normal` (~1.2 = ~19.2px for 16px font). Where `font-size` is explicitly set, that value is used.

## Touch Target Audit Matrix

| Element | CSS Class / Selector | Explicit Size or Padding | Computed Height (approx) | Standard (44px) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Floating action buttons | `.floating-button` | `width: 52px; height: 52px` | 52px | 44px | PASS |
| Primary panel button | `.primary-panel-button` | `padding: 12px 14px` | ~43px | 44px | BORDERLINE PASS |
| Secondary panel button | `.secondary-panel-button` | `padding: 12px 14px` | ~43px | 44px | BORDERLINE PASS |
| Danger panel button | `.danger-panel-button` | `padding: 12px 14px` | ~43px | 44px | BORDERLINE PASS |
| Participants toggle | `.participants-toggle-button` | `padding: 12px 14px` | ~43px | 44px | BORDERLINE PASS |
| Navigation option button | `.navigation-option-button` | `min-height: 44px; padding: 10px 12px` | ≥44px | 44px | PASS |
| Primary modal button | `.primary-modal-button` | `padding: 12px 14px` | ~43px | 44px | BORDERLINE PASS |
| Secondary modal button | `.secondary-modal-button` | `padding: 12px 14px` | ~43px | 44px | BORDERLINE PASS |
| Admin sidebar button | `.admin-sidebar-button` | `padding: 12px 14px` | ~43px | 44px | BORDERLINE PASS |
| Schedule mode radio label | `.schedule-mode-options label` | `padding: 10px 12px` | ~41px | 44px | FAIL |
| Notification tab button | `.notifications-tabs button` | `padding: 10px 12px` | ~41px | 44px | FAIL |
| Auth mode tab button | `.auth-mode-tabs button` | `padding: 10px 12px` | ~41px | 44px | FAIL |
| Auth toolbar logout button | `.auth-toolbar button` | `padding: 8px 10px` | ~35px | 44px | FAIL |
| Modal close button | `.modal-close-button` | `font-size: 20px; no min-width/height` | ~20px | 44px | FAIL |
| Panel close button | `.panel-close-button` | `font-size: 20px; no min-width/height` | ~20px | 44px | FAIL |
| Admin tab filter button | `.admin-tab-button` | `padding: 9px 12px` | ~37px | 44px | FAIL |
| Admin table action button | `.admin-actions button` | `padding: 8px 10px` | ~35px | 44px | FAIL |
| Admin secondary/danger button | `.admin-secondary-button` | `padding: 8px 10px` | ~35px | 44px | FAIL |
| Admin user action button | `.admin-action-button` | `padding: 4px 10px; font-size: 0.8rem` | ~25px | 44px | FAIL |
| Admin status select | `.admin-status-select` | `padding: 8px 10px` | ~35px | 44px | FAIL |
| Mark-read button | `.notification-mark-read-button` | `padding: 7px 9px; font-size: 13px` | ~30px | 44px | FAIL |
| Mark-all button | `.notifications-list-header button` | `padding: 8px 10px` | ~35px | 44px | FAIL |
| Language switcher select | `.language-switcher select` | `padding: 7px 9px` | ~33px | 44px | FAIL |
| City autocomplete option | `.city-autocomplete-option` | `padding: 10px 12px; font-size: 14px` | ~39px | 44px | FAIL |
| Location picker button | `.location-picker-header button` | `padding: 8px 10px` | ~35px | 44px | FAIL |
| Admin back link | `.admin-back-link` | `padding: 10px 12px` | ~41px | 44px | FAIL |
| My Games filter toggle | `.my-games-filter-toggle` | `padding: 6px 14px; font-size: 14px` | ~29px | 44px | FAIL |
| My Games back button | `.my-games-back-button` | `padding: 0 (implicit)` | ~19px | 44px | FAIL |
| Error retry buttons | `.admin-error button` etc. | `padding: 6px 16px; font-size: 13px` | ~28px | 44px | FAIL |
| Leaflet zoom controls | Leaflet default CSS | `width: 30px; height: 30px` | 30px | 44px | FAIL |
| Field markers | `.field-marker` | `width: 54px; height: 54px` | 54px | 44px | PASS |

## Detailed Findings

### TTMOB-001: Modal Close Buttons Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Create Game, Add Field, Notifications Inbox, Notifications Preferences, Field Report, Navigation
- **CSS**: `.modal-close-button` (line 1003 in App.css)
- **Current size**: `font-size: 20px` with no explicit width, height, min-width, or min-height. Computed hit area is approximately 20x24px.
- **Standard**: 44x44px minimum
- **Gap**: 24px below minimum
- **Impact**: High miss-tap rate on all modal close buttons. Users must tap precisely on the small `x` character.
- **Cross-reference**: Partially overlaps `CGMOB-003` from ISSUE-135.
- **Recommended fix**: Add `min-width: 44px; min-height: 44px; display: grid; place-items: center;` to `.modal-close-button` on mobile.

### TTMOB-002: Panel Close Button Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Field Details Panel
- **CSS**: `.panel-close-button` (line 692 in App.css)
- **Current size**: `font-size: 20px` with no explicit dimensions. Computed hit area is approximately 20x24px.
- **Standard**: 44x44px minimum
- **Gap**: 24px below minimum
- **Impact**: Users struggle to close the field details panel, contributing to the "viewport trap" risk on small screens.
- **Cross-reference**: Related to `ML-MAP-001` and `ML-FIELD-DETAILS-001` from ISSUE-135.
- **Recommended fix**: Add `min-width: 44px; min-height: 44px; display: grid; place-items: center;` to `.panel-close-button` on mobile.

### TTMOB-003: Admin User Action Buttons Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Admin Panel — Users tab
- **CSS**: `.admin-action-button` (line 2067 in App.css)
- **Current size**: `padding: 4px 10px; font-size: 0.8rem` (~12.8px). Computed height is approximately 25px.
- **Standard**: 44x44px minimum
- **Gap**: 19px below minimum
- **Impact**: Ban, Suspend, Unban, and Unsuspend buttons are very difficult to tap accurately. Risk of accidental action on wrong user. Adjacent destructive buttons (Ban/Suspend) lack spacing safeguards.
- **Cross-reference**: `ADMOB-004` from ISSUE-135.
- **Recommended fix**: Increase padding to `12px 14px` and font-size to at least `14px` on mobile. Add 8px gap between adjacent destructive actions.

### TTMOB-004: Notification Mark-Read Button Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Notifications Inbox
- **CSS**: `.notification-mark-read-button` (line 1230 in App.css)
- **Current size**: `padding: 7px 9px; font-size: 13px`. Computed height is approximately 30px.
- **Standard**: 44x44px minimum
- **Gap**: 14px below minimum
- **Impact**: Small inline button is difficult to tap per notification item.
- **Cross-reference**: `NTMOB-002` from ISSUE-135.
- **Recommended fix**: Increase padding to `12px 14px` and font-size to `14px` on mobile.

### TTMOB-005: Notification Mark-All Button Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Notifications Inbox
- **CSS**: `.notifications-list-header button` (line 1133 in App.css)
- **Current size**: `padding: 8px 10px` with inherited 16px font-size. Computed height is approximately 35px.
- **Standard**: 44x44px minimum
- **Gap**: 9px below minimum
- **Impact**: Mark All as Read header button is undersized.
- **Cross-reference**: `NTMOB-003` from ISSUE-135.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-006: Admin Tab Filter Buttons Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Admin Panel — Fields, Games, Field Reports tabs
- **CSS**: `.admin-tab-button` (line 1762 in App.css)
- **Current size**: `padding: 9px 12px`. Computed height is approximately 37px.
- **Standard**: 44x44px minimum
- **Gap**: 7px below minimum
- **Impact**: Switching between Approved/Pending/All filter tabs is harder than necessary.
- **Cross-reference**: `ADMOB-005` from ISSUE-135.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-007: Admin Table Action Buttons Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Admin Panel — Fields, Games tables
- **CSS**: `.admin-actions button` (line 1828 in App.css), `.admin-secondary-button` / `.admin-danger-button` (line 1901 in App.css)
- **Current size**: `padding: 8px 10px`. Computed height is approximately 35px.
- **Standard**: 44x44px minimum
- **Gap**: 9px below minimum
- **Impact**: Approve, Reject, Delete, and status-change buttons in admin tables are undersized.
- **Cross-reference**: `ADMOB-006` from ISSUE-135.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-008: Admin Status Select Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Admin Panel — Fields, Games tables
- **CSS**: `.admin-status-select` (line 1851 in App.css)
- **Current size**: `padding: 8px 10px`. Computed height is approximately 35px.
- **Standard**: 44x44px minimum
- **Gap**: 9px below minimum
- **Impact**: Status dropdown is difficult to tap in table rows.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-009: Leaflet Zoom Controls Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Map
- **CSS**: Leaflet default styles (not in App.css)
- **Current size**: `width: 30px; height: 30px` (Leaflet default)
- **Standard**: 44x44px minimum
- **Gap**: 14px below minimum
- **Impact**: Zoom in/out buttons are small on touch screens.
- **Cross-reference**: `ML-MAP-002` from ISSUE-135.
- **Recommended fix**: Override `.leaflet-control-zoom a` with `width: 44px; height: 44px; line-height: 44px;` on mobile.

### TTMOB-010: City Autocomplete Suggestion Options Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Notifications Preferences (CityAutocomplete)
- **CSS**: `.city-autocomplete-option` (line 1360 in App.css)
- **Current size**: `padding: 10px 12px; font-size: 14px; line-height: 1.3`. Computed height is approximately 38px.
- **Standard**: 44x44px minimum
- **Gap**: 6px below minimum
- **Impact**: Suggestion items are slightly undersized for reliable finger tapping, especially when scrolling through the list.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-011: Language Switcher Select Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Login (language switcher in top-right corner)
- **CSS**: `.language-switcher select` (line 74 in App.css)
- **Current size**: `padding: 7px 9px`. Computed height is approximately 33px.
- **Standard**: 44x44px minimum
- **Gap**: 11px below minimum
- **Impact**: Language selection dropdown is undersized.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-012: Auth Toolbar Logout Button Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Map page (auth toolbar in top area)
- **CSS**: `.auth-toolbar button` (line 398 in App.css)
- **Current size**: `padding: 8px 10px`. Computed height is approximately 35px.
- **Standard**: 44x44px minimum
- **Gap**: 9px below minimum
- **Impact**: Logout button is undersized.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-013: Location Picker Button Below 44px Touch Target

- **Severity**: Medium
- **Screens**: Add Field Modal (location picker header)
- **CSS**: `.location-picker-header button` (line 1440 in App.css)
- **Current size**: `padding: 8px 10px`. Computed height is approximately 35px.
- **Standard**: 44x44px minimum
- **Gap**: 9px below minimum
- **Impact**: "Use current location" button in the Add Field modal is undersized.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-014: My Games Filter Toggle Below 44px Touch Target

- **Severity**: Medium
- **Screens**: My Games
- **CSS**: `.my-games-filter-toggle` (line 2143 in App.css)
- **Current size**: `padding: 6px 14px; font-size: 14px`. Computed height is approximately 29px.
- **Standard**: 44x44px minimum
- **Gap**: 15px below minimum
- **Impact**: Filter toggle pill is significantly undersized for touch interaction.
- **Recommended fix**: Increase padding to `14px` vertical on mobile.

### TTMOB-015: Auth Mode Tab Buttons Below 44px Touch Target

- **Severity**: Low
- **Screens**: Login / Registration
- **CSS**: `.auth-mode-tabs button` (line 190 in App.css)
- **Current size**: `padding: 10px 12px; font-size: 14px`. Computed height is approximately 41px.
- **Standard**: 44x44px minimum
- **Gap**: 3px below minimum
- **Impact**: Login/Register tabs are marginally undersized. Low severity because the gap is small and users tap these infrequently.
- **Cross-reference**: `ML-LOGIN-002` and `ML-REGISTER-004` from ISSUE-135.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-016: Notification Tab Buttons Below 44px Touch Target

- **Severity**: Low
- **Screens**: Notifications Preferences
- **CSS**: `.notifications-tabs button` (line 1097 in App.css)
- **Current size**: `padding: 10px 12px`. Computed height is approximately 41px.
- **Standard**: 44x44px minimum
- **Gap**: 3px below minimum
- **Impact**: Preferences/Inbox tab buttons are marginally undersized. Low severity due to small gap.
- **Recommended fix**: Increase padding to `12px 14px` on mobile.

### TTMOB-017: My Games Back Button Below 44px Touch Target

- **Severity**: Low
- **Screens**: My Games
- **CSS**: `.my-games-back-button` (line 2125 in App.css)
- **Current size**: No explicit padding, just `background: transparent`. Computed height is approximately 19px (text only).
- **Standard**: 44x44px minimum
- **Gap**: 25px below minimum
- **Impact**: Back button text with no padding is very undersized, but it is navigational and not a frequent tap target.
- **Recommended fix**: Add `min-height: 44px; padding: 10px 0;` on mobile.

### TTMOB-018: Error Retry Buttons Below 44px Touch Target

- **Severity**: Low
- **Screens**: Admin Panel errors, My Games errors, Admin Stats errors
- **CSS**: `.admin-error button`, `.admin-stats-error button`, `.my-games-error button` (line 2387 in App.css)
- **Current size**: `padding: 6px 16px; font-size: 13px`. Computed height is approximately 28px.
- **Standard**: 44x44px minimum
- **Gap**: 16px below minimum
- **Impact**: Error state retry buttons are undersized, but error states are infrequent.
- **Recommended fix**: Increase padding to `12px 16px` on mobile.

## Known Findings From Previous Audits

The following touch-target-related findings from `docs/mobile-audit-consolidated-report.md` (ISSUE-135) are cross-referenced with this audit:

| ISSUE-135 ID | This Audit ID | Screen | Element | Status |
| :--- | :--- | :--- | :--- | :--- |
| `CGMOB-003` | `TTMOB-001` | Create Game | Modal close button, form inputs | Cataloged — close button covered; form input height (~38px with 10px+10px padding) is borderline |
| `GDMOB-002` | — | Game Details | Participants toggle header | Re-measured: `.participants-toggle-button` has `padding: 12px 14px` = ~43px. Borderline pass, not a new finding |
| `NTMOB-002` | `TTMOB-004` | Notifications | Mark-read button | Cataloged |
| `NTMOB-003` | `TTMOB-005` | Notifications | Mark-all button | Cataloged |
| `ADMOB-004` | `TTMOB-003` | Admin Panel | User moderation buttons | Cataloged |
| `ADMOB-005` | `TTMOB-006` | Admin Panel | Tab filter buttons | Cataloged |
| `ADMOB-006` | `TTMOB-007` | Admin Panel | Table action buttons | Cataloged |
| `ML-MAP-002` | `TTMOB-009` | Map | Leaflet zoom controls | Cataloged |
| `ML-LOGIN-002` | `TTMOB-015` | Login | Auth tab buttons | Cataloged |
| `ML-REGISTER-004` | `TTMOB-015` | Registration | Auth tab buttons (shared with login) | Cataloged |

## Screen-by-Screen Review

### Login / Registration Screen

**Components**: `LoginPage.jsx`, `LanguageSwitcher.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Language switcher | `.language-switcher select` | ~33px | `TTMOB-011` |
| Auth mode tabs | `.auth-mode-tabs button` | ~41px | `TTMOB-015` |
| Password input | `.auth-form input` | ~39px | Borderline — no finding |
| Submit button | `.auth-form button[type=submit]` | ~43px | Borderline pass |
| Google OAuth button | Container `min-height: 44px` | ≥44px | PASS |

### Map Screen

**Components**: `MapPage.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Floating buttons | `.floating-button` | 52px | PASS |
| Field markers | `.field-marker` | 54px | PASS |
| Leaflet zoom controls | `.leaflet-control-zoom a` | 30px | `TTMOB-009` |
| Auth toolbar logout | `.auth-toolbar button` | ~35px | `TTMOB-012` |

### Field Details Panel

**Components**: `FieldDetailsPanel.jsx`, `GamePanel.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Panel close button | `.panel-close-button` | ~20px | `TTMOB-002` |
| Primary panel button | `.primary-panel-button` | ~43px | Borderline pass |
| Secondary panel button | `.secondary-panel-button` | ~43px | Borderline pass |
| Danger panel button | `.danger-panel-button` | ~43px | Borderline pass |
| Participants toggle | `.participants-toggle-button` | ~43px | Borderline pass |
| Navigation option buttons | `.navigation-option-button` | ≥44px | PASS |

### Create Game Modal

**Components**: `OpenGameModal.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Modal close button | `.modal-close-button` | ~20px | `TTMOB-001` |
| Form inputs | `.open-game-form input` | ~39px | Borderline — not a new finding |
| Schedule radio labels | `.schedule-mode-options label` | ~41px | Borderline fail — subsumed by `TTMOB-015` pattern |
| Submit button | `.primary-panel-button` | ~43px | Borderline pass |

### Notifications

**Components**: `NotificationInboxModal.jsx`, `NotificationsModal.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Modal close button | `.modal-close-button` | ~20px | `TTMOB-001` |
| Mark-read button | `.notification-mark-read-button` | ~30px | `TTMOB-004` |
| Mark-all button | `.notifications-list-header button` | ~35px | `TTMOB-005` |
| Notification tabs | `.notifications-tabs button` | ~41px | `TTMOB-016` |
| City autocomplete options | `.city-autocomplete-option` | ~38px | `TTMOB-010` |

### Add Field Modal

**Components**: `AddFieldModal.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Modal close button | `.modal-close-button` | ~20px | `TTMOB-001` |
| Location picker button | `.location-picker-header button` | ~35px | `TTMOB-013` |
| Submit/cancel buttons | `.primary-modal-button` / `.secondary-modal-button` | ~43px | Borderline pass |

### Field Report Modal

**Components**: `FieldReportModal.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Modal close button | `.modal-close-button` | ~20px | `TTMOB-001` |
| Submit/cancel buttons | `.primary-modal-button` / `.secondary-modal-button` | ~43px | Borderline pass |

### Admin Panel

**Components**: `AdminPage.jsx`, `AdminUsers.jsx`, `AdminFields.jsx`, `AdminGames.jsx`, `AdminFieldReports.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Sidebar buttons | `.admin-sidebar-button` | ~43px | Borderline pass |
| Tab filter buttons | `.admin-tab-button` | ~37px | `TTMOB-006` |
| Table action buttons | `.admin-actions button` | ~35px | `TTMOB-007` |
| Secondary/danger buttons | `.admin-secondary-button` | ~35px | `TTMOB-007` |
| User action buttons | `.admin-action-button` | ~25px | `TTMOB-003` |
| Status select | `.admin-status-select` | ~35px | `TTMOB-008` |
| Back link | `.admin-back-link` | ~41px | Borderline fail |
| Error retry buttons | `.admin-error button` | ~28px | `TTMOB-018` |

### My Games

**Components**: `MyGamesPage.jsx`

| Element | Class | Touch Target | Finding |
| :--- | :--- | :--- | :--- |
| Back button | `.my-games-back-button` | ~19px | `TTMOB-017` |
| Filter toggle | `.my-games-filter-toggle` | ~29px | `TTMOB-014` |
| Error retry button | `.my-games-error button` | ~28px | `TTMOB-018` |

## Remediation Plan

### Priority 1 — Close Buttons (TTMOB-001, TTMOB-002)

**Impact**: All modals and the Field Details panel
**Effort**: Small — CSS-only change
**Approach**: Add `min-width: 44px; min-height: 44px; display: grid; place-items: center;` to `.modal-close-button` and `.panel-close-button` in a mobile media query. No component changes needed.

### Priority 2 — Admin User Action Buttons (TTMOB-003)

**Impact**: Admin user moderation — destructive actions with tiny targets
**Effort**: Small — CSS-only change
**Approach**: Increase `.admin-action-button` padding to `12px 14px` and font-size to `14px` on mobile. Add 8px gap between adjacent destructive buttons (already present via flex gap).

### Priority 3 — Notification Action Buttons (TTMOB-004, TTMOB-005)

**Impact**: Notification inbox read actions
**Effort**: Small — CSS-only change
**Approach**: Increase padding on `.notification-mark-read-button` and `.notifications-list-header button` to achieve 44px height on mobile.

### Priority 4 — Admin Table and Filter Buttons (TTMOB-006, TTMOB-007, TTMOB-008)

**Impact**: Admin panel tab filters and table row actions
**Effort**: Small — CSS-only changes
**Approach**: Increase padding on `.admin-tab-button`, `.admin-actions button`, `.admin-secondary-button`, `.admin-danger-button`, and `.admin-status-select` on mobile.

### Priority 5 — Map and Autocomplete (TTMOB-009, TTMOB-010)

**Impact**: Leaflet zoom controls and city autocomplete suggestions
**Effort**: Small — CSS override for Leaflet; padding increase for autocomplete
**Approach**: Override Leaflet zoom control size on mobile. Increase `.city-autocomplete-option` padding on mobile.

### Priority 6 — Remaining Elements (TTMOB-011 through TTMOB-018)

**Impact**: Language switcher, auth toolbar, location picker button, My Games buttons, error retry buttons
**Effort**: Small — CSS-only changes
**Approach**: Increase padding values on mobile for each element. All are mobile-scoped CSS changes with no component modifications.

### Remediation Implementation Notes

- All fixes must be scoped to `@media (max-width: 640px)` to preserve desktop layout.
- Close button fixes (TTMOB-001, TTMOB-002) should use `min-width`/`min-height` rather than changing `padding`, to avoid repositioning the `x` character.
- Admin action button gap (TTMOB-003) is already addressed by the `gap: 6px` on `.admin-user-actions`, which meets the 8px gap recommendation only if padding increases do not cause overflow. Test on 360px viewport.
- Leaflet zoom control override (TTMOB-009) requires targeting `.leaflet-control-zoom a` which is a third-party CSS selector. Use specific enough selector to avoid unintended side effects.

## Engineering Rules

1. **All interactive elements must achieve at least 44x44px touch target area on mobile** (per `docs/mobile-design-guide.md`).
2. **Primary action buttons should target 48x48px** touch area on mobile.
3. **Icon-only buttons** (close, toggle) must use `min-width`/`min-height` to achieve 44px hit diameter.
4. **Adjacent destructive buttons** must maintain at least 8px separation.
5. **Touch target fixes must be mobile-scoped** using `@media (max-width: 640px)` to preserve desktop layout.
6. **Third-party controls** (Leaflet) must be overridden via CSS specificity, not by modifying library source.
7. **New interactive elements** added in future issues must meet the 44px standard before merge.

## Risks

| Risk | Severity | Mitigation |
| :--- | :--- | :--- |
| Increasing padding may cause text wrapping or layout overflow on narrow admin tables | Medium | Test all changes on 360px viewport width. Use `white-space: nowrap` where appropriate. |
| Close button padding increase may shift the `x` character position | Low | Use `min-width`/`min-height` with `display: grid; place-items: center` instead of padding. |
| Leaflet CSS override may conflict with future Leaflet version updates | Low | Pin Leaflet version and document the override in a CSS comment. |
| Increasing autocomplete option height reduces visible suggestion count | Low | Acceptable trade-off for touch usability. Max-height on suggestions container ensures scroll. |

## Final Verdict

The frontend has **18 touch target violations** across all screens. The most severe cluster is the modal/panel close buttons (TTMOB-001, TTMOB-002) at ~20px — less than half the 44px standard — affecting every modal in the application. The admin panel has 6 violations concentrated in action buttons and filter tabs.

All violations are fixable with CSS-only changes scoped to mobile viewports. No component restructuring is needed. Remediation should proceed in the priority order defined above, starting with close buttons (highest impact, lowest effort) and progressing through admin and notification buttons.

No touch target violations are blocking for desktop use. Mobile production readiness requires at minimum fixing Priority 1 (close buttons) and Priority 2 (admin destructive action buttons) before launch.
