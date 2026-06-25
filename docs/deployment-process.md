# Deployment Process Playbook

## 1. Purpose
* **Core Purpose**: This document serves as the absolute source of truth for building, verifying, deploying, and rolling back the `yesh_mishak` application.
* **Intended Audience**: Any developer, sysadmin, or operator tasked with deploying updates to the staging or production environments. A new developer must be able to successfully build and deploy the entire system safely by following these steps.

## 2. System Overview
The `yesh_mishak` application is split into a static frontend SPA and a Python REST API backend, backed by database and notification services:
* **Frontend**: React / Vite Single Page Application (SPA), compiled into static assets and hosted on **Vercel**.
* **Backend**: FastAPI (Python), utilizing Uvicorn as the ASGI web server, built automatically via Nixpacks and hosted on **Railway**.
* **Database & Authentication**: Supabase (PostgreSQL with Row-Level Security and integrated Google Auth).
* **Push Notifications**: Firebase Cloud Messaging (FCM) for web push delivery.
* **Local Development Ports**:
  * Frontend (Vite Dev Server): `http://localhost:5173`
  * Backend (FastAPI Server): `http://localhost:8000`

## 3. Deployment Ownership
* **Deployment Execution**: Designated developers or DevOps administrators.
* **PR Reviews**: Every deployment PR must be reviewed and approved by at least one other engineer before merge.
* **Environment Variables Ownership**: The Lead Architect/DevOps Owner manages production environment keys in hosting provider consoles.
* **Rollback Authorization**: The Incident Lead (IL) or Technical Lead has the authority to command an immediate rollback during a failed release.
* **Production Approvals**: Deploying to production requires approval from the Product Owner (PO) or Technical Lead.

## 4. Branching and Release Rules
* **No Direct Deploys from Local**: Never build and deploy directly to production from a developer's local machine. All releases must originate from the repository branch.
* **Main Branch Rule**: The `main` branch represents the stable production-ready code. Commits are merged to `main` only via Pull Requests.
* **PR Workflow**: Code changes -> Feature branch -> Pull Request -> CI checks (linting, tests) -> Review approval -> Merge to `main`.
* **Deployment Freeze**: A deployment freeze is immediately active during a security incident (SEV-0/1/2) or when the production environment is verified as degraded.

## 5. Frontend Deployment
* **Code Location**: `frontend/`
* **Install Command**: `npm install`
* **Build Command**: `npm run build`
* **Preview Command**: `npm run preview` (runs local server on built static files)
* **Hosting Provider**: **Vercel**
* **Deployment Process**:
  1. Automated: Vercel project integrations trigger builds automatically when a Pull Request is opened (Preview environment) or when changes are merged to the `main` branch (Production environment).
  2. Manual (Vercel CLI):
     ```bash
     cd frontend
     # For staging preview
     vercel --build
     # For production deploy
     vercel --prod
     ```
* **Post-Deploy Frontend Checks**:
  1. Open the deployment URL.
  2. Confirm the main map page loads without rendering errors.
  3. Inspect the browser console for failed resources or JS exceptions.
* **Common Failure Modes**:
  * *Vite build errors*: Syntax or type check issues. Check build logs in Vercel console.
  * *Missing VITE_ variables*: Vercel settings lack keys. Check Vercel project settings -> Environment Variables.
* **Rollback Steps**:
  1. Open Vercel project dashboard.
  2. Go to the `Deployments` tab.
  3. Locate the last known stable deployment.
  4. Click the three dots and select `Redeploy` -> `Promote to Production`.

## 6. Backend Deployment
* **Code Location**: `backend/`
* **Runtime Requirements**: Python 3.11+, pip dependencies in `requirements.txt`.
* **Install Command**: `pip install -r requirements.txt` (local dev)
* **Start Command**: `python -m uvicorn app.main:app` (local dev)
* **Hosting Provider**: **Railway**
* **Deployment Process**:
  1. Automated: Railway Nixpacks builder automatically detects Python requirements, compiles dependencies, and exposes the app. Triggered on merge to `main`.
  2. Manual (Railway CLI):
     ```bash
     cd backend
     railway up
     ```
* **Post-Deploy Backend Checks**:
  1. Invoke the API health check endpoint: `GET https://[backend-domain]/`.
  2. Verify JSON response: `{"status": "ok"}`.
  3. Open `GET https://[backend-domain]/docs` to verify Swagger documentation is accessible.
* **Common Failure Modes**:
  * *Nixpacks build failure*: Pip dependency version conflicts or incorrect Python version settings. Check Railway logs.
  * *Supabase Connection Error*: Backend cannot connect to database due to incorrect `SUPABASE_URL` or `SUPABASE_KEY`. Check Railway container startup logs.
* **Rollback Steps**:
  1. Open Railway project console.
  2. Go to the backend service deployment list.
  3. Find the last known stable generation.
  4. Select `Redeploy` to revert to that deployment artifact.

## 7. Environment Variables

| Variable Name | Area | Required | Purpose | Secret? | Example Format | Local Storage | Production Config | Rotation Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SUPABASE_URL** | Backend | Yes | Base endpoint of the Supabase project. | No | `https://xyz.supabase.co` | `backend/.env` | Railway Env | Rotate only if database instance changes. |
| **SUPABASE_KEY** | Backend | Yes | Supabase anon/public key for client initialization. | No | `eyJhbGciOi...` | `backend/.env` | Railway Env | Rotate if client-side abuse is detected. |
| **SUPABASE_SERVICE_ROLE_KEY** | Backend | Yes | Supabase master key (bypasses RLS). | **Yes** | `eyJhbGciOi...` | `backend/.env` | Railway Env | **Rotate immediately** on leak or staff offboarding. |
| **GOOGLE_CLIENT_ID** | Backend & Frontend | Yes | Google OAuth Client ID for identity verification. | No | `123-abc.apps.googleusercontent.com` | `.env` | Railway & Vercel Env | Update if client configuration changes on GCP. |
| **JWT_SECRET** | Backend | Yes | Cryptographic secret for signing API access tokens. | **Yes** | `random_secure_hex_32` | `backend/.env` | Railway Env | **Rotate immediately** if compromised (invalidates sessions). |
| **CORS_ORIGINS** | Backend | Yes | Allowed client origins for FastAPI middleware. | No | `https://yesh-mishak.vercel.app` | `backend/.env` | Railway Env | Update when client domain changes. |
| **JWT_ALGORITHM** | Backend | No | Algorithm for JWT tokens (defaults to HS256). | No | `HS256` | `backend/.env` | Railway Env | Do not change unless migrating algorithm. |
| **JWT_EXPIRE_MINUTES** | Backend | No | JWT token validity lifespan (defaults to 10080). | No | `10080` | `backend/.env` | Railway Env | Shorten to harden token security. |
| **FIREBASE_PROJECT_ID** | Backend & Frontend | Yes | Firebase project identifier. | No | `yesh-mishak` | `.env` | Railway & Vercel Env | Matches Firebase configuration name. |
| **FIREBASE_SERVICE_ACCOUNT_JSON** | Backend | Yes (Alternative) | Raw Firebase Service account private key string. | **Yes** | `{"type": "service_account", ...}` | `backend/.env` | Railway Env | Rotate via Google Cloud IAM console on leak. |
| **FIREBASE_SERVICE_ACCOUNT_FILE** | Backend | Yes (Alternative) | Path to service account file. | **Yes** | `/secrets/firebase-key.json` | `backend/.env` | Local filesystem | Avoid in production env; use JSON string instead. |
| **DISABLE_GAME_CREATED_NOTIFICATIONS** | Backend | No | Disables creation alert push notifications. | No | `False` | `backend/.env` | Railway Env | Toggle to `True` during incident spam. |
| **AUTH_USER_CACHE_TTL_SECONDS** | Backend | No | In-memory cache TTL for user validation. | No | `300` | `backend/.env` | Railway Env | Lower value increases DB read load. |
| **VITE_API_URL** | Frontend | Yes | Endpoint gateway of the backend FastAPI. | No | `https://api.domain.com` | `frontend/.env` | Vercel Env | Points to production Railway backend. |
| **VITE_API_BASE_URL** | Frontend | No | Fallback gateway URL. | No | `https://api.domain.com` | `frontend/.env` | Vercel Env | Point to VITE_API_URL to align. |
| **VITE_GOOGLE_CLIENT_ID** | Frontend | Yes | Google Client ID loaded by OAuth button. | No | `123-abc.apps.googleusercontent.com` | `frontend/.env` | Vercel Env | Match with Google Cloud OAuth console. |
| **VITE_FIREBASE_API_KEY** | Frontend | Yes | Firebase client Web SDK key. | No | `AIzaSy...` | `frontend/.env` | Vercel Env | Match with Firebase Client Web App. |
| **VITE_FIREBASE_AUTH_DOMAIN** | Frontend | Yes | Firebase domain configuration. | No | `domain.firebaseapp.com` | `frontend/.env` | Vercel Env | Match Firebase console. |
| **VITE_FIREBASE_STORAGE_BUCKET** | Frontend | Yes | Firebase storage bucket. | No | `domain.appspot.com` | `frontend/.env` | Vercel Env | Match Firebase console. |
| **VITE_FIREBASE_MESSAGING_SENDER_ID** | Frontend | Yes | Firebase sender ID for push messages. | No | `1029384756` | `frontend/.env` | Vercel Env | Match Firebase console. |
| **VITE_FIREBASE_APP_ID** | Frontend | Yes | Firebase web client app ID. | No | `1:102:web:abc` | `frontend/.env` | Vercel Env | Match Firebase console. |
| **VITE_FIREBASE_VAPID_KEY** | Frontend | Yes | Public Web Push token key. | No | `BPh...` | `frontend/.env` | Vercel Env | Matches Web Push key generated in FCM settings. |
| **VITE_SHOW_TEST_PUSH** | Frontend | No | Toggles visual manual test push buttons. | No | `false` | `frontend/.env` | Vercel Env | Keep `false` in production. |

> [!WARNING]
> Do NOT configure backend-only secrets (such as `SUPABASE_SERVICE_ROLE_KEY`, `JWT_SECRET`, or `FIREBASE_SERVICE_ACCOUNT_JSON`) inside Vercel environment configurations. They will be bundled into public client bundles.

## 8. Database / Supabase Deployment Notes
* **Migrations Location**: Schema SQL declaration is in [schema.sql](file:///c:/Users/orel1/yesh_mishak/backend/schema.sql) and custom patch files are in [backend/migrations/](file:///c:/Users/orel1/yesh_mishak/backend/migrations/).
* **Applying Schema Changes**:
  * Schema additions or migrations must be run manually via the Supabase Dashboard SQL Editor or utilizing the Supabase CLI before deploying backend updates that depend on them.
* **Verifying Database State**:
  * Execute validation queries or run the game data integrity audit tool:
    ```bash
    cd backend
    python scripts/audit_game_data_integrity.py
    ```
* **Database Rollback Policy**:
  * **CAUTION**: Database schema rollbacks must be handled carefully. Application rollbacks are fast, but database changes are stateful and irreversible if data is lost.
  * If a schema update fails, do NOT run blind `DROP TABLE` commands. Apply backwards-compatible migrations or restore a Supabase database backup snapshot.

## 9. Firebase / Push Notification Deployment Notes
* **Config variables**: Ensure all `VITE_FIREBASE_*` variables match the active Firebase project.
* **Service Worker**: The service worker resides in [firebase-messaging-sw.js](file:///c:/Users/orel1/yesh_mishak/frontend/public/firebase-messaging-sw.js).
* **VAPID Key**: The `VITE_FIREBASE_VAPID_KEY` must match the key configured in the FCM Web Configuration settings, otherwise browsers will reject push tokens.
* **Backend Credentials**: FCM private key must be mapped to `FIREBASE_SERVICE_ACCOUNT_JSON` as a single-line string in Railway (remove newlines from the JSON payload when inserting).

## 10. Google Auth Deployment Notes
* **OAuth Configuration**: Set up the client credentials inside Google Cloud Console API & Services credentials panel.
* **Authorized Redirect Domains**:
  * Under Authorized JavaScript Origins, add local dev URLs (`http://localhost:5173`, `http://localhost:8000`) and the production Vercel frontend URL (e.g. `https://yesh-mishak.vercel.app`).
  * Ensure redirect origins match client scopes.
* **Auth Alignment**: If login attempts return `401 Unauthorized` or token verify fails, confirm that the client client ID (`VITE_GOOGLE_CLIENT_ID`) matches the backend client ID (`GOOGLE_CLIENT_ID`).

## 11. Pre-Deployment Checklist
- [ ] **Branch Verified**: You are on the correct release branch (`main` or staging branch).
- [ ] **Clean Working Tree**: Git working tree is clean.
- [ ] **Latest Main Pulled**: Local branch contains latest updates.
- [ ] **PR Approved**: Code changes are merged following peer review.
- [ ] **Build Succeeds**: Static frontend compiles locally (`npm run build`) with no lint errors.
- [ ] **Tests Pass**: Run the Python test suite: `pytest backend/tests/`.
- [ ] **Environment Variables Confirmed**: Production variables are updated in Railway and Vercel.
- [ ] **Secret Scan**: No credentials or private keys are committed in git.
- [ ] **DB Migrations Scheduled**: Schema additions applied in Supabase.
- [ ] **Rollback Plan Verified**: Verified rollback steps for both frontend and backend.

## 12. Post-Deployment Verification Checklist
- [ ] **Frontend Application Loads**: Navigate to frontend host; confirm page renders.
- [ ] **API Endpoint Responds**: Run `GET https://[backend-domain]/` and check `{"status": "ok"}`.
- [ ] **Authentication Works**: Log in with Google Auth; confirm name/avatar loads in header.
- [ ] **Playground Map Renders**: Confirm map is visible and loads fields.
- [ ] **Fields Fetch Successfully**: Check that active playgrounds display correct statuses.
- [ ] **Game Creation Works**: Create a test game at a verified field.
- [ ] **Join/Leave Operations Succeed**: Join the created game, verify count increases, and leave it.
- [ ] **Admin Operations Accessible**: Log in with admin account, open `/admin` views, and confirm reports show.
- [ ] **Test Notifications**: Trigger a notification or check unread count.
- [ ] **Server Log Review**: Check Railway live container logs for 15 minutes post-deploy to confirm no traceback spikes.

## 13. Rollback Procedure

### Frontend Rollback
1. Open the Vercel project dashboard.
2. Select the target project.
3. Click the `Deployments` tab.
4. Locate the last stable deployment ID.
5. Click the option menu (`...`) and select `Redeploy` -> select `Promote to Production`. Vercel instantly routes traffic to the old build.

### Backend Rollback
1. Open the Railway project dashboard.
2. Select the backend app service.
3. Locate the list of prior service generations.
4. Click `Redeploy` on the last working release version. nixpacks loads the previous build.

### Environment Variable Rollback
1. Revert the configuration key values in Vercel/Railway environment settings.
2. Redepoy the latest code build to load the reverted variables.

### Database Rollback
1. Do NOT delete tables.
2. If a migration broke a column, run backwards-compatible SQL queries to add missing fields or restore data.
3. If critical state corruption occurs, restore the Supabase database to the last automatic backup snapshot.

### Feature Rollback
1. Revert the offending commit on local git branch: `git revert [commit_hash]`.
2. Commit, push, and open a rollback PR to merge back into `main`.

### Emergency Rollback
1. Execute both Vercel and Railway instant redeployment steps above.
2. Freeze all deployment pipelines until the root cause is resolved.

## 14. Incident / Failed Deployment Procedure
* **Stop Further Deployments**: Immediately lock down the branch and pause any concurrent PR merges.
* **Assign Owner**: Designate a Technical Investigator (TI) to diagnose the failure.
* **Preserve Log Files**: Capture build logs and active server tracebacks before rolling back.
* **Command Rollback**: If production is broken, trigger the rollback steps immediately.
* **Communicate**: Notify the team using the status templates.
* **Track Remediation**: Open a GitHub issue detailing the cause and remediation. Refer to the [Security Incident Handling Playbook](file:///c:/Users/orel1/yesh_mishak/docs/product-decisions.md#L17461-L17806) if the failure involved data exposure or breaches.

## 15. New Developer Deployment Walkthrough
1. **Clone the Repo**:
   ```bash
   git clone https://github.com/sandrusipredicts/yesh_mishak.git
   cd yesh_mishak
   ```
2. **Install Frontend Dependencies**:
   ```bash
   cd frontend
   npm install
   ```
3. **Configure Local Frontend Environment**:
   * Copy `.env.example` to `.env`.
   * Fill in public client variables.
4. **Install Backend Dependencies**:
   ```bash
   cd ../backend
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
5. **Configure Local Backend Environment**:
   * Copy `.env.example` to `.env`.
   * Fill in Supabase keys and credentials.
6. **Run Backend API locally**:
   ```bash
   python -m uvicorn app.main:app --reload
   ```
7. **Run Frontend Application locally**:
   ```bash
   cd ../frontend
   npm run dev
   ```
8. **Build and Preview Frontend locally**:
   ```bash
   npm run build
   npm run preview
   ```
9. **Deploy**:
   * Create a pull request merging your changes to `main`.
   * Vercel will build and deploy a preview version of the frontend.
   * On merge to `main`, Vercel and Railway will build and deploy the production builds automatically.

## 16. Known Gaps / Needs Confirmation
* **Staging Server Names**: Staging project naming and separate CLI credentials are TBD.
* **Vercel Project Name**: Exact name of Vercel production hosting project is not declared in configuration files.
* **Railway Service Name**: Exact Nixpacks service definition or container memory size parameters are TBD.
* **Deployer Group Members**: The list of developers who possess admin credentials for Railway, Vercel, and Supabase dashboards must be confirmed.
* **Automatic DB migrations**: Whether there is any future CI workflow to automate migrations in Supabase or if they remain strictly manual needs confirmation.

## 17. Final Result
* **Deployment document exists**: YES
* **Frontend deploy documented**: YES
* **Backend deploy documented**: YES
* **Env vars documented**: YES
* **Rollback documented**: YES
* **New developer can follow process**: YES (with documented environment credentials in password vault)
* **Runtime behavior changed**: NO
* **DB schema changed**: NO
