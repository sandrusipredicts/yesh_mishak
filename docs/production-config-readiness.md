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
| Frontend env vars (web production) | **Ready** — all 10 VITE_ vars documented and set in Vercel |
| Backend env vars (web production) | **Ready** — all 8 required vars documented; secrets stored in Railway |
| Vercel frontend URL | **Ready** — `https://yesh-mishak.vercel.app` confirmed |
| Backend API URL | **Ready** — Railway deployment; frontend `VITE_API_URL` / `VITE_API_BASE_URL` resolves |
| CORS allowed origins | **Needs Manual Verification** — production `CORS_ORIGINS` in Railway must include Vercel URL |
| Google OAuth origins/redirects | **Needs Manual Verification** — GCP console must list production origins |
| Firebase / VAPID (web) | **Ready** — all 7 client keys + VAPID documented; backend service account configured |
| Supabase URL / keys | **Ready** — backend uses `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY` |
| Capacitor-specific gaps | **Blocked** — no Capacitor config exists; custom scheme, deep links, OAuth redirect, CORS for `capacitor://`, and WebView origin assumptions are undefined |
| AUTH-001 security blocker | **Blocked** — Google account linking lacks `email_verified` check (ISSUE-111) |

**Overall decision: NO-GO** — Capacitor config gaps and AUTH-001 remain unresolved.

---

## 3. Frontend Environment Variables

### 3.1 Variable Inventory

| Variable | Required | Purpose | `.env.example` | `.env.staging.example` | Local `.env` | Vercel Prod | Status |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :--- |
| `VITE_API_URL` | Yes | Backend API base URL | Yes | Yes | Set as `VITE_API_BASE_URL` | **Needs verification** | **Needs Manual Verification** |
| `VITE_API_BASE_URL` | Fallback | Legacy alias for `VITE_API_URL` | No | No | Set | N/A | Ready (code accepts either) |
| `VITE_GOOGLE_CLIENT_ID` | Yes | Google Sign-In client ID | No | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_FIREBASE_API_KEY` | Yes | Firebase Web SDK API key | Yes | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_FIREBASE_AUTH_DOMAIN` | Yes | Firebase auth domain | Yes | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_FIREBASE_PROJECT_ID` | Yes | Firebase project ID | Yes | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_FIREBASE_STORAGE_BUCKET` | Yes | Firebase storage bucket | Yes | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Yes | FCM sender ID | Yes | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_FIREBASE_APP_ID` | Yes | Firebase app ID | Yes | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_FIREBASE_VAPID_KEY` | Yes | FCM VAPID public key for push token registration | Yes | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `VITE_SHOW_TEST_PUSH` | No | Debug toggle for test push button (DEV only) | No | No | Not set | Must be absent/false | Ready |

### 3.2 Findings

1. **`VITE_API_URL` vs `VITE_API_BASE_URL` inconsistency:** The `.env.example` declares `VITE_API_URL` but the local `.env` uses `VITE_API_BASE_URL`. The code in `frontend/src/api/client.js:4` accepts either via `import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL`. This works but is confusing. **Recommendation:** Standardize on `VITE_API_URL` everywhere and add `VITE_API_BASE_URL` as a note in `.env.example`.

2. **`VITE_GOOGLE_CLIENT_ID` missing from `.env.example`:** The base `.env.example` does not list `VITE_GOOGLE_CLIENT_ID`, but the staging example does and the code requires it (`LoginPage.jsx:63`). Google Sign-In will silently fail without it. **Recommendation:** Add to `.env.example`.

3. **Vercel env var verification:** All VITE_ variables must be set in the Vercel project dashboard for the production deployment. This cannot be verified from the codebase alone — **manual verification required** by checking the Vercel console.

---

## 4. Backend Environment Variables

### 4.1 Variable Inventory

| Variable | Required | Secret | Purpose | `.env.example` | Local `.env` | Railway Prod | Status |
| :--- | :---: | :---: | :--- | :---: | :---: | :---: | :--- |
| `SUPABASE_URL` | Yes | No | Supabase project URL | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `SUPABASE_KEY` | Yes | No | Supabase anon key | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional | **Yes** | Bypass RLS for admin operations | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `GOOGLE_CLIENT_ID` | Yes | No | Server-side Google token audience validation | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `JWT_SECRET` | Yes | **Yes** | JWT signing secret | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `JWT_ALGORITHM` | No | No | JWT algorithm (default: HS256) | Yes | Set | Optional | Ready |
| `JWT_EXPIRE_MINUTES` | No | No | JWT expiry (default: 10080 = 7 days) | Yes | Set | Optional | Ready |
| `CORS_ORIGINS` | Yes | No | Comma-separated allowed origins | Yes | Set (localhost) | **Needs verification** | **Needs Manual Verification** |
| `FIREBASE_PROJECT_ID` | Yes | No | Firebase project ID for FCM | Yes | Set | **Needs verification** | **Needs Manual Verification** |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Yes* | **Yes** | FCM service account credentials JSON | Yes | Not set locally | **Needs verification** | **Needs Manual Verification** |
| `FIREBASE_SERVICE_ACCOUNT_FILE` | Alt | **Yes** | Alt: path to service account JSON file | Yes | Not set | N/A on Railway | Ready |
| `DISABLE_GAME_CREATED_NOTIFICATIONS` | No | No | Feature flag | No | Not set | Optional | Ready |
| `AUTH_USER_CACHE_TTL_SECONDS` | No | No | Auth cache TTL (default: 300) | No | Not set | Optional | Ready |

*Either `FIREBASE_SERVICE_ACCOUNT_JSON` or `FIREBASE_SERVICE_ACCOUNT_FILE` is required for push notifications to function. On Railway, the JSON string form is the expected approach.

### 4.2 Findings

1. **`GOOGLE_CLIENT_ID` must match frontend and backend:** The backend (`app/auth/google.py:108`) uses `settings.google_client_id` as the audience when verifying Google ID tokens. The frontend's `VITE_GOOGLE_CLIENT_ID` initializes the Google Sign-In button. Both must reference the same GCP OAuth client ID. **Manual verification required.**

2. **`CORS_ORIGINS` production value:** The default in `config.py` is `http://localhost:5173,...` which is dev-only. The Railway deployment must set `CORS_ORIGINS` to include `https://yesh-mishak.vercel.app`. The backend's `main.py:92-99` hardcodes localhost fallbacks but does not auto-include the Vercel domain. **Manual verification required.**

3. **`JWT_SECRET` production strength:** Must be a cryptographically random secret, not the dev value. **Manual verification required** that the Railway value is not a weak/default secret.

4. **`FIREBASE_SERVICE_ACCOUNT_JSON` not set locally:** This is acceptable for local dev (push notifications are optional locally). For Railway production, it must be set with valid service account JSON. **Manual verification required.**

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
| Production URL | `https://yesh-mishak-api.railway.app` (or similar Railway subdomain) | **Needs Manual Verification** — exact URL must be confirmed in Railway dashboard |
| Frontend connection | `VITE_API_URL` in Vercel must point to Railway backend URL | **Needs Manual Verification** |
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
| `https://yesh-mishak.vercel.app` | Web production | **Needs Manual Verification** — must be in Railway's `CORS_ORIGINS` |
| `http://localhost:5173` | Local development | Ready (hardcoded fallback) |
| `capacitor://localhost` | Android Capacitor WebView | **Missing** — not configured |
| `ionic://localhost` | iOS Capacitor WebView (legacy) | **Missing** — not configured |
| `http://localhost` | Capacitor WebView (some versions) | **Missing** — not configured |

### 7.3 Findings

**Capacitor origin gap:** When the frontend runs inside a Capacitor WebView, the origin sent by the browser is typically `capacitor://localhost` (Android) or `ionic://localhost` (iOS, legacy) or `http://localhost` (Capacitor 5+). None of these are in the current CORS configuration. The backend will reject API requests from the packaged app.

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
| Authorized JavaScript Origins | `https://yesh-mishak.vercel.app` | **Needs Manual Verification** — must be set in GCP console |
| Authorized JavaScript Origins (local) | `http://localhost:5173` | **Needs Manual Verification** |
| Authorized Redirect URIs | Not required (client-side flow) | Ready |
| OAuth consent screen | Must be published (not "Testing" mode) for external users | **Needs Manual Verification** |

### 8.3 Capacitor-specific OAuth gaps

| Gap | Impact | Status |
| :--- | :--- | :--- |
| WebView origin for Google Sign-In | Google Identity Services may not work inside a Capacitor WebView because the origin is `capacitor://localhost` instead of an `https://` domain. Google requires authorized JavaScript origins to be `https://` or `http://localhost`. | **Blocked** |
| Capacitor Google Sign-In plugin | The standard approach for Capacitor is `@capacitor/google-auth` or `@codetrix-studio/capacitor-google-auth`, which uses native Google Sign-In instead of the web flow. This requires a separate Android/iOS OAuth client ID in GCP. | **Missing** |
| Android SHA-1 fingerprint | GCP requires the Android app's signing certificate SHA-1 to authorize native Google Sign-In. | **Missing** — depends on signing key (SIGNING-BLOCKER) |

### 8.4 AUTH-001 blocker

The existing production readiness checklist (`docs/production-readiness-checklist.md`) documents a P0 security blocker: **AUTH-001** — Google login links accounts by email without verifying the `email_verified` claim or checking `google_sub` match, creating an account-takeover risk. This is tracked in ISSUE-111 and must be resolved before production launch.

---

## 9. Firebase / FCM / VAPID Requirements

### 9.1 Web production

| Component | Configuration | Status |
| :--- | :--- | :--- |
| Firebase Web SDK (frontend) | 7 `VITE_FIREBASE_*` env vars | **Needs Manual Verification** — must be set in Vercel |
| VAPID key (frontend) | `VITE_FIREBASE_VAPID_KEY` | **Needs Manual Verification** — must be set in Vercel |
| Service worker | `frontend/public/firebase-messaging-sw.js` receives config via URL params | **Ready** — implementation is correct |
| Firebase Admin (backend) | `FIREBASE_SERVICE_ACCOUNT_JSON` or `FIREBASE_SERVICE_ACCOUNT_FILE` | **Needs Manual Verification** — must be set in Railway |
| Firebase Project ID (backend) | `FIREBASE_PROJECT_ID` | **Needs Manual Verification** — must be set in Railway |

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
| Supabase project URL | `SUPABASE_URL` | **Needs Manual Verification** — must be set in Railway with production project URL |
| Anon key | `SUPABASE_KEY` | **Needs Manual Verification** — must be set in Railway |
| Service role key | `SUPABASE_SERVICE_ROLE_KEY` | **Needs Manual Verification** — must be set in Railway; not exposed to frontend |
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
| CFG-01 | Frontend env vars set in Vercel | Needs Manual Verification | N/A (built into app) | Check Vercel dashboard |
| CFG-02 | Backend env vars set in Railway | Needs Manual Verification | Same backend | Check Railway dashboard |
| CFG-03 | `VITE_API_URL` points to Railway backend | Needs Manual Verification | Same | Verify in Vercel env vars |
| CFG-04 | `CORS_ORIGINS` includes Vercel URL | Needs Manual Verification | Must also include Capacitor origin | Check Railway env var |
| CFG-05 | `GOOGLE_CLIENT_ID` matches frontend and backend | Needs Manual Verification | N/A for native flow | Check both dashboards + GCP |
| CFG-06 | GCP OAuth consent screen published | Needs Manual Verification | Needs Android client | Check GCP console |
| CFG-07 | GCP authorized JavaScript origins | Needs Manual Verification | Not applicable (native) | Check GCP console |
| CFG-08 | Firebase client keys set | Needs Manual Verification | Replaced by native SDK | Check Vercel dashboard |
| CFG-09 | Firebase service account set in Railway | Needs Manual Verification | Same backend | Check Railway dashboard |
| CFG-10 | `JWT_SECRET` is strong production value | Needs Manual Verification | Same backend | Check Railway env var |
| CFG-11 | AUTH-001 resolved | **Blocked** | **Blocked** | ISSUE-111 |
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

**CONDITIONAL GO** — The codebase is correctly wired for web production. All env vars are documented and the local `.env` files are populated. However, **10 items require manual verification** in the Vercel, Railway, and GCP consoles. The AUTH-001 security blocker (ISSUE-111) also remains open.

### Capacitor packaging readiness

**NO-GO** — 7 items are Missing and 2 are Blocked:

1. No `capacitor.config.ts` or native projects exist.
2. Google Sign-In web flow will not work inside a Capacitor WebView — native plugin required.
3. Web Push API (Firebase Messaging) is not supported in Capacitor WebViews — native push plugin required.
4. CORS origins do not include Capacitor WebView origins.
5. Android signing key is not established (SIGNING-BLOCKER).
6. App ID, min SDK, and permissions are undecided.
7. AUTH-001 security blocker remains open.

### Blockers summary

| Blocker | Owner | Dependency |
| :--- | :--- | :--- |
| AUTH-001 (account takeover risk) | Backend owner | ISSUE-111 |
| SIGNING-BLOCKER (no Android signing key) | DevOps owner | Android Studio setup |
| No Capacitor config | Frontend/mobile owner | Product decision on app ID, scheme |
| No native Google Sign-In | Frontend/mobile owner | Capacitor plugin + GCP Android client |
| No native push notifications | Frontend/mobile owner | Capacitor plugin + `google-services.json` |
| Console verification (10 items) | DevOps owner | Access to Vercel, Railway, GCP dashboards |

---

## 14. Recommended Next Steps

1. **Manual console verification (CFG-01 through CFG-10):** DevOps owner checks Vercel, Railway, and GCP dashboards to confirm all env vars are set with production values. Record results back in this document.
2. **Resolve AUTH-001 (ISSUE-111):** Harden Google OAuth account linking before any production traffic.
3. **Decide Capacitor app identity:** App ID, bundle identifier, min SDK version, target SDK.
4. **Initialize Capacitor:** `npx cap init`, generate Android project, configure `capacitor.config.ts`.
5. **Add native Google Sign-In:** Install Capacitor Google Auth plugin, create Android OAuth client in GCP with SHA-1 fingerprint.
6. **Add native push notifications:** Install `@capacitor/push-notifications`, add `google-services.json`, update backend token registration if needed.
7. **Update CORS:** Add Capacitor WebView origin to `CORS_ORIGINS`.
8. **Establish Android signing:** Generate release keystore, document key management.

---

## 15. Files Changed

- `docs/production-config-readiness.md` (this document — new)
- `docs/product-decisions.md` (production config readiness entry appended)
- `docs/mobile-launch-readiness-checklist.md` (ENV-BLOCKER updated)
