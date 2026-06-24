# Frontend Error State Inventory

**Issue:** ISSUE-059  
**Date:** 2026-06-24  
**Status:** Complete  
**Scope:** All frontend screens, components, modals, and async operations  

---

## 1. Purpose

This document provides a complete inventory of every frontend error state across the yesh_mishak app. It identifies how each component handles loading, errors, failures, and edge cases — and where gaps exist. The goal is to enable follow-up implementation issues with precise, actionable findings.

## 2. Scope

The audit covers every file in `frontend/src/` that performs:
- API calls (Axios via `api/client.js`)
- Async operations (geolocation, Firebase push tokens, dynamic imports)
- Form submissions
- Auth flows (Google OAuth, password login/register)
- Admin moderation actions
- Notification operations (preferences, push, inbox)
- Map/field loading

**Framework:** React 19 + Vite, Axios, Leaflet, Firebase Messaging, i18next.

## 3. Method

1. Read every component, page, modal, API service, and utility file in `frontend/src/`.
2. Traced every `try/catch`, `.catch()`, error state variable, loading state, and `console.error` call.
3. Verified whether errors are shown to the user, logged only, or swallowed silently.
4. Checked for retry/recovery mechanisms.
5. Assessed severity of each gap.

---

## 4. Summary Table

| # | Area | Component | File | Operation | Error Visible? | Loading State? | Retry? | Severity |
|---|------|-----------|------|-----------|---------------|---------------|--------|----------|
| 1 | Auth | LoginPage | `src/components/LoginPage.jsx` | Google OAuth init | Yes | Yes | No | OK |
| 2 | Auth | LoginPage | `src/components/LoginPage.jsx` | Google sign-in callback | Yes | Yes | No | OK |
| 3 | Auth | LoginPage | `src/components/LoginPage.jsx` | Password login | Yes | Yes | No | OK |
| 4 | Auth | LoginPage | `src/components/LoginPage.jsx` | Password register | Yes | Yes | No | OK |
| 5 | Auth | AdminRoute | `src/components/AdminRoute.jsx` | Admin verification | Yes | Yes | Yes | OK |
| 6 | Map | MapPage / FieldLoader | `src/pages/MapPage.jsx` | Load fields | Yes | Yes | No (auto-reload on pan) | OK |
| 7 | Map | MapPage | `src/pages/MapPage.jsx` | Geolocation | Silent | No | No | Partial |
| 8 | Map | MapPage | `src/pages/MapPage.jsx` | Notification polling | Silent | No | Auto (interval) | Partial |
| 9 | Map | MapPage | `src/pages/MapPage.jsx` | Initial notification load | Silent | No | No | Partial |
| 10 | Map | MapPage | `src/pages/MapPage.jsx` | Refresh field by ID | Silent fallback | No | Falls back to full reload | OK |
| 11 | Map | MapPage | `src/pages/MapPage.jsx` | Notification target navigation | Silent | No | No | Partial |
| 12 | Games | GamePanel | `src/components/GamePanel.jsx` | Join game | Yes | Yes | No | OK |
| 13 | Games | GamePanel | `src/components/GamePanel.jsx` | Leave game | Yes | Yes | No | OK |
| 14 | Games | GamePanel | `src/components/GamePanel.jsx` | Extend game | Yes | Yes | No | OK |
| 15 | Games | GamePanel | `src/components/GamePanel.jsx` | Close game | Yes | Yes | No | OK |
| 16 | Games | OpenGameModal | `src/components/OpenGameModal.jsx` | Create game | Yes | Yes | No | OK |
| 17 | Games | MyGamesPage | `src/pages/MyGamesPage.jsx` | Load my games | Yes | Yes | No | Partial |
| 18 | Fields | AddFieldModal | `src/components/AddFieldModal.jsx` | Create field | Yes | Yes | No | OK |
| 19 | Fields | AddFieldModal | `src/components/AddFieldModal.jsx` | Geolocation | Yes | No | No | Partial |
| 20 | Fields | FieldReportModal | `src/components/FieldReportModal.jsx` | Submit report | Yes | Yes | No | OK |
| 21 | Notifications | NotificationsModal | `src/components/NotificationsModal.jsx` | Load preferences | Yes | Yes | No | Partial |
| 22 | Notifications | NotificationsModal | `src/components/NotificationsModal.jsx` | Save preferences | Yes | Yes | No | OK |
| 23 | Notifications | NotificationsModal | `src/components/NotificationsModal.jsx` | Geolocation for distance | Yes (partial) | No | No | OK |
| 24 | Notifications | NotificationsModal | `src/components/NotificationsModal.jsx` | Enable push | Yes + console.error | Yes | No | Partial |
| 25 | Notifications | NotificationsModal | `src/components/NotificationsModal.jsx` | Disable push | Yes + console.error | Yes | No | Partial |
| 26 | Notifications | NotificationsModal | `src/components/NotificationsModal.jsx` | Test push | Yes + console.error | Yes | No | Partial |
| 27 | Notifications | NotificationInboxModal | `src/components/NotificationInboxModal.jsx` | Mark read | Yes | Yes | No | OK |
| 28 | Notifications | NotificationInboxModal | `src/components/NotificationInboxModal.jsx` | Mark all read | Yes | Yes | No | OK |
| 29 | Admin | AdminStats | `src/components/admin/AdminStats.jsx` | Load stats | Yes | Yes | No | Partial |
| 30 | Admin | AdminFields | `src/components/admin/AdminFields.jsx` | Load pending fields | Yes | Yes | No | Partial |
| 31 | Admin | AdminFields | `src/components/admin/AdminFields.jsx` | Load all fields | Yes | Yes | No | Partial |
| 32 | Admin | AdminFields | `src/components/admin/AdminFields.jsx` | Approve field | Yes | Yes (per-field) | No | OK |
| 33 | Admin | AdminFields | `src/components/admin/AdminFields.jsx` | Reject field | Yes | Yes (per-field) | No | OK |
| 34 | Admin | AdminFields | `src/components/admin/AdminFields.jsx` | Update field status | Yes | Yes (per-field) | No | OK |
| 35 | Admin | AdminGames | `src/components/admin/AdminGames.jsx` | Load games | Yes | Yes | No | Partial |
| 36 | Admin | AdminGames | `src/components/admin/AdminGames.jsx` | Extend game | Yes | Yes (per-game) | No | OK |
| 37 | Admin | AdminGames | `src/components/admin/AdminGames.jsx` | Close game | Yes | Yes (per-game) | No | OK |
| 38 | Admin | AdminUsers | `src/components/admin/AdminUsers.jsx` | Load users | Yes | Yes | No | Partial |
| 39 | Admin | AdminUsers | `src/components/admin/AdminUsers.jsx` | Ban/Suspend/Unban/Unsuspend | Yes | Yes (per-user) | No | OK |
| 40 | Admin | AdminFieldReports | `src/components/admin/AdminFieldReports.jsx` | Load reports | Yes | Yes | No | Partial |
| 41 | Firebase | firebaseMessaging.js | `src/firebaseMessaging.js` | Push token request | Thrown (caller handles) | N/A | No | OK |
| 42 | Firebase | App.jsx | `src/App.jsx` | Start foreground push | Swallowed | No | No | Missing |
| 43 | App | App.jsx | `src/App.jsx` | Unhandled errors | No error boundary | N/A | No | Missing |
| 44 | Status | BackendStatusPage | `src/pages/BackendStatusPage.jsx` | Health check | Yes | Yes | No | OK |

---

## 5. Detailed Findings by Area

### 5.1 Authentication (LoginPage.jsx)

**Google OAuth flow** (lines 70-142):
- Handles: missing client ID, script load failure, button mount failure, no credential, sign-in API failure.
- All errors set `error` state and display via `<p>` element.
- Loading state via `isLoading` disables form elements.
- `isMounted` guard prevents state updates after unmount.
- **Gap:** No retry button. User must reload the page if Google script fails to load.
- **Severity: OK** — all errors are visible, well-translated.

**Password login** (lines 167-180):
- Extracts backend error via `getApiErrorMessage()` which reads `response.data.detail`.
- Falls back to generic translated message.
- **Severity: OK**.

**Password register** (lines 182-195):
- Same pattern as login.
- **Gap:** No field-level validation errors (e.g., which specific field failed). Backend may return array of validation errors but only the first `.msg` is shown.
- **Severity: OK** — functional, could be improved.

### 5.2 Map (MapPage.jsx)

**Field loading** (FieldLoader, lines 145-189):
- Uses `requestId` pattern to prevent stale responses.
- Sets error state on failure, displayed in `.map-error` div.
- Auto-reloads on map pan/zoom (`moveend` event).
- **Severity: OK**.

**User geolocation** (lines 246-282):
- Silent failure: error callback sets `userLocation` to `null` but shows no message.
- User simply doesn't see their location marker.
- **Gap:** No user feedback when location is denied or unavailable.
- **Severity: Partial** — functional degradation is graceful but user has no idea why.

**Notification polling** (lines 298-343):
- `refreshUnreadCount()` catches errors and sets count to 0 silently.
- Initial notification load (lines 307-327) also catches silently — sets empty arrays.
- **Gap:** If notification API is down, user sees badge count reset to 0 with no indication of failure.
- **Severity: Partial** — silent failure is reasonable for polling but could show stale count.

**Notification target navigation** (lines 431-456):
- When clicking a notification to navigate to its field, if field not found in current list, fetches all fields.
- If that fetch also fails, catches silently and `targetField` stays null — nothing happens.
- **Gap:** No feedback when target field can't be found.
- **Severity: Partial**.

**Field cache** (lines 55-87):
- `readCachedFields` and `writeCachedFields` both catch JSON parse errors silently with fallback.
- **Severity: OK** — localStorage is a cache, silent fallback is correct.

### 5.3 Games

**GamePanel.jsx** (lines 167-226):
- All four actions (join, leave, extend, close) follow identical pattern: `setIsLoading(true)`, `setError('')`, try/catch, translated error, finally `setIsLoading(false)`.
- Errors displayed in `<p className="panel-error">`.
- Close game has `window.confirm()` gate.
- Buttons disabled during `isLoading`.
- **Gap:** Generic error messages — doesn't extract backend detail (e.g., "game is full", "already a participant"). Uses only translated fallback like `t('game.joinFailed')`.
- **Severity: OK** — all errors visible, but messages could be more specific.

**OpenGameModal.jsx** (lines 37-108):
- Client-side validation for all fields before API call.
- `getErrorMessage()` (lines 6-22) handles 401, checks for "active game already exists", falls through to raw `detail` string, then generic fallback.
- **Severity: OK** — well-handled, extracts backend messages.

**MyGamesPage.jsx** (lines 115-126):
- Loads games with loading + error state.
- Error displayed in page.
- **Gap:** No retry button. User must navigate away and back.
- **Severity: Partial**.

### 5.4 Fields

**AddFieldModal.jsx** (lines 91-127):
- Validates name and coordinates before submission.
- `getErrorMessage()` handles 401, generic fallback otherwise.
- **Gap:** Does not extract backend `detail` (e.g., content moderation rejection message). Returns generic `t('addField.submitFailed')` for all non-401 errors.
- **Severity: OK** — functional, but content moderation rejection won't show the specific reason.

**AddFieldModal.jsx — geolocation** (lines 74-88):
- Shows error if `navigator.geolocation` is unavailable.
- Shows error if `getCurrentPosition` fails.
- **Gap:** No loading indicator while waiting for location.
- **Severity: Partial**.

**FieldReportModal.jsx** (lines 42-81):
- Full validation: category required, description required.
- `getApiErrorMessage()` extracts `detail` string, array `.msg`, or `.message`.
- Success closes modal after 700ms delay.
- **Severity: OK**.

### 5.5 Notifications

**NotificationsModal.jsx — load preferences** (lines 124-155):
- Loading state, error state, `isMounted` guard.
- Loads both preferences and fields in parallel via `Promise.all`.
- **Gap:** If only one of the two parallel requests fails, both fail together. No partial recovery.
- **Severity: Partial**.

**NotificationsModal.jsx — save preferences** (lines 228-293):
- Validates city against `israelCities` list.
- Geolocation failure is handled gracefully: saves other prefs, shows partial success message.
- **Severity: OK** — sophisticated partial success handling.

**NotificationsModal.jsx — push notifications** (lines 295-366):
- Enable, disable, and test push all use `isPushSavingRef` to prevent double-submission.
- All three use `console.error()` in addition to setting error state.
- **Gap:** `console.error` is redundant and may leak info in production. Not harmful but unnecessary.
- **Severity: Partial** — errors are visible to user, `console.error` is a minor issue.

**NotificationInboxModal.jsx** (lines 55-107):
- Mark read and mark all read both show errors in modal.
- Proper loading states per notification.
- **Severity: OK**.

### 5.6 Admin

**AdminRoute.jsx** (lines 24-71):
- Handles 401 (clears auth, redirects to login), 403 (calls `onForbidden`), other errors (shows with retry button).
- **Severity: OK** — has retry mechanism, the only component in the app with one.

**AdminStats.jsx** (lines 19-48):
- Loading and error states, `isMounted` guard.
- **Gap:** No retry. User must navigate away and back.
- **Severity: Partial**.

**AdminFields.jsx** (lines 62-170):
- Three separate error states: `pendingError`, `allFieldsError`, `actionError`.
- Per-field loading via `workingFieldId`.
- **Gap:** No retry on initial load failure. `actionError` is not cleared when switching tabs.
- **Severity: Partial**.

**AdminGames.jsx** (lines 106-175):
- Separate `loadError` and `actionError`.
- Per-game loading via `workingGameId`.
- Reloads full game list after successful action.
- **Gap:** No retry on initial load failure.
- **Severity: Partial**.

**AdminUsers.jsx** (lines 50-118):
- `window.prompt()` for ban/suspend reason — returns `null` on cancel (handled correctly).
- Validates non-empty reason.
- Per-user loading via `actionLoading`.
- **Gap:** No retry on initial load. `window.prompt()` is a poor UX for collecting moderation reasons.
- **Severity: Partial**.

**AdminFieldReports.jsx** (lines 27-52):
- Read-only component with loading/error states.
- **Gap:** No retry on load failure. No actions (view only).
- **Severity: Partial**.

### 5.7 Firebase / Push Notifications

**firebaseMessaging.js** (lines 24-148):
- `assertFirebaseConfig()` throws synchronously if env vars missing.
- `getFirebaseMessaging()` throws if: no service worker support, no Notification API, Firebase not supported.
- `requestNotificationPermission()` throws with descriptive messages for denied/not-granted states.
- `requestFirebasePushToken()` throws if no token returned.
- All errors propagate to caller (NotificationsModal), which catches and displays them.
- **Severity: OK** — clean throw-based pattern.

**startForegroundPushNotifications** (App.jsx line 72):
- Called with `.catch(() => {})` — error is swallowed entirely.
- **Gap:** If foreground push setup fails silently, user receives no foreground notifications and has no idea.
- **Severity: Missing** — completely silent failure with no logging.

### 5.8 App-Level

**App.jsx**:
- No React Error Boundary wrapping any component.
- An unhandled error in any component will crash the entire app with a white screen.
- **Gap:** No global error boundary, no fallback UI, no error recovery.
- **Severity: Missing** — any unhandled exception crashes the app.

### 5.9 Language Selection

**LanguageSelectionScreen.jsx**, **LanguageSwitcher.jsx**:
- `i18n.changeLanguage()` is called without error handling.
- **Gap:** If language change fails (extremely unlikely with bundled translations), no error is shown.
- **Severity: OK** — risk is negligible with static bundles.

---

## 6. Critical Gaps

### 6.1 No React Error Boundary (App.jsx)
- **Impact:** Any unhandled exception renders a blank white screen with no recovery option.
- **Risk:** High. A single malformed API response, null pointer, or rendering error crashes the entire app.
- **Fix:** Add a top-level `ErrorBoundary` component that catches render errors and shows a "Something went wrong" screen with a retry/reload button.

### 6.2 Foreground Push Setup Silently Swallowed (App.jsx:72)
- **Impact:** If Firebase foreground messaging setup fails, user gets no foreground push notifications and has no indication.
- **Risk:** Medium. Affects notification delivery without user awareness.
- **Fix:** At minimum log the error. Optionally set a state flag to show a subtle banner.

### 6.3 No Retry on Data Load Failures (Multiple Admin Components, MyGamesPage)
- **Impact:** If initial data load fails (network blip, server restart), user sees an error message with no way to retry except navigating away and back.
- **Affected:** AdminStats, AdminFields, AdminGames, AdminUsers, AdminFieldReports, MyGamesPage.
- **Risk:** Medium. Poor UX during transient failures.
- **Fix:** Add retry buttons on error states, similar to AdminRoute's pattern.

### 6.4 Generic Error Messages Hide Backend Details (GamePanel, AddFieldModal)
- **Impact:** GamePanel actions (join/leave/extend/close) and AddFieldModal don't extract backend error details. Users see generic "Failed to join game" instead of specific reasons like "Game is full" or "Content violates guidelines".
- **Risk:** Medium. Users can't understand why their action failed.
- **Fix:** Extract `response.data.detail` (same pattern used in OpenGameModal and FieldReportModal).

### 6.5 Silent Geolocation Failure on Map (MapPage.jsx:267-271)
- **Impact:** If browser geolocation is denied or unavailable, map silently centers on default location. User has no feedback about why their location isn't shown.
- **Risk:** Low. App works fine without location; just poor discoverability.
- **Fix:** Optional subtle message like "Location unavailable — showing default area."

---

## 7. Patterns Observed

### 7.1 Consistent Positive Patterns
- **isMounted guard:** Used in 10+ components to prevent state updates after unmount. Well-implemented.
- **Loading states:** Every async operation has a loading state that disables relevant buttons.
- **Error state variables:** Every component that makes API calls has `[error, setError]`.
- **Error clearing:** Errors are cleared at the start of each new operation.
- **i18n error messages:** All user-facing error messages use `t()` for translation.
- **Request deduplication:** Fields API uses request dedup to prevent duplicate fetches.
- **requestId pattern:** MapPage FieldLoader uses incrementing request IDs to handle race conditions.

### 7.2 Anti-Patterns Found
- **`console.error` in production:** NotificationsModal uses `console.error` for push notification errors (lines 312, 336, 360). Should be removed or replaced with structured logging.
- **`window.prompt()` for moderation:** AdminUsers uses browser `prompt()` for collecting ban/suspend reasons. Poor UX, not translatable, not validatable beyond empty-check.
- **`window.confirm()` for destructive action:** GamePanel uses browser `confirm()` for game close. Functional but not consistent with the modal-based UI elsewhere.
- **No error boundary:** App has no crash recovery mechanism.

---

## 8. Recommended Next Issues

| Priority | Issue Title | Scope | Effort |
|----------|-------------|-------|--------|
| P0 | Add React Error Boundary | App.jsx — wrap entire app | Small |
| P1 | Add retry buttons to admin data load failures | AdminStats, AdminFields, AdminGames, AdminUsers, AdminFieldReports | Medium |
| P1 | Extract backend error details in GamePanel | GamePanel.jsx — 4 action handlers | Small |
| P1 | Extract backend error details in AddFieldModal | AddFieldModal.jsx — getErrorMessage | Small |
| P1 | Add retry button to MyGamesPage | MyGamesPage.jsx | Small |
| P2 | Replace window.prompt with modal for moderation reasons | AdminUsers.jsx | Medium |
| P2 | Replace window.confirm with custom modal for game close | GamePanel.jsx | Small |
| P2 | Log or surface foreground push setup failure | App.jsx line 72 | Small |
| P2 | Remove console.error calls from NotificationsModal | NotificationsModal.jsx lines 312, 336, 360 | Small |
| P3 | Show subtle message for geolocation failure on map | MapPage.jsx | Small |
| P3 | Add notification load failure indicator on map | MapPage.jsx polling | Small |
| P3 | Improve NotificationsModal partial failure for Promise.all | NotificationsModal.jsx | Small |

---

## 9. Definition of Done Checklist

- [x] All frontend pages inspected: MapPage, MyGamesPage, OnboardingPage, AdminPage, BackendStatusPage
- [x] All frontend components inspected: LoginPage, AdminRoute, GamePanel, FieldDetailsPanel, OpenGameModal, FieldReportModal, AddFieldModal, NotificationsModal, NotificationInboxModal, CityAutocomplete, LanguageSelectionScreen, LanguageSwitcher, StatusCard
- [x] All admin components inspected: AdminStats, AdminFields, AdminGames, AdminUsers, AdminFieldReports
- [x] All API services inspected: auth.js, games.js, fields.js, fieldReports.js, notifications.js, admin.js, backend.js, client.js
- [x] Firebase messaging inspected: firebaseMessaging.js
- [x] App.jsx top-level error handling inspected
- [x] Every try/catch, .catch(), error state documented
- [x] Every loading state documented
- [x] console.error usage documented
- [x] window.alert / window.confirm / window.prompt usage documented
- [x] Silent failures documented
- [x] Missing retry mechanisms documented
- [x] Critical gaps identified
- [x] Recommended follow-up issues listed with priority and effort
- [x] No frontend code was changed
- [x] No backend code was changed
