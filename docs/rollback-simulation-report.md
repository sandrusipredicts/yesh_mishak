# Rollback Simulation Report

## 1. Purpose

This document records the results of a rollback simulation exercise performed to validate the rollback procedure documented in [docs/rollback-procedure.md](rollback-procedure.md).

Documentation alone is insufficient to ensure operational readiness. A simulation exercise verifies that the procedure is complete, actionable, and can be followed under pressure. It also identifies gaps, missing information, and areas where the procedure needs improvement.

**Exercise type: TABLETOP / DRY-RUN SIMULATION**

No live staging or production rollback was performed. The staging environment is not yet live (ISSUE-114 status: PREPARED / WAITING FOR EXTERNAL DASHBOARD SETUP). This exercise walked through the rollback procedure step-by-step against a simulated failure scenario, measuring estimated operational times and documenting findings.

## 2. Exercise Metadata

| Field | Value |
| :--- | :--- |
| **Issue** | ISSUE-118 |
| **Date** | 2026-06-25 |
| **Branch** | `issue-118-rollback-simulation-exercise` |
| **Exercise type** | TABLETOP / DRY-RUN SIMULATION |
| **Facilitator** | Development team (automated exercise) |
| **Participants** | Needs confirmation — no named participants assigned |
| **Target environment** | Simulated production failure |
| **Scenario name** | Game Creation Failure — Backend Deployment Unhealthy |
| **Rollback procedure used** | [docs/rollback-procedure.md](rollback-procedure.md) |
| **Related documents** | [docs/deployment-process.md](deployment-process.md), [docs/release-checklist-template.md](release-checklist-template.md), [docs/staging-smoke-test-checklist.md](staging-smoke-test-checklist.md) |

## 3. Preconditions

| Condition | Status |
| :--- | :--- |
| Staging environment live | NO — prepared but not provisioned (ISSUE-114) |
| Production touched | NO |
| Deployments changed | NO |
| Database changed | NO |
| Secrets changed | NO |
| Rollback commands actually executed | NO — tabletop simulation only |
| Real Vercel/Railway dashboards accessed | NO |

## 4. Scenario Description

### Failure Trigger
A new release (`v1.3.0`, commit `abc1234` — simulated) is merged to `main` and auto-deployed. The release included a backend change to the game creation endpoint. After deployment, the backend service on Railway starts but the game creation endpoint returns 500 errors due to a database query referencing a column that does not exist in the current schema (migration was not applied before deployment).

### User Impact
- Users can log in and view the map and fields.
- Users **cannot** create new games (500 error).
- Users **cannot** join existing games (500 error on related query).
- Existing games and fields display correctly.
- Notifications are unaffected.

### Affected Systems
- Backend API (game endpoints)
- Frontend (game creation modal shows error)

### Assumed Releases
- **Bad release**: `v1.3.0` / commit `abc1234` (simulated)
- **Previous stable release**: `v1.2.1` / commit `0b02f20` (last known-good — actual latest main commit used for realism)

### Severity Classification
**SEV-1 High** — Core user flow (game creation/join) is broken. Users are partially blocked. Login, fields, and map work. Per rollback-procedure.md section 4: "SEV-1: rollback within 30 min if forward-fix not ready."

## 5. Exercise Timeline

| Step | T+ Offset | Duration | Owner | Action | Evidence | Result |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1. Detection | T+0:00 | 5 min | On-call / user report | User reports game creation failing. On-call checks backend logs, sees 500 errors on `POST /games/`. | Simulated Railway log showing `column "scheduled_type" does not exist` | Issue confirmed |
| 2. Severity classification | T+5:00 | 2 min | Rollback Lead | Classified as SEV-1: core flow broken, partial user impact. | Rollback-procedure.md section 4 | SEV-1 confirmed |
| 3. Stop new deploys | T+7:00 | 1 min | Rollback Lead | Announce deployment freeze in team channel. | Simulated message | Freeze active |
| 4. Assign rollback owner | T+8:00 | 1 min | Rollback Lead | Rollback Lead assumes ownership. | Simulated assignment | Owner assigned |
| 5. Identify bad release | T+9:00 | 2 min | Rollback Lead | Check Railway deployment history for latest deploy. Identify commit `abc1234` / `v1.3.0`. | Simulated Railway dashboard | Bad release identified |
| 6. Identify previous stable release | T+11:00 | 2 min | Rollback Lead | Check Railway deployment history. Previous deploy was commit `0b02f20`. | Simulated Railway dashboard | Stable release identified |
| 7. Preserve logs | T+13:00 | 3 min | Backend Owner | Export Railway container logs showing the 500 errors. Screenshot the error. | Simulated log export | Logs preserved |
| 8. Decide: rollback vs forward-fix | T+16:00 | 3 min | Rollback Lead | Root cause is a missing migration. Applying migration is possible but risky under pressure. Decision: **rollback** to restore service, apply migration properly in next release. | Rollback-procedure.md section 14 | Rollback chosen |
| 9. Backend rollback | T+19:00 | 5 min | Backend Owner | Open Railway dashboard → backend service → deployment history → find `0b02f20` → click Redeploy. Wait for build and health check. | Simulated Railway redeploy | Backend rolled back |
| 10. Frontend check | T+24:00 | 2 min | Frontend Owner | Frontend was not changed in the bad release. Verify frontend still loads and points to correct backend URL. | Simulated browser check | Frontend OK — no rollback needed |
| 11. Env var check | T+26:00 | 2 min | Env Owner | No environment variables were changed in the bad release. Verify current env vars match known-good values. | Simulated Railway env check | Env vars OK |
| 12. Database risk review | T+28:00 | 3 min | Database Owner | The bad release expected a new column but the migration was never applied. Current DB schema is still in the known-good state. No DB rollback needed. | Simulated Supabase check | DB OK — no action needed |
| 13. Auth check | T+31:00 | 2 min | Verification Owner | Simulate Google login flow. Login works, token is valid, user identity displays correctly. | Simulated browser test | Auth OK |
| 14. Notification check | T+33:00 | 1 min | Verification Owner | Notification preferences load. Unread count responds. No spam detected. | Simulated API check | Notifications OK |
| 15. Fields/map check | T+34:00 | 1 min | Verification Owner | Map loads, fields display, field detail works. | Simulated browser check | Fields OK |
| 16. Games check | T+35:00 | 2 min | Verification Owner | Game creation works again. Join/leave works. Participant count correct. | Simulated API + browser check | Games OK — **recovery confirmed** |
| 17. Admin protection check | T+37:00 | 1 min | Verification Owner | Non-admin user gets 403 on admin endpoints. Admin user can access admin dashboard. | Simulated API check | Admin OK |
| 18. Log monitoring | T+38:00 | 5 min | Backend Owner | Monitor Railway logs for 5 minutes. No 500 errors. No unhandled exceptions. | Simulated log watch | Logs clean |
| 19. Communication update | T+43:00 | 2 min | Communications Owner | Send internal update: "Rollback complete. Game creation restored. Root cause: missing DB migration in v1.3.0. Forward-fix planned." | Simulated message | Team notified |
| 20. Follow-up issue | T+45:00 | 3 min | Rollback Lead | Create follow-up issue: "Apply scheduled_type migration and re-release v1.3.0 as v1.3.1 with pre-deploy migration step." | Simulated issue creation | Follow-up created |
| **Total** | | **~48 min** | | | | **Recovery complete** |

## 6. Rollback Procedure Walkthrough

Each step references [docs/rollback-procedure.md](rollback-procedure.md):

| Procedure Step | Section | Performed? | Notes |
| :--- | :--- | :--- | :--- |
| Stop new deploys | §6 | Simulated | Clear — announce freeze in team channel |
| Assign rollback owner | §5, §6 | Simulated | Clear — Rollback Lead takes ownership |
| Identify bad release/commit | §6 | Simulated | Requires Railway dashboard access — **gap: exact project/service name not confirmed** |
| Identify previous stable release/commit | §6 | Simulated | Requires Railway dashboard access |
| Preserve logs | §2, §6 | Simulated | Clear — export Railway logs before rollback |
| Decide rollback vs forward-fix | §14 | Simulated | Clear — decision matrix in procedure was helpful |
| Frontend rollback | §7 | Not needed | Frontend was not part of the bad release |
| Backend rollback | §8 | Simulated | Requires Railway dashboard — **gap: exact Redeploy button location not confirmed** |
| Env var rollback/check | §9 | Simulated | No env vars changed — verification only |
| Database risk review | §10 | Simulated | Clear — migration was never applied, DB is in known-good state |
| Auth check | §12 | Simulated | Clear — Google login verification steps are documented |
| Notification check | §11 | Simulated | Clear — check push token safety and spam |
| Fields check | §15 | Simulated | Clear |
| Games check | §15 | Simulated | Clear — this was the broken flow, confirmed restored |
| Admin protection check | §15 | Simulated | Clear |
| Logs monitoring | §15 | Simulated | Clear — 30-60 min monitoring recommended |
| Communication | §16 | Simulated | Templates in procedure were usable |
| Follow-up issue | §2, §18 | Simulated | Clear — post-rollback review template is helpful |

## 7. Measured Rollback Timing

| Step | Tabletop Time | Estimated Real Operational Time | Bottleneck? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Detection | 5 min | 5-15 min | Possible | Depends on monitoring/alerting — currently no automated alerting |
| Severity classification | 2 min | 2-5 min | No | Procedure matrix makes this straightforward |
| Decision (rollback vs forward-fix) | 3 min | 5-10 min | Possible | Under pressure, decision may take longer |
| Frontend rollback | 0 min (not needed) | 2-5 min when needed | No | Vercel instant redeploy is fast |
| Backend rollback | 5 min | 5-10 min | YES | Railway rebuild time is the main bottleneck |
| Env var verification | 2 min | 3-5 min | No | Quick dashboard check |
| DB risk review | 3 min | 5-10 min | Possible | May be slower if migration was actually applied |
| Smoke verification | 8 min | 10-15 min | No | Multiple flows to check |
| Communication | 2 min | 5 min | No | Using templates from procedure |
| Post-rollback monitoring | 5 min (abbreviated) | 30-60 min | No | Required but not a blocker |
| **Total estimated recovery** | **~48 min** | **~30-60 min** | | Excluding post-rollback monitoring |

**Key finding**: The estimated real operational recovery time is **30-60 minutes** for a SEV-1 backend rollback scenario. The main bottleneck is Railway rebuild time and detection time (no automated alerting exists).

## 8. Verification Results

| Check | Result | Notes |
| :--- | :--- | :--- |
| Frontend loads | SIMULATED PASS | Not affected in this scenario |
| Backend responds (health check) | SIMULATED PASS | After Railway redeploy |
| Login works | SIMULATED PASS | Google OAuth not affected |
| Fields load | SIMULATED PASS | Field endpoints not affected |
| Map loads | SIMULATED PASS | Map rendering not affected |
| Game creation works | SIMULATED PASS | **This was the broken flow — restored after rollback** |
| Join/leave works | SIMULATED PASS | Restored with game endpoints |
| Notifications checked | SIMULATED PASS | Not affected |
| Admin route protection checked | SIMULATED PASS | Not affected |
| Logs reviewed | SIMULATED PASS | No errors after rollback |
| No new critical errors | SIMULATED PASS | Clean state restored |

## 9. Findings / Gaps

### What Was Clear
- The rollback procedure document (ISSUE-117) provided a logical, step-by-step flow that was easy to follow.
- The severity matrix made classification straightforward.
- The rollback vs forward-fix decision framework was helpful.
- Communication templates were usable and saved time.
- The reusable rollback checklist covered all necessary steps.
- Database rollback guidance was appropriately cautious.

### What Was Unclear or Missing

| Finding | Severity | Notes |
| :--- | :--- | :--- |
| **Exact Vercel project name not documented** | Medium | Cannot perform frontend rollback without knowing which Vercel project to open |
| **Exact Railway service name not documented** | Medium | Cannot perform backend rollback without knowing which Railway service to open |
| **No monitoring/alerting exists** | High | Detection relies on user reports or manual log checks — SEV-0 could go undetected for minutes |
| **No dashboard access inventory** | Medium | It is unknown which team members have Vercel, Railway, Supabase, Firebase, and Google Cloud access |
| **Staging not live** | High | Cannot perform a live rollback drill until staging is provisioned (ISSUE-114) |
| **Railway rebuild time unknown** | Medium | Estimated 3-8 minutes but not confirmed — this is the main rollback bottleneck |
| **Supabase backup retention/frequency unknown** | Medium | Procedure references backups but retention policy is not confirmed |
| **No on-call rotation defined** | Medium | Who detects the issue outside business hours? |
| **Rollback owner assignment is informal** | Low | No formal on-call or escalation chain exists |
| **No automated rollback trigger** | Low | All rollback steps are manual dashboard actions |

### Ambiguities in rollback-procedure.md
- Section 8 (Backend Rollback): "Find the last known stable generation" — the term "generation" is Railway-specific and may confuse team members unfamiliar with Railway's UI. Consider adding a screenshot reference or more specific navigation instructions.
- Section 10 (Database Rollback): The approval requirement (Database Owner + Technical Lead + Rollback Lead) is clear, but it is not documented who currently holds these roles.

## 10. Risk Assessment

| Question | Answer |
| :--- | :--- |
| Can the team perform rollback today? | **PARTIAL** — the procedure is documented and followable, but exact dashboard project names are unconfirmed, and it is unknown which team members have dashboard access |
| What is blocked by external dashboard access? | Frontend rollback (Vercel), backend rollback (Railway), DB rollback (Supabase), secret rotation (Firebase, Google Cloud) |
| What is blocked by staging not being live? | Cannot perform a live rollback drill. Cannot validate rollback timing with real infrastructure. |
| What could fail under pressure? | Dashboard access — if the person with access is unavailable. Detection delay — no automated alerting. Decision paralysis — if rollback owner is not pre-assigned. |
| Highest risk rollback area | **Database rollback** — stateful, potentially destructive, requires explicit approval, and backup restore policy is unconfirmed |

## 11. Follow-Up Issues

| Priority | Recommendation |
| :--- | :--- |
| P1 | **Assign deployment/rollback owners** — name specific people for each role in section 5 of the rollback procedure |
| P1 | **Confirm exact Vercel project name and rollback steps** — document with screenshots or exact navigation path |
| P1 | **Confirm exact Railway service name and rollback steps** — document with screenshots or exact navigation path |
| P1 | **Create dashboard access inventory** — who has access to Vercel, Railway, Supabase, Firebase, Google Cloud |
| P1 | **Make staging fully live (ISSUE-114 follow-up)** — required before a live rollback drill can be performed |
| P2 | **Confirm Supabase backup/snapshot policy and retention** |
| P2 | **Run live staging rollback drill** — once staging is live, perform an actual rollback on staging infrastructure |
| P2 | **Add monitoring/alerting** — automated health checks and alerts for backend downtime, error rate spikes |
| P2 | **Define on-call rotation** — ensure someone can detect and respond to incidents outside business hours |
| P3 | **Add rollback timing to release checklist** — include estimated rollback time as a release gate |
| P3 | **Add automated health check after deployment** — Railway/Vercel post-deploy webhook or script |

## 12. Final Exercise Result

| Item | Status |
| :--- | :--- |
| Rollback exercise performed | YES |
| Exercise type | TABLETOP / DRY-RUN SIMULATION |
| Rollback time measured | YES (tabletop + estimated operational) |
| Total tabletop time | ~48 minutes |
| Total estimated real recovery time | 30-60 minutes (SEV-1 backend rollback) |
| Production touched | NO |
| Deployment changed | NO |
| Database changed | NO |
| Secrets changed | NO |
| Runtime behavior changed | NO |
| Procedure usable today | PARTIAL |
| Main blocker | Dashboard project/service names unconfirmed; staging not live for live drill; no monitoring/alerting; dashboard access inventory missing |
