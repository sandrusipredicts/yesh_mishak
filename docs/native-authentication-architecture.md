# Native Authentication Architecture (ISSUE-237)

## Dependency

This architecture is built directly on the ISSUE-236 audit (`docs/authentication-flow-audit.md`, PR #789) and on the certified session foundation (ISSUE-229–235: `docs/session-lifecycle.md`, `docs/secure-storage-failure-handling-strategy.md`, `docs/secure-storage-certification-review.md`). Every decision below resolves a precondition or fact recorded in that audit.

## Scope

Defines the **official, closed** architecture for authentication in the Android (Capacitor) app: Google authentication, manual authentication, token exchange, session creation, first login, existing-user login, new-user registration, logout, token storage/restore, and failure/recovery. Documentation only.

## Out of Scope

- Any implementation (Native Login implementation happens only in the follow-up issues listed at the end).
- Plugin installation, backend/frontend/native code changes, package changes.
- iOS execution or validation (architecture is written to be iOS-compatible later, but only Android is in scope for validation).
- Push notifications (except the pre-existing FCM-logout follow-up noted for completeness).
- Password-reset / password-set flows, email verification, refresh tokens (explicitly deferred; see Security considerations).

## Executive Summary

Google login is the only authentication flow broken in the Android WebView (ISSUE-236). The chosen fix: **Native SDK sign-in via Android Credential Manager ("Sign in with Google"), exposed through a Capacitor plugin, configured with `serverClientId` = the existing web OAuth client ID.** The approved **target** architecture keeps the backend unchanged: with that configuration the returned Google ID token is **expected** to carry an audience compatible with the current backend `verify_google_token` check, so the existing `POST /auth/google` endpoint verifies it as-is — no backend modification, no new endpoint, no audience list. **This audience assumption must be validated during NA-1 / NA-3 on Samsung SM-S928B.** If the selected plugin cannot produce a backend-verifiable Google ID token with the existing web client ID audience, **NA-B1 becomes a blocking backend follow-up before Native Authentication can ship.** Everything after the Google ID token is obtained is byte-for-byte the current, certified pipeline: same token exchange, same `TokenResponse`, same `saveAuthSession`, same secure storage, same restore/logout behavior. Manual login and registration change nothing. Implementation is **blocked** on exactly one named follow-up (plugin technology selection) plus one operational task (Google Cloud console Android client registration).

## Architecture Decision Record

| # | Decision | Status |
| --- | --- | --- |
| ADR-1 | **Native SDK, not Browser Redirect** for Google auth on Android | **DECIDED** |
| ADR-2 | Google ID token obtained via **Android Credential Manager** ("Sign in with Google") through a Capacitor plugin | **DECIDED** (concrete plugin: blocking follow-up NA-1, mirroring the ISSUE-227→228 architecture/technology split) |
| ADR-3 | Plugin configured with **`serverClientId` = existing web OAuth client ID** → ID-token `aud` = web client ID | **DECIDED** |
| ADR-4 | **Backend unchanged in the target architecture**: single audience (`google_client_id`) remains; `POST /auth/google` reused; **no** native-specific endpoint. Contingent on the ADR-3 audience assumption, which must be validated in NA-1/NA-3 on device; if disproved, NA-B1 (backend audience change) becomes blocking before ship | **DECIDED (target; assumption validated in NA-1/NA-3)** |
| ADR-5 | Account linking stays **email-based** (with backend-enforced `email_verified === true`); `google_sub` linkage is a non-blocking hardening follow-up | **DECIDED** |
| ADR-6 | Google-created partial profiles (null username/phone, no password) **remain acceptable** for the first native release; profile completion is a non-blocking product follow-up | **DECIDED** |
| ADR-7 | Manual login and registration: **no changes** for mobile | **DECIDED** |
| ADR-8 | Logout: existing certified flow **plus native provider sign-out** (Credential Manager `clearCredentialState`) | **DECIDED** |
| ADR-9 | App JWT storage/restore: **exactly the certified ISSUE-235 mechanism**, no new storage paths | **DECIDED** |
| ADR-10 | Web build keeps the current GIS flow; runtime `Capacitor.isNativePlatform()` selects native vs web Google flow | **DECIDED** |

## Official chosen architecture

1. Android obtains a **Google ID token** natively via Credential Manager ("Sign in with Google") through a Capacitor plugin, requested with `serverClientId` = the existing web client ID (`VITE_GOOGLE_CLIENT_ID` / backend `google_client_id`).
2. The frontend sends that ID token to the **existing** `POST /auth/google` — the same call `loginWithGoogle` makes today.
3. The backend verifies it against the **existing single audience**, requires `email_verified`, and finds-or-creates the user **by email** (unchanged `verify_google_token` / `find_or_create_google_user`).
4. The backend returns the **existing internal app JWT** (`TokenResponse`).
5. The frontend stores it via the **certified** `saveAuthSession` → secure storage path.
6. Startup/restore continues to use the certified ISSUE-235 behavior, untouched.
7. Logout runs the certified cleanup **plus** native provider sign-out.

This matches the "preferred architecture" proposed in ISSUE-237 and is hereby **APPROVED**, with one refinement: no native-specific backend endpoint is introduced (rejected below).

## Rejected alternatives

| Alternative | Why rejected |
| --- | --- |
| **Browser Redirect** (Custom Tabs / system browser OAuth redirect back into the app) | Requires deep-link/redirect handling not yet built, adds an app-switch to the UX, and provides nothing the native SDK doesn't; Google is actively deprecating WebView-based OAuth, and Credential Manager is the platform-recommended path |
| Keep the **GIS web script** inside the WebView | Empirically broken (device-observed load failure, ISSUE-231/233 validations); Google blocks OAuth in WebViews |
| **Firebase Authentication** as the sign-in layer | Issues Firebase-signed ID tokens (different `iss`/`aud`) that `verify_google_token` cannot verify → would force backend changes and couple auth to Firebase; the app uses Firebase only for push today |
| **New native-specific backend endpoint** | Unnecessary: with ADR-3 the existing endpoint verifies native tokens as-is; a second endpoint doubles the audited surface |
| **Backend multi-audience list** (accept the Android client ID as `aud`) | Not needed under the ADR-3 target assumption; kept as the documented fallback if NA-1 evaluation or NA-3 device validation disproves the `serverClientId` assumption — in that case a small, separately-approved backend change reopens via NA-B1, blocking before ship |
| **Switch account linking to `google_sub`** now | Requires a schema/data migration and changes web behavior mid-phase; email linking is bounded by the `email_verified` requirement; revisit as non-blocking hardening (NA-5) |

## Flow maps

### Google Authentication Flow (native Android)

```
User taps "Sign in with Google" (native path)
  → Capacitor plugin → Android Credential Manager bottom-sheet (account picker)
  → user picks account → plugin returns Google ID token (aud = web client ID)
  → POST /auth/google { token }                      [Token Exchange Flow]
  → backend verifies audience + email_verified, finds-or-creates by email
  → TokenResponse { access_token, user }
  → saveAuthSession(authData)                        [Session Creation Flow]
  → authenticated UI
Cancel/dismiss → stay on login page, no error banner
Plugin/Play-services unavailable → Google option hidden or disabled with
  translated notice; manual login remains available (fail closed, never crash)
```

On web (`!isNativePlatform()`), the current GIS button flow remains exactly as documented in ISSUE-236 Flow 1.

### Manual Authentication Flow

Unchanged (ADR-7): login tab → `POST /auth/login` (username-or-email + bcrypt + progressive delays) → `TokenResponse` → `saveAuthSession`. Already native-certified on the Samsung device.

### Token Exchange Flow

Google ID token → `POST /auth/google { token }` → app JWT. One exchange, no intermediate state: the app never treats the Google ID token as a session, never stores it, and discards it after the exchange resolves. Accepted audience: **the single existing web client ID** (ADR-3/4). The Google ID token must never be logged (same redaction rules as the app JWT, ISSUE-233 §8).

### Session Creation Flow

`saveAuthSession(authData)` (unchanged): `setToken` → certified secure-storage write with retry + persistence-warning semantics (ISSUE-233 G2) → `setUserMetadata` → `auth-session-changed` → `onLogin` sets `currentUser`. Identical for Google, manual login, and registration.

### First Login Flow (new Google user, first native sign-in)

Credential Manager picker → ID token → exchange → `find_or_create_google_user` **creates** the user (name/email from Google; username, phone_number, password all null/absent) → JWT → session. The app must tolerate null username/phone everywhere it renders user context (it does today — toolbar falls back to name/email). No forced profile completion in the first release (ADR-6; follow-up NA-6).

### Existing User Login Flow

Same path; `find_or_create_google_user` **matches by email** — including accounts originally created through the registration form (ADR-5). A returning user with a valid stored session never re-enters login at all: certified startup restore handles them.

### New User Registration Flow

Two unchanged paths: (a) the registration form (`POST /auth/register`, auto-login on 201) — no mobile changes (ADR-7); (b) first Google sign-in as above. No third path is introduced.

### Logout Flow

Certified ISSUE-231/233 flow unchanged (epoch bump, pinned-Bearer revocation, ordered non-aborting cleanup, delete retry + warning banner, logged-out UI guaranteed) **plus one addition (ADR-8):** call the plugin's provider sign-out (`clearCredentialState`) so the next sign-in shows the account picker instead of silently reusing the last account. Provider sign-out failure is non-fatal: log a redacted event; app logout semantics are unaffected.

### Token Storage / Session Restore Flow

Exactly the certified ISSUE-235 behavior (ADR-9): app JWT in Keystore-backed secure storage; 5s startup deadlines; `/games/me` validation before authenticated UI; deduplicated resume revalidation; fail-closed everywhere. **No new storage paths, keys, or tiers are introduced by native auth.** The Google ID token is never persisted.

### Failure and Recovery Flow

| Failure | Behavior |
| --- | --- |
| Credential Manager / Play services unavailable | Google option hidden/disabled with translated notice; manual login unaffected; no crash |
| User cancels the picker | Return to login page silently (cancellation is not an error) |
| Plugin returns no/invalid ID token | Translated error on login page; nothing stored |
| `POST /auth/google` 401 (bad token, unverified email) | Translated error; no session mutation |
| Exchange network failure | Translated error; retry is user-initiated (tap again); no automatic retry loops |
| Secure-storage write failure after exchange | Certified ISSUE-233 G2: retry once → in-memory session + persistence warning |
| Provider sign-out failure at logout | Non-fatal, redacted log; app logout completes regardless |

No failure path may leave a partial session: the session exists only after `saveAuthSession` resolves.

## Backend contract

The approved target architecture keeps the backend unchanged by configuring the native Google Sign-In plugin with `serverClientId` equal to the existing web OAuth client ID, so the returned Google ID token is **expected** to have an audience compatible with the current backend `verify_google_token` check. **This assumption must be validated during NA-1 / NA-3 on Samsung SM-S928B. If the selected plugin cannot produce a backend-verifiable Google ID token with the existing web client ID audience, NA-B1 becomes a blocking backend follow-up before Native Authentication can ship.**

Under the target architecture, everything else stays as audited in ISSUE-236: `POST /auth/google` request/response, Google ID-token audience verification (single `google_client_id`), `email_verified` requirement, email-based find-or-create, app JWT shape (HS256, `sub`/`email`/`iat`/`exp` plus configured `iss`/`aud`, 7-day TTL), revocation via `tokens_valid_after`, and rate limits (10/min, 50/hr per IP). Backend work may reopen **only** through NA-B1, separately approved.

## Frontend contract

- `LoginPage` branches on `Capacitor.isNativePlatform()`: native → plugin sign-in button (rendered by the app, not GIS); web → current GIS flow untouched.
- The native path calls the existing `loginWithGoogle(idToken)` and `handleAuthSuccess` — no new auth plumbing, no changes to `api/auth.js`, `api/client.js`, or `sessionStorage.js` contracts.
- `handleLogout` additionally invokes provider sign-out via the plugin, best-effort.
- All user-facing failure states use translated strings (en + he), consistent with existing auth error handling.

## Android contract

- An **Android OAuth client ID** must exist in the same Google Cloud project, registered with the app's package id (`com.yeshmishak.app`) and the SHA-1 fingerprints of both debug and release signing keys (operational task NA-2). It authorizes the device flow; it is **not** the token audience (ADR-3).
- The plugin is configured with `serverClientId` = the existing web client ID.
- No other Android-native file changes beyond what the chosen plugin's install requires (evaluated in NA-1; `npx cap sync` will be justified there as a native-dependency change per repo rules).
- minSdk 24 / target 36 (current project settings) must be satisfied by the chosen plugin.

## Security considerations

1. The Google ID token is exchange-only: never stored, never logged, discarded after `POST /auth/google` (same redaction discipline as `secure_storage.*` events).
2. All certified invariants (ISSUE-234 §8) apply unchanged: no JWT in web storage on native, fail closed, logout wins over late async work, no token values in logs.
3. Email-based linking (ADR-5) is bounded by the backend's `email_verified === true` requirement; `google_sub` linkage is queued as hardening (NA-5).
4. Provider sign-out at logout prevents silent account reuse on shared devices (ADR-8).
5. Deferred and explicitly out of scope here: password-set flow for Google-created accounts (NA-7), refresh tokens, email verification for form registration, FCM token cleanup at logout (NA-8, pre-existing ISSUE-226 finding).

## Manual validation checklist (Samsung SM-S928B — required before implementation acceptance)

1. Native Google sign-in: picker appears, sign-in completes, authenticated toolbar visible.
2. First-login (new Google account): user created, app tolerates null username/phone.
3. Existing-account sign-in: same email → same account (including a form-registered account).
4. App JWT only in secure storage (`run-as`); Google ID token nowhere on disk; no JWT in localStorage/sessionStorage.
5. Force-stop → relaunch restores session; device restart restores session.
6. Logout → certified cleanup checks (secure store `<map />`, storages clean) **plus** next sign-in shows the account picker (provider sign-out proof).
7. Post-logout relaunch and device restart remain logged out; late-validation race re-run.
8. Cancel the picker → login page, no error, no crash. Airplane-mode exchange failure → clean error.
9. Manual login + registration regression (unchanged behavior).
10. Logcat scan: zero JWT-like values (covers both Google ID tokens and app JWTs — same `eyJ` pattern).
11. Backend/iOS untouched proof for the implementation PR.

## Implementation issue breakdown

**Blocking (implementation may not start until resolved):**
- **NA-1 — Native Google sign-in technology selection:** evaluate Credential Manager–based Capacitor plugins (candidates: `@capgo/capacitor-social-login`, `@codetrix-studio/capacitor-google-auth`, direct thin native bridge) against: returns raw Google ID token with `serverClientId` audience, Capacitor 8 + minSdk 24 compatibility, maintenance health, provider sign-out support. Output: one approved plugin (repo precedent: ISSUE-228).
- **NA-2 — Google Cloud console setup:** create/verify the Android OAuth client ID (package + debug/release SHA-1s); confirm the web client ID serves as `serverClientId`. Operational, no code.

**Implementation (sequenced after NA-1/NA-2):**
- **NA-3 — Native Google sign-in implementation:** plugin install (+`cap sync`, justified), LoginPage native branch, error states (en+he), exchange wiring.
- **NA-4 — Provider sign-out at logout** (may merge into NA-3 if small).
- **NA-V — Samsung SM-S928B validation** of the checklist above (its own gate, per repo protocol).

**Non-blocking follow-ups:** NA-5 `google_sub` linkage hardening · NA-6 profile completion for Google-created users (product) · NA-7 password-set flow (product) · NA-8 FCM token logout cleanup (pre-existing ISSUE-226 finding).

**Conditional:** NA-B1 backend audience list — opened **only if** the ADR-3 audience assumption is disproved during NA-1 evaluation or NA-3 device validation on Samsung SM-S928B; in that case NA-B1 is **blocking before Native Authentication can ship**. Until then the backend remains frozen.

## Final decision checklist

| Required question | Answer | Closed? |
| --- | --- | --- |
| 1. Native SDK or Browser Redirect? | **Native SDK** (Credential Manager via Capacitor plugin); Browser Redirect rejected | ✅ |
| 2. How are Google tokens created? | Natively by Credential Manager "Sign in with Google", requested with `serverClientId` = web client ID | ✅ |
| 3. Which client IDs / audiences are accepted? | The single existing web client ID (`google_client_id`) | ✅ |
| 4. Backend multi-audience support needed? | **Not in the target architecture** (ADR-3/4); the audience assumption is validated in NA-1/NA-3 on device, and NA-B1 becomes a blocking backend follow-up if it fails | ✅ |
| 5. How is the Google ID token exchanged for the app JWT? | Existing `POST /auth/google`, unchanged | ✅ |
| 6. How is the app JWT stored? | Certified secure-storage path via `saveAuthSession` (ISSUE-235) | ✅ |
| 7. First login for a new Google user? | Auto-create by email; partial profile accepted (ADR-6) | ✅ |
| 8. How are existing users matched? | By email via `find_or_create_google_user`, unchanged | ✅ |
| 9. Linking policy: email or google_sub? | **Email** (ADR-5); `google_sub` deferred to NA-5 (non-blocking) | ✅ |
| 10. Null username/phone/password Google users? | Tolerated in v1; profile completion NA-6, password-set NA-7 (non-blocking) | ✅ |
| 11. Does Manual Login change for mobile? | **No** | ✅ |
| 12. Does Registration change for mobile? | **No** | ✅ |
| 13. Does Logout change for mobile? | Certified flow + provider sign-out (ADR-8) | ✅ |
| 14. Samsung validation required before acceptance? | Yes — checklist above, on SM-S928B | ✅ |

No authentication architecture decision remains open. The only blocking items are the two named pre-implementation issues (NA-1 technology selection, NA-2 console setup); **Native Authentication implementation is blocked until NA-1 and NA-2 are resolved**, and conditionally on NA-B1 only if NA-1 disproves ADR-3.

## Final verdict

**APPROVED.** The preferred architecture proposed in ISSUE-237 is adopted as the official native authentication architecture, with the refinement that no native-specific backend endpoint is created and the backend is kept unchanged **in the target architecture** (single audience via the `serverClientId` mechanism) — an audience assumption that must be validated during NA-1/NA-3 on Samsung SM-S928B, with NA-B1 becoming a blocking backend follow-up before Native Authentication can ship if it is disproved. All fourteen required questions are decided; rejected alternatives are recorded with reasons; implementation proceeds only through the NA-1 → NA-2 → NA-3/NA-4 → NA-V issue sequence, each under the repository's per-issue approval protocol. This document contains no implementation and changes no runtime behavior.
