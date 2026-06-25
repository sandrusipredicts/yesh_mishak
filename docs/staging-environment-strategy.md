# Staging Environment Strategy

## 1. Purpose
* **Core Purpose**: This staging environment strategy outlines the official architecture, decisions, and guidelines for implementing and managing a pre-production sandbox environment.
* **Objective**: The staging environment serves as the final validation gate before production release. Isolating staging from production mitigates deployment risk, safeguards customer PII, prevents notification spam, and provides a safe area for testing code, database schema migrations, and configuration updates.
* **Scope**: This is a strategy and decision document; it does not provision infrastructure.

## 2. Current Environment State
* **Local environment status**: Active. Developers run the React frontend locally (`localhost:5173`) and the FastAPI backend locally (`localhost:8000`), using local config files and development databases.
* **Production environment status**: Active. Frontend is hosted on Vercel (`https://yesh-mishak.vercel.app`) and backend on Railway. Both communicate with the production Supabase database/auth and Firebase FCM notification triggers.
* **Staging Availability**: **Not currently implemented**. 
  * *Frontend preview*: Vercel automatically deploys feature branches to preview URLs, but they are configured to talk directly to the production backend database.
  * *Backend staging*: Not implemented. No staging Railway service exists.
  * *Separate staging DB*: Not implemented. No staging Supabase database project exists.
  * *Separate staging Firebase*: Not implemented. No staging FCM application is configured.
  * *Separate staging Google OAuth*: Not implemented.
* **Known gaps (from [docs/environment-inventory.md](file:///c:/Users/orel1/yesh_mishak/docs/environment-inventory.md))**: Pre-production testing is currently conducted on preview builds that reference the live production database, exposing production user tables to staging schema changes and data corruption.

## 3. Decision Summary
* **Staging required**: **YES**. A dedicated staging environment is mandatory before scaling development to prevent data corruption, notification spam, and access bypasses.
* **Recommended staging model**: A completely isolated replica of the production environment, including dedicated Vercel frontend, Railway backend, Supabase DB/Auth, and Firebase FCM projects.
* **Minimum viable staging setup**: 
  1. A staging frontend environment on Vercel pointing to a staging backend.
  2. A staging backend service on Railway pointing to a staging Supabase database.
  3. A dedicated staging database project in Supabase.
* **What can wait**: Multi-region hosting setups, automated performance testing infrastructure, and dedicated staging domains (using default Railway/Vercel preview subdomains is acceptable for MVP).
* **What must be separated**: The database, Firebase push notifications configuration, Google OAuth credentials, and all environment variables. Staging must never share write/read access to production resources.

## 4. Decision Matrix

| Component | Options Considered | Recommended Decision | Reason | Risk if NOT Separated | Cost/Complexity | Follow-up Required? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Frontend** | 1. Share production build.<br>2. Dedicated staging site. | **Dedicated staging site** | Enables testing frontend configurations and custom environment variables without affecting production. | Build regressions or configuration bugs directly impact live users. | Low cost; standard Vercel environment setup. | YES (Configure Vercel project environment). |
| **Backend** | 1. Direct traffic to prod backend.<br>2. Dedicated staging backend service. | **Dedicated staging backend service** | Isolates API endpoints and enables logging of backend staging actions. | Backend crashes or database connection leaks degrade production API performance. | Medium; separate Railway Nixpacks service. | YES (Provision Railway staging service). |
| **Database / Supabase** | 1. Share production DB instance.<br>2. Dedicated staging Supabase project. | **Dedicated staging Supabase project** | Isolates user data and allows testing migrations on a separate database. | **High Risk**: Schema migrations can break production database. Staging tests could corrupt production data. | Medium complexity; Supabase free/developer tier is sufficient. | YES (Create staging Supabase project). |
| **Auth / Google OAuth** | 1. Reuse production client keys.<br>2. Dedicated staging Google client credentials. | **Dedicated staging Google client credentials** | Isolates redirect origins to prevent staging auth redirects from targeting production. | Google OAuth login attempts from preview builds fail or redirect to production. | Low; add a client credential in GCP. | YES (Configure Google OAuth staging client). |
| **Firebase / FCM** | 1. Share production Firebase project.<br>2. Dedicated staging Firebase project. | **Dedicated staging Firebase project** | Prevents staging test dispatches from sending notification alerts to production devices. | Staging test scripts trigger notification spam to active production users. | Low; create Firebase staging project. | YES (Create Firebase staging project). |
| **Environment variables** | 1. Reuse production env keys.<br>2. Completely isolated staging keys. | **Completely isolated staging keys** | Standard practice to ensure staging services never connect to production instances. | Staging services write to production database. | Low; manage via Railway/Vercel settings. | YES (Sync staging variables). |
| **Admin users** | 1. Copy prod admin list.<br>2. Independent staging admins. | **Independent staging admins** | Allows testers to toggle admin status freely on staging without administrative leakage. | Production admin credentials leaked or compromised during staging validations. | Low; database seeding task. | YES (Seed staging admin data). |
| **Test data** | 1. Copy production DB rows.<br>2. Synthetic/test data only. | **Synthetic/test data only** | Complies with GDPR/privacy rules. Ensures no production PII exists in staging. | Production PII leaked to staging logs, developers, or external testing interfaces. | Low; write database seed script. | YES (Write seed data script). |
| **Logs/monitoring** | 1. Share production logs.<br>2. Separated staging log streams. | **Separated staging log streams** | Keeps logs clean and prevents staging failures from contaminating production alerts. | Production alert monitoring triggers false alarms on staging test failures. | Low; standard hosting configuration. | YES (Separate log services). |
| **Deployment flow** | 1. Manual deploys.<br>2. PR merge triggers staging, manual promotion to prod. | **PR merge triggers staging** | Establishes a staging validation gate. Merges to `staging` branch deploy to staging; manual release to `main` deploys to prod. | Accidental commits instantly deployed to production without testing. | Medium; configure GitHub branch rules. | YES (Configure staging branching rules). |

## 5. Frontend Staging Strategy
* **Should frontend staging be separated**: **YES**.
* **Recommended provider setup**: Vercel preview/staging project configuration.
* **Are Vercel preview deployments enough**: No. Standard Vercel preview builds are dynamically created for every PR, which is excellent for visual review, but they must point to a stable pre-production API. We require a dedicated `staging` deployment that maps to a stable staging branch.
* **Required staging URL pattern**: `https://staging.yesh-mishak.vercel.app` (or default Vercel preview subdomain matching `*-staging.vercel.app`).
* **Required environment variable differences**: `VITE_API_URL` must point to the staging backend API url, and all Firebase client SDK config keys must match the staging Firebase project.
* **Frontend checks before production release**:
  1. Build succeeds locally and in Vercel staging deploy with zero errors.
  2. Map loads and renders playground locations.
  3. User profile details show up in the header after login.

## 6. Backend Staging Strategy
* **Should backend staging be separated**: **YES**.
* **Recommended provider setup**: A separate Railway service named `yesh-mishak-staging` running inside the same or a separate Railway project.
* **Railway service setup**: Runs Nixpacks Python container, configured with staging environment variables.
* **Required API URL pattern**: `https://yesh-mishak-api-staging.railway.app` (or default Railway staging domain).
* **Required CORS rules**: `CORS_ORIGINS` must list the staging frontend URLs (e.g. `https://staging.yesh-mishak.vercel.app`).
* **Required environment variable differences**: `SUPABASE_URL` and `SUPABASE_KEY` point to the staging Supabase project, and FCM keys match the staging Firebase instance. `DISABLE_GAME_CREATED_NOTIFICATIONS` is set to `False` (to verify push alerts in staging).
* **Backend checks before production release**:
  1. Swagger API page loads and routes respond.
  2. Database reads/writes resolve without timeouts.
  3. `GET /` health check responds with 200.

## 7. Database / Supabase Staging Strategy
* **Should DB be separated**: **YES**.
* **Recommended Supabase project separation**: A completely separate staging project in Supabase (e.g. `yesh-mishak-staging`).
* **Can staging share production DB**: **NO**. Sharing production databases is strictly forbidden due to data integrity and schema corruption risks.
* **RLS/policy testing**: Database policies must be validated on staging before deployment. Testers should simulate user actions to confirm RLS blocks unauthorized reads/writes.
* **Seed/test data strategy**: A dedicated SQL seed script (`backend/migrations/seed_staging.sql`) will populate the staging database with mock fields and test users.
* **Migration testing strategy**: Run new migrations on the staging database, verify the schema updates successfully, run the automated backend test suite, and check for runtime failures.
* **Risks of sharing production DB**: High risk of accidental data deletion, schema locking during migration updates, and PII leaks to testing environments.

## 8. Firebase / Push Notification Staging Strategy
* **Should Firebase/FCM be separated**: **YES**.
* **Recommended staging Firebase project**: A separate Firebase project (e.g. `yesh-mishak-staging`).
* **Push notification test strategy**: Testers register their devices using staging credentials and trigger test notifications. Verification ensures only staging tokens are contacted.
* **Avoid sending staging notifications to prod users**: Ensuring the staging backend only references the staging Supabase database (which only contains synthetic staging tokens) prevents contacting production FCM tokens.
* **Token separation rules**: Never mix staging and production push tokens in tables. Ensure FCM credentials in env variables are strictly isolated.

## 9. Google OAuth Staging Strategy
* **Should OAuth client be separated**: **YES**.
* **Required authorized JavaScript origins**: Staging frontend URLs (e.g. `https://staging.yesh-mishak.vercel.app`).
* **Required backend audience validation**: The backend `GOOGLE_CLIENT_ID` variable in the staging environment must match the staging OAuth client ID, and Google tokens are verified against it.
* **Risks of mixing configurations**: Authentication callbacks redirecting to the wrong environment, session hijacking vulnerabilities, or login loop failures.

## 10. Environment Variable Separation Strategy
* **Local environment variables**: Managed via local `backend/.env` and `frontend/.env` (untracked in git).
* **Staging environment variables**: Managed via Railway/Vercel staging dashboard panels, pointing exclusively to staging Supabase, Firebase, and Google clients.
* **Production environment variables**: Managed via Railway/Vercel production dashboard panels, pointing to production services.
* **Secret ownership**: Only the Lead Architect/DevOps Owner has dashboard write access for production and staging configurations.
* **Rotation expectations**: Database credentials and JWT secrets must be rotated immediately upon suspected compromise or developer offboarding.
* **Core Rules**:
  1. Never include backend secrets in `VITE_` prefixed variables.
  2. Staging and local environments must never load the production `SUPABASE_SERVICE_ROLE_KEY`.

## 11. Data Strategy for Staging
* **Use synthetic data only**: **YES**. The staging database must only contain synthetic, generated test data.
* **Allow copied production data**: **NO**. Copying production user records, emails, phone numbers, or active game history to staging is forbidden to comply with privacy regulations and avoid credential leakage.
* **PII Rules**: No real emails, phone numbers, or exact residential address coordinates are permitted in the staging environment database.
* **Test Users**: Create pre-defined test accounts (e.g. `user1@staging.local`, `admin1@staging.local`) in the SQL seed script.
* **Test Games & Fields**: Populate staging with 10-15 mock sports fields located in distinct cities and pre-configured games in various states.
* **Cleanup expectations**: Staging databases can be wiped and re-seeded weekly or after major feature test cycles.

## 12. Deployment Promotion Flow
The recommended release promotion lifecycle:
1. **Local Development**: Developer implements feature branch, runs tests, and validates locally.
2. **Pull Request**: Developer opens PR to merge changes to `staging` branch. GitHub Actions run lint and test suites. Vercel generates a preview build.
3. **Staging Deployment**: PR is approved and merged into `staging`. Staging Railway backend and Vercel frontend rebuild and deploy.
4. **Staging Smoke Test**: QA or release owner performs the Staging Smoke Test checklist.
5. **Production Approval**: Once smoke tests pass, a PR is opened to merge `staging` into `main`. The PR is reviewed and approved by the Technical Lead.
6. **Production Deployment**: Merge triggers automatic production release on Vercel and Railway.
7. **Post-Production Verification**: Perform the Post-Deployment Verification checklist.

## 13. Staging Smoke Test Checklist
Perform these checks on the staging environment before approving a production release:
- [ ] **Frontend Verification**: Staging site loads successfully.
- [ ] **Backend Health**: `GET /` returns `{"status": "ok"}`.
- [ ] **API Documentation**: `/docs` Swagger page loads.
- [ ] **Google Login**: Login with staging Google user test credentials resolves successfully.
- [ ] **Playground Map**: Leaflet map renders and loads fields list.
- [ ] **Field Detail**: Click on field; confirm metadata and status displays correctly.
- [ ] **Game Creation**: Create a new game, confirming validation works.
- [ ] **Join/Leave**: Join a game, check participant count increases, and leave it.
- [ ] **Admin Operations**: Access staging `/admin` views, confirming report queues load.
- [ ] **Field Approval Flow**: Submit a report or approve a pending field in admin dashboard.
- [ ] **Notification Preferences**: Modify user notifications coordinates, verify preferences save.
- [ ] **Push Notification Dispatch**: Trigger game alerts, confirming FCM push message is received on test device.
- [ ] **Server Logs**: Check Railway staging live container logs for exceptions or tracebacks.

## 14. Risks and Tradeoffs
* **Cost**: Separate Railway containers and Supabase projects increase infrastructure costs (though free tiers can initially cover staging).
* **Maintenance overhead**: DevOps team must maintain and sync environment configurations across two separate cloud deployment tracks.
* **Environment drift**: If package updates or schema changes are applied to production without being tested in staging, the environments drift, leading to false confidence. Strict branching rules are required.
* **Data staleness**: Synthetic staging data might not duplicate production data complexities (e.g. large field lists, database sizes), leading to undetected query performance issues. Periodic stress testing is required.

## 15. Recommended Implementation Plan
We recommend deploying the staging strategy in 4 prioritized stages:
* **Stage 1 (High Priority)**: Provision a separate staging backend service on Railway and a staging frontend on Vercel.
* **Stage 2 (High Priority)**: Provision a separate staging Supabase project, execute schemas, and deploy the staging database seed script. Point staging backend/frontend variables to this DB.
* **Stage 3 (Medium Priority)**: Provision a separate staging Firebase project and create staging Google OAuth client credentials to isolate auth/notifications.
* **Stage 4 (Medium Priority)**: Configure git branch rules (locking `main`, setting `staging` branch as the deployment source for staging builds) and adopt the staging smoke-test checklist.

## 16. Follow-Up Issues

1. **ISSUE-126: Create staging backend service (P1)**: Provision Railway staging backend container and configure staging subdomains.
2. **ISSUE-127: Create staging frontend site (P1)**: Configure Vercel staging deployment and map environmental variables.
3. **ISSUE-128: Provision staging Supabase project (P1)**: Create separate Supabase project, execute `schema.sql`, and restrict database permissions.
4. **ISSUE-129: Provision staging Firebase project (P2)**: Set up isolated FCM staging project and generate staging service account key.
5. **ISSUE-130: Create staging Google OAuth client (P2)**: Set up client credential credentials in GCP console mapping staging domains.
6. **ISSUE-131: Write staging SQL seed script (P2)**: Create `backend/migrations/seed_staging.sql` to populate mock fields, test users, and admin configurations.
7. **ISSUE-132: Configure GitHub branching rules for staging promotion (P2)**: Establish `staging` branch and lock direct merges.

## 17. Final Decision
* **Staging required**: YES
* **Separate frontend**: YES (Vercel preview/staging environment)
* **Separate backend**: YES (separate Railway service)
* **Separate DB**: YES (separate Supabase project)
* **Separate Firebase/FCM**: YES (separate Firebase project)
* **Separate OAuth config**: YES (separate Google client mapping staging domains)
* **Strategy approved**: YES
* **Runtime behavior changed**: NO
* **DB schema changed**: NO
