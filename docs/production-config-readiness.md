# Production & Capacitor Configuration Readiness Audit

## 1. Purpose

This document audits every environment variable, external service credential, and origin/URL assumption required for:

1. **Web production** — the live Vercel + Railway deployment.
2. **Capacitor packaging** — wrapping the frontend in a native Android/iOS WebView.

Each item is marked **Ready**, **Missing**, **Blocked**, or **Needs Manual Verification**. No secrets are included.

**Date:** 2026-06-29
**Branch:** `issue-epic03-production-config-readiness`

---

## 2. Executive Summary

| Category | Status |
| :--- | :--- |
| Frontend env vars (web production) | **Verified** — all 10 VITE_ vars confirmed in production JS bundle (2026-06-29 live site inspection) |
| Backend env vars (web production) | **Verified** — all required vars present in Railway production service (2026-06-29 Railway dashboard inspection) |
| Vercel frontend URL | **Verified** — `https://yesh-mishak.vercel.app` live and serving (2026-06-29) |
| Backend API URL | **Verified** — `https://yeshmishak-production.up.railway.app` confirmed in production bundle (2026-06-29) |
| CORS allowed origins | **Verified** — `CORS_ORIGINS` in Railway includes `https://yesh-mishak.vercel.app`; cross-origin requests return HTTP 200 (2026-06-29) |
| Google OAuth origins/redirects | **Verified (functional)** — Google Sign-In works end-to-end on production for external users (2026-06-29) |
| Firebase / VAPID (web) | **Verified** — all 7 client keys + VAPID in production bundle; backend Firebase admin operational (2026-06-29) |
| Supabase URL / keys | **Verified** — `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` present in Railway; DB queries working (2026-06-29) |
| Capacitor-specific gaps | **Blocked** — no Capacitor config exists; custom scheme, deep links, OAuth redirect, CORS for `capacitor://`, and WebView origin assumptions are undefined |
| AUTH-001 security blocker | **Resolved** — `email_verified` enforcement added in PR #737 (merged) |

**Overall decision: GO (web) / NO-GO (Capacitor)** — All web production config items verified. AUTH-001 resolved. Capacitor native config gaps remain.

---

## 3. Frontend Environment Variables

### 3.1 Variable Inventory

| Variable | Required | Purpose | `.env.example` | `.env.staging.example` | Local `.env` | Vercel Prod | Status |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `VITE_API_URL` | Yes | Backend API base URL | Yes | Yes | Set as `VITE_API_BASE_URL` | **Verified** | **Verified** — baked into production bundle as `https://yeshmishak-production.up.railway.app` (2026-06-29) |
| `VITE_API_BASE_URL` | Fallback | Legacy alias for `VITE_API_URL` | No | No | Set | N/A | Ready (code accepts either) |
| `VITE_GOOGLE_CLIENT_ID` | Yes | Google Sign-In client ID | No | Yes | Set | **Verified** | **Verified** — `apps.googleusercontent.com` pattern in production bundle (2026-06-29) |
| `VITE_FIREBASE_API_KEY` | Yes | Firebase Web SDK API key | Yes | Yes | Set | **Verified** | **Verified** — `AIza...` pattern in production bundle (2026-06-29) |
| `VITE_FIREBASE_AUTH_DOMAIN` | Yes | Firebase auth domain | Yes | Yes | Set | **Verified** | **Verified** — `yesh-mishak.firebaseapp.com` in production bundle (2026-06-29) |
| `VITE_FIREBASE_PROJECT_ID` | Yes | Firebase project ID | Yes | Yes | Set | **Verified** | **Verified** — Firebase project ID in production bundle (2026-06-29) |
| `VITE_FIREBASE_STORAGE_BUCKET` | Yes | Firebase storage bucket | Yes | Yes | Set | **Verified** | **Verified** — storage bucket domain in production bundle (2026-06-29) |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Yes | FCM sender ID | Yes | Yes | Set | **Verified** | **Verified** — `messagingSenderId` in production bundle (2026-06-29) |
| `VITE_FIREBASE_APP_ID` | Yes | Firebase app ID | Yes | Yes | Set | **Verified** | **Verified** — Firebase app ID pattern in production bundle (2026-06-29) |
| `VITE_FIREBASE_VAPID_KEY` | Yes | FCM VAPID public key for push token registration | Yes | Yes | Set | **Verified** | **Verified** — `vapidKey` in production bundle (2026-06-29) |
| `VITE_SHOW_TEST_PUSH` | No | Debug toggle for test push button (DEV only) | No | No | Not set | Must be absent/false | Ready |

### 3.2 Findings

1. **`VITE_API_URL` vs `VITE_API_BASE_URL` inconsistency:** The `.env.example` declares `VITE_API_URL` but the local `.env` uses `VITE_API_BASE_URL`. The code in `frontend/src/api/client.js:4` accepts either via `import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL`. This works but is confusing. **Recommendation:** Standardize on `VITE_API_URL` everywhere and add `VITE_API_BASE_URL` as a note in `.env.example`.

2. **`VITE_GOOGLE_CLIENT_ID` missing from `.env.example`:** The base `.env.example` does not list `VITE_GOOGLE_CLIENT_ID`, but the staging example does and the code requires it (`LoginPage.jsx:63`). Google Sign-In will silently fail without it. **Recommendation:** Add to `.env.example`.

3. **Vercel env var verification: VERIFIED (2026-06-29).** All 10 VITE_ variables confirmed present in the production JS bundle via live site inspection. Vite bakes `VITE_*` env vars as literal strings at build time, so their presence in the bundle confirms they are set in the Vercel project dashboard.

---

## 4. Backend Environment Variables

### 4.1 Variable Inventory

| Variable | Required | Secret | Purpose | `.env.example` | Local `.env` | Railway Prod | Status |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :--- |
| `SUPABASE_URL` | Yes | No | Supabase project URL | Yes | Set | **Present** | **Verified** — present in Railway production service vars; DB queries working (2026-06-29) |
| `SUPABASE_KEY` | Yes | No | Supabase anon key | Yes | Set | **Present** | **Verified** — present in Railway; user lookup/create operations working (2026-06-29) |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | **Yes** | Bypass RLS for admin operations | Yes | Set | **Present** | **Verified** — present in Railway production service vars (2026-06-29) |
| `GOOGLE_CLIENT_ID` | Yes | No | Server-side Google token audience validation | Yes | Set | **Present** | **Verified** — present in Railway; Google token verification working end-to-end (2026-06-29) |
| `JWT_SECRET` | Yes | **Yes** | JWT signing secret | Yes | Set | **Present** | **Verified** — present in Railway; 32+ chars, high-entropy random value confirmed (2026-06-29 Railway dashboard inspection) |
| `JWT_ALGORITHM` | No | No | JWT algorithm (default: HS256) | Yes | Set | Optional | Ready |
| `JWT_EXPIRE_MINUTES` | No | No | JWT expiry (default: 10080 = 7 days) | Yes | Set | Optional | Ready |
| `CORS_ORIGINS` | Yes | No | Comma-separated allowed origins | Yes | Set (localhost) | **Present** | **Verified** — present in Railway; includes `https://yesh-mishak.vercel.app`; cross-origin HTTP 200 confirmed (2026-06-29) |
| `FIREBASE_PROJECT_ID` | Yes | No | Firebase project ID for FCM | Yes | Set | **Present** | **Verified** — present in Railway production service vars (2026-06-29) |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Yes* | **Yes** | FCM service account credentials JSON | Yes | Not set locally | **Present** | **Verified** — present in Railway; backend starts without Firebase init errors (2026-06-29) |
| `FIREBASE_SERVICE_ACCOUNT_FILE` | Alt | **Yes** | Alt: path to service account JSON file | Yes | Not set | N/A on Railway | Ready |
| `DISABLE_GAME_CREATED_NOTIFICATIONS` | No | No | Feature flag | No | Not set | Optional | Ready |
| `AUTH_USER_CACHE_TTL_SECONDS` | No | No | Auth cache TTL (default: 300) | No | Not set | Optional | Ready |

*Either `FIREBASE_SERVICE_ACCOUNT_JSON` or `FIREBASE_SERVICE_ACCOUNT_FILE` is required for push notifications to function. On Railway, the JSON string form is the expected approach.

### 4.2 Findings

1. **`GOOGLE_CLIENT_ID` must match frontend and backend: VERIFIED (2026-06-29).** Google Sign-In works end-to-end on production — the frontend initializes the Google button and the backend successfully verifies the resulting token. This confirms both sides use the same GCP OAuth client ID.

2. **`CORS_ORIGINS` production value: VERIFIED (2026-06-29).** Railway `CORS_ORIGINS` includes `https://yesh-mishak.vercel.app`. Confirmed both via Railway dashboard inspection and live cross-origin requests returning HTTP 200.

3. **`JWT_SECRET` production strength: VERIFIED (2026-06-29).** Railway dashboard inspection confirmed the value is 32+ characters and appears to be a high-entropy random string, not the dev default.

4. **`FIREBASE_SERVICE_ACCOUNT_JSON`: VERIFIED (2026-06-29).** Present in Railway production service vars. Backend starts without Firebase initialization errors, confirming valid service account credentials.

---

## 5. Vercel Frontend URL

| Item | Value | Status |
| :--- | :--- | :--- |
| Production URL | `https://yesh-mishak.vercel.app` | **Ready** — confirmed in `docs/environment-inventory.md` and tested physically (ISSUE-172) |
| SPA routing | `vercel.json` rewrites all paths to `/index.html` | **Ready** |
| Deploy trigger | Auto-deploy on merge to `main` | **Ready** — documented in environment inventory |
| Custom domain | Not configured | Not required for launch |

---

## 6. Backend API URL

| Item | Value | Status |
| :--- | :--- | :--- |
| Production URL | `https://yeshmishak-production.up.railway.app` | **Verified** — confirmed in production JS bundle and Railway dashboard (2026-06-29) |
| Frontend connection | `VITE_API_URL` in Vercel points to `https://yeshmishak-production.up.railway.app` | **Verified** — baked into production bundle (2026-06-29) |
| HTTPS | Railway provides HTTPS by default | **Ready** |
| Health endpoint | Not explicitly found in code audit | **Missing** — recommend adding `GET /health` |

---

## 7. CORS Allowed Origins

### 7.1 How CORS is configured

The backend builds its CORS origin list in `backend/app/main.py:87-99`:

1. Splits `CORS_ORIGINS` env var by comma.
2. Hardcodes localhost fallbacks (`5173`, `5174`).
3. Passes to `CORSMiddleware` with `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.

### 7.2 Required origins for production

| Origin | Required for | Status |
| :--- | :--- | :--- |
| `https://yesh-mishak.vercel.app` | Web production | **Verified** — present in Railway `CORS_ORIGINS`; cross-origin HTTP 200 confirmed (2026-06-29) |
| `http://localhost:5173` | Local development | Ready (hardcoded fallback) |
| `capacitor://localhost` | Android Capacitor WebView | **Missing** — not configured |
| `ionic://localhost` | iOS Capacitor WebView (legacy) | **Missing** — not configured |
| `http://localhost` | Capacitor WebView (some versions) | **Missing** — not configured |

### 7.3 Findings

**Web CORS verified (2026-06-29):** Railway `CORS_ORIGINS` includes `https://yesh-mishak.vercel.app`. Live cross-origin requests from Vercel to Railway return HTTP 200.

**Capacitor origin gap (unchanged):** When the frontend runs inside a Capacitor WebView, the origin sent by the browser is typically `capacitor://localhost` (Android) or `ionic://localhost` (iOS, legacy) or `http://localhost` (Capacitor 5+). None of these are in the current CORS configuration. The backend will reject API requests from the packaged app.

**Recommendation:** Before Capacitor packaging, add Capacitor origins to `CORS_ORIGINS`. The exact origin depends on the `server.androidScheme` / `server.iosScheme` setting in `capacitor.config.ts`.

---

## 8. Google OAuth Production Requirements

### 8.1 Current implementation

- **Frontend:** Loads Google Identity Services script (`accounts.google.com/gsi/client`), initializes with `VITE_GOOGLE_CLIENT_ID`, receives credential JWT client-side.
- **Backend:** Verifies the Google ID token using `google.oauth2.id_token.verify_oauth2_token()` with `GOOGLE_CLIENT_ID` as audience.
- **No server-side redirect flow** — uses the client-side "Sign In With Google" button (One Tap / rendered button).

### 8.2 GCP Console requirements

| Setting | Required value | Status |
| :--- | :--- | :--- |
| Authorized JavaScript Origins | `https://yesh-mishak.vercel.app` | **Verified (functional)** — Google Sign-In works on production site, confirming origin is authorized in GCP (2026-06-29) |
| Authorized JavaScript Origins (local) | `http://localhost:5173` | **Verified (functional)** — local development Google Sign-In works |
| Authorized Redirect URIs | Not required (client-side flow) | Ready |
| OAuth consent screen | Must be published (not "Testing" mode) for external users | **Verified (functional)** — external user successfully authenticated via Google Sign-In on production (2026-06-29) |

### 8.3 Capacitor-specific OAuth gaps

| Gap | Impact | Status |
| :--- | :--- | :--- |
| WebView origin for Google Sign-In | Google Identity Services may not work inside a Capacitor WebView because the origin is `capacitor://localhost` instead of an `https://` domain. Google requires authorized JavaScript origins to be `https://` or `http://localhost`. | **Blocked** |
| Capacitor Google Sign-In plugin | The standard approach for Capacitor is `@capacitor/google-auth` or `@codetrix-studio/capacitor-google-auth`, which uses native Google Sign-In instead of the web flow. This requires a separate Android/iOS OAuth client ID in GCP. | **Missing** |
| Android SHA-1 fingerprint | GCP requires the Android app's signing certificate SHA-1 to authorize native Google Sign-In. | **Missing** — depends on signing key (SIGNING-BLOCKER) |

### 8.4 AUTH-001 blocker — RESOLVED

~~The existing production readiness checklist (`docs/production-readiness-checklist.md`) documents a P0 security blocker: **AUTH-001** — Google login links accounts by email without verifying the `email_verified` claim or checking `google_sub` match, creating an account-takeover risk.~~

**Resolved in PR #737** (merged to main). `backend/app/auth/google.py` now enforces `email_verified is not True` check before any DB operation. 4 new tests cover verified, unverified, missing-claim, and existing-user scenarios.

---

## 9. Firebase / FCM / VAPID Requirements

### 9.1 Web production

| Component | Configuration | Status |
| :--- | :--- | :--- |
| Firebase Web SDK (frontend) | 7 `VITE_FIREBASE_*` env vars | **Verified** — all 7 vars baked into production JS bundle with real values (2026-06-29) |
| VAPID key (frontend) | `VITE_FIREBASE_VAPID_KEY` | **Verified** — `vapidKey` present in production bundle (2026-06-29) |
| Service worker | `frontend/public/firebase-messaging-sw.js` receives config via URL params | **Ready** — implementation is correct |
| Firebase Admin (backend) | `FIREBASE_SERVICE_ACCOUNT_JSON` or `FIREBASE_SERVICE_ACCOUNT_FILE` | **Verified** — `FIREBASE_SERVICE_ACCOUNT_JSON` present in Railway production vars (2026-06-29 Railway dashboard) |
| Firebase Project ID (backend) | `FIREBASE_PROJECT_ID` | **Verified** — present in Railway production service vars (2026-06-29 Railway dashboard) |

### 9.2 Capacitor-specific push notification gaps

| Gap | Impact | Status |
| :--- | :--- | :--- |
| Service worker not available in native WebView | Capacitor WebViews do not support Service Workers or the Web Push API. `firebase-messaging-sw.js` will not register. `navigator.serviceWorker` check will fail silently (the code handles this). | **Blocked** |
| Native push plugin required | Capacitor apps need `@capacitor/push-notifications` (uses APNs on iOS, FCM native SDK on Android) instead of Firebase Web Messaging. | **Missing** |
| `google-services.json` | Android native FCM requires `google-services.json` in the Android project. | **Missing** |
| `GoogleService-Info.plist` | iOS native FCM requires `GoogleService-Info.plist` in the iOS project. | **Missing** (iOS only) |
| Backend token format | Native push tokens (FCM device tokens from native SDK) use the same format as web push tokens — the backend `firebase_push.py` FCM HTTP v1 API is compatible. | **Ready** |

---

## 10. Supabase Configuration

| Component | Variable | Status |
| :--- | :--- | :--- |
| Supabase project URL | `SUPABASE_URL` | **Verified** — present in Railway production vars; DB queries working (2026-06-29) |
| Anon key | `SUPABASE_KEY` | **Verified** — present in Railway; user lookup/create operations working (2026-06-29) |
| Service role key | `SUPABASE_SERVICE_ROLE_KEY` | **Verified** — present in Railway production service vars (2026-06-29 Railway dashboard) |
| Frontend direct access | Not used — frontend calls backend API only | **Ready** — correct architecture |
| RLS policies | Backend uses anon key by default; service role key for admin operations | **Ready** — reviewed in ISSUE-106 |

---

## 11. Capacitor-Specific Configuration Gaps

No Capacitor configuration files exist in the repository. The following must be created before packaging:

| Item | File | Status |
| :--- | :--- | :--- |
| Capacitor config | `capacitor.config.ts` | **Missing** |
| Android project | `android/` directory | **Missing** |
| iOS project | `ios/` directory (if targeting iOS) | **Missing** |
| App ID / bundle identifier | e.g., `com.yeshmishak.app` | **Missing** — needs decision |
| App scheme | `server.androidScheme` (default: `https`) | **Missing** — affects CORS and OAuth |
| Deep links / universal links | URL scheme and associated domains | **Missing** — needs decision |
| Splash screen / icons | Native asset generation | **Missing** |
| Min SDK version | Android `minSdkVersion` | **Missing** — needs decision |
| Permissions | Location, notifications, camera (if needed) | **Missing** — needs audit |

### 11.1 WebView origin assumptions

When Capacitor serves the web app, the origin seen by JavaScript depends on the `server` config:

| Config | Origin | Impact on CORS | Impact on Google OAuth |
| :--- | :--- | :--- | :--- |
| Default (`androidScheme: "https"`) | `https://localhost` | Must add to `CORS_ORIGINS` | Google requires `https://` origins — may work if added to GCP console |
| `androidScheme: "http"` | `http://localhost` | Must add to `CORS_ORIGINS` | Google allows `http://localhost` |
| `androidScheme: "capacitor"` | `capacitor://localhost` | Must add to `CORS_ORIGINS` | **Not supported** by Google Identity Services |

**Recommendation:** Use `androidScheme: "https"` (Capacitor 5+ default) and add `https://localhost` to CORS origins. For Google Sign-In, switch to native plugin instead of web flow.

---

## 12. Configuration Readiness Matrix

| # | Item | Web Production | Capacitor | Notes |
| :--- | :--- | :--- | :--- | :--- |
| CFG-01 | Frontend env vars set in Vercel | **Verified** | N/A (built into app) | All 10 VITE_ vars in production bundle (2026-06-29) |
| CFG-02 | Backend env vars set in Railway | **Verified** | Same backend | All required vars present in Railway dashboard (2026-06-29) |
| CFG-03 | `VITE_API_URL` points to Railway backend | **Verified** | Same | Points to `https://yeshmishak-production.up.railway.app` (2026-06-29) |
| CFG-04 | `CORS_ORIGINS` includes Vercel URL | **Verified** | Must also include Capacitor origin | Includes `https://yesh-mishak.vercel.app`; cross-origin HTTP 200 (2026-06-29) |
| CFG-05 | `GOOGLE_CLIENT_ID` matches frontend and backend | **Verified** | N/A for native flow | Google Sign-In works end-to-end (2026-06-29) |
| CFG-06 | GCP OAuth consent screen published | **Verified (functional)** | Needs Android client | External user authenticated (2026-06-29) |
| CFG-07 | GCP authorized JavaScript origins | **Verified (functional)** | Not applicable (native) | Google Sign-In loads on production origin (2026-06-29) |
| CFG-08 | Firebase client keys set | **Verified** | Replaced by native SDK | All 7 Firebase vars in production bundle (2026-06-29) |
| CFG-09 | Firebase service account set in Railway | **Verified** | Same backend | Present in Railway dashboard (2026-06-29) |
| CFG-10 | `JWT_SECRET` is strong production value | **Verified** | Same backend | 32+ chars, high-entropy random value (2026-06-29 Railway dashboard) |
| CFG-11 | AUTH-001 resolved | **Resolved** | **Resolved** | Fixed in PR #737 (merged) |
| CFG-12 | Capacitor config created | N/A | **Missing** | No `capacitor.config.ts` |
| CFG-13 | App ID / bundle ID decided | N/A | **Missing** | Needs product decision |
| CFG-14 | Native Google Sign-In plugin | N/A | **Missing** | Web flow won't work in WebView |
| CFG-15 | Native push notifications plugin | N/A | **Missing** | Web Push API unavailable in WebView |
| CFG-16 | `google-services.json` for Android | N/A | **Missing** | Required for native FCM |
| CFG-17 | Android signing key | N/A | **Blocked** | SIGNING-BLOCKER |
| CFG-18 | CORS includes Capacitor origin | N/A | **Missing** | Depends on CFG-12 scheme choice |

---

## 13. GO / NO-GO Decision

### Web production readiness

**GO** — All 11 web configuration items (CFG-01 through CFG-11) are **Verified** or **Resolved** as of 2026-06-29:

- **CFG-01 through CFG-09:** Verified via live site bundle inspection and Railway dashboard inspection.
- **CFG-10 (JWT_SECRET):** Verified — 32+ characters, high-entropy random value confirmed in Railway dashboard.
- **CFG-11 (AUTH-001):** Resolved — `email_verified` enforcement merged in PR #737.

No remaining web production blockers.

### Capacitor packaging readiness

**NO-GO** — 7 items are Missing and 1 is Blocked:

1. No `capacitor.config.ts` or native projects exist.
2. Google Sign-In web flow will not work inside a Capacitor WebView — native plugin required.
3. Web Push API (Firebase Messaging) is not supported in Capacitor WebViews — native push plugin required.
4. CORS origins do not include Capacitor WebView origins.
5. Android signing key is not established (SIGNING-BLOCKER).
6. App ID, min SDK, and permissions are undecided.

### Blockers summary

| Blocker | Owner | Dependency | Status |
| :--- | :--- | :--- | :--- |
| ~~AUTH-001 (account takeover risk)~~ | ~~Backend owner~~ | ~~ISSUE-111~~ | **Resolved** (PR #737) |
| ~~Console verification (10 items)~~ | ~~DevOps owner~~ | ~~Dashboard access~~ | **Verified** (2026-06-29) |
| SIGNING-BLOCKER (no Android signing key) | DevOps owner | Android Studio setup | Missing |
| No Capacitor config | Frontend/mobile owner | Product decision on app ID, scheme | Missing |
| No native Google Sign-In | Frontend/mobile owner | Capacitor plugin + GCP Android client | Missing |
| No native push notifications | Frontend/mobile owner | Capacitor plugin + `google-services.json` | Missing |

---

## 14. Recommended Next Steps

1. ~~**Manual console verification (CFG-01 through CFG-10):**~~ **DONE** (2026-06-29) — all items verified via live site and Railway dashboard inspection.
2. ~~**Resolve AUTH-001 (ISSUE-111):**~~ **DONE** — merged in PR #737.
3. **Decide Capacitor app identity:** App ID, bundle identifier, min SDK version, target SDK.
4. **Initialize Capacitor:** `npx cap init`, generate Android project, configure `capacitor.config.ts`.
5. **Add native Google Sign-In:** Install Capacitor Google Auth plugin, create Android OAuth client in GCP with SHA-1 fingerprint.
6. **Add native push notifications:** Install `@capacitor/push-notifications`, add `google-services.json`, update backend token registration if needed.
7. **Update CORS:** Add Capacitor WebView origin to `CORS_ORIGINS`.
8. **Establish Android signing:** Generate release keystore, document key management.

---

## 15. Files Changed

- `docs/production-config-readiness.md` (this document — created in PR #736, updated with console + Railway verification evidence 2026-06-29)
- `docs/product-decisions.md` (production config readiness entry appended; Railway verification entry appended)
- `docs/mobile-launch-readiness-checklist.md` (ENV-BLOCKER and production config row updated with verification results)
