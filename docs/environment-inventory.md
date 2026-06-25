# Environment Inventory Playbook

## 1. Purpose
* **Core Purpose**: This environment inventory serves as the formal source of truth for all runtime configurations, infrastructure environments, and third-party integrations in the `yesh_mishak` project.
* **Objective**: It establishes clear boundaries and security segregation rules to prevent mixing configurations or credentials across the local development, production, and future staging environments.

## 2. Environment Summary

| Environment Name | Status | Purpose | Frontend Host / Provider | Backend Host / Provider | Database / Supabase Project | Auth / OAuth Configuration | Firebase / FCM Configuration | Owner | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Local** | **Active** | Developer coding, debugging, and unit testing. | Localhost (`http://localhost:5173`) | Localhost (`http://localhost:8000`) | Shared local development database OR shared Supabase project | Google Cloud Console credentials (local origins) | FCM Client / Local Application Default Credentials (ADC) | Individual Developer | Stored locally in untracked `.env` files. |
| **Production** | **Active** | Live application serving actual users. | Vercel (`https://yesh-mishak.vercel.app`) | Railway (`https://yesh-mishak-api.railway.app` or similar) | Production Supabase Database | Google Cloud Console production Client credentials | Production FCM key dispatching real notifications | DevOps Owner / Lead Architect | Configured via Railway and Vercel dashboards. |
| **Future Staging** | **Planned** | Pre-production validation and E2E testing. | *Planned* Vercel Preview/Staging URL | *Planned* Railway Staging service | *Planned* Dedicated Staging Supabase DB | *Planned* Google OAuth Staging Client credentials | *Planned* Staging FCM project | *Planned* DevOps Owner | Non-existent; currently simulated via preview builds. |

## 3. Local Environment
* **Purpose**: Local feature development and test execution.
* **Who uses it**: All software engineers working on frontend or backend repositories.
* **Frontend Local URL(s)**: `http://localhost:5173` (Vite dev server)
* **Backend Local URL(s)**: `http://localhost:8000` (FastAPI / Uvicorn ASGI server)
* **Common Ports**:
  * Frontend: `5173` (defaults to `5174`, `5175` if port is occupied)
  * Backend: `8000`
* **Install Commands**:
  * Frontend: `npm install`
  * Backend: `python -m venv .venv` -> `source .venv/bin/activate` -> `pip install -r requirements.txt`
* **Run Commands**:
  * Frontend: `npm run dev`
  * Backend: `python -m uvicorn app.main:app --reload`
* **Build Commands**:
  * Frontend: `npm run build`
  * Backend: Nixpacks locally (optional)
* **Required Frontend Env Vars**: `VITE_API_URL`, `VITE_GOOGLE_CLIENT_ID`, `VITE_FIREBASE_*` SDK keys.
* **Required Backend Env Vars**: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_CLIENT_ID`, `JWT_SECRET`, `CORS_ORIGINS`, `FIREBASE_PROJECT_ID`.
* **Supabase Usage**: Direct queries to database via Supabase Python SDK client.
* **Google OAuth Local Origins**: `http://localhost:5173` (JavaScript Origin), `http://localhost:8000` (Redirect Origin).
* **Firebase Local Behavior**: Receives mock token registrations or registers real user push tokens if FCM keys are configured in local `.env`. Supports Application Default Credentials (ADC) via local `gcloud` login.
* **CORS/Local Origin Requirements**: Backend `CORS_ORIGINS` must include `http://localhost:5173` to accept local browser API hits.
* **Known Local Pitfalls**:
  * Committing `.env` config changes to git (resolved by verifying `.gitignore`).
  * Running backend without activating the virtual environment, leading to global package contamination.
* **Verification Checklist**:
  - [ ] Node modules and pip requirements installed successfully.
  - [ ] Backend API responds at `http://localhost:8000/`.
  - [ ] Frontend loads and successfully queries local API.

## 4. Production Environment
* **Purpose**: Live environment for end users.
* **Frontend Host & URL**: Hosted on **Vercel** at `https://yesh-mishak.vercel.app` (or custom production domain).
* **Backend Host & URL**: Hosted on **Railway** at a dedicated Nixpacks subdomain (e.g. `https://yesh-mishak-api.railway.app`).
* **Supabase Project**: Production database instance hosting `users`, `fields`, `games`, and associated triggers.
* **Firebase/FCM Project**: Production Firebase application (`yesh-mishak`) used to distribute push alerts.
* **Google OAuth Production Origins**:
  * Authorized Javascript Origin: `https://yesh-mishak.vercel.app`
  * Authorized Redirect Origin: `https://yesh-mishak-api.railway.app/auth/google/callback` (or direct client token parsing).
* **Required Frontend Env Vars**: `VITE_API_URL` pointing to backend gateway, verified client-side Firebase keys.
* **Required Backend Env Vars**: Server-side secrets (`SUPABASE_SERVICE_ROLE_KEY`, production `JWT_SECRET`, and `FIREBASE_SERVICE_ACCOUNT_JSON`).
* **Secret Storage Location**: Configured only inside Railway and Vercel console settings; never committed.
* **Deployment Trigger**: Automatic build triggers on merge to the `main` branch.
* **Rollback Owner/Process**: Handled by DevOps Owner via the Vercel/Railway console redeploy options (promoting previous stable deployments).
* **Access Control Notes**: Production databases and cloud consoles are restricted to designated project owners. Developers have no direct database write access.
* **Monitoring/Logging**: Manual inspections of live Railway container logs, Vercel build logs, and Supabase database graphs.
* **Known Production Risks**:
  * Single database instance risk (no staging barrier).
  * Administrative access accounts showing unmasked PII.
* **Verification Checklist**:
  - [ ] Production API health returns `{"status": "ok"}`.
  - [ ] Frontend loads correctly and Google login functions.

## 5. Future Staging Environment
* **Intended Purpose**: Sandbox environment duplicating production data configurations to run manual tests, regression cycles, and E2E Playwright validation before production releases.
* **Current Status**: **Planned / Not implemented** (Staging does not exist. Preview branches build on Vercel, but point to production backend database/services).
* **Recommended Frontend Host**: Vercel (using separate Staging project or preview branch configuration).
* **Recommended Backend Host**: Railway (using a separate Staging service).
* **Recommended Supabase Strategy**: Create a dedicated Staging Supabase project, duplicating schema SQL definitions, to isolate database read/writes.
* **Recommended Firebase Strategy**: Create a separate Firebase project (e.g. `yesh-mishak-staging`) to ensure staging push tokens do not mix with production user FCM tokens.
* **Recommended Google OAuth Setup**: Define a separate Google Cloud credentials client containing JavaScript origins set to the staging frontend URLs.
* **Recommended Env Var Separation**: Configure all staging credentials inside dedicated staging Vercel/Railway projects.
* **Required Differences from Production**:
  * Short TTLs on caches.
  * Verbose logging allowed (with strict PII masking).
  * Staging VITE configs point exclusively to the staging API subdomain.
* **Required Differences from Local**:
  * Deployed on public preview domains rather than localhost.
  * Uses dedicated containerized database and auth services rather than mock variables.
* **Open Decisions / Needs Confirmation**:
  * Naming conventions for staging domains.
  * Resource quotas allocated for staging Railway/Vercel services.
* **Minimum Setup Checklist**:
  - [ ] Create staging project in Google GCP, Supabase, and Firebase consoles.
  - [ ] Create staging Railway backend service and Vercel frontend project.
  - [ ] Map staging environment variables in the console settings.
  - [ ] Run initial SQL schemas in staging Supabase.

## 6. Environment Variable Inventory by Environment

| Variable Name | Local (Dev) | Production | Future Staging | Frontend / Backend | Secret? | Purpose | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **VITE_API_URL** | `http://localhost:8000` | `https://api.production.com` | `https://api.staging.com` | Frontend | No | Points to the backend API. | Core client gateway. |
| **VITE_API_BASE_URL** | `http://localhost:8000` | `https://api.production.com` | `https://api.staging.com` | Frontend | No | Fallback gateway URL. | Deprecated; point to VITE_API_URL. |
| **VITE_SUPABASE_URL** | *Not Used / Planned* | *Not Used / Planned* | *Not Used / Planned* | Frontend | No | Supabase Client URL. | Frontend calls API, not DB. |
| **VITE_SUPABASE_ANON_KEY** | *Not Used / Planned* | *Not Used / Planned* | *Not Used / Planned* | Frontend | No | Supabase Client Anon Key. | Frontend calls API, not DB. |
| **VITE_GOOGLE_CLIENT_ID** | `dev-google-id` | `prod-google-id` | `staging-google-id` | Frontend | No | Client ID for Google login init. | Must match GCP console. |
| **VITE_FIREBASE_API_KEY** | `dev-fcm-key` | `prod-fcm-key` | `staging-fcm-key` | Frontend | No | Firebase public client Web SDK key. | Obtained from Firebase Web App. |
| **VITE_FIREBASE_AUTH_DOMAIN**| `dev.firebaseapp.com` | `prod.firebaseapp.com` | `staging.firebaseapp.com` | Frontend | No | Firebase client auth domain. | Matches Firebase project. |
| **VITE_FIREBASE_PROJECT_ID** | `yesh-mishak` | `yesh-mishak` | `yesh-mishak-staging` | Frontend | No | Firebase project ID. | Matches Firebase project. |
| **VITE_FIREBASE_STORAGE_BUCKET**| `dev.appspot.com` | `prod.appspot.com` | `staging.appspot.com` | Frontend | No | Firebase storage bucket. | Matches Firebase project. |
| **VITE_FIREBASE_MESSAGING_SENDER_ID**| `dev-sender-id` | `prod-sender-id` | `staging-sender-id` | Frontend | No | Firebase client sender ID. | Matches Firebase project. |
| **VITE_FIREBASE_APP_ID** | `dev-app-id` | `prod-app-id` | `staging-app-id` | Frontend | No | Firebase client application ID. | Matches Firebase project. |
| **VITE_FIREBASE_VAPID_KEY** | `dev-vapid-key` | `prod-vapid-key` | `staging-vapid-key` | Frontend | No | FCM client push key registration. | Matches Firebase project. |
| **VITE_SHOW_TEST_PUSH** | `true` | `false` | `true` | Frontend | No | Toggles diagnostic push buttons. | Always `false` in production. |
| **SUPABASE_URL** | `https://xyz.supabase.co` | `https://prod.supabase.co` | `https://staging.supabase.co`| Backend | No | API URL for DB connection. | Checked in `db/supabase.py`. |
| **SUPABASE_KEY** | `dev-anon-key` | `prod-anon-key` | `staging-anon-key` | Backend | No | Anon key used for standard queries. | Equivalent to `SUPABASE_ANON_KEY`. |
| **SUPABASE_SERVICE_ROLE_KEY**| `dev-service-role` | `prod-service-role` | `staging-service-role` | Backend | **Yes** | Bypass RLS key for DB triggers. | **Do not commit / expose**. |
| **JWT_SECRET** | `dev-jwt-secret` | `prod-jwt-secret` | `staging-jwt-secret` | Backend | **Yes** | Secret for signing API access JWTs. | **Rotate if exposed**. |
| **GOOGLE_CLIENT_ID** | `dev-google-id` | `prod-google-id` | `staging-google-id` | Backend | No | Server-side Google ID validator. | Must match frontend client ID. |
| **FIREBASE_SERVICE_ACCOUNT_JSON**| `dev-fcm-json-string` | `prod-fcm-json-string`| `staging-fcm-json` | Backend | **Yes** | Credentials JSON for FCM gateway. | Single-line JSON representation. |
| **FRONTEND_URL** | `http://localhost:5173` | `https://yesh-mishak.vercel.app`| `https://staging.vercel.app`| Backend | No | Primary frontend client origin. | Points to client URL. |
| **CORS_ORIGINS** | `http://localhost:5173` | `https://yesh-mishak.vercel.app`| `https://staging.vercel.app`| Backend | No | Allowed CORS origins for backend. | Comma-separated client URLs. |

## 7. External Service Inventory

### Supabase
* **Environments Used**: Local (connects to Supabase development DB) and Production (connects to Supabase production DB).
* **Data / Config Handled**: User profiles, credentials metadata, game states, playground coordinates, report queues, and row permissions.
* **PII Storage**: **YES** (Stores emails, phone numbers, Google subs, usernames).
* **Required keys**: `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`.
* **Owner/Access**: Lead Architect / Database Administrator.
* **Environment Separation Risk**: High. Sharing a single database project between local developers and production users will contaminate live app data. Always provision separate project instances.

### Google OAuth
* **Environments Used**: Local (dev callback ports) and Production (production client validation).
* **Data / Config Handled**: Authentication payloads and user identity tokens.
* **PII Storage**: Indirect (reads email, profile pictures, and names from Google profile).
* **Required keys**: `GOOGLE_CLIENT_ID`.
* **Owner/Access**: DevOps Owner.
* **Environment Separation Risk**: Low. GCP allows defining multiple client credentials keys under one project, separating redirect URIs strictly by origin.

### Firebase / FCM
* **Environments Used**: Local (optional) and Production.
* **Data / Config Handled**: Web push token registrations and push notifications dispatching.
* **PII Storage**: **YES** (Sends notification text containing player names and field names; logs device push tokens).
* **Required keys**: `FIREBASE_PROJECT_ID`, `FIREBASE_SERVICE_ACCOUNT_JSON`, client Web SDK keys.
* **Owner/Access**: DevOps Owner.
* **Environment Separation Risk**: Medium. Using one Firebase project for staging and production leads to staging tests pushing notifications to real users. Always split projects.

### Vercel
* **Environments Used**: Production and Preview (simulated staging).
* **Data / Config Handled**: Frontend static asset compilation and routing rewrites.
* **PII Storage**: No.
* **Required keys**: Vercel deployment credentials (CLI).
* **Owner/Access**: Frontend Tech Lead / DevOps Owner.
* **Environment Separation Risk**: Low. Vercel automatically isolates preview branch deployments from the production domain.

### Railway
* **Environments Used**: Production.
* **Data / Config Handled**: Backend container orchestration and server logs.
* **PII Storage**: Indirect (backend logs contain user IDs, but avoid contact details).
* **Required keys**: Railway deploy tokens (CLI).
* **Owner/Access**: Backend Tech Lead / DevOps Owner.
* **Environment Separation Risk**: Low. Separate services can be created for staging vs production under one project.

### OpenStreetMap (OSM) Tiles
* **Environments Used**: Local and Production.
* **Data / Config Handled**: Browser map tile HTTP queries.
* **PII Storage**: Indirect (user browsers request tiles directly from OSM servers, exposing user IP addresses and coordinates).
* **Required keys**: None (public server tiles).
* **Owner/Access**: External (OpenStreetMap Foundation).
* **Environment Separation Risk**: None.

## 8. Environment Separation Rules
* **No Key Sharing**: Never use production service-role keys or database credentials in local development settings.
* **No Committed Secrets**: Never check in real `.env` configurations or service account keys to git repository history.
* **Backend Secrets Segregation**: Never put backend-only secrets (like `SUPABASE_SERVICE_ROLE_KEY` or `JWT_SECRET`) inside `VITE_` prefixed variables or Vercel configurations.
* **Isolated Databases**: Local, staging, and production environments must utilize completely isolated databases. Staging testing must never target the production database.
* **Isolated Push notifications**: Staging runs must utilize a separate Firebase project to prevent test notifications from routing to production push device tokens.
* **OAuth origin strictness**: Ensure Google Client redirect URIs are locked to specific domain origins per environment.
* **CORS containment**: Never use `*` (wildcards) for `CORS_ORIGINS` in production settings; explicitly list the client domain.

## 9. Environment Promotion Flow
The planned deployment pipeline when updates are introduced:
1. **Local Development**: Code written and tested locally by developers.
2. **Pull Request**: Commits pushed to feature branches. Vercel generates a preview deployment. Backend tests are run in CI.
3. **Staging Validation (Planned Gap)**: Changes merged to a `staging` branch. Deployed to Staging Vercel/Railway environments connected to the staging database. Complete manual verification and E2E Playwright tests executed here.
   * *Current Gap*: Staging does not exist. Preview builds run on Vercel but hook into the production database.
4. **Production Deployment**: Changes merged to `main` branch. Automate builds deploy to production Railway/Vercel hosts.
5. **Post-Production Verification**: Perform the Post-Deployment Verification checklist.

## 10. Access Control by Environment

| Environment | Who Should Have Access | Deployment Access | Secret Access | Database Access | Admin App Access | Notes / Needs Confirmation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Local** | Individual Developer | Local Dev Only | Local `.env` | Local DB / Dev DB | Local Admin View | Developer controls their local workstation environment. |
| **Production** | End Users (app), DevOps/Owners (dashboard) | DevOps / Owners | Owners Only (railway/vercel console) | Owners Only (direct write blocked for dev) | Verified Admins | Strict production access control rules apply. |
| **Future Staging**| QA Engineers, Developers | Developers / QA | Developers / QA | Developers / QA | Staging Admin View | Credentials shared among dev/test team via vault. |

## 11. Environment Risks and Gaps
* **No Staging Environment**: The lack of a true staging environment means pre-production testing is performed on preview builds connecting directly to the production database. Schema changes are run on production database before validation.
* **Shared Firebase/Supabase Risk**: Using one Firebase project means test push tokens mix with live tokens.
* **Implicit Deployments**: Merges to `main` instantly trigger production deploys. If a merge occurs accidentally, production is updated without final gating.

## 12. Recommended Follow-Up Issues
1. **ISSUE-126: Create dedicated staging environment (P0)**: Provision staging projects in Vercel, Railway, Supabase, and Google Cloud, separating domains.
2. **ISSUE-127: Add env validation at startup (P1)**: Add backend startup validators in `config.py` checking key sizes and formats.
3. **ISSUE-128: Split production and staging Firebase/FCM instances (P1)**: Isolate messaging tokens.
4. **ISSUE-129: Document dashboard owners (P2)**: Maintain an access inventory of who holds administrator console logins.

## 13. Final Result
* **Environment inventory exists**: YES
* **Local documented**: YES
* **Production documented**: YES
* **Future staging documented**: YES
* **Unknown details marked clearly**: YES
* **Runtime behavior changed**: NO
* **DB schema changed**: NO
