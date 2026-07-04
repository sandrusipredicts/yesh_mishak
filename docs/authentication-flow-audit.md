# Authentication Flow Audit for Mobile Adaptation (ISSUE-236)

## Scope / Out of Scope

**In scope:** a code-grounded map of every current authentication flow (web + Capacitor Android WebView), the files and endpoints involved, token/session behavior, storage, restoration, error behavior, and per-flow mobile adaptation notes. All statements below were verified against the codebase at the time of writing (main after PR #788).

**Out of scope — explicitly:** implementing Native Authentication (Native Login implementation is **out of scope** for this issue), any frontend/backend/native code change, push notifications, and auth refactors. This document is a reference to be read **before** starting the Native Authentication phase.

## Executive summary

The app has three entry flows (Google login, manual login, registration) that all converge on a single contract: the backend returns `TokenResponse { access_token, token_type: "bearer", user }`, and the frontend persists it through one path (`saveAuthSession` → `sessionStorage.js`). Session storage, restoration, logout, and failure handling were hardened and certified in ISSUE-229–235 (see `docs/session-lifecycle.md` and `docs/secure-storage-certification-review.md`). The single flow that does **not** work in the Android WebView today is Google login — the Google Identity Services (GIS) web script fails to load/render in the WebView (observed live on the Samsung device during ISSUE-231/233 validation as the login-page error "לא ניתן לטעון התחברות Google"). That is the core problem Native Authentication must solve; manual login/registration already work natively end-to-end and are device-certified.

## Current authentication architecture overview

- **Token model:** stateless JWT (HS256), payload `{ sub: user_id, email, iat, exp }`, default TTL 10080 minutes (7 days) via `JWT_EXPIRE_MINUTES` (`backend/app/core/config.py:18`). Created only by `create_access_token` (`backend/app/auth/jwt.py`). No refresh tokens.
- **Revocation:** logout sets `users.tokens_valid_after = now()`; every authenticated request compares the JWT `iat` against it (`_check_token_revoked`, `backend/app/auth/dependencies.py:53`). An in-process user cache (TTL `auth_user_cache_ttl_seconds`) fronts the DB lookup; logout invalidates the cache entry.
- **Request auth:** `HTTPBearer` → `decode_access_token` → user lookup → status check (`require_active_user` rejects banned/suspended with 403 `ACCOUNT_RESTRICTED`).
- **Frontend auth spine:** `frontend/src/api/auth.js` (flow calls + `saveAuthSession`), `frontend/src/api/sessionStorage.js` (sole storage owner: Android secure storage on native, localStorage tier on web), `frontend/src/api/client.js` (axios: request interceptor attaches `Authorization: Bearer`, response interceptor clears the session on 401), `frontend/src/App.jsx` (session state machine, restoration, logout).
- **Abuse controls:** per-IP rate limits on all three auth endpoints; per-IP+username progressive delay on failed password logins (`app/brute_force.py`).

---

## Flow 1: Google Login

- **User entry point:** the rendered GIS button at the bottom of the login page (`.google-login-button`).
- **Frontend files:** `LoginPage.jsx` — dynamically injects `https://accounts.google.com/gsi/client` (`loadGoogleScript`, lines 11–43), initializes `google.accounts.id` with `VITE_GOOGLE_CLIENT_ID`, renders the button, receives the credential in a callback; `api/auth.js` `loginWithGoogle`.
- **API endpoint:** `POST /auth/google` with `{ token: <Google ID token (JWT "credential")> }`. Rate-limited 10/min, 50/hr per IP.
- **Backend files/functions:** `app/api/auth.py::google_login` → `app/auth/google.py::verify_google_token` (verifies via `google.oauth2.id_token.verify_oauth2_token` against the **single configured `google_client_id` audience**; requires `email_verified is True`) → `find_or_create_google_user` (**matches by `email`**, not by Google `sub`; creates the user if absent, with `username` and `phone_number` null) → `_create_token_response`.
- **Request/response shape:** request `{ token }`; response `TokenResponse { access_token, token_type, user: { id, email, name, username?, phone_number? } }`.
- **Token/session creation:** app JWT minted exactly as for password flows; `last_login` updated.
- **Storage / restoration:** identical to all flows (see lifecycle section).
- **Error/failure behavior:** frontend maps every failure stage to a translated message (client id missing, script load failure, button render failure, no credential, sign-in rejected). Backend returns 401 `AUTH_INVALID` for bad/unverified tokens.
- **Mobile adaptation notes:** **this flow is broken in the Android WebView today** — the GIS script/button does not work there (device-observed load error). Native adaptation requires a native credential source (e.g., Android Credential Manager / Google Sign-In via a Capacitor plugin) that yields a Google ID token, which can then be POSTed to the existing `/auth/google` endpoint.
- **Risks / unknowns:**
  - **Audience mismatch:** a native sign-in flow issues ID tokens whose `aud` is the Android (or a different web) OAuth client ID. `verify_google_token` accepts only the one configured `google_client_id`. The backend may need to accept a list of audiences — that is a backend change and must be planned, not assumed away.
  - **Email-based account matching:** because matching is by email, a native Google login with the same email as a password account silently logs into that account. Acceptable today, but must be a conscious decision for native.
  - Google users have null `username`/`phone_number` — any native onboarding must tolerate that.
- **Must not be assumed for Native Auth:** that the GIS web flow can be made to work in the WebView; that the existing client ID will validate native tokens; that `email_verified` is always present/true for all account types; that the plugin's token format matches `verify_oauth2_token` expectations without testing.

## Flow 2: Manual Login

- **User entry point:** the "login" tab form on the login page (`#login-tabpanel`): username-or-email + password.
- **Frontend files:** `LoginPage.jsx::handlePasswordLogin` → `api/auth.js::loginWithPassword` → `saveAuthSession`.
- **API endpoint:** `POST /auth/login` with `{ username, password }`. Rate-limited 10/min, 50/hr per IP.
- **Backend:** `app/api/auth.py::login` — looks up by `username`, then by `email` if the input contains `@`; bcrypt verification (`app/auth/passwords.py`); failed attempts feed a per-IP+username progressive delay (`app/brute_force.py`); success resets that state and updates `last_login`.
- **Request/response shape:** `{ username, password }` → `TokenResponse` (same shape as Google).
- **Error behavior:** 401 `AUTH_INVALID` "Invalid username or password" (no user-enumeration distinction); frontend surfaces the backend `detail` string or a translated fallback.
- **Storage / restoration / logout:** shared lifecycle (below).
- **Mobile adaptation notes:** works natively end-to-end today; certified on Samsung SM-S928B in ISSUE-233/235. No changes required for native. Password managers/autofill work via standard `autocomplete` attributes.
- **Risks / unknowns:** progressive delay is keyed per IP — carrier NAT on mobile could theoretically group users; no evidence of a problem, monitor only.
- **Must not be assumed:** that native auth replaces this flow — it must remain the fallback when native credentials are unavailable.

## Flow 3: Registration

- **User entry point:** the "register" tab form (`#register-tabpanel`): full name, username (min 3), email, phone number, password + confirm (8–128).
- **Frontend files:** `LoginPage.jsx::handleRegister` (client-side password-match check) → `api/auth.js::registerWithPassword` → `saveAuthSession`. Availability helpers `checkUsername`/`checkEmail` exist in `api/auth.js` (`POST /auth/check-username`, `/auth/check-email`) but are not wired into the current form.
- **API endpoint:** `POST /auth/register`. Rate-limited 5/min, 20/hr per IP. Returns **201** with `TokenResponse` — registration is an **auto-login**.
- **Backend:** `app/api/auth.py::register` — password match + `validate_password`; uniqueness pre-checks and DB-constraint fallbacks for username/email/phone (409 with specific codes `USERNAME_TAKEN`/`EMAIL_TAKEN`/`PHONE_TAKEN`); bcrypt hash; insert; token minted immediately.
- **Error behavior:** 400 `VALIDATION_ERROR` (mismatch/policy), 409 conflicts; frontend shows backend `detail` or fallback.
- **Mobile adaptation notes:** works natively today (device-certified — throwaway validation accounts were registered through this exact form on the Samsung device). Native sign-up via Google is a different path (Flow 6).
- **Risks / unknowns:** phone number is required and unique here but null for Google users — a future native flow mixing the two must handle both shapes.
- **Must not be assumed:** that registration implies a verified email (there is no email verification step today).

## Flow 4: Logout

- **User entry point:** the "Logout" button in the authenticated toolbar (`App.jsx`); also triggered by `AdminRoute` on unauthorized.
- **Frontend files:** `App.jsx::handleLogout` → `api/auth.js::logoutFromServer` + `sessionStorage.js::clearSession`.
- **API endpoint:** `POST /auth/logout` — requires an active user; the Authorization header is **pinned from the token captured at call time** so revocation reaches the server even though local cleanup clears the in-memory token synchronously (ISSUE-231). Fire-and-forget: offline logout still cleans local state fully.
- **Backend:** `app/api/auth.py::logout` — sets `tokens_valid_after = now()` (revokes all outstanding JWTs for the user) and invalidates the user cache.
- **Cleanup behavior (ordered, none aborting the others):** session epoch bump + dedup-promise drop → UI logged out immediately → metadata cache, legacy keys, sessionStorage residue, in-memory token, localStorage token key, secure-storage delete (one retry; red warning banner on final failure while UI stays logged out).
- **Race guarantees:** logout wins over in-flight validation; a late `/games/me` 200 cannot restore the user; resume revalidation cannot fire without a token.
- **Mobile adaptation notes:** fully native-certified (ISSUE-231/235, including force-stop, background/resume, and device-reboot checks). Native Auth must route its sign-out through this same `handleLogout`/`clearSession` path — **and additionally sign out of the native credential provider** (e.g., clear the Google account selection) so a fresh login doesn't silently reuse the previous account.
- **Risks / unknowns:** the FCM push token survives logout (known ISSUE-226 audit finding, still open) — flagged for the Native Auth phase.
- **Must not be assumed:** that clearing app storage clears native-provider sign-in state; those are separate scopes.

## Flow 5: Existing User Login

This is a scenario view over Flows 1–2 (the code paths are the same):

- **Password path:** `POST /auth/login` finds the user by username/email → verify → token. Entry: login tab.
- **Google path:** `POST /auth/google` verifies the ID token, then `find_or_create_google_user` **finds the existing account by email** (`backend/app/auth/google.py:206–249`) and returns it — including accounts originally created via the registration form. `last_login` updated in both paths.
- **Restoration counts here too:** an existing user with a valid stored token never re-enters a login flow — startup restores and validates the session (lifecycle section).
- **Mobile adaptation notes / must not assume:** identity linking is **email-based**; Native Auth must not assume a Google-`sub`-keyed identity exists. If native sign-in returns a different email (alias, workspace account), it will create a *new* account rather than log into the expected one.

## Flow 6: New User Registration

Also a scenario view — there are two creation paths:

- **Form path (Flow 3):** full profile (name, unique username, unique email, unique phone, password), auto-login on 201.
- **Google first-login path (Flow 1):** `find_or_create_google_user` creates a user with Google name/email and **null username, null phone_number, no password_hash**. No onboarding step currently forces completing the profile (backend logs `username_is_null`/`phone_is_null` on Google logins to track this).
- **Mobile adaptation notes:** a native Google sign-in inherits this partial-profile behavior; if product wants username/phone for all users, Native Auth needs an explicit profile-completion step — a product decision, not an implementation detail.
- **Must not be assumed:** that all users have a password (Google-created users cannot use manual login until a password exists — there is no password-set/reset flow today), or that all users have username/phone.

---

## Auth storage and session lifecycle (shared by all flows)

Authoritative detail lives in `docs/session-lifecycle.md`; summary:

- **Where auth state is stored on Web:** JWT in `localStorage` under `access_token` (temporary web fallback tier, architecture §16); user metadata display cache in `localStorage` (`currentUserId/Name/Email/Username`); nothing in `sessionStorage`. **On native Android:** JWT only in Keystore-backed secure storage; same metadata cache; never a localStorage JWT.
- **How auth state is restored on startup/reload:** `App.jsx` gates rendering on a session-checking state; `initSessionStorage()` (availability guard + 5s deadlines) loads the token; on native, `/games/me` validates before the UI authenticates; web restores optimistically and relies on the 401 interceptor. Resume revalidation is deduplicated and token-gated.
- **Failure behavior:** every storage failure fails closed to logged-out with redacted `secure_storage.*` events; login-persistence failure keeps an in-memory session with a warning banner. Certified GO in ISSUE-235 (Samsung SM-S928B, Android 16).

## Web vs Mobile adaptation notes (cross-flow)

| Concern | Web today | Native Android today | Native Auth implication |
| --- | --- | --- | --- |
| Google login | GIS script + rendered button | **Broken** (script fails in WebView) | Needs native credential flow feeding `/auth/google` |
| Manual login / registration | Works | Works, device-certified | Keep as-is (fallback path) |
| Token storage | localStorage tier | Secure storage (certified) | Reuse `saveAuthSession`; no new storage paths |
| Session restore / logout / failure handling | Implemented | Implemented + certified | Native Auth must plug into the existing lifecycle, not duplicate it |
| OAuth client IDs | Single web client ID (`VITE_GOOGLE_CLIENT_ID` / backend `google_client_id`) | Same single ID | Native tokens likely carry a different `aud` → backend audience list may be required (backend change, needs its own approval) |
| Provider sign-out | N/A (page-scoped) | N/A | Native provider sign-out must be added alongside app logout |

## Risks / open questions

1. **Backend audience verification** (`verify_google_token`) accepts one client ID; native ID tokens may not validate without a backend change — the only identified item that may exceed frontend-only scope in the Native Auth phase.
2. **Email-based account matching** for Google (no `google_sub` linkage) — account-takeover surface is limited by Google's `email_verified` requirement, but the linking policy should be reaffirmed before native.
3. **Google-created users lack password/username/phone** — no password-set flow exists; product decision needed for native onboarding.
4. **FCM token survives logout** (ISSUE-226 finding, open).
5. **No refresh tokens; 7-day JWT TTL** — acceptable today; native auth should not silently depend on longer-lived sessions.
6. **`checkUsername`/`checkEmail` endpoints exist but are unused by the form** — available for a native registration UX if wanted.

## Final reference checklist

| Required item | Covered in |
| --- | --- |
| Google Login | Flow 1 |
| Manual Login | Flow 2 |
| Registration | Flow 3 |
| Logout | Flow 4 |
| Existing User Login | Flow 5 |
| New User Registration | Flow 6 |
| Entry points, files, endpoints, backend functions per flow | Each flow section |
| Request/response shapes | Each flow section (all converge on `TokenResponse`) |
| Token/session creation | Architecture overview + per flow |
| Web auth storage | Storage & lifecycle section |
| Startup/reload restoration | Storage & lifecycle section |
| Error/failure behavior | Per flow + lifecycle section |
| Logout/cleanup | Flow 4 |
| Mobile adaptation notes | Per flow + cross-flow table |
| Risks / unknowns / must-not-assume | Per flow + risks section |
| Native Login implementation out of scope | Stated in Scope section |

## Final verdict: Native Authentication readiness

**READY, with three pre-conditions to resolve in the Native Auth phase planning:** (1) decide how the backend will validate native Google ID-token audiences (likely a small, separately-approved backend change); (2) reaffirm the email-based account-linking policy; (3) decide the onboarding treatment for Google-created partial profiles. The storage/session foundation underneath all flows is certified (ISSUE-235, Section 1 Complete) and requires no changes. Manual login and registration are already fully functional and device-validated on native; Google login is the sole flow requiring native adaptation work.
