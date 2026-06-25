# Release Checklist Template

## 1. Purpose

This document is the official release checklist for the yesh_mishak project. It must be copied or referenced before every release. No release should proceed unless all required checks pass or exceptions are explicitly approved and documented.

The checklist ensures consistent quality, security, and safety across all releases by covering backend tests, frontend tests, auth, notifications, games, fields, admin, environment, database, and security checks.

## 2. Release Metadata

Fill in before starting the checklist:

| Field | Value |
| :--- | :--- |
| **Release version** | |
| **Release type** | Major / Minor / Patch / Hotfix / Pre-release |
| **Release branch** | |
| **Git commit SHA** | |
| **PR link** | |
| **Target environment** | Staging / Production |
| **Release owner** | |
| **QA owner** | |
| **Approval owner** | |
| **Planned release date/time** | |
| **Rollback owner** | |
| **Rollback plan link** | |

## 3. Pre-Release Gate

- [ ] Correct branch checked out (`git branch --show-current`)
- [ ] Working tree is clean (`git status --short` shows no unexpected changes)
- [ ] Latest main pulled (`git pull origin main`)
- [ ] PR reviewed and approved
- [ ] Version bump decision made per [docs/release-versioning-policy.md](release-versioning-policy.md)
- [ ] Deployment process reviewed per [docs/deployment-process.md](deployment-process.md)
- [ ] Staging status checked (if staging deployment exists)
- [ ] Known P0/P1 blockers reviewed — none open or exceptions approved
- [ ] Security readiness blockers reviewed — none open or exceptions approved
- [ ] Rollback plan confirmed and documented
- [ ] No real secrets committed (`git diff` reviewed)
- [ ] Environment variables verified for target environment

## 4. Backend Tests

| Check | Command | Pass/Fail | Evidence | Owner | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Install dependencies | `cd backend && pip install -r requirements.txt` | | | | |
| Run full test suite | `cd backend && python -m pytest tests/ -v` | | | | |
| Run auth tests | `cd backend && python -m pytest tests/test_manual_auth.py tests/test_google_auth.py tests/test_jwt_lifecycle.py tests/test_password_validation.py -v` | | | | |
| Run notification tests | `cd backend && python -m pytest tests/test_notifications.py tests/test_notification_templates.py tests/test_notification_cleanup.py tests/test_notification_stress.py -v` | | | | |
| Run games tests | `cd backend && python -m pytest tests/test_game_transitions.py tests/test_game_close.py tests/test_game_cancel.py tests/test_game_participant_limits.py tests/test_game_creator_ownership.py tests/test_game_visibility.py tests/test_game_payloads.py tests/test_my_games.py tests/test_duplicate_detection.py -v` | | | | |
| Run fields tests | `cd backend && python -m pytest tests/test_field_reports_api.py tests/test_field_reports_schema.py tests/test_inactive_field_lifecycle.py -v` | | | | |
| Run admin tests | `cd backend && python -m pytest tests/test_admin_me.py tests/test_admin_user_moderation.py -v` | | | | |
| Run rate limiting tests | `cd backend && python -m pytest tests/test_rate_limiting.py -v` | | | | |
| Run content moderation tests | `cd backend && python -m pytest tests/test_content_moderation.py tests/test_content_moderation_endpoints.py -v` | | | | |
| API health check | `curl <backend-url>/` returns 200 | | | | |
| API docs check | `curl <backend-url>/docs` loads Swagger UI | | | | |

## 5. Frontend Tests

| Check | Command | Pass/Fail | Evidence | Owner | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Install dependencies | `cd frontend && npm install` | | | | |
| Lint | `cd frontend && npm run lint` | | | | |
| Build | `cd frontend && npm run build` | | | | |
| E2E tests (Playwright) | `cd frontend && npm run test:e2e` | | | | |
| Browser smoke test | Manual — see section 12 | | | | |
| Mobile/responsive check | Manual — verify key screens at mobile viewport width | | | | |

## 6. Auth Checks

- [ ] Logged-out user can only view allowed public screens (map, login)
- [ ] Google login completes successfully
- [ ] Invalid token returns 401
- [ ] Expired token returns 401
- [ ] Logout works and clears session
- [ ] Admin-only routes return 403 for non-admin users
- [ ] User identity (name/avatar) shown correctly after login
- [ ] No token, email, or PII exposed in browser console or network logs
- [ ] Known auth blockers reviewed (check product-decisions.md for AUTH items)
- [ ] Any auth migration or re-login impact documented in release notes

## 7. Notifications Checks

- [ ] Notification preferences page loads
- [ ] Notification preferences save correctly
- [ ] City preference behavior works as expected
- [ ] Radius preference behavior works as expected
- [ ] Specific fields preference behavior works as expected
- [ ] Unread notification count displays correctly
- [ ] Mark read / mark all read works
- [ ] Game-created notification is sent to eligible users
- [ ] Player-joined notification is sent to game organizer
- [ ] Push token registration works (if push notifications enabled)
- [ ] Push notification received on test device (staging only)
- [ ] Staging does NOT send notifications to production users
- [ ] No duplicate or spam notifications observed

## 8. Games Checks

- [ ] Active games load on field detail
- [ ] Upcoming/scheduled games load on field detail
- [ ] Create immediate game succeeds
- [ ] Create scheduled game succeeds
- [ ] Duplicate game prevention works (same field, overlapping time)
- [ ] Join game increments participant count
- [ ] Leave game decrements participant count
- [ ] Game auto-closes when full (if applicable)
- [ ] Organizer can close their game
- [ ] Organizer can extend their game
- [ ] Non-owner cannot close/extend another user's game
- [ ] Max players limit enforced
- [ ] Game participant count is accurate

## 9. Fields Checks

- [ ] Map loads and renders correctly
- [ ] Field list/markers load on map
- [ ] Field detail page loads with correct metadata
- [ ] Approved fields are visible on the map
- [ ] Pending/rejected fields are NOT visible on the public map
- [ ] Add field flow works for authenticated users
- [ ] Field approval flow works for admin users
- [ ] Field rejection flow works for admin users
- [ ] Field status (open/closed/renovation) displays correctly
- [ ] Location/map bounds filtering works
- [ ] No private user location stored unexpectedly

## 10. Admin Checks

- [ ] Admin dashboard loads for admin users
- [ ] Non-admin users cannot access admin dashboard or admin API endpoints
- [ ] Admin users list loads correctly
- [ ] Admin stats/metrics load correctly (if applicable)
- [ ] Admin field approval/rejection works
- [ ] Admin actions do not expose unnecessary PII beyond approved behavior
- [ ] Admin route authorization verified (403 for non-admin)

## 11. API / Backend Smoke Checks

- [ ] `GET /` health endpoint returns 200
- [ ] `GET /docs` Swagger page loads
- [ ] Auth endpoints respond (login, register, Google)
- [ ] Fields endpoints respond (`GET /fields/`)
- [ ] Games endpoints respond (authenticated)
- [ ] Notifications endpoints respond (authenticated)
- [ ] Admin endpoints reject non-admin users with 403
- [ ] Backend logs reviewed after smoke test — no unhandled exceptions

## 12. Frontend Smoke Checks

- [ ] App loads without blank screen
- [ ] Main map page renders with field markers
- [ ] Login button/flow is visible and functional
- [ ] Authenticated user flow works (login → map → field → game)
- [ ] Add field button/modal works
- [ ] Create game modal works
- [ ] Notifications inbox/modal works
- [ ] Admin page works for admin users (if applicable)
- [ ] Browser console checked — no critical errors

## 13. Environment / Deployment Checks

- [ ] Frontend `VITE_API_URL` points to correct backend for target environment
- [ ] Backend `CORS_ORIGINS` includes correct frontend URL for target environment
- [ ] Backend `SUPABASE_URL` and `SUPABASE_KEY` point to correct Supabase project
- [ ] Backend `FIREBASE_PROJECT_ID` and service account match correct Firebase project
- [ ] Backend `GOOGLE_CLIENT_ID` matches frontend `VITE_GOOGLE_CLIENT_ID`
- [ ] Correct environment confirmed: Local / Staging / Production
- [ ] Staging is NOT using production `SUPABASE_SERVICE_ROLE_KEY`
- [ ] Production is NOT using staging keys
- [ ] No real secrets in frontend bundle (no `SUPABASE_SERVICE_ROLE_KEY` or `JWT_SECRET` in VITE_ vars)
- [ ] Environment variable changes documented in release notes

## 14. Database Checks

- [ ] Migrations reviewed (if any in this release)
- [ ] Schema changes reviewed (if any in this release)
- [ ] RLS / policy impact reviewed (if any in this release)
- [ ] Data backfill required: YES / NO
- [ ] Rollback plan for DB changes documented (if applicable)
- [ ] Production data risk reviewed
- [ ] Backup / snapshot status checked (if required by change scope)

## 15. Security / Privacy Checks

- [ ] No P0 security blockers open (or exceptions explicitly approved)
- [ ] Known P1/P2 security risks reviewed
- [ ] No secrets committed in code or config files
- [ ] Admin authorization verified
- [ ] User ownership checks verified (users can only modify their own resources)
- [ ] PII exposure reviewed — no emails, phone numbers, or tokens in API responses beyond approved behavior
- [ ] Logs reviewed for token, email, phone, or location leakage
- [ ] Push notification token safety checked (staging tokens separate from production)
- [ ] Incident handling process available (see product-decisions.md)

## 16. Release Notes Checklist

- [ ] User-visible changes summarized
- [ ] Admin-visible changes summarized
- [ ] Bug fixes summarized
- [ ] Security fixes summarized (if safe to disclose)
- [ ] Known issues documented
- [ ] Rollback notes documented
- [ ] Version number confirmed per versioning policy
- [ ] App Store / Google Play notes prepared (if applicable)

## 17. Final Release Approval

| Area | Owner | Status | Evidence | Approval Timestamp |
| :--- | :--- | :--- | :--- | :--- |
| Backend | | | | |
| Frontend | | | | |
| Auth | | | | |
| Notifications | | | | |
| Games | | | | |
| Fields | | | | |
| Admin | | | | |
| Security | | | | |
| Deployment | | | | |
| Product | | | | |

## 18. Rollback Readiness

- [ ] Previous stable version identified: v___
- [ ] Frontend rollback path confirmed (Vercel redeploy or revert merge)
- [ ] Backend rollback path confirmed (Railway redeploy or revert merge)
- [ ] DB rollback strategy confirmed (if schema changes exist)
- [ ] Environment variable rollback strategy confirmed
- [ ] Rollback owner assigned: ___
- [ ] Communication plan ready (who to notify if rollback triggered)

## 19. Post-Release Verification

- [ ] Production frontend loads without errors
- [ ] Production backend responds (health check 200)
- [ ] Login works on production
- [ ] Fields load on the map
- [ ] Games load and can be interacted with
- [ ] Notifications checked (preferences load, counts correct)
- [ ] Admin route protection verified
- [ ] Logs reviewed for 30-60 minutes post-deploy — no critical errors
- [ ] No critical user reports received
- [ ] Release marked complete

## 20. Exception Handling

If a check fails:
1. **Document the failure** in the checklist with details and evidence.
2. **Assess severity**: Is this a release blocker or an acceptable known issue?
3. **Escalate if needed**: The release owner decides whether to proceed or halt.
4. **Approval required**: Only the approval owner can approve an exception to proceed despite a failed check.
5. **Cannot be bypassed**: Security P0 blockers, broken auth, data corruption risks, and production secret leaks cannot be overridden.
6. **Create follow-up**: If proceeding with an exception, create a follow-up issue for the failed check.
7. **Document the exception** in the release notes under "Known Issues."

## 21. Reusable Blank Checklist

Copy this section for quick release signoff:

```
## Release v___ Signoff

- [ ] Backend tests passed
- [ ] Frontend tests passed
- [ ] Auth checked
- [ ] Notifications checked
- [ ] Games checked
- [ ] Fields checked
- [ ] Admin checked
- [ ] Environment variables checked
- [ ] Database changes reviewed
- [ ] Security / privacy reviewed
- [ ] Rollback plan confirmed
- [ ] Release approved

Approved by: ___
Date: ___
```

## 22. Final Result

| Item | Status |
| :--- | :--- |
| Release checklist exists | YES |
| Backend tests included | YES |
| Frontend tests included | YES |
| Notifications included | YES |
| Auth included | YES |
| Games included | YES |
| Fields included | YES |
| Admin included | YES |
| Security/privacy included | YES |
| Environment/deployment included | YES |
| Database included | YES |
| Release signoff section exists | YES |
| Rollback readiness included | YES |
| Post-release verification included | YES |
| Reusable for every release | YES |
| Runtime behavior changed | NO |
| DB schema changed | NO |
