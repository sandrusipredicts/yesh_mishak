# Staging Environment Setup

## 1. Purpose

The staging environment is used to test changes before they reach Production. It provides a safe, isolated replica of the production stack where developers can validate features, database migrations, configuration changes, and notification flows without risking production data or user experience.

Staging must be fully isolated from Production. It must never share a database, Firebase project, or OAuth credentials with the production environment.

## 2. Current Staging Status

**Status: PREPARED / WAITING FOR EXTERNAL DASHBOARD SETUP**

Repository-level preparation is complete:
- Environment variable templates exist for frontend and backend staging.
- Setup instructions and verification checklists are documented.
- The staging strategy is approved (ISSUE-113).

External dashboard provisioning is required before staging goes live:
- Vercel staging project/environment is not yet created.
- Railway staging service is not yet created.
- Supabase staging project is not yet created.
- Firebase staging project is not yet created.
- Google OAuth staging client is not yet created.

## 3. Target Staging Architecture

```
Developer pushes to staging branch
        |
        v
+------------------+       +--------------------+
| Vercel Staging   | ----> | Railway Staging     |
| (Frontend)       |       | (Backend API)       |
| staging.yesh-    |       | yesh-mishak-api-    |
|  mishak.vercel.  |       |  staging.railway.   |
|  app             |       |  app                |
+------------------+       +--------------------+
                                   |
                    +--------------+--------------+
                    |              |              |
                    v              v              v
            +------------+  +-----------+  +------------+
            | Supabase   |  | Firebase  |  | Google     |
            | Staging    |  | Staging   |  | OAuth      |
            | Project    |  | Project   |  | Staging    |
            +------------+  +-----------+  | Client     |
                                           +------------+
```

Key isolation rules:
- **Separate frontend**: Vercel staging deployment pointing to staging backend.
- **Separate backend**: Railway staging service with staging environment variables.
- **Separate database**: Dedicated Supabase staging project.
- **Separate Firebase/FCM**: Dedicated Firebase staging project to prevent notification spam to production users.
- **Separate Google OAuth**: Staging OAuth client with staging-specific authorized origins.
- **Synthetic test data only**: No production PII is ever copied into staging.

## 4. Frontend Staging Setup

### Expected Staging Frontend URL
`https://staging-yesh-mishak.vercel.app` (or Vercel's default preview subdomain for the staging branch).

### Vercel Project/Environment Setup Steps
1. In the Vercel dashboard, open the `yesh-mishak` project (or create a dedicated staging project).
2. Go to **Settings > Domains** and optionally add a staging subdomain.
3. Go to **Settings > Environment Variables**.
4. Add all variables from `frontend/.env.staging.example` under the **Preview** or **Staging** environment scope.
5. Go to **Settings > Git** and configure the staging branch (`staging`) as the deployment trigger for the staging environment.

### Build Command
```bash
cd frontend && npm install && npm run build
```

### Required Staging Frontend Environment Variables
See `frontend/.env.staging.example` for the full list. Key variables:

| Variable | Purpose |
| :--- | :--- |
| `VITE_API_URL` | Points to the staging backend API URL |
| `VITE_GOOGLE_CLIENT_ID` | Staging Google OAuth client ID |
| `VITE_FIREBASE_API_KEY` | Staging Firebase API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Staging Firebase auth domain |
| `VITE_FIREBASE_PROJECT_ID` | Staging Firebase project ID |
| `VITE_FIREBASE_STORAGE_BUCKET` | Staging Firebase storage bucket |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Staging Firebase sender ID |
| `VITE_FIREBASE_APP_ID` | Staging Firebase app ID |
| `VITE_FIREBASE_VAPID_KEY` | Staging Firebase VAPID key for web push |

### How Frontend Staging Points to Backend Staging
`VITE_API_URL` must be set to the staging backend URL (e.g. `https://yesh-mishak-api-staging.railway.app`). The frontend Axios client reads this at build time to determine the API base URL.

### Verification Steps
1. Staging site loads without console errors.
2. Login page renders with Google OAuth button.
3. Map renders and is interactive.
4. Network requests go to the staging backend URL, not production.

## 5. Backend Staging Setup

### Expected Staging Backend URL
`https://yesh-mishak-api-staging.railway.app` (or Railway's default service domain).

### Railway Service/Environment Setup Steps
1. In the Railway dashboard, create a new service named `yesh-mishak-staging` (in the same or a separate project).
2. Connect it to the repository and set the root directory to `backend/`.
3. Railway auto-detects the Python/Nixpacks build.
4. Set the start command (see below).
5. Add all environment variables from `backend/.env.staging.example` in the Railway service settings.
6. Deploy the `staging` branch.

### Start Command
```bash
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

### Required Staging Backend Environment Variables
See `backend/.env.staging.example` for the full list. Key variables:

| Variable | Purpose | Secret? |
| :--- | :--- | :--- |
| `SUPABASE_URL` | Staging Supabase project URL | No |
| `SUPABASE_KEY` | Staging Supabase anon key | Yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Staging Supabase service role key | Yes |
| `JWT_SECRET` | Staging JWT signing secret | Yes |
| `JWT_ALGORITHM` | JWT algorithm (HS256) | No |
| `JWT_EXPIRE_MINUTES` | Token expiration | No |
| `GOOGLE_CLIENT_ID` | Staging Google OAuth client ID | No |
| `FIREBASE_PROJECT_ID` | Staging Firebase project ID | No |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Staging Firebase service account | Yes |
| `FIREBASE_SERVICE_ACCOUNT_FILE` | Alternative to JSON env var | Yes |
| `CORS_ORIGINS` | Staging frontend URLs | No |

### CORS Rules for Staging Frontend
`CORS_ORIGINS` must include the staging frontend URL and local development URLs:
```
https://staging-yesh-mishak.vercel.app,http://localhost:5173,http://127.0.0.1:5173
```

### Verification Steps
1. `GET /` returns a 200 health check response.
2. `GET /docs` loads the Swagger/OpenAPI documentation page.
3. Auth endpoints respond (register, login, Google login).
4. Database queries resolve without connection errors.

## 6. Supabase Staging Setup

### Setup Steps
1. **Create a separate Supabase project** named `yesh-mishak-staging` in the Supabase dashboard.
2. **Apply schema/migrations**: Run the same migration scripts used in production against the staging database. If using Supabase CLI: `supabase db push --db-url <staging-db-url>`.
3. **Configure RLS**: Verify that Row Level Security policies match production. Test that unauthorized reads/writes are blocked.
4. **Create test users**: Insert synthetic test accounts (e.g. `user1@staging.local`, `admin1@staging.local`). Do not use real email addresses.
5. **Seed test data**: Populate 10-15 mock sports fields in distinct cities and pre-configured games in various states.

### Security Rules
- **Never use the production service-role key in staging.**
- Staging `SUPABASE_URL` and `SUPABASE_KEY` must point to the staging project.
- Staging `SUPABASE_SERVICE_ROLE_KEY` must belong to the staging project.

### Verification Checklist
- [ ] Staging Supabase project exists and is accessible.
- [ ] Schema matches production (tables, columns, indexes).
- [ ] RLS policies are active and tested.
- [ ] Test users exist and can authenticate.
- [ ] Test fields and games are seeded.
- [ ] Production credentials are NOT configured anywhere in staging.

## 7. Firebase / FCM Staging Setup

### Setup Steps
1. **Create a separate Firebase project** named `yesh-mishak-staging` in the Firebase Console.
2. **Add a web app** to the staging Firebase project and copy the SDK config values.
3. **Configure VAPID key**: Go to **Cloud Messaging > Web configuration** and generate a VAPID key pair.
4. **Generate service account JSON**: Go to **Project Settings > Service Accounts > Generate new private key**. This JSON is used as `FIREBASE_SERVICE_ACCOUNT_JSON` in the backend.
5. **Update frontend env vars**: Set all `VITE_FIREBASE_*` variables to the staging Firebase project values.
6. **Update backend env vars**: Set `FIREBASE_PROJECT_ID` and `FIREBASE_SERVICE_ACCOUNT_JSON` to staging values.

### Push Notification Safety
- Staging push tokens are registered against the staging Firebase project. They are completely separate from production tokens.
- The staging backend reads push tokens from the staging Supabase database, which only contains synthetic test device tokens.
- **Result**: Staging notifications can never reach production users because the staging backend has no access to production push tokens or production Firebase credentials.

### Verification
- [ ] Staging Firebase project exists.
- [ ] Frontend SDK config matches staging project.
- [ ] Backend service account JSON matches staging project.
- [ ] Test push notification is received only on staging test devices.
- [ ] No production device tokens exist in the staging database.

## 8. Google OAuth Staging Setup

### Setup Steps
1. **Go to Google Cloud Console** > APIs & Services > Credentials.
2. **Create a new OAuth 2.0 Client ID** (or add staging origins to the existing client).
3. **Add authorized JavaScript origins**:
   - `https://staging-yesh-mishak.vercel.app`
   - `http://localhost:5173` (for local development against staging)
   - `http://localhost:3000` (if applicable)
4. **Copy the Client ID** and set it as:
   - `VITE_GOOGLE_CLIENT_ID` in the frontend staging environment.
   - `GOOGLE_CLIENT_ID` in the backend staging environment.
5. **Verify**: The backend `GOOGLE_CLIENT_ID` must match what the frontend sends as the Google OAuth audience.

### Common Misconfiguration Risks
- **Origin mismatch**: If the staging frontend URL is not in the authorized JavaScript origins, Google login will fail silently or show a popup error.
- **Client ID mismatch**: If the frontend and backend use different Google Client IDs, token verification will fail with 401.
- **Redirect confusion**: If staging and production share the same OAuth client without proper origin separation, login callbacks may redirect to the wrong environment.

## 9. Environment Variables

### Frontend Staging Environment Variables

| Variable | Purpose | Secret? | Example Placeholder | Set Locally | Set in Staging Dashboard | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `VITE_API_URL` | Backend API base URL | No | `https://yesh-mishak-api-staging.railway.app` | `frontend/.env` | Vercel env vars | Must point to staging backend |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth client ID | No | `your-staging-google-client-id.apps.googleusercontent.com` | `frontend/.env` | Vercel env vars | Must match backend `GOOGLE_CLIENT_ID` |
| `VITE_FIREBASE_API_KEY` | Firebase SDK API key | No | `your-staging-firebase-api-key` | `frontend/.env` | Vercel env vars | From staging Firebase project |
| `VITE_FIREBASE_AUTH_DOMAIN` | Firebase auth domain | No | `your-staging-project.firebaseapp.com` | `frontend/.env` | Vercel env vars | From staging Firebase project |
| `VITE_FIREBASE_PROJECT_ID` | Firebase project ID | No | `your-staging-project-id` | `frontend/.env` | Vercel env vars | From staging Firebase project |
| `VITE_FIREBASE_STORAGE_BUCKET` | Firebase storage bucket | No | `your-staging-project.firebasestorage.app` | `frontend/.env` | Vercel env vars | From staging Firebase project |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Firebase Cloud Messaging sender ID | No | `your-staging-sender-id` | `frontend/.env` | Vercel env vars | From staging Firebase project |
| `VITE_FIREBASE_APP_ID` | Firebase app ID | No | `your-staging-app-id` | `frontend/.env` | Vercel env vars | From staging Firebase project |
| `VITE_FIREBASE_VAPID_KEY` | Web push VAPID key | No | `your-staging-vapid-key` | `frontend/.env` | Vercel env vars | From staging Firebase Cloud Messaging settings |

### Backend Staging Environment Variables

| Variable | Purpose | Secret? | Example Placeholder | Set Locally | Set in Staging Dashboard | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SUPABASE_URL` | Supabase project URL | No | `https://your-staging-project.supabase.co` | `backend/.env` | Railway env vars | Must point to staging Supabase |
| `SUPABASE_KEY` | Supabase anon/public key | Yes | `your-staging-supabase-anon-key` | `backend/.env` | Railway env vars | From staging Supabase project |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | Yes | `your-staging-service-role-key` | `backend/.env` | Railway env vars | Never use production key |
| `JWT_SECRET` | JWT signing secret | Yes | `replace-with-strong-staging-secret` | `backend/.env` | Railway env vars | Must be unique to staging |
| `JWT_ALGORITHM` | JWT signing algorithm | No | `HS256` | `backend/.env` | Railway env vars | Same as production |
| `JWT_EXPIRE_MINUTES` | Token expiration in minutes | No | `10080` | `backend/.env` | Railway env vars | Same as production |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | No | `your-staging-google-client-id.apps.googleusercontent.com` | `backend/.env` | Railway env vars | Must match frontend `VITE_GOOGLE_CLIENT_ID` |
| `FIREBASE_PROJECT_ID` | Firebase project ID | No | `your-staging-project-id` | `backend/.env` | Railway env vars | From staging Firebase project |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Firebase service account credentials | Yes | `{"type":"service_account","project_id":"your-staging-project-id"}` | `backend/.env` | Railway env vars | From staging Firebase service account |
| `FIREBASE_SERVICE_ACCOUNT_FILE` | Path to service account file (alternative) | Yes | `staging-service-account.json` | `backend/.env` | Railway env vars | Alternative to JSON env var |
| `CORS_ORIGINS` | Allowed CORS origins | No | `https://staging-yesh-mishak.vercel.app,http://localhost:5173,http://127.0.0.1:5173` | `backend/.env` | Railway env vars | Must include staging frontend URL |

## 10. Manual External Setup Steps

These steps require dashboard access and cannot be automated from the repository.

### Vercel (Frontend Staging)
1. Log in to the Vercel dashboard.
2. Open the `yesh-mishak` project (or create a new project for staging).
3. Go to **Settings > Environment Variables**.
4. Add all variables from `frontend/.env.staging.example` scoped to the **Preview** environment (or a custom **Staging** environment).
5. Go to **Settings > Git** and configure deployments from the `staging` branch.
6. Optionally add a custom domain alias (e.g. `staging-yesh-mishak.vercel.app`).
7. Trigger a deployment and verify the staging site loads.

### Railway (Backend Staging)
1. Log in to the Railway dashboard.
2. Create a new service named `yesh-mishak-staging`.
3. Connect it to the GitHub repository.
4. Set the root directory to `backend/`.
5. Set the start command: `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`.
6. Add all environment variables from `backend/.env.staging.example`.
7. Configure the service to deploy from the `staging` branch.
8. Deploy and verify `GET /` returns 200.

### Supabase (Staging Database)
1. Log in to the Supabase dashboard.
2. Create a new project named `yesh-mishak-staging`.
3. Copy the project URL, anon key, and service role key.
4. Apply database schema (run migrations or use `supabase db push`).
5. Enable Row Level Security on all tables.
6. Seed test data (synthetic users, fields, games).
7. Verify the backend can connect and query data.

### Firebase (Staging Notifications)
1. Log in to the Firebase Console.
2. Create a new project named `yesh-mishak-staging`.
3. Add a web app and copy the SDK configuration values.
4. Go to **Cloud Messaging > Web configuration** and generate a VAPID key pair.
5. Go to **Project Settings > Service Accounts** and generate a private key JSON.
6. Set all Firebase-related environment variables in both frontend and backend staging configs.
7. Test push notification delivery on a staging test device.

### Google Cloud OAuth (Staging Auth)
1. Log in to the Google Cloud Console.
2. Go to **APIs & Services > Credentials**.
3. Create a new OAuth 2.0 Client ID (or add staging origins to the existing client).
4. Add authorized JavaScript origins for the staging frontend URL.
5. Copy the client ID and set it in both `VITE_GOOGLE_CLIENT_ID` (frontend) and `GOOGLE_CLIENT_ID` (backend).
6. Verify Google login works on the staging frontend.

## 11. Staging Verification Flow

After all external services are provisioned:

1. **Deploy frontend staging**: Push to the `staging` branch or trigger a Vercel deployment.
2. **Deploy backend staging**: Push to the `staging` branch or trigger a Railway deployment.
3. **Confirm environment variables**: Verify all staging env vars are set in Vercel and Railway dashboards.
4. **Confirm backend health**: `GET /` returns 200. `GET /docs` loads Swagger UI.
5. **Confirm frontend loads**: Staging site renders without errors. Check browser console for warnings.
6. **Confirm login**: Google OAuth login completes successfully on staging.
7. **Confirm fields load**: Map renders and displays seeded test fields.
8. **Confirm game creation**: Create a game on a test field. Verify it appears in the field detail.
9. **Confirm join/leave**: Join and leave a game. Verify participant count updates.
10. **Confirm admin protection**: Non-admin users cannot access admin endpoints.
11. **Confirm notifications use staging config only**: Trigger a test push notification. Verify it arrives on a staging test device only. Confirm no production tokens are contacted.
12. **Confirm logs are clean**: Check Railway staging logs for exceptions, tracebacks, or connection errors.

See [docs/staging-smoke-test-checklist.md](staging-smoke-test-checklist.md) for the full checklist.

## 12. Rollback / Disable Staging

If staging needs to be disabled or reset:

1. **Disable staging frontend**: Remove the staging environment from Vercel or delete the staging project. The staging URL will stop responding.
2. **Disable staging backend**: Stop or delete the Railway staging service.
3. **Rotate staging secrets**: Regenerate `JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, and `FIREBASE_SERVICE_ACCOUNT_JSON` for staging. This invalidates all active staging sessions and tokens.
4. **Disable staging Firebase keys**: Revoke the staging Firebase service account key in the Firebase Console.
5. **Disable staging OAuth client**: Delete or disable the staging OAuth client ID in Google Cloud Console.
6. **Preserve logs**: If a staging incident occurred, export Railway and Vercel logs before deleting the staging services.

## 13. Known Gaps / Blockers

| Gap | Status | Blocked By |
| :--- | :--- | :--- |
| Vercel staging project not created | Waiting | Requires Vercel dashboard access |
| Railway staging service not created | Waiting | Requires Railway dashboard access |
| Supabase staging project not created | Waiting | Requires Supabase dashboard access |
| Firebase staging project not created | Waiting | Requires Firebase Console access |
| Google OAuth staging client not created | Waiting | Requires Google Cloud Console access |
| Staging database seed script not written | Future issue (ISSUE-131) | Depends on staging Supabase project |
| GitHub `staging` branch protection rules | Future issue (ISSUE-132) | Requires repository admin access |

## 14. Final Result

| Item | Status |
| :--- | :--- |
| Staging setup document exists | YES |
| Frontend staging prepared | PARTIAL (env template ready, Vercel setup pending) |
| Backend staging prepared | PARTIAL (env template ready, Railway setup pending) |
| Separate DB required | YES |
| Separate Firebase required | YES |
| Separate OAuth required | YES |
| Manual dashboard steps documented | YES |
| Runtime behavior changed | NO |
| DB schema changed | NO |
| Staging live | NO (waiting for external dashboard setup) |
