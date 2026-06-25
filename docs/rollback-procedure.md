# Rollback Procedure

## 1. Purpose

This document is the source of truth during failed deployments and production incidents. It defines the complete rollback procedure for the yesh_mishak application, covering frontend, backend, environment variables, database, notifications, and authentication.

Rollback should be used when production or staging becomes unstable after a release and a forward-fix is not feasible within the acceptable time window.

For deployment steps and environment variable reference, see [docs/deployment-process.md](deployment-process.md).

## 2. Rollback Principles

1. **Stop further deploys before rollback.** Freeze all merges and deployments until the situation is assessed.
2. **Assign a rollback owner.** One person leads the rollback; others support.
3. **Preserve logs and evidence.** Capture build logs, server logs, error screenshots, and user reports before making changes.
4. **Prefer the smallest safe rollback.** Roll back only the component that caused the failure, not the entire stack.
5. **Do not hide incidents.** All rollbacks must be documented and communicated.
6. **Do not delete evidence.** Logs, failed deployment artifacts, and error reports must be preserved for post-incident review.
7. **Database rollback is riskier than app rollback.** App rollbacks are fast and low-risk. Database rollbacks can cause data loss — treat them with extra caution.
8. **Communicate status clearly.** Keep the team informed at each step.
9. **Open follow-up issues after rollback.** Every rollback must result in a follow-up issue documenting root cause and remediation.

## 3. Rollback Triggers

Rollback is required or should be considered when any of the following occur after a deployment:

- Frontend blank screen or crash
- Backend API unavailable (health check fails)
- Login / auth broken (Google OAuth fails, JWT validation errors)
- Game creation, join, or leave broken
- Fields / map broken or not loading
- Notification spam or notification outage
- Admin access broken (403 for admins, or non-admins gaining access)
- Security or privacy incident (data exposure, credential leak)
- Bad environment variable deployment (wrong Supabase project, wrong Firebase project)
- Failed database migration (schema error, data corruption)
- Severe performance regression (API response times >10x normal)
- Production users blocked from core flows (login, view fields, create/join games)

## 4. Severity and Decision Matrix

| Symptom | Severity | Rollback Required? | Owner | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Production API down | SEV-0 Critical | YES — immediate | Rollback Lead | Roll back backend immediately |
| Login completely broken | SEV-0 Critical | YES — immediate | Rollback Lead | Roll back backend + check env vars |
| Frontend blank screen | SEV-0 Critical | YES — immediate | Frontend Owner | Redeploy last stable Vercel build |
| Notification spam to production users | SEV-0 Critical | YES — immediate | Backend Owner | Disable notifications, roll back |
| Security/PII data leak | SEV-0 Critical | YES — immediate | Rollback Lead | Follow security incident process |
| Game creation broken | SEV-1 High | YES — within 30 min | Backend Owner | Roll back if forward-fix not ready |
| Fields/map not loading | SEV-1 High | YES — within 30 min | Frontend/Backend Owner | Check API + frontend |
| Admin access broken | SEV-1 High | Consider | Backend Owner | Assess scope of impact |
| Notification delivery delayed | SEV-2 Medium | Consider | Backend Owner | May forward-fix |
| UI rendering bug (non-blocking) | SEV-2 Medium | No — forward-fix | Frontend Owner | Patch in next release |
| Minor styling issue | SEV-3 Low | No | Frontend Owner | Fix in next release |
| Documentation error | SEV-3 Low | No | Any | Fix in next commit |

**Decision rule**: SEV-0 requires immediate rollback. SEV-1 requires rollback within 30 minutes if forward-fix is not ready. SEV-2/3 are forward-fix candidates.

## 5. Roles and Responsibilities

| Role | Responsibility |
| :--- | :--- |
| **Rollback Lead** | Coordinates the rollback, makes go/no-go decisions, communicates status |
| **Frontend Owner** | Executes Vercel rollback, verifies frontend recovery |
| **Backend Owner** | Executes Railway rollback, verifies backend recovery |
| **Database Owner** | Assesses DB impact, executes DB rollback if approved, verifies data integrity |
| **Environment/Secrets Owner** | Reverts environment variables, rotates secrets if needed |
| **Communications Owner** | Sends internal/external status updates |
| **Verification Owner** | Runs post-rollback verification checklist |

In small teams, one person may fill multiple roles. The Rollback Lead role is mandatory.

## 6. Immediate Failed Deployment Checklist

When a deployment failure is detected:

- [ ] **Stop new deploys** — freeze merges and deployment pipelines.
- [ ] **Identify the bad release** — record version, branch, commit SHA, PR link.
- [ ] **Identify affected environment** — staging or production.
- [ ] **Identify affected users/flows** — which features are broken, how many users impacted.
- [ ] **Check logs** — Railway container logs, Vercel build logs, browser console.
- [ ] **Decide: rollback vs forward-fix** — see section 14.
- [ ] **Assign rollback owner.**
- [ ] **Preserve evidence** — screenshot errors, export logs, save user reports.
- [ ] **Start incident timeline** — record detection time and each subsequent action.
- [ ] **Notify team** — message the team with environment, symptom, and assigned owner.

## 7. Frontend Rollback Procedure

### Vercel Rollback Steps
1. Open the Vercel project dashboard. *(Project name: needs confirmation)*
2. Go to the **Deployments** tab.
3. Locate the last known stable deployment (check by date and commit SHA).
4. Click the three-dot menu (**...**) on the stable deployment.
5. Select **Redeploy** → **Promote to Production**.
6. Vercel instantly routes production traffic to the previous build.

### Verification After Frontend Rollback
- [ ] Production frontend URL loads without blank screen.
- [ ] Map page renders with field markers.
- [ ] Login button is visible and functional.
- [ ] Browser console has no critical errors.
- [ ] Network requests target the correct backend API URL.

### Frontend Environment Variable Check
- Verify `VITE_API_URL` points to the correct backend (production or staging).
- Verify `VITE_GOOGLE_CLIENT_ID` matches the backend `GOOGLE_CLIENT_ID`.
- Verify all `VITE_FIREBASE_*` variables match the correct Firebase project.

### Common Frontend Rollback Risks
- **Stale API contract**: If the backend was also updated with new endpoints/fields, rolling back the frontend alone may cause broken API calls. Coordinate with backend rollback.
- **Cached service worker**: Users may have a cached service worker. A hard refresh or cache clear may be needed.
- **CDN cache**: Vercel CDN may serve cached assets briefly. Allow 1-2 minutes for propagation.

## 8. Backend Rollback Procedure

### Railway Rollback Steps
1. Open the Railway project dashboard. *(Service name: needs confirmation)*
2. Navigate to the backend service.
3. Go to the deployment history / service generations list.
4. Identify the last known stable deployment (check by date and commit SHA).
5. Click **Redeploy** on the stable deployment. Railway rebuilds from that commit.

### Verification After Backend Rollback
- [ ] `GET /` returns HTTP 200 with health check response.
- [ ] `GET /docs` loads the Swagger/OpenAPI documentation page.
- [ ] Auth endpoints respond (login, register, Google login).
- [ ] `GET /fields/` returns field data.
- [ ] Game endpoints respond for authenticated users.
- [ ] Notification endpoints respond for authenticated users.
- [ ] Admin endpoints reject non-admin users with 403.
- [ ] Railway container logs show no unhandled exceptions.

### Common Backend Rollback Risks
- **Database schema mismatch**: If the bad release included a migration, the rolled-back code may expect the old schema. See section 10 for DB rollback.
- **Environment variable dependency**: If new env vars were added for the bad release, the rolled-back code should not depend on them. Verify env var compatibility.
- **Active user sessions**: Rolling back JWT_SECRET invalidates all active sessions. Only rotate JWT_SECRET if it was compromised, not as a routine rollback step.

## 9. Environment Variable Rollback Procedure

### Identifying Recent Changes
1. Check the Vercel and Railway dashboards for recent environment variable modifications.
2. Compare current values against `backend/.env.staging.example` and `frontend/.env.staging.example` for expected variable names.
3. Review the deployment PR for any env var change documentation.

### Restoring Previous Values
1. Identify the known-good values from the previous stable deployment.
2. Update the changed variables in the hosting provider dashboard (Vercel for frontend, Railway for backend).
3. Redeploy the service to load the reverted variables.
4. Do NOT share secret values in chat, tickets, or logs.

### High-Risk Environment Variables

| Variable | Risk If Wrong | Area |
| :--- | :--- | :--- |
| `SUPABASE_URL` | Backend connects to wrong database | Backend |
| `SUPABASE_KEY` | Backend cannot authenticate with Supabase | Backend |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend loses elevated DB access; **leak = full DB exposure** | Backend |
| `JWT_SECRET` | All user sessions invalidated; **leak = token forgery** | Backend |
| `GOOGLE_CLIENT_ID` | Google login fails on frontend or backend | Both |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Push notifications fail; **leak = FCM abuse** | Backend |
| `FIREBASE_PROJECT_ID` | Notifications sent to wrong project | Backend |
| `VITE_API_URL` | Frontend calls wrong backend | Frontend |
| `VITE_GOOGLE_CLIENT_ID` | Google login button fails | Frontend |
| `VITE_FIREBASE_*` variables | Push registration fails or targets wrong project | Frontend |
| `CORS_ORIGINS` | Frontend requests blocked by CORS | Backend |

### Verification After Environment Variable Rollback
- [ ] Backend health check responds.
- [ ] Frontend loads and calls the correct backend.
- [ ] Login works end-to-end.
- [ ] No CORS errors in browser console.
- [ ] Push notification registration works (if applicable).

### Secret Rotation Notes
If a secret was exposed during the incident:
- **JWT_SECRET**: Rotate immediately. All active user sessions will be invalidated — users must re-login.
- **SUPABASE_SERVICE_ROLE_KEY**: Rotate via Supabase dashboard immediately. Update Railway env var.
- **FIREBASE_SERVICE_ACCOUNT_JSON**: Revoke the key in Google Cloud IAM console. Generate a new one in the Firebase Console.

## 10. Database / Supabase Rollback Procedure

**Database rollback is fundamentally different from application rollback.** Application rollbacks are fast and stateless. Database changes are stateful and may cause data loss if reversed incorrectly.

### Rules
1. **Do NOT blindly drop tables or columns in production.**
2. **Do NOT run `DELETE` or `TRUNCATE` without explicit approval.**
3. Review the migration/schema changes that caused the issue.
4. **Prefer forward-fix migrations** — add a new migration that corrects the schema rather than reverting it.
5. Use backup/snapshot restore **only with explicit approval** from the Database Owner and Technical Lead.
6. Review RLS/policy changes — a reverted policy may re-expose data or block legitimate access.
7. Assess data-loss risk before any rollback action.

### Verification After Database Rollback
- [ ] Backend can connect and query the database.
- [ ] Core tables exist and have expected columns.
- [ ] RLS policies are active and correct.
- [ ] No data corruption in critical tables (users, fields, games).
- [ ] Game data integrity audit passes (if applicable): `cd backend && python scripts/audit_game_data_integrity.py`

### Approval Requirements
Database rollback requires approval from:
- Database Owner
- Technical Lead
- Rollback Lead (if different from above)

### Backup/Snapshot Restore
Supabase provides automatic daily backups. To restore:
1. Open the Supabase project dashboard.
2. Go to **Database > Backups**.
3. Select the appropriate backup point.
4. Restore the backup.
5. **Warning**: This overwrites ALL data since the backup point. Data written after the backup is lost.

## 11. Firebase / Push Notification Rollback Procedure

### When to Act
- Staging notifications are reaching production users.
- Users are receiving spam notifications.
- Push notification errors are flooding logs.
- Firebase credentials were compromised.

### Steps to Stop Notification Spam
1. Set `DISABLE_GAME_CREATED_NOTIFICATIONS=True` in the Railway backend environment variables.
2. Redeploy the backend to apply the change.
3. This immediately stops game-created push notifications without rolling back code.

### Credential Rollback
If Firebase credentials were compromised:
1. Revoke the leaked service account key in Google Cloud IAM console.
2. Generate a new private key in Firebase Console > Project Settings > Service Accounts.
3. Update `FIREBASE_SERVICE_ACCOUNT_JSON` in Railway.
4. Redeploy the backend.

### Cross-Environment Safety Verification
- [ ] Staging backend uses staging Firebase project credentials.
- [ ] Staging database contains only synthetic push tokens.
- [ ] Production backend uses production Firebase project credentials.
- [ ] No staging push tokens exist in the production database.
- [ ] No production push tokens exist in the staging database.

### Push Notification Rollback Risks
- Revoking Firebase credentials stops ALL push notifications until new credentials are deployed.
- Users who registered push tokens during the incident may need to re-register.

## 12. Google Auth Rollback Procedure

### OAuth Misconfiguration Rollback
If Google login is broken after a deployment:
1. Verify `GOOGLE_CLIENT_ID` in Railway matches `VITE_GOOGLE_CLIENT_ID` in Vercel.
2. Verify the frontend origin URL is listed in the Google Cloud Console > APIs & Services > Credentials > Authorized JavaScript Origins.
3. If a new OAuth client was deployed, revert to the previous client ID in both frontend and backend env vars.
4. Redeploy both frontend and backend.

### Login Verification After Rollback
- [ ] Google login button renders on the login page.
- [ ] Clicking login opens the Google consent screen.
- [ ] After consent, user is redirected back and authenticated.
- [ ] User identity (name/avatar) displays correctly.
- [ ] Backend validates the Google token without errors.

### Security Considerations
- **Do NOT reintroduce known P0 auth vulnerabilities during rollback.** If the bad release fixed a security issue, rolling back re-exposes that vulnerability. In this case, prefer a forward-fix or apply the security fix as an isolated hotfix.
- If rolling back auth changes, verify that user ownership checks and admin authorization are still enforced.

## 13. Feature Rollback Procedure

When a specific feature (not the entire release) needs to be rolled back:

### Using `git revert`
```bash
git revert <bad-commit-sha>
git push origin main
```

### Rules
- Prefer reverting the smallest risky change, not the entire release.
- Avoid rewriting shared history (`git rebase`, `git reset --hard` on shared branches).
- If multiple commits need reverting, revert them in reverse chronological order.

### Hotfix Branch
If a targeted fix is needed:
1. Create a hotfix branch: `hotfix/vX.Y.Z`
2. Apply the fix.
3. Follow the release versioning policy: [docs/release-versioning-policy.md](release-versioning-policy.md)
4. Bump the PATCH version (e.g. `1.2.1`).
5. Open a PR, get review, merge, and deploy.

## 14. Rollback vs Forward-Fix Decision

| Factor | Rollback | Forward-Fix |
| :--- | :--- | :--- |
| **When to use** | Root cause is unclear, fix is not ready, users are blocked | Root cause is clear, fix is small and testable |
| **Time pressure** | SEV-0: rollback immediately; SEV-1: rollback within 30 min if fix not ready | Fix can be deployed within acceptable window |
| **Risk** | Low — restores known-good state | Medium — new code under pressure |
| **Data impact** | None (app rollback) to high (DB rollback) | Depends on the fix |
| **Preferred for** | Multi-component failures, unknown root cause | Single-line bugs, config fixes |

### Maximum Investigation Time Before Rollback
- **SEV-0**: Rollback immediately. Investigate after rollback.
- **SEV-1**: 30 minutes maximum. If no fix is ready, rollback.
- **SEV-2**: 2 hours. Forward-fix is preferred.

### Decision Owner
The Rollback Lead makes the rollback vs forward-fix decision. For SEV-0, any team member can initiate rollback without waiting for approval.

## 15. Rollback Verification Checklist

After any rollback, verify all core flows:

- [ ] Frontend loads without errors
- [ ] Backend health check responds (200)
- [ ] Google login works end-to-end
- [ ] Fields load on the map
- [ ] Map renders and is interactive
- [ ] Game creation works
- [ ] Game join/leave works
- [ ] Notification preferences load
- [ ] Unread notification count is correct
- [ ] Admin routes reject non-admin users (403)
- [ ] Admin dashboard loads for admin users
- [ ] Backend logs are clean (no unhandled exceptions)
- [ ] No new critical errors in browser console
- [ ] User reports monitored for 30-60 minutes

## 16. Communication Procedure

### Internal Update Template
```
[INCIDENT] Rollback in progress
Environment: Production / Staging
Symptom: <brief description>
Bad release: v<version> / commit <sha>
Rolling back to: v<version> / commit <sha>
Status: In progress / Completed / Monitoring
Owner: <name>
ETA: <time>
```

### User-Facing Update Template (if needed)
```
We are aware of an issue affecting <feature>.
Our team is working to resolve it.
We expect the issue to be fixed by <time>.
We apologize for the inconvenience.
```

### Communication Rules
- **Do not speculate** about root cause before it is verified.
- **Do not share internal details** (commit hashes, env vars, error messages) in user-facing updates.
- **Communicate uncertainty honestly**: "We are investigating" is better than a wrong explanation.
- The Communications Owner sends updates. Others should not send conflicting messages.
- If the incident involves security or privacy, follow the security incident handling process documented in product-decisions.md.

## 17. Rollback Timeline Template

| Field | Value |
| :--- | :--- |
| **Detected at** | |
| **Detected by** | |
| **Affected environment** | Production / Staging |
| **Bad release/version/commit** | |
| **Previous stable release/version/commit** | |
| **Rollback owner** | |
| **Decision time** (rollback vs forward-fix) | |
| **Rollback started** | |
| **Rollback completed** | |
| **Verification completed** | |
| **Final status** | Resolved / Monitoring / Escalated |
| **Follow-up issues** | |

## 18. Post-Rollback Review

After the incident is resolved, complete a post-rollback review:

| Question | Answer |
| :--- | :--- |
| **Root cause** | |
| **Detection gap** | How was it detected? Could it have been caught earlier? |
| **Testing gap** | Did tests cover this scenario? If not, what tests are needed? |
| **Deployment gap** | Was the deployment process followed? What step was missed? |
| **Monitoring gap** | Would automated monitoring have caught this faster? |
| **Documentation gap** | Does any documentation need updating? |
| **Follow-up issue owner** | |
| **Due date for follow-up** | |

## 19. Reusable Rollback Checklist

Copy this section for each rollback event:

```
## Rollback — v___ — <date>

- [ ] Stop new deploys
- [ ] Assign rollback owner
- [ ] Identify bad release/commit
- [ ] Identify previous stable release/commit
- [ ] Preserve logs and evidence
- [ ] Decide rollback vs forward-fix
- [ ] Roll back frontend (if needed)
- [ ] Roll back backend (if needed)
- [ ] Roll back environment variables (if needed)
- [ ] Review database rollback risk
- [ ] Verify auth works
- [ ] Verify fields load
- [ ] Verify games work
- [ ] Verify notifications work
- [ ] Verify admin protection
- [ ] Monitor logs for 30-60 minutes
- [ ] Communicate status to team
- [ ] Open follow-up issue

Rollback owner: ___
Completed at: ___
Verified by: ___
```

## 20. Known Gaps / Needs Confirmation

| Gap | Status |
| :--- | :--- |
| Exact Vercel project name | Needs confirmation |
| Exact Railway service name | Needs confirmation |
| Dashboard owners / access list | Needs confirmation |
| Supabase backup/snapshot policy and retention | Needs confirmation |
| Automated deployment rollback support (one-click) | Not confirmed |
| Monitoring / alerting ownership and tooling | Not implemented |
| Staging live status | Not live — waiting for external dashboard setup (ISSUE-114) |

## 21. Final Result

| Item | Status |
| :--- | :--- |
| Rollback procedure exists | YES |
| Frontend rollback documented | YES |
| Backend rollback documented | YES |
| Environment variable rollback documented | YES |
| Database rollback considerations documented | YES |
| Firebase/notification rollback documented | YES |
| Google Auth rollback documented | YES |
| Feature rollback documented | YES |
| Rollback vs forward-fix decision documented | YES |
| Severity matrix documented | YES |
| Communication procedure documented | YES |
| Reusable rollback checklist included | YES |
| Runtime behavior changed | NO |
| DB schema changed | NO |
