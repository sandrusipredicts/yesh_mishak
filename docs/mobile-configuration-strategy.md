# Mobile Configuration Strategy

**ISSUE:** 185
**Date:** 2026-06-30
**Status:** Approved strategy reference
**Scope:** Documentation only - no implementation, no secrets
**Dependency:** ISSUE-184 (mobile environment strategy)

---

## 1. Purpose

This document defines how configuration is managed across mobile environments so that API URLs, feature flags, environment variables, and build variables are not hardcoded or manually changed in source code.

This strategy applies to:

- Frontend (React + Vite + Capacitor) builds
- Backend (FastAPI) configuration
- Supabase connection configuration
- Firebase / push notification configuration
- Feature flag management

This document complements `docs/mobile-environment-strategy.md` (ISSUE-184), which defines the three environments (development, staging, production) and their isolation rules.

---

## 2. Configuration Source

Environment-specific files and CI/CD variables are the source of truth for all configuration.

| Source | Environments | Committed to Git |
| :--- | :--- | :--- |
| `.env.development` or `.env.local` | Local development | No |
| `.env.staging` | Staging builds | No |
| `.env.production` | Production builds | No |
| `.env.example` | Development template with placeholders | Yes |
| `.env.staging.example` | Staging template with placeholders | Yes |
| CI/CD environment variables | Staging and production deployments | No (stored in Vercel/Railway) |

Rules:

1. Real `.env` files must not be committed. The `.gitignore` already excludes `.env`.
2. Only placeholder examples (`.env.example`, `.env.staging.example`) may be committed.
3. CI/CD platforms (Vercel for frontend, Railway for backend) inject production and staging values at build/deploy time.
4. Developers create their own `.env` or `.env.local` from `.env.example`.

### 2.1 Existing Environment Templates

The project already has these committed templates:

**Frontend (`frontend/`):**
- `.env.example` - points `VITE_API_URL` to `http://localhost:8000` with placeholder Firebase values
- `.env.staging.example` - points to staging API/Firebase with placeholder values

**Backend (`backend/`):**
- `.env.example` - local development defaults with placeholder Supabase/Firebase values
- `.env.staging.example` - staging defaults with placeholder values

---

## 3. Frontend/Mobile Variable Exposure

### 3.1 Allowed Variables (VITE_ prefix)

Only variables intended for the frontend/mobile may use the `VITE_` prefix. These are embedded in the built JavaScript bundle and are visible to anyone who inspects the app.

| Variable | Purpose | Status |
| :--- | :--- | :--- |
| `VITE_API_URL` | Backend API base URL | **Canonical** |
| `VITE_API_BASE_URL` | Backend API base URL (legacy name) | Backward-compatible fallback only |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `VITE_FIREBASE_API_KEY` | Firebase API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID |
| `VITE_FIREBASE_STORAGE_BUCKET` | Firebase storage bucket |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase messaging sender ID |
| `VITE_FIREBASE_APP_ID` | Firebase app ID |
| `VITE_FIREBASE_VAPID_KEY` | Web push VAPID key |
| `VITE_APP_ENV` | Environment marker (future) |
| `VITE_SHOW_TEST_PUSH` | Dev-only: show test push button |
| `VITE_FEATURE_*` | Feature flags (future) |

### 3.2 Never Expose to Frontend/Mobile

These values must never appear in frontend/mobile code, environment files with the `VITE_` prefix, or the built JavaScript bundle:

| Secret | Where It Belongs |
| :--- | :--- |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend only (`backend/.env`) |
| Database passwords | Backend/infrastructure only |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Backend only |
| `FIREBASE_SERVICE_ACCOUNT_FILE` | Backend only |
| `JWT_SECRET` | Backend only |
| Railway/Vercel deploy tokens | CI/CD only |
| Apple signing credentials | CI/CD or local keychain only |
| Google Play signing key | CI/CD or secure storage only |
| Admin API secrets | Backend only |

### 3.3 Current State

The frontend source code does not contain any service role keys, database passwords, or backend secrets. All sensitive operations use backend endpoints. The Supabase service role key is only accessed in `backend/app/db/supabase.py` and never exposed to the frontend.

---

## 4. API URL Strategy

### 4.1 How It Works Today

The API base URL is read from environment variables in `frontend/src/api/client.js`:

```
const apiBaseUrl =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL
```

All API calls go through this centralized axios client. No component hardcodes a backend URL.

### 4.2 Canonical Variable

**`VITE_API_URL` is the canonical variable.** All new `.env` files, documentation, and CI/CD configuration should use `VITE_API_URL`.

`VITE_API_BASE_URL` is a backward-compatible fallback only. The API client reads it as a fallback if `VITE_API_URL` is not set, but it should not be used in new configuration. Removal of the fallback should happen in a separate implementation issue to avoid breaking existing developer setups.

### 4.3 Rules

1. The API base URL must come from `VITE_API_URL`. The fallback `VITE_API_BASE_URL` exists only for backward compatibility.
2. Components must not hardcode backend URLs.
3. The centralized API client (`frontend/src/api/client.js`) is the single point of configuration.
4. Development points to `http://localhost:8000` (from `.env.example`).
5. Staging points to the staging Railway deployment.
6. Production points to the production Railway deployment.

### 4.4 Current Audit Result

No hardcoded backend URLs were found in `frontend/src/`. The API client correctly reads from environment variables. This is compliant.

---

## 5. Supabase Configuration Strategy

### 5.1 Frontend

The frontend does not directly use a Supabase client. All database operations go through the backend API. This is the correct architecture - the frontend never needs Supabase credentials.

If a future feature requires a frontend Supabase client (e.g., real-time subscriptions), it must use:

| Variable | Allowed in Frontend |
| :--- | :--- |
| `VITE_SUPABASE_URL` | Yes |
| `VITE_SUPABASE_ANON_KEY` | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Never |

### 5.2 Backend

The backend reads Supabase configuration from environment variables via `backend/app/core/config.py`:

- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_KEY` - Supabase anon key (used for regular client)
- `SUPABASE_SERVICE_ROLE_KEY` - service role key (used for admin operations)

These are read from `.env` files or CI/CD variables. No Supabase URLs are hardcoded in backend source code.

### 5.3 Rules

1. Dev, staging, and production must use separate Supabase projects (per ISSUE-184).
2. The service role key must only exist in backend environments.
3. Frontend/mobile must never access the service role key.

---

## 6. Firebase / Push Configuration Strategy

### 6.1 How It Works Today

Firebase frontend config is read from environment variables in `frontend/src/firebaseMessaging.js`:

```
const FIREBASE_CONFIG = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
}
```

The code validates that required keys are present before initializing Firebase (`assertFirebaseConfig()`).

### 6.2 Backend Firebase Config

The backend reads Firebase credentials from:

- `FIREBASE_PROJECT_ID` - project identifier
- `FIREBASE_SERVICE_ACCOUNT_JSON` - service account credentials (JSON string)
- `FIREBASE_SERVICE_ACCOUNT_FILE` - path to service account file (alternative)

These are backend-only and never exposed to the frontend.

### 6.3 Rules

1. Firebase frontend config must come from `VITE_FIREBASE_*` environment variables.
2. Firebase service account credentials must never be bundled into frontend/mobile builds.
3. Dev, staging, and production must use separate Firebase projects (per ISSUE-184).
4. Push notification tokens must not be mixed across environments.
5. Test push controls are already guarded: `SHOW_TEST_PUSH` requires both `import.meta.env.DEV` and `VITE_SHOW_TEST_PUSH === 'true'`.

---

## 7. Feature Flag Strategy

### 7.1 Current State

The codebase uses two environment-aware flags today:

| Flag | File | Behavior |
| :--- | :--- | :--- |
| `import.meta.env.DEV` (Vite built-in) | `MapPage.jsx:17` | Faster poll interval in dev (1s vs 20s) |
| `SHOW_TEST_PUSH` | `NotificationsModal.jsx:22` | Shows test push button only in dev mode AND when `VITE_SHOW_TEST_PUSH=true` |

Both are safe: they use Vite's built-in `DEV` flag which is `false` in production builds. No feature flags are scattered as hardcoded booleans.

### 7.2 Recommended Pattern

Future feature flags should follow this pattern:

| Variable | Purpose | Default |
| :--- | :--- | :--- |
| `VITE_FEATURE_PUSH_NOTIFICATIONS` | Enable push notification UI | `true` in production |
| `VITE_FEATURE_IN_APP_NOTIFICATIONS` | Enable in-app notification inbox | `true` in production |
| `VITE_FEATURE_MAP_DEBUG_TOOLS` | Enable map debug overlay | `false` in production |
| `VITE_FEATURE_DEV_TEST_CONTROLS` | Enable dev/test UI controls | `false` in production |

### 7.3 Rules

1. Feature flags must be defined as environment variables, not hardcoded booleans.
2. Feature flags should be environment-aware: dev may enable debug features that production disables.
3. Production-dangerous flags (debug tools, test controls) must default to `false`.
4. Dev/test UI must be disabled in production builds.
5. Feature flags should be read from a centralized location, not scattered across components.

---

## 8. Build Variable Strategy

### 8.1 Environment Marker

A `VITE_APP_ENV` variable should identify the build environment at runtime:

| Value | Meaning |
| :--- | :--- |
| `development` | Local development build |
| `staging` | Staging validation build |
| `production` | Production release build |

This is not yet implemented. Vite's built-in `import.meta.env.MODE` serves a similar purpose (`development` vs `production`) but does not distinguish staging.

### 8.2 Build Commands

Future build scripts should make environment selection explicit:

```
npm run build                    # production (default)
npm run build:staging            # staging
npm run build:development        # development
npm run cap:sync:development     # Capacitor sync for dev
npm run cap:sync:staging         # Capacitor sync for staging
npm run cap:sync:production      # Capacitor sync for production
```

These scripts would set the correct `.env` file and `VITE_APP_ENV` value.

### 8.3 Rules

1. Build-time variables decide which environment is used.
2. Runtime user-facing environment switch is forbidden (per ISSUE-184).
3. Each build is locked to exactly one environment.
4. Capacitor syncs must use the same environment as the web build.

---

## 9. Centralized Config Layer

### 9.1 Current State

No centralized config module exists at `frontend/src/config/`. Configuration is read directly via `import.meta.env` in individual files:

- `frontend/src/api/client.js` - reads `VITE_API_URL`
- `frontend/src/firebaseMessaging.js` - reads `VITE_FIREBASE_*`
- `frontend/src/components/LoginPage.jsx` - reads `VITE_GOOGLE_CLIENT_ID`
- `frontend/src/components/NotificationsModal.jsx` - reads `VITE_SHOW_TEST_PUSH`
- `frontend/src/pages/MapPage.jsx` - reads `import.meta.env.DEV`

### 9.2 Recommended Future Module

A centralized config module (e.g., `frontend/src/config/env.js`) should:

1. Read all environment variables once at startup.
2. Validate that required values are present.
3. Expose typed/normalized config to the rest of the app.
4. Fail fast when required config is missing (rather than failing at first use).
5. Expose helper booleans:
   - `isDevelopment`
   - `isStaging`
   - `isProduction`

This module is not yet implemented. It should be created in a separate implementation issue.

---

## 10. Production Build Safety

### 10.1 Pre-Release Verification

Before any production mobile build, verify:

| Check | Expected Value |
| :--- | :--- |
| `VITE_APP_ENV` | `production` |
| `VITE_API_URL` | Production backend URL |
| Supabase project | Production project |
| Firebase project | Production project |
| App identifier | `com.yeshmishak.app` (no `.dev` or `.staging` suffix) |
| Display name | יש משחק (no Dev or Staging label) |
| Dev feature flags | All disabled or `false` |
| No localhost URLs in config | Verified |
| No service role keys in bundle | Verified |

### 10.2 Automated Verification (Future)

CI should validate production builds:

1. Grep the built bundle for `localhost` or `127.0.0.1` - fail if found.
2. Verify `VITE_API_URL` matches the expected production URL.
3. Verify no `.dev` or `.staging` suffix in app identifier.
4. Verify `VITE_APP_ENV` is `production`.

---

## 11. Hardcoded Configuration Audit

Audit performed 2026-06-30 on `main` branch.

### 11.1 Frontend Source (`frontend/src/`)

| Pattern | Found | Classification |
| :--- | :--- | :--- |
| Hardcoded `localhost` URLs | None | Compliant |
| Hardcoded `127.0.0.1` | None | Compliant |
| Hardcoded backend URLs | None | Compliant |
| Hardcoded Supabase URLs | None | Compliant |
| Hardcoded Firebase config values | None | Compliant - all read from `VITE_FIREBASE_*` env vars |
| Service role keys | None | Compliant |
| Hardcoded feature flags | None | Compliant - uses `import.meta.env.DEV` (Vite built-in) |

### 11.2 Backend Source (`backend/app/`)

| Pattern | Found | Classification |
| :--- | :--- | :--- |
| Hardcoded `localhost` in CORS defaults | `config.py:14` and `main.py:93-96` | Acceptable - these are development fallback defaults; production overrides via `CORS_ORIGINS` env var |
| Supabase service role key usage | Multiple files in `db/supabase.py`, `api/admin.py`, `routers/notifications.py`, `routers/games.py` | Acceptable - backend-only, read from env var, never exposed to frontend |
| Hardcoded backend/Supabase/Firebase URLs | None | Compliant - all read from env vars via `config.py` |

### 11.3 Environment Templates

| File | Classification |
| :--- | :--- |
| `frontend/.env.example` | Acceptable - placeholder values, `localhost:8000` is correct for dev |
| `frontend/.env.staging.example` | Acceptable - placeholder values with `your-staging-*` markers |
| `backend/.env.example` | Acceptable - placeholder values, localhost CORS defaults |
| `backend/.env.staging.example` | Acceptable - placeholder values with `your-staging-*` markers |

### 11.4 Audit Verdict

No risky hardcoded configuration was found. All environment-specific values are read from environment variables. The localhost defaults in backend CORS configuration are development fallbacks that are overridden in staging/production by the `CORS_ORIGINS` environment variable.

**Audit result: PASS - no remediation required.**

---

## 12. Summary

Configuration management follows these principles:

1. **Environment variables are the source of truth.** No hardcoded URLs, keys, or project IDs in source code.
2. **Build-time selection, not runtime switching.** Each build is locked to one environment.
3. **Secrets stay on the backend.** Service role keys, JWT secrets, and service accounts never reach the frontend.
4. **Feature flags are environment-aware.** Dev features default to off in production.
5. **Templates, not real configs, are committed.** `.env.example` files with placeholders are in Git; real `.env` files are not.
6. **Three isolated environments.** Development, staging, and production each have their own services (per ISSUE-184).
