# Session Lifecycle (ISSUE-234)

## 1. Overview

This document describes the **final implemented session lifecycle** of the application after ISSUE-229 (secure token storage, PR #782), ISSUE-230 (secure session restoration, PR #783), ISSUE-231 (secure logout cleanup, PR #784), ISSUE-232 (failure handling strategy, PR #785), and ISSUE-233 (failure handling implementation, PR #786). It is documentation only; the code of record is `frontend/src/api/sessionStorage.js` (sole owner of auth storage), `frontend/src/api/auth.js`, `frontend/src/api/client.js`, and `frontend/src/App.jsx`.

**What a session is:** a JWT access token issued by the backend (`/auth/login`, `/auth/register`, `/auth/google`) plus the cached user identity derived from it. The server is the source of truth: token TTL and revocation (`tokens_valid_after`) are enforced server-side; the client only holds, restores, and destroys its copy.

**Storage layers:**

| Layer | Contents | Role |
| --- | --- | --- |
| Android secure storage (`@aparajita/capacitor-secure-storage` v8; AES-GCM values in `WSSecureStorageSharedPreferences`, Keystore-backed) | The JWT (`capacitor-storage_access_token`) | Only durable token store on native |
| In-memory (`cachedToken` module state + React `currentUser` state) | Token + user context for the current run | What the UI actually renders from |
| `localStorage` | User metadata display cache (`currentUserId/Name/Email/Username`); the JWT **only on the web build** (temporary web fallback tier, architecture doc §16); legacy keys are cleanup-only | Never a token store on native |
| `sessionStorage` | Nothing is written; auth keys are defensively deleted at cleanup | Cleanup-only |

**Security principle:** *uncertain auth state = logged out.* Every ambiguous outcome (storage failure, timeout, corrupt data, race) resolves to the unauthenticated state. A wrongly logged-out user can log in again; a wrongly kept session is a security defect.

## 2. Login lifecycle

1. User submits credentials (password login, registration, or Google) → backend returns `{ access_token, user }`.
2. `saveAuthSession` runs: `setToken(access_token)` then `setUserMetadata(user)`, then dispatches `auth-session-changed`.
3. **Native token write (ISSUE-233):** `setToken` caches the token in memory first, then writes to secure storage:
   - **Write succeeds** → `auth-persistence-changed {persisted: true}` is emitted (clears any stale warning). Session survives restarts.
   - **Write fails once, retry succeeds** → `secure_storage.write_retry_success` event; identical outcome to success; no user-visible warning.
   - **Write fails permanently (both attempts)** → `secure_storage.write_failure` event; **no localStorage JWT fallback, ever**; the session remains **in-memory only** (login itself succeeded server-side, so the user stays signed in for this run); a non-blocking amber **persistence warning** banner (`auth.persistenceWarning`) tells the user they may need to log in again after restarting the app.
   - **Retry safety:** the retry is skipped if the token was superseded while the first attempt was in flight (logout cleared it, or a newer login replaced it). A first attempt that lands *after* logout is compensated with a delete so secure storage never holds a token post-logout.
4. On the web build, the token goes to the `localStorage` web fallback tier instead (platform decision, not a failure fallback).
5. User context initialization: metadata cache is written, the user id comes from the JWT `sub` claim.
6. UI transition: `onLogin` sets `currentUser` → authenticated UI (map page + auth toolbar) renders. Logout/persistence warnings from previous sessions are cleared on successful login.

## 3. Restore lifecycle

1. **App startup enters the session-checking state** (`auth-checking` screen). The UI renders nothing else until the check settles — the login page is never flashed before validation completes (**no login flicker rule**, regression-tested).
2. `initSessionStorage()` runs exactly once (memoized promise; React StrictMode double-mount cannot duplicate it). On native:
   - **Plugin availability check first:** `Capacitor.isPluginAvailable('SecureStorage')` is verified *before any plugin call*. If the native registration is missing, calling the plugin proxy would enter an infinite microtask loop that starves timers and wedges the WebView beyond any timeout — the guard throws instead, emitting `secure_storage.unavailable` and failing closed.
   - **Read with timeout:** plugin load, the token read, and post-failure cleanup are each bounded by a **5-second deadline** (`SECURE_STORAGE_INIT_TIMEOUT_MS`). The app can never sit on the checking screen indefinitely (**no infinite checking screen rule**). A read that settles *after* the deadline is discarded — a late token cannot race the app into an authenticated state.
   - **Legacy migration:** if a plaintext token is found in `localStorage` (pre-ISSUE-229 install), it is migrated into secure storage; the plaintext copy is deleted **regardless** of migration success.
3. **Token found** → `validateStoredSession()` calls the authenticated endpoint `GET /games/me`:
   - **Success** → `currentUser` is restored from the cached metadata; authenticated UI renders.
   - **401/failure** → `clearSession()`, logged out (see section 5).
4. **Missing token** → unauthenticated; login page renders. Orphaned metadata is cleared.
5. **Read failure / timeout / unavailable / corrupt token** → fail closed: metadata cleared, best-effort delete of the bad entry, login page. Events: `secure_storage.read_failure` / `read_timeout` / `unavailable`.
6. **Background resume revalidation:** on `visibilitychange` → visible and on Capacitor `appStateChange` → active, the session is revalidated against `/games/me` — but **only if a token exists in memory**. After logout there is no token, so resume never fires an authenticated request.
7. **Request deduplication:** one validation promise is shared (`validationPromiseRef`); overlapping triggers (startup + resume + visibility) reuse the in-flight request — no request storm. Deduplication cannot preserve stale state: the promise is dropped on logout and every result is gated by the session epoch (section 4).
8. **Device restart** behaves exactly like a cold start: valid token → validated restore; no token → logged out. Both were validated on the physical device.
9. On the web build, restoration is optimistic (stored user rendered without a startup `/games/me` validation); the 401 interceptor still fails it closed on first authenticated request.

## 4. Logout lifecycle

Triggered by the toolbar Logout button (also by `AdminRoute` on unauthorized). Ordered behavior (`handleLogout` + `clearSession`):

1. **Session epoch is bumped and the deduplicated validation promise is dropped** — any in-flight or late validation result is now inert.
2. **Authenticated revocation request:** `POST /auth/logout` is sent with the **Authorization header pinned from the token captured at call time**, so the request reaches the server authenticated even though local cleanup clears the in-memory token synchronously (the server sets `tokens_valid_after`, revoking all existing JWTs). The request is fire-and-forget: offline logout still fully cleans local state.
3. **UI transitions to logged out immediately** (`currentUser = null`); warnings from prior operations are cleared.
4. **Cleanup, in order, none aborting the others:** user metadata cache → legacy localStorage keys → sessionStorage auth keys → in-memory token (`cachedToken = null`, synchronous) → localStorage token key → native secure-storage delete.
5. **Secure delete failure (ISSUE-231/233):** the delete is retried once (`secure_storage.delete_failure` / `delete_retry_success` events). If it still fails: all other cleanup has already completed, listeners are still notified (`try/finally`), the error propagates, and the red **logout warning banner** (`auth.logoutCleanupError`) tells the user cleanup did not fully succeed. **The UI remains logged out no matter what** — a delete failure can never restore authenticated UI.
6. **Logout wins over in-flight validation:** a `/games/me` request that was in flight when logout happened may still succeed later; the epoch guard plus a post-await token check discard the result. **A late `/games/me` success cannot restore the user.** Validated both in Playwright and live on the device (request held in flight, logout tapped, late 200 released — user stayed logged out).

## 5. Expiration / invalid session lifecycle

The client never inspects JWT expiry locally; expiration and revocation surface as backend rejections.

1. **Expired or revoked token / backend 401:** the axios response interceptor catches any 401 while a token is held and runs `clearSession()` — same cleanup as logout steps 4–5, without the banner (the user did not initiate it; the login page itself is the message). 403 on admin routes routes through `AdminRoute.onUnauthorized` → full logout flow.
2. **Validation failure at startup/resume:** `/games/me` failing → `clearSession()` → logged out.
3. **Corrupt token:** unreadable/undecryptable stored value → fail closed at read time, corrupt entry deleted (regression-tested: "corrupted token fails closed and clears auth state").
4. Cleanup covers secure storage, localStorage auth keys, sessionStorage auth keys, and in-memory state; UI becomes logged out.
5. **Relaunch after any of the above remains logged out** — no stale-token restoration, and no request ever carries the dead token again (validated on device: zero auth API calls after logout/invalidations).

## 6. Failure handling (summary of ISSUE-233; full strategy in `docs/secure-storage-failure-handling-strategy.md`)

| Failure | Behavior | Event |
| --- | --- | --- |
| Storage unavailable (plugin missing/bridge dead) | Fail closed at startup; availability checked before any proxy call (prevents the microtask-loop wedge) | `secure_storage.unavailable` |
| Read failure | Fail closed, metadata cleared, bad entry deleted best-effort | `secure_storage.read_failure` |
| Read timeout (5s deadline) | Same as read failure; late settle discarded | `secure_storage.read_timeout` |
| Write failure | One retry → in-memory-only session + persistence warning; never a web-storage fallback | `secure_storage.write_failure` / `write_retry_success` |
| Delete failure | One retry → propagate; UI already logged out; logout banner when user-initiated | `secure_storage.delete_failure` / `delete_retry_success` |
| Migration failure | Plaintext deleted regardless; start logged out | `secure_storage.migration_failure` |

**Logging rules:** all failure logging goes through one helper emitting `event=secure_storage.*` plus the error object. **No token values** — plain or encrypted, no prefixes, no decoded claims — appear in logs, thrown errors, UI, or test output.

**User-facing warning rules:** a banner appears only when the user initiated the partially-failed action (logout → red banner) or when their expectation will silently break later (login persistence → amber banner). Startup failures resolve silently to the login screen.

## 7. State machine

States:

- `checking_session` — startup; nothing but the checking screen renders.
- `unauthenticated` — login page.
- `authenticating` — credentials submitted, awaiting backend.
- `authenticated` — token in secure storage + user context in memory.
- `in_memory_only_authenticated` — login succeeded but persistence failed; persistence warning shown; identical to `authenticated` except it cannot survive a restart.
- `logging_out` — cleanup in progress; UI already shows logged out.
- `cleanup_warning` — logged out with the logout warning banner (secure delete failed).
- `expired_or_invalid` — transient: 401/validation failure triggering cleanup; resolves to `unauthenticated`.

Allowed transitions:

```
checking_session  → authenticated | unauthenticated            (validated restore / fail closed)
unauthenticated   → authenticating → authenticated
                                    | in_memory_only_authenticated
                                    | unauthenticated           (login rejected)
authenticated     → logging_out → unauthenticated | cleanup_warning
authenticated     → expired_or_invalid → unauthenticated
in_memory_only_authenticated → logging_out | expired_or_invalid   (same as authenticated)
cleanup_warning   → authenticating                               (user logs in again; warning cleared)
```

Forbidden transitions (each guarded in code and regression-tested):

- `checking_session → authenticated` **without** a successful `/games/me` validation on native.
- `checking_session` persisting beyond the startup deadline (no permanent checking state).
- `logging_out / unauthenticated → authenticated` via **any late async result** (stale validation, late secure-storage read, deduplicated promise) — the session epoch makes these inert. Only a new user-initiated login authenticates.
- `cleanup_warning → authenticated` without a fresh login.
- Any transition that writes a JWT to web storage as a recovery path.

## 8. Security invariants

1. The JWT is **never stored in localStorage as a fallback** on native (the web build's temporary tier is a platform decision, not a failure response).
2. The JWT is **never stored in sessionStorage**, on any platform.
3. **Token values are never logged** — not in console events, thrown errors, UI text, or test output.
4. **Authenticated UI is never shown while session state is uncertain** (checking state gates rendering; failures resolve to logged out).
5. **Logout wins over all late async work** — in-flight validation, late `/games/me` success, resume revalidation, pending writes (compensated), deduplicated promises.
6. **Storage cleanup failure never restores authenticated UI** — it surfaces a warning at most.
7. **Fail closed is always preferred over silent insecure persistence.**

## 9. Validation history

| Issue | What was validated | Where |
| --- | --- | --- |
| ISSUE-229 (PR #782) | Secure token storage + legacy migration | Implementation PR; behavior re-validated on device during later issues |
| ISSUE-230 (PR #783) | Session restoration, no-flicker startup, resume dedup, corrupt-token fail-closed | `tests/session-restoration.spec.js` (6 tests) |
| ISSUE-231 (PR #784) | Full logout cleanup, revocation with pinned token, logout-vs-validation race, relaunch/resume/device-restart logged-out guarantees | `tests/logout-cleanup.spec.js` (9 tests) + **Samsung SM-S928B, Android 16 physical validation (GO)** including `run-as` inspection of secure storage, held-in-flight race test, and full device reboot |
| ISSUE-233 (PR #786) | All failure modes (unavailable/read/hang/write/migration/delete), startup deadline, persistence warning, plugin-availability guard | `tests/secure-storage-failures.spec.js` (7 tests; 22/22 across all suites) + **Samsung SM-S928B, Android 16 regression (GO)**: login, restart restore, logout cleanup, force-stop relaunch, background/resume, 0 JWT-like values in logcat |

Failure *simulations* are automated-test-only: the app ships no runtime failure-injection hooks by design; Playwright injects failures through a Capacitor bridge mock. On-device secure-storage evidence is collected externally (`run-as` on `WSSecureStorageSharedPreferences.xml`), never by adding token logging to app code. Nothing beyond the rows above is claimed as validated.

## 10. Operational troubleshooting

| Symptom | Likely cause | Where to look |
| --- | --- | --- |
| Stuck on "Checking your session..." | Should be impossible past ~5s per storage read (G1 deadline). If it persists: network hang on `/games/me` startup validation (no HTTP timeout), or a regression around the deadline guard | WebView console for `secure_storage.read_timeout`; network log for a pending `/games/me` |
| Login works but user is logged out after restart | Persistence failed at login — the amber warning should have been shown (`secure_storage.write_failure`); or Keystore invalidated the key (device credential change) → read fails closed at next start | Logcat for `write_failure` at login time / `read_failure` at startup |
| Logout warning banner appears | Secure delete failed twice at logout; local state is cleaned and UI is logged out, but ciphertext may remain on disk until next successful cleanup | `secure_storage.delete_failure` events; `run-as` on the prefs file |
| User restored after force-stop when they should not be | Expected only if a valid token legitimately survived. If it happens after logout: security regression in delete/epoch handling — treat as NO-GO | `logout-cleanup.spec.js` relaunch test; prefs file on device |
| 401 on `/games/me` | Token expired or revoked (`tokens_valid_after`); interceptor logs the user out silently — this is correct behavior, not a bug | Backend auth logs (`event=auth.*`) |
| No resume revalidation | Correct when logged out (guard requires an in-memory token). If logged in: check the `appStateChange`/`visibilitychange` listeners registration | `App.jsx` resume effects |
| Secure storage plugin unavailable | JS present but native registration missing (bad build / skipped native update). The availability guard fails closed; without it the WebView would wedge in a microtask loop | `secure_storage.unavailable` at startup; verify plugin in `capacitor.settings.gradle` |
| Token found in localStorage on native | **Security regression / NO-GO.** Only the one-time legacy migration may ever see a plaintext token, and it deletes it in the same run | JWT-pattern scan; `secure-storage-failures.spec.js` leakage checks |

## 11. Future issue handoff — ISSUE-235 certification review checklist

ISSUE-235 should certify the lifecycle end-to-end. Suggested acceptance criteria:

1. **Document accuracy review:** every statement in sections 2–8 of this document matches the code on main (files listed in section 1). Any drift is a finding.
2. **Invariant audit:** each security invariant in section 8 is traced to (a) the enforcing code path and (b) at least one regression test. Missing coverage is a finding.
3. **Full regression run:** `npx playwright test session-restoration logout-cleanup secure-storage-failures` → 22/22 green on main; `npm run lint`, `npm run build`, `npm run build:android`, Android `assembleDebug` all pass.
4. **Device certification:** one Samsung physical pass covering: fresh install → login → restart restore → logout → relaunch/resume logged out → JWT-pattern scan empty → logcat token scan empty → secure prefs empty after logout.
5. **Leakage sweep:** repo-wide check that no code path writes a JWT to `localStorage`/`sessionStorage` on native and no log statement prints token material.
6. **GO/NO-GO:** GO only if all of the above pass with zero unproven claims; NO-GO if any invariant lacks an enforcing code path + test, if any device check fails, or if any token material is found outside secure storage.

Out of scope for ISSUE-235 unless separately approved: refresh tokens, FCM token logout cleanup (known audit finding from ISSUE-226), web-build secure storage strategy, and any iOS execution.
