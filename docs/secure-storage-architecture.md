# Secure Storage Architecture (ISSUE-227)

## 1. Purpose

Define the agreed architecture for how the application stores, restores, and clears authentication state before any native secure storage is implemented. This document records the storage decisions required by ISSUE-227 and is the design baseline for ISSUE-228 through ISSUE-234.

It explicitly answers the four questions posed by the issue: what is stored, for how long, what is deleted on logout, and what survives an application restart.

## 2. Scope

- Access token storage on web and in the Android (Capacitor) app.
- User metadata (ID and cached profile fields) storage.
- Future refresh tokens (placement and rules only — not implemented now).
- Logout cleanup semantics, session restoration semantics, legacy key migration, and failure behavior, at the architecture level.

## 3. Non-goals

- No code changes in this issue.
- No technology or plugin selection — that is ISSUE-228.
- No secure storage implementation — ISSUE-229 and later.
- No auth behavior changes and no backend changes.
- No refresh-token implementation.
- No iOS-specific execution, configuration, or validation. This architecture is Android/app/web/backend-safe and must not require iPhone/iOS validation (see section 16).

## 4. Inputs from ISSUE-226 Audit

From `docs/authentication-storage-audit.md` (merged in PR #779), the findings this architecture must resolve by design:

1. The JWT access token and PII profile fields live in plain `localStorage`, including inside the native WebView.
2. Four legacy fallback keys (`authToken`, `token`, `current_user_id`, `user_id`) are read and honored but never written or cleared.
3. Three independent, inconsistent logout cleanup paths exist (`App.jsx`, the 401 interceptor, `AdminRoute`), one of which misses `currentUsername`.
4. The FCM push token survives logout and is never unregistered server-side.
5. Session restoration is purely optimistic: no expiry check, no server validation.
6. There is no refresh-token model and no storage abstraction — five files access `localStorage` directly with duplicated key lists.

## 5. Data Classification Inventory

| Item | Example | Sensitivity | Required storage tier |
| --- | --- | --- | --- |
| Access token (JWT) | `access_token` | Secret — grants full session | Secure tier (native); web fallback tier on browser |
| Refresh token (future) | — | High secret — long-lived credential | Secure tier only, never web storage |
| User ID | JWT `sub` / `currentUserId` | Low — identifier, derivable from token | Persistent tier, only if required for startup UX |
| Profile fields (name, email, username) | `currentUserName` etc. | PII — display cache only, never a security source of truth | Persistent tier as display cache, or not persisted at all |
| Push notification token (FCM) | `push_notification_token` | Medium — device-addressable identifier | Persistent tier; must be cleared and unregistered at logout |
| Legacy fallback keys | `authToken`, `token`, `current_user_id`, `user_id` | Deprecated | None — one-time cleanup, then removed from code |

Storage tiers:

- **Secure tier** — hardware/OS-backed secure storage on the native app (Android Keystore-backed; concrete mechanism selected in ISSUE-228).
- **Persistent tier** — regular durable app storage for non-secret state.
- **Web fallback tier** — browser `localStorage`, permitted only as a temporary compatibility fallback for the web build until a better web strategy is defined.

## 6. Storage Decision Table

| Data | Where (native Android app) | Where (web browser) | Retention | Cleared on logout | Survives restart |
| --- | --- | --- | --- | --- | --- |
| Access token | Secure tier | Web fallback tier (temporary) | Until logout, 401, or expiry; server-side TTL is the source of truth | Yes | Yes (subject to restoration validation) |
| Refresh token (future) | Secure tier only | Not stored | Rotation policy stricter than access token (defined when introduced) | Yes | Yes (subject to validation) |
| User ID | Persistent tier (startup UX only) | Web fallback tier | Same as access token | Yes | Yes |
| Profile fields | Persistent tier, display cache only | Web fallback tier | Refreshed from server after each validated restore | Yes | Yes, as stale display cache pending refresh |
| Push token local reference | Persistent tier | Web fallback tier | Until logout or push disabled | Yes (plus server-side unregister attempt) | Yes while logged in |
| Legacy keys | Removed | Removed | One-time migration cleanup | Deleted by migration, not only logout | No |
| Non-auth app state (language, onboarding, map cache) | Persistent tier | localStorage | Unchanged by this architecture | No | Yes |

## 7. The Four Required Architecture Answers

**1. What is stored?**
The access token, the user ID (only because startup UX needs an immediate identity hint), profile fields strictly as a display cache, and the push token local reference. A refresh token is stored only if/when introduced, and then only in the secure tier on native. Nothing else auth-related is persisted.

**2. For how long?**
Until one of: explicit logout, a 401/invalid-token signal, or token expiry discovered at restoration or during use. The client never extends a session's life; the backend TTL is authoritative. Profile display cache lives only until the next validated restore refreshes it.

**3. What is deleted on logout?**
Everything session-scoped, through one canonical cleanup path: access token, user ID, all cached profile fields, all legacy fallback auth keys, session restoration state, and the push token local reference — with a best-effort server-side push token unregister and server logout. Non-auth app state (language, onboarding flag, map cache) is not deleted.

**4. What survives an app restart?**
The access token, user ID, profile display cache, and push token reference survive restart — but survival is not trust: restoration must re-validate (expiry check and/or backend validation) before the UI treats the user as logged in. Nothing survives a restart that follows logout or a failed validation.

## 8. Storage Abstraction Design

A single session-storage module owns all auth persistence. No other file may touch storage keys directly.

Interface (names indicative; final API in implementation issues):

- `getToken()` / `setToken(token)` / `clearToken()`
- `getUserMetadata()` / `setUserMetadata(metadata)`
- `clearSession()` — the one canonical cleanup path (section 12)
- `restoreSession()` — the one canonical restoration path (section 11)
- `clearLegacyKeys()` — one-time migration (section 14)

Properties:

- One canonical key list defined in this module only.
- Backed by the secure tier on native and the web fallback tier on browser; callers never know which.
- The five current call sites (`api/auth.js`, `api/client.js`, `App.jsx`, `AdminRoute.jsx`, `NotificationsModal.jsx` for the push token reference) migrate to this module in later implementation issues; direct `localStorage` access is removed from all of them.

## 9. Login Flow Architecture

1. Login (Google or password) returns auth data from the backend, unchanged.
2. The success handler calls the abstraction: `setToken(...)` then `setUserMetadata(...)`.
3. User ID continues to be derived from the JWT `sub` claim; the persisted copy is a startup hint only.
4. Profile fields are written as display cache with no security meaning.
5. The session-changed notification (currently the `auth-session-changed` event) is emitted by the abstraction, not by callers.

## 10. API Authorization Flow Architecture

1. The request interceptor obtains the bearer token via `getToken()` only — the fallback chain over `authToken`/`token` is removed.
2. On 401 with a stored session, the interceptor calls `clearSession()` (the canonical path) instead of maintaining its own key list.
3. No other behavior of the API client changes.

## 11. Session Restoration Architecture

Startup must not blindly trust stored state.

1. `restoreSession()` loads the token through the abstraction.
2. If the JWT carries an `exp` claim, expiry is checked locally; an expired token means `clearSession()` and a logged-out start.
3. When backend validation is required (policy per ISSUE-230), the token is validated against the server before the UI enters logged-in state; an invalid/revoked token means `clearSession()`.
4. The UI renders logged-in only after a clear session decision — no more optimistic render followed by surprise 401.
5. **Offline policy (explicit decision, not an assumption):** if the device is offline and the token is present and not locally expired, the app may enter logged-in state provisionally and must re-validate on the first connectivity; if that validation fails, `clearSession()` runs immediately. This provisional-offline behavior is a policy decision that ISSUE-230 implements and may tighten, but must not silently loosen.
6. Admin routes keep their stricter behavior: server verification before rendering.

## 12. Logout Cleanup Architecture

One canonical path, `clearSession()`, replaces the three current implementations:

1. Best-effort server calls first: `POST /auth/logout` and push token unregister. Failures do not abort local cleanup, but they are logged/handled — not silently swallowed.
2. Local cleanup always runs: token, user ID, profile cache, legacy keys, restoration state, push token local reference.
3. The session-changed notification is emitted once, by the abstraction.
4. `App.jsx` logout, the 401 interceptor, and `AdminRoute` all call this one path. No duplicated key lists remain anywhere.

## 13. Push Token Handling

- The local push token reference is part of session state: cleared by `clearSession()`.
- Logout attempts server-side unregistration of the device token so a shared device stops receiving the previous account's notifications; failure is logged and does not block logout.
- Push token acquisition after login is unchanged by this architecture.

## 14. Legacy Key Migration

- `authToken`, `token`, `current_user_id`, and `user_id` are deprecated: never written, and after migration never read.
- A one-time `clearLegacyKeys()` cleanup removes them from storage at first run of the new abstraction.
- All read-fallback chains over these keys are deleted from code in the implementation issues.
- After migration, exactly one canonical key list exists, owned by the abstraction module.

## 15. Failure Handling Policy

Fail closed:

- If secure storage is unavailable, corrupted, or returns partial/inconsistent session data, the app clears the unsafe session state and returns the user to login.
- A clear, user-facing error is shown only when user action is needed; otherwise the app degrades to logged-out silently.
- The native Android app must not silently fall back to insecure (WebView localStorage) storage when the secure tier fails — any such fallback would require an explicit, documented decision. Detailed failure taxonomy and handling is ISSUE-232/ISSUE-233.

## 16. Web vs Android/Native Storage Policy

- **Android (Capacitor app):** the access token (and any future refresh token) moves to the secure tier once ISSUE-229 lands. Non-secret metadata may use the persistent tier.
- **Web (browser):** `localStorage` remains only as a temporary compatibility fallback behind the abstraction, until a better web strategy (e.g., cookie-based or in-memory + re-auth) is defined as separate future work. Moving behind the abstraction now is what makes that future swap possible without touching call sites.
- **iOS:** explicitly out of scope for execution and validation in this phase. The abstraction is platform-agnostic by design, so no decision here creates iOS-specific work or requires iOS validation.

## 17. Future Refresh-Token Policy

- Refresh tokens are future-facing only; nothing is implemented now.
- If introduced: stored only in the secure tier on the native app; never in web `localStorage`; stricter cleanup and rotation rules than access tokens (rotated on use, revoked server-side at logout, never cached outside the abstraction).
- Introducing refresh tokens requires backend work and a new issue; this document only reserves their architectural placement.

## 18. Security Risks Reduced by This Architecture

| Audit risk | How the architecture reduces it |
| --- | --- |
| Token theft via XSS from localStorage (native app) | Token moves to hardware-backed secure tier on Android |
| Legacy keys silently authenticating requests | Fallback chains removed; one-time cleanup; single key list |
| Inconsistent logout across three paths | One canonical `clearSession()` used everywhere |
| Push token surviving logout (cross-user notification leak) | Push token in session cleanup + server-side unregister attempt |
| Optimistic restoration of dead sessions | Expiry check + validation before logged-in UI |
| PII treated as identity source | Profile fields demoted to display cache; identity from token/server |
| Scattered storage access blocking migration | All access behind one abstraction module |

## 19. Remaining Risks

- Web build still uses `localStorage` (fallback tier) until a dedicated web strategy exists — XSS exposure on web is reduced in blast radius but not eliminated.
- No refresh-token model yet: sessions still end at access-token expiry, and a leaked token remains valid until server TTL/revocation.
- Best-effort server logout means server-side token revocation is not guaranteed at logout.
- Provisional offline restore (section 11) accepts a locally-unexpired token without server validation until connectivity returns.

## 20. Mapping to Implementation Issues

| Decision in this document | Implementing issue |
| --- | --- |
| Storage technology/plugin selection for the secure tier | #317 / ISSUE-228 — technology selection |
| Token storage behind the abstraction (secure tier on Android) | #318 / ISSUE-229 — secure token storage implementation |
| Restoration with expiry check, validation, offline policy | #319 / ISSUE-230 — session restoration |
| Canonical `clearSession()` incl. push token + legacy keys | #320 / ISSUE-231 — logout cleanup |
| Fail-closed behavior for unavailable/corrupted storage | #321 / ISSUE-232 — secure storage failure handling |
| Documented failure strategy | #322 / ISSUE-233 — failure strategy documentation |
| Documented end-to-end session lifecycle | #323 / ISSUE-234 — session lifecycle documentation |

## 21. Approval Checklist

Acceptance for ISSUE-227 requires explicit approval of these decisions:

- [ ] Data classification and storage tiers (sections 5–6)
- [ ] The four answers: stored / retention / logout deletions / restart survival (section 7)
- [ ] Single storage abstraction owning all auth persistence (section 8)
- [ ] Identity restored from token/server; profile fields are display cache only (sections 9, 11)
- [ ] One canonical logout path clearing token, ID, profile cache, legacy keys, restoration state, and push token, with best-effort server logout/unregister (section 12)
- [ ] Legacy key deprecation and one-time cleanup (section 14)
- [ ] Fail-closed policy; no silent insecure fallback on native (section 15)
- [ ] Web localStorage as temporary fallback only (section 16)
- [ ] Refresh tokens future-only, secure tier only, stricter rules (section 17)

Approval is recorded by merging the PR for this document.
