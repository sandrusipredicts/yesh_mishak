# Authentication Storage Audit (ISSUE-226)

## Summary

The web application persists the entire authentication session in plain browser `localStorage`. The JWT access token, the user identifier, and user profile fields are written at login, read synchronously at startup for session restoration, attached to every API request by an Axios interceptor, and removed by three separate logout/cleanup paths that are not fully consistent with each other.

There is no cookie-based session, no `sessionStorage` usage, no refresh token, no client-side expiry handling, and no secure or native storage of any kind. Capacitor 8 is installed for the mobile shells, but no storage plugin is present, so inside the Android and iOS apps the session currently lives in WebView `localStorage`.

This audit documents every storage point and flow as required by ISSUE-226. No code was changed. The audit is based on branch `issue-226-authentication-storage-audit`, created from updated `main` at `42c40bc` on 2026-07-02.

## Scope

In scope, per the issue: access token storage, user ID storage, login persistence, and the logout flow. Out of scope: code changes and secure storage design (deferred to ISSUE-227 through ISSUE-232).

## Files Reviewed

| File | Role in authentication storage |
| --- | --- |
| `frontend/src/api/auth.js` | Session save (`saveAuthSession`), stored-user-ID resolution, JWT payload decoding, login/logout API calls |
| `frontend/src/api/client.js` | Axios instance: request interceptor (attaches token), response interceptor (401 cleanup) |
| `frontend/src/App.jsx` | Startup session restoration (`getStoredUser`), logout handler, session-change event listeners |
| `frontend/src/components/LoginPage.jsx` | Login flows (Google and password) ending in `saveAuthSession` |
| `frontend/src/components/AdminRoute.jsx` | Admin gate: token presence check, server verification, its own storage cleanup |
| `frontend/src/components/NotificationsModal.jsx` | FCM push token persistence (auth-adjacent) |
| `frontend/package.json`, `frontend/capacitor.config.ts` | Capacitor platform and plugin inventory |

A full-project search for `localStorage`, `sessionStorage`, `document.cookie`, `refresh_token`, `expires_in`, `@capacitor/preferences`, and secure-storage plugins was used to confirm the inventory below is complete.

## Storage Inventory

### Authentication keys (localStorage)

| Key | Content | Written by | Read by | Removed by |
| --- | --- | --- | --- | --- |
| `access_token` | JWT access token | `saveAuthSession` (`auth.js:95`) | `client.js:16`, `App.jsx:18`, `auth.js:29`, `AdminRoute.jsx:8` | All three cleanup paths |
| `currentUserId` | User ID | `saveAuthSession` (`auth.js:96`) | `getStoredSessionUserId` fallback (`auth.js:36`) | All three cleanup paths |
| `currentUserName` | Display name | `saveAuthSession` (`auth.js:97`) | `App.jsx:27` | All three cleanup paths |
| `currentUserEmail` | Email address | `saveAuthSession` (`auth.js:98`) | `App.jsx:28` | All three cleanup paths |
| `currentUsername` | Username (optional) | `saveAuthSession` (`auth.js:101`) | `App.jsx:29` | `App.jsx` logout and 401 interceptor only — **not** `AdminRoute.clearAuthStorage` |

### Legacy fallback keys (read-only, never written, never cleaned)

| Key | Read by |
| --- | --- |
| `authToken` | `client.js:17` |
| `token` | `client.js:18` |
| `current_user_id` | `auth.js:37` |
| `user_id` | `auth.js:38` |

No code path writes or removes these keys. If any of them is present from an older application version, the request interceptor will silently use it as a bearer token, and no logout path clears it.

### Auth-adjacent keys (localStorage)

| Key | Content | Notes |
| --- | --- | --- |
| `push_notification_token` | FCM device token | Written/removed only inside `NotificationsModal.jsx`; **survives logout** |

### Non-authentication localStorage keys (for completeness)

Language selection keys (`i18n/index.js`), `onboarding_done` and `userCity` (`OnboardingPage.jsx`), and cached map fields with timestamp (`MapPage.jsx`). These are not part of the session but share the same storage medium.

### Mechanisms not in use

- `sessionStorage`: no usage anywhere in `frontend/src`.
- Cookies: `document.cookie` is never referenced; there is no httpOnly session cookie.
- In-memory-only tokens: none. React state `currentUser` in `App.jsx` mirrors localStorage; it is initialized from it and refreshed via `storage` and `auth-session-changed` window events.
- Refresh tokens / expiry metadata: no `refresh_token`, `expires_in`, or `token_type` handling exists in the frontend.
- Capacitor native or secure storage: `@capacitor/core`, `@capacitor/android`, `@capacitor/ios`, and `@capacitor/push-notifications` are installed, but no `@capacitor/preferences` or secure-storage plugin. In the native shells the session is WebView localStorage.

## Flows

### Login persistence

Both login methods (Google via `POST /auth/google`, password via `POST /auth/login`) resolve to `saveAuthSession(authData)` in `auth.js:92-109`, which:

1. Derives the user ID from the JWT `sub` claim (`getJwtSubject`, decoded client-side with `atob`; falls back to `authData.user.id`).
2. Writes `access_token` and the three or four profile keys to localStorage.
3. Dispatches the `auth-session-changed` window event so `App.jsx` refreshes its state.

### Request authentication

`client.js:10-25` attaches `Authorization: Bearer <token>` to every request, resolving the token as `access_token` → `authToken` → `token` in that order.

### Session restoration (startup)

`App.jsx:17-31` (`getStoredUser`) runs synchronously at mount: if `access_token` and a resolvable user ID exist, the user is treated as logged in. Restoration is purely optimistic — the token is not validated against the server and its expiry is not checked; an expired token is only discovered when the first API call returns 401. The exception is `/admin`, where `AdminRoute` verifies the token via `GET` admin-me before rendering.

### Logout and cleanup paths

There are three independent cleanup implementations:

1. **User logout** (`App.jsx:78-86`): fire-and-forget `POST /auth/logout` (`logoutFromServer` swallows all errors), then removes the five auth keys and nulls React state.
2. **Global 401 handling** (`client.js:27-45`): on any 401 response while `access_token` exists, removes the five auth keys and dispatches `auth-session-changed`.
3. **Admin 401 handling** (`AdminRoute.jsx:11-16`): removes only four keys — `currentUsername` is missed.

None of the three paths removes `push_notification_token` or the legacy fallback keys, and logout does not unregister the FCM device token from the backend.

## Risks

### Security

1. **Token theft via XSS.** A JWT in localStorage is readable by any script executing in the page; a single XSS vulnerability yields full session takeover. This is the primary motivation for native secure storage.
2. **No expiry or refresh model.** The client never inspects `exp` and holds no refresh token. Sessions end abruptly on the first 401, and a leaked token remains usable until server-side TTL/revocation.
3. **Plaintext PII at rest.** Name, email, and username persist unencrypted in localStorage.
4. **Legacy keys can silently authenticate.** `authToken`/`token` are honored by the interceptor but never written or cleared by current code — a stale value from an old version would keep authenticating requests after logout.
5. **Inconsistent cleanup.** `AdminRoute.clearAuthStorage` leaves `currentUsername` behind; three duplicated key lists must be kept in sync by hand.
6. **Best-effort server logout.** Local wipe proceeds even if server-side revocation fails. Acceptable UX trade-off, but it means logout does not guarantee token invalidation.

### Mobile-specific

1. **WebView storage is evictable and not hardware-backed.** In the Capacitor Android shell, the OS can clear WebView storage under pressure, silently logging users out; the data is also unprotected compared to Keystore-backed storage.
2. **Push token survives logout.** A shared device could continue receiving pushes addressed to the previous account until the token is rotated or the modal's disable path runs.
3. **No storage abstraction.** Five files access `localStorage` directly with duplicated key lists, so a native-storage migration must modify every one of them consistently.

## Gaps Against Secure-Storage Requirements

| Gap | Addressed by |
| --- | --- |
| No secure/native storage medium | ISSUE-227 (architecture), ISSUE-228 (technology selection) |
| Token persisted in web-readable storage | ISSUE-229 (secure token storage) |
| Optimistic restoration without validation/expiry handling | ISSUE-230 (secure session restoration) |
| Inconsistent, incomplete logout cleanup (three paths; push token and legacy keys never cleared) | ISSUE-231 (secure logout cleanup) |
| No behavior defined for storage read/write failure or eviction | ISSUE-232 (failure handling) |
| No documented session lifecycle | ISSUE-234 (session lifecycle documentation) |

## Conclusion

All authentication storage points are documented above; the acceptance criterion of ISSUE-226 is met. The current implementation is a coherent, purely localStorage-based session with three duplicated cleanup paths and no abstraction layer. Before native secure storage is introduced (ISSUE-227+), the audit highlights four pre-existing inconsistencies that the follow-up issues should resolve by design rather than carry over: the legacy fallback token keys, the `AdminRoute` cleanup omission, the logout-surviving push token, and the absence of any expiry handling.
