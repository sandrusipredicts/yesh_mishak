# Mobile Environment Strategy

**ISSUE:** 184
**Date:** 2026-06-30
**Status:** Approved strategy reference
**Scope:** Documentation only - no implementation, no project creation, no secrets

---

## 1. Purpose

This document defines the environment strategy for the Yesh Mishak mobile application. It establishes how development, staging, and production environments are separated, how builds target the correct services, and what rules prevent production contamination.

This strategy applies to:

- Frontend (React + Capacitor) builds for web, Android, and iOS
- Backend (FastAPI) deployments
- Supabase project isolation
- Firebase / push notification isolation
- Mobile app identifiers per environment

---

## 2. Environment Overview

| Property | Development | Staging | Production |
| :--- | :--- | :--- | :--- |
| **Purpose** | Local development and fast iteration | Production-like validation before release | Real users and real data |
| **Backend** | Local FastAPI (`localhost:8000`) or dedicated dev deployment | Staging backend deployment | Production backend deployment |
| **Supabase** | Dev Supabase project or local Supabase | Separate staging Supabase project | Production Supabase project |
| **Firebase** | Dev Firebase project/app | Separate staging Firebase project/app | Production Firebase project/app |
| **Android applicationId** | `com.yeshmishak.app.dev` | `com.yeshmishak.app.staging` | `com.yeshmishak.app` |
| **iOS Bundle Identifier** | `com.yeshmishak.app.dev` | `com.yeshmishak.app.staging` | `com.yeshmishak.app` |
| **Display name** | יש משחק Dev | יש משחק Staging | יש משחק |
| **Frontend URL** | `http://localhost:5173` | `https://staging-yesh-mishak.vercel.app` | `https://yesh-mishak.vercel.app` |

---

## 3. Server Strategy

Each environment uses a separate backend deployment:

| Environment | Backend URL | Database |
| :--- | :--- | :--- |
| Development | `http://localhost:8000` (local) | Dev Supabase or local database |
| Staging | Staging Railway deployment | Staging Supabase project |
| Production | Production Railway deployment | Production Supabase project |

Rules:

1. Development can use a local backend for fast iteration.
2. Staging must use a separate staging backend deployment, not the production backend.
3. Production must use the production backend deployment.
4. Staging and production must not share databases.
5. Development may use a local database or a dev-only Supabase project.

---

## 4. Supabase Strategy

Each environment should use a separate Supabase project:

| Environment | Supabase Project | Purpose |
| :--- | :--- | :--- |
| Development | Dev or local Supabase | Safe experimentation, throwaway data |
| Staging | Staging Supabase project | Pre-release validation with production-like schema |
| Production | Production Supabase project | Real user data |

Rules:

1. Schema changes must be tested in staging before production.
2. Manual dashboard changes should be avoided. If made, they must be documented and converted into migrations.
3. The Supabase service role key must never be exposed to the frontend or mobile app.
4. The Supabase anon key is the only key the frontend should use.
5. Each environment's Supabase URL and anon key are set via environment variables.

---

## 5. Firebase / Push Notification Strategy

Each environment should use a separate Firebase app or project configuration:

| Environment | Firebase Config | Push Tokens |
| :--- | :--- | :--- |
| Development | Dev Firebase project/app | Dev tokens only |
| Staging | Staging Firebase project/app | Staging tokens only |
| Production | Production Firebase project/app | Production tokens only |

Rules:

1. Push notification tokens must not be mixed across environments.
2. Test pushes must never reach production users.
3. Each environment uses its own `google-services.json` (Android) and `GoogleService-Info.plist` (iOS).
4. The backend's `FIREBASE_SERVICE_ACCOUNT_JSON` must match the environment's Firebase project.
5. VAPID keys (for web push) are environment-specific.

---

## 6. Mobile App Identifiers

Different app identifiers per environment allow all three builds to be installed side-by-side on the same device. This prevents confusion during testing and avoids accidental use of a dev or staging build as if it were production.

### 6.1 Android

| Environment | applicationId | Display Name |
| :--- | :--- | :--- |
| Development | `com.yeshmishak.app.dev` | יש משחק Dev |
| Staging | `com.yeshmishak.app.staging` | יש משחק Staging |
| Production | `com.yeshmishak.app` | יש משחק |

The production `applicationId` (`com.yeshmishak.app`) was approved in ISSUE-182.

### 6.2 iOS

| Environment | Bundle Identifier | Display Name |
| :--- | :--- | :--- |
| Development | `com.yeshmishak.app.dev` | יש משחק Dev |
| Staging | `com.yeshmishak.app.staging` | יש משחק Staging |
| Production | `com.yeshmishak.app` | יש משחק |

The production Bundle Identifier (`com.yeshmishak.app`) was approved in ISSUE-183.

### 6.3 Identifier Rationale

- Suffixed identifiers (`.dev`, `.staging`) allow side-by-side installation on the same device.
- Production has no suffix - it is the canonical app identity.
- Display names include the environment label so testers can visually distinguish builds.
- Each identifier gets its own push notification token registration, preventing cross-environment token contamination.

---

## 7. Environment Switching

Environment selection happens at build time, not at runtime.

### 7.1 Build-Time Selection

The app uses Vite environment files to inject the correct service URLs and keys:

| File | Purpose |
| :--- | :--- |
| `.env.development` | Used by `npm run dev` and development builds |
| `.env.staging` | Used by staging builds |
| `.env.production` | Used by production builds |

Example build commands (future implementation):

```
npm run build                   # production (default)
npm run build:staging           # staging
npm run build:development       # development
```

For Capacitor native builds, the same environment files apply because Capacitor bundles the Vite-built `dist/` output into the native app.

### 7.2 Existing Environment Files

The project already has environment file templates:

**Frontend:**
- `frontend/.env.example` - development template (points to `localhost:8000`)
- `frontend/.env.staging.example` - staging template

**Backend:**
- `backend/.env.example` - development template (local CORS origins)
- `backend/.env.staging.example` - staging template (staging Supabase, staging CORS origins)

### 7.3 Environment Variables

Each environment file should define:

| Variable | Purpose | Example (production) |
| :--- | :--- | :--- |
| `VITE_API_URL` | Backend API base URL | `https://yesh-mishak-api.railway.app` |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth client ID | (environment-specific) |
| `VITE_FIREBASE_API_KEY` | Firebase API key | (environment-specific) |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain | (environment-specific) |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID | (environment-specific) |
| `VITE_FIREBASE_STORAGE_BUCKET` | Firebase storage bucket | (environment-specific) |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase messaging sender | (environment-specific) |
| `VITE_FIREBASE_APP_ID` | Firebase app ID | (environment-specific) |
| `VITE_FIREBASE_VAPID_KEY` | Web push VAPID key | (environment-specific) |

Backend environment variables:

| Variable | Purpose |
| :--- | :--- |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (backend only, never in frontend) |
| `JWT_SECRET` | JWT signing secret |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `FIREBASE_PROJECT_ID` | Firebase project ID |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase service account credentials (backend only) |
| `CORS_ORIGINS` | Allowed CORS origins for the environment |

### 7.4 No Runtime Environment Switch

There is no in-app toggle for switching environments. This is intentional:

- Runtime switches risk production users accidentally connecting to staging services.
- Build-time selection ensures each binary is locked to exactly one environment.
- Testers who need multiple environments install separate builds (made possible by distinct app identifiers).

---

## 8. What Must Never Be Shared Across Environments

| Resource | Rule |
| :--- | :--- |
| Database | Each environment must use its own database. Staging and production must never share a database. |
| Supabase service role key | Must never appear in frontend or mobile code. Backend only. |
| JWT signing secret | Each environment must use its own secret. A compromised dev secret must not grant access to production. |
| Firebase service account | Each environment must use its own service account credentials. |
| Push notification tokens | Tokens registered in one environment must not receive pushes from another. |
| User data | Production user data must not be copied to staging or dev without explicit anonymization. |
| Google OAuth credentials | Each environment should use its own OAuth client with appropriate redirect URIs. |

---

## 9. Release Safety Rules

### 9.1 Pre-Release Checklist

Before any production release:

1. Verify the build uses `.env.production` (not `.env.staging` or `.env.development`).
2. Verify `VITE_API_URL` points to the production backend.
3. Verify Firebase config matches the production Firebase project.
4. Verify the app identifier is `com.yeshmishak.app` (no `.dev` or `.staging` suffix).
5. Verify the display name is "יש משחק" (no Dev or Staging label).
6. Verify CORS origins on the production backend include the correct production frontend URL and Capacitor origin (`https://localhost`).

### 9.2 Hard Rules

1. **Production builds must never point to staging or dev services.** A production APK/IPA connecting to a staging backend would show test data to real users.
2. **Dev/staging builds must never point to production services.** A staging build connecting to the production backend risks corrupting real user data.
3. **Never commit `.env` files containing real secrets.** Only `.env.example` and `.env.staging.example` templates (with placeholder values) are committed.
4. **Never ship a build with debug logging enabled to production.** Debug logs may expose tokens, user data, or internal state.
5. **Signing keys are environment-specific.** Debug signing keys must not be used for production releases.

### 9.3 Contamination Prevention

| Scenario | Prevention |
| :--- | :--- |
| Staging build shipped to Play Store / App Store | App identifier check: production is `com.yeshmishak.app`, staging is `com.yeshmishak.app.staging`. Store listing is tied to the production identifier. |
| Production build pointing to staging API | Pre-release checklist step 2. CI can validate `VITE_API_URL` matches expected production URL. |
| Push tokens mixed across environments | Separate Firebase projects per environment. Separate token registration endpoints if needed. |
| Staging database contains production data | Policy: never copy production data to staging without anonymization. |

---

## 10. CORS Configuration Per Environment

The backend's `CORS_ORIGINS` must include the correct origins for each environment:

| Environment | Required CORS Origins |
| :--- | :--- |
| Development | `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000` |
| Staging | `https://staging-yesh-mishak.vercel.app`, `http://localhost:5173` (for local testing against staging API) |
| Production | `https://yesh-mishak.vercel.app`, `https://localhost` (Capacitor WebView origin) |

The Capacitor WebView origin (`https://localhost`) must be added to the production `CORS_ORIGINS` before the mobile app can call the production backend. This is tracked as active blocker B-04 in `docs/epic-03-completion-review.md`.

---

## 11. Future Implementation Notes

This document defines the strategy. The following implementation work is required in separate issues:

| Item | Status |
| :--- | :--- |
| Create `.env.production.example` template | Not yet done |
| Add build scripts (`build:staging`, `build:development`) | Not yet done |
| Configure Capacitor flavor/scheme per environment | Not yet done (requires Android product flavors and iOS build schemes) |
| Create staging Supabase project | Not yet done |
| Create dev/staging Firebase projects | Not yet done |
| Add CI validation for environment variables in production builds | Not yet done |
| Add `https://localhost` to production CORS origins | Not yet done (blocker B-04) |

---

## 12. Summary

The mobile environment strategy uses three isolated environments (development, staging, production) with build-time selection. Each environment has its own backend, Supabase project, Firebase configuration, and mobile app identifier. No runtime environment switch exists. Production isolation is enforced through separate identifiers, separate service credentials, and pre-release validation.
