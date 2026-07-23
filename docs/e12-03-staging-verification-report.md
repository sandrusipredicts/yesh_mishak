# E12-03 Staging Environment Verification Report

## Objective
Operationally verify that the staging environment is correctly configured, deployable, isolated from production, and capable of supporting end-to-end testing.

## Current State: No Staging Environment Exists
After inspecting the repository (`docs/environment-inventory.md`), configuration files (`.env.staging.example`), and live endpoints, I have determined that **no operational staging environment exists**.

### Evidence
- **Frontend:** Requests to `https://staging-yesh-mishak.vercel.app/` return a `404 Not Found` with the `DEPLOYMENT_NOT_FOUND` error from Vercel.
- **Backend:** Requests to `https://yesh-mishak-api-staging.railway.app/` return the default "Home of the Railway API" ASCII art rather than our FastAPI `{"status": "ok"}` payload. The backend application has not been successfully deployed to this domain.
- **Configuration:** Staging variables are mocked in `.env.staging.example` files, but active deployment workflows targeting staging do not exist in `.github/workflows/`.

---

## Staging Dependency Matrix

| Component          | Staging resource | Production resource | Isolated? | Verified? | Evidence |
| ------------------ | ---------------- | ------------------- | --------- | --------- | -------- |
| Frontend           | `staging-yesh-mishak.vercel.app` (Missing) | `yesh-mishak.vercel.app` | N/A | **No** | Vercel 404 DEPLOYMENT_NOT_FOUND |
| Backend            | `yesh-mishak-api-staging.railway.app` (Empty) | `yesh-mishak-api.railway.app` | N/A | **No** | Returns Railway ASCII art proxy |
| Database           | Missing | Production Supabase | N/A | **No** | Requires new Supabase project |
| Storage            | Missing | Production Supabase Storage | N/A | **No** | Requires new Supabase project |
| Authentication     | Missing | Production Google OAuth | N/A | **No** | Requires new GCP Web Client IDs |
| Push notifications | Missing | Production Firebase FCM | N/A | **No** | Requires new Firebase project |
| Scheduled jobs     | Missing | Production Cron | N/A | **No** | Backend container not running |
| Monitoring         | Missing | Production Sentry (`yesh-mishak`) | N/A | **No** | Cannot verify without environment |
| Deep links         | Missing | Production `.well-known` config | N/A | **No** | Depends on frontend deployment |

---

## Minimum Architecture Required
To proceed with staging validation, a fully isolated parallel infrastructure must be established. The following minimum architecture must be deployed by the project owner:

1. **Vercel Frontend (Staging Project):** A new project connected to the repository configured to build the `staging` branch (or preview branches) and host it at a stable URL.
2. **Railway Backend (Staging Service):** A new Railway service explicitly running the backend codebase with isolated secrets.
3. **Supabase (Staging Project):** A completely separate Supabase instance containing the identical schema as production, but distinct `SUPABASE_URL` and keys.
4. **Firebase (Staging Project):** A `yesh-mishak-staging` Firebase project to ensure test push tokens never mix with production FCM routing.
5. **Google Cloud Console (Staging Client ID):** A distinct OAuth Web Client ID authorized for the staging frontend JavaScript origin and redirect callbacks.

---

## Owner Actions and Secrets Required
This requires dashboard access held exclusively by DevOps Owners. The owner must manually:

1. **Supabase:** Provision a new Supabase project (`yesh-mishak-staging`). Execute `backend/schema.sql` to initialize it. Extract `SUPABASE_URL`, anon key, and `SUPABASE_SERVICE_ROLE_KEY`.
2. **Firebase:** Create a new project. Generate a service account JSON and public SDK client keys.
3. **Google Cloud:** Create a new Web Application OAuth client ID. Add the staging Vercel domain to **Authorized JavaScript origins**.
4. **Vercel:** Create a new Vercel project or assign environment variables to the Preview environment containing `VITE_GOOGLE_CLIENT_ID`, `VITE_FIREBASE_*`, and `VITE_API_URL` (pointing to the Railway URL).
5. **Railway:** Create a new service. Assign `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_CLIENT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`, and generate a distinct `JWT_SECRET`.
6. **Sentry:** Add `SENTRY_DSN` and set `SENTRY_ENVIRONMENT=staging` to all configs.

---

## Follow-up Issues Created
Placeholder issues tracking the infrastructure gaps:

- **[E12-03A] Provision Staging Database and Cloud Resources:** Create staging Supabase, Firebase, and Google OAuth projects to physically isolate environments.
- **[E12-03B] Configure Staging Railway Backend:** Deploy the backend application and inject isolated staging secrets.
- **[E12-03C] Configure Staging Vercel Frontend:** Deploy the frontend and configure CORS and API routing.

> [!WARNING]
> E12-03 cannot proceed past Phase 1. The issue is currently **blocked** pending the owner actions above. No automated testing or verification can be executed.
