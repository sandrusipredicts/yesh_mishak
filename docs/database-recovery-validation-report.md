# Database Recovery Validation Report

## 1. Purpose

This report documents the ISSUE-120 database recovery validation exercise for `yesh_mishak`.

A backup that has not been restored or walked through is not reliable. The purpose of this exercise is to validate whether the documented database backup and restore strategy can be followed safely, what recovery timing should be expected, and what gaps still block a fully verified production recovery process.

Exercise type: **TABLETOP / DRY-RUN RESTORE VALIDATION**.

No live staging restore was performed because the repository documentation shows that the dedicated staging Supabase environment is planned but not yet live. No production database restore was performed.

## 2. Validation Metadata

| Field | Value |
| :--- | :--- |
| Issue | ISSUE-120: Validate database recovery process |
| Date | 2026-06-25 |
| Branch | `issue-120-validate-database-recovery-process` |
| Exercise type | TABLETOP / DRY-RUN |
| Facilitator | Codex |
| Participants | Not recorded |
| Target environment | Simulated isolated/staging restore target |
| Scenario name | Bad migration or accidental data change corrupts game/field-related data |
| Backup strategy used | ISSUE-119 database backup strategy |
| Related documents | `docs/database-backup-strategy.md`, `docs/rollback-procedure.md`, `docs/rollback-simulation-report.md`, `docs/staging-setup.md`, `docs/staging-environment-strategy.md`, `docs/environment-inventory.md`, `docs/deployment-process.md`, `docs/release-checklist-template.md`, `backend/schema.sql` |

## 3. Dependency Verification

| Dependency item | Result | Evidence |
| :--- | :--- | :--- |
| ISSUE-119 exists | YES | `docs/product-decisions.md` contains `ISSUE-119: Database Backup Strategy`. |
| `docs/database-backup-strategy.md` exists | YES | Dedicated backup and restore strategy document is present. |
| Backup frequency strategy available | YES | ISSUE-119 defines daily production backups as the minimum and manual pre-change snapshots before risky migrations. |
| Retention strategy available | YES | ISSUE-119 defines daily, weekly, monthly, pre-migration, and security incident retention targets. |
| Restore process available | YES | ISSUE-119 defines an 18-step restore process and verification checklist. |
| Dependency note | VERIFIED | The task dependency is ISSUE-119. Any reference to ISSUE-11 is treated as a typo. |

## 4. Preconditions

| Precondition | Result | Notes |
| :--- | :--- | :--- |
| Staging DB exists | NO / NOT VERIFIED | `docs/staging-setup.md` and `docs/staging-environment-strategy.md` state staging is prepared/planned but not fully live. |
| Production was touched | NO | No production restore, dashboard action, export, or query was performed. |
| Production data was exported | NO | No production data, PII, dump, or backup artifact was copied into the repository. |
| Restore command was run | NO | Exercise was tabletop/dry-run only. |
| Database schema was changed | NO | No migrations or schema edits were made. |
| Secrets were accessed or committed | NO | No `.env` files, credentials, or dashboard secrets were accessed or committed. |
| Supabase dashboard access was available | NO | Dashboard access was not available in this repository-only exercise. |
| PITR/backup availability was verified | BLOCKED | Needs Supabase dashboard confirmation. |

## 5. Scenario Description

| Scenario element | Description |
| :--- | :--- |
| Failure trigger | A bad migration or accidental data update corrupts game/field-related production data. |
| Affected tables | `fields`, `games`, `game_players`, and possibly `notification_preferences`, `notifications`, `push_tokens`, and `field_reports` depending on side effects. |
| User/business impact | Map data may be wrong, games may disappear or show incorrect player counts, users may be unable to join games, and notifications may reference invalid games or fields. |
| Data-loss risk | Any restore point before the corruption can lose legitimate changes made after that point. |
| Assumed bad release/change | A schema migration or manual data operation corrupts field status, game status, participant rows, or related notification data. |
| Target restore point | Last known-good point immediately before the bad migration/data operation. In this dry run, the simulated target is "just before the corrupting change on 2026-06-25". |
| Severity classification | P0 if production game/field data is corrupted and core app flows are unavailable or misleading. |

## 6. Restore Decision Walkthrough

| Step | Dry-run outcome |
| :--- | :--- |
| Incident declared | Simulated as a P0 database integrity incident. |
| Restore owner assigned | BLOCKED: role is documented conceptually, but a named database restore owner/access inventory is not confirmed. |
| Deployments frozen | Simulated per rollback and deployment procedures. |
| Evidence preserved | Simulated: preserve logs, failing requests, bad migration identifier, timestamps, and affected records without exporting PII into repo files. |
| Affected environment identified | Production in the scenario; no production system was touched during this exercise. |
| Restore reason identified | Corruption affects core field/game data and may be too broad for a safe forward-fix. |
| Target restore point selected | Simulated: timestamp immediately before the bad change. |
| Backup availability checked/simulated | BLOCKED: repository defines the check, but actual Supabase backup/PITR availability needs dashboard confirmation. |
| Data-loss window estimated | Up to 24 hours under the documented daily-backup minimum; lower if PITR is enabled, but PITR is not verified. |
| Approval required | Technical Lead + Database Owner; add Product Owner when data loss is expected; add Security Owner if security-related. |
| Restore vs forward-fix decision | Dry-run decision: prefer isolated restore validation first; production restore only if approved and safer than forward-fix. |
| Production restore decision | NO production restore performed or approved in this task. |

## 7. Restore Execution Walkthrough

No live restore was performed.

Dry-run operational steps that would be performed:

1. Freeze production deployments and stop any pending database migrations.
2. Assign a restore owner with Supabase production access.
3. Identify the exact bad change and the last known-good timestamp.
4. Open the Supabase production project dashboard.
5. Confirm available backups, retention, and PITR status. **Needs confirmation.**
6. Estimate data loss between the target restore point and current time.
7. Obtain required approvals before any production restore.
8. Prefer restoring to an isolated/staging Supabase project first. **Blocked until staging Supabase exists.**
9. Verify schema, RLS/policies, grants, critical tables, and app smoke flows against the isolated restore.
10. Decide whether to forward-fix production or restore production.
11. If production restore is approved, perform the provider-supported restore action in Supabase. **Exact UI/CLI steps need dashboard confirmation.**
12. Run the restore verification checklist.
13. Re-enable deployments only after verification passes.
14. Document final timing, data-loss window, and follow-up fixes.

Estimated restore execution time for a real operation: **30-90 minutes after approvals and dashboard access are available**, plus verification time. This is an estimate only because no live Supabase restore was executed.

## 8. Restore Verification Checklist

| Verification item | Result | Evidence | Notes |
| :--- | :--- | :--- | :--- |
| App connects to DB | SIMULATED | `backend/app/db/supabase.py` creates Supabase clients from configured env vars. | Requires restored environment env vars and smoke test. |
| Auth/user records available | SIMULATED | `backend/schema.sql` defines `users`; auth docs require user/admin records. | Verify user rows and auth compatibility in restored target. |
| Admin users/roles correct | SIMULATED | `users.role` exists with `user`/`admin` check. | Must verify at least one intended admin after restore. |
| Fields load | SIMULATED | `fields` table and field indexes exist in schema. | Run `GET /fields/` smoke test after restore. |
| Games load | SIMULATED | `games` table and indexes exist in schema. | Run game list/detail smoke checks after restore. |
| Game participants correct | SIMULATED | `game_players` table has unique `(game_id, user_id)`. | Compare player counts with `games.players_present`. |
| Notification preferences available | SIMULATED | `notification_preferences` table and indexes exist. | Verify user-scoped preferences after restore. |
| Notifications available if expected | SIMULATED | `notifications` table and indexes exist. | Verify unread count and inbox behavior. |
| Push tokens valid or safely invalidated | BLOCKED | Push token table exists in migrations, but live restored token validity cannot be verified without staging/FCM. | Avoid sending to production tokens in staging. |
| RLS policies active | BLOCKED | Schema includes some RLS/grants, but full live policy state requires Supabase inspection. | Needs dashboard/SQL verification. |
| Critical API endpoints pass | SIMULATED | Staging smoke checklist defines backend/auth/fields/games/admin/notification checks. | Requires live isolated restore target. |
| Frontend smoke test passes | SIMULATED | Staging smoke checklist exists. | Requires staging frontend/backend connected to restored DB. |
| No obvious data corruption | SIMULATED | Verification method defined. | Requires SQL checks and API smoke results. |
| Logs checked | SIMULATED | Release checklist and staging smoke checklist include log review. | Requires Railway/Supabase logs for actual restore. |

## 9. Table / Data Area Verification

| Data area | Recovery priority | Verification method | Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `users` | P0 | Confirm core user rows, admin role rows, status fields, and token validity assumptions. | SIMULATED | Contains PII; do not export to repo. |
| `fields` | P0 | Confirm approved fields, coordinates, status, approval status, `verified`, and required columns. | SIMULATED | Core map data. |
| `games` | P0 | Confirm active/scheduled games, status, scheduled times, creator links, and player limits. | SIMULATED | Core gameplay data. |
| `game_players` | P0 | Confirm participant rows, uniqueness, and alignment with game player counts. | SIMULATED | High risk for join/leave correctness. |
| `notification_preferences` | P1 | Confirm user-scoped city/radius/specific-field preferences. | SIMULATED | Important for notification targeting. |
| `notifications` | P2 | Confirm inbox data, unread counts, game/field references, and duplicate-prevention constraints. | SIMULATED | Some notification history can be stale after restore. |
| `push_tokens` | P1 | Confirm tokens are environment-safe or invalidated in staging. | BLOCKED | Needs restored DB and separate staging Firebase. |
| `field_reports` | P2 | Confirm report rows, statuses, reviewer links, and field links. | SIMULATED | Moderation continuity. |
| `user_moderation_audit` / admin roles | P1 | Confirm audit rows and `users.role` admin assignments. | SIMULATED | Audit logs should not be replaced by app logs. |
| Schema/RLS policies | P0 | Confirm tables, indexes, grants, RLS enablement, and policies in Supabase after restore. | BLOCKED | Needs Supabase dashboard or SQL access. |

## 10. Timing Measurement

Measured as tabletop elapsed time / estimated operational recovery time.

| Step | Tabletop elapsed time | Estimated real operational time | Bottleneck? | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Scenario identification | 5 minutes | 5-15 minutes | NO | Corrupt field/game data is a clear P0 scenario. |
| Target restore point selection | 6 minutes | 10-20 minutes | NO | Depends on bad migration timestamp, logs, and deployment history. |
| Backup availability confirmation | 4 minutes | 10-30 minutes | YES | Requires Supabase dashboard access and confirmation of backups/PITR. |
| Approval | 5 minutes | 15-30 minutes | YES | Named approvers and access path need confirmation. |
| Restore execution | 0 minutes live / simulated only | 30-90 minutes | YES | No live restore performed; real time depends on Supabase plan/data size. |
| DB verification | 12 minutes | 30-60 minutes | YES | Needs SQL checks and RLS/policy verification. |
| App smoke verification | 8 minutes | 20-40 minutes | NO | Use staging smoke checklist once staging exists. |
| Communication | 5 minutes | 10-20 minutes | NO | Status updates and final incident notes. |
| Total estimated recovery time | 45 minutes tabletop | 2-4 hours | YES | Estimate assumes dashboard access and usable backup are available. |

## 11. Result Summary

| Result item | Value |
| :--- | :--- |
| Restore validation performed | YES |
| Restore type | TABLETOP / DRY-RUN |
| Restore successful | SIMULATED |
| Recovery time measured | YES |
| Total measured/estimated recovery time | 45 minutes tabletop elapsed / 2-4 hours estimated operational recovery |
| Procedure usable today | PARTIAL |
| Main blocker | Supabase backup/PITR settings, restore steps, dashboard access, and staging restore target are not verified/live. |

## 12. Findings / Gaps

- Supabase backup/PITR dashboard confirmation is missing.
- Supabase backup retention and available restore windows are not verified.
- Exact Supabase restore UI/CLI steps are not confirmed from a live dashboard.
- Dedicated staging Supabase database is not live.
- No live staging restore drill has been performed.
- No staging seed data process is implemented.
- Restore owner and dashboard access inventory are not confirmed.
- Automated backup monitoring is not implemented.
- RLS restore verification needs an executable checklist or SQL script.
- Push token restore handling needs a staging-safe validation path to avoid messaging production devices.

## 13. Risk Assessment

| Risk | Assessment |
| :--- | :--- |
| Highest risk restore area | `games` and `game_players`, because mismatched game status/player counts can break core user flows. |
| Risk of data loss | High for production restore if using daily backups; lower if PITR is enabled, but PITR is unverified. |
| Risk of restoring stale data | Medium to high; notifications, game joins, field submissions, and moderation actions after the restore point may be lost. |
| Risk of breaking auth/admin/RLS | High if restore does not preserve users, roles, grants, and RLS/policy state. |
| Risk of restoring into wrong environment | High until staging and production project names/access controls are clearly separated and documented. |
| Risk of exposing PII during restore | High if production dumps or screenshots are copied into tickets/repo; this exercise avoided that. |
| Risk from missing dashboard access | High; restore timing and feasibility cannot be guaranteed without confirmed access. |

## 14. Follow-Up Issues

| Priority | Follow-up |
| :--- | :--- |
| P0 | Confirm Supabase backup/PITR settings for production. |
| P0 | Confirm Supabase backup retention and restore windows. |
| P0 | Assign database restore owner and backup owner. |
| P0 | Create dashboard access inventory for Supabase, Railway, and Vercel. |
| P0 | Create dedicated staging Supabase project. |
| P0 | Run a live staging restore drill with synthetic data. |
| P1 | Add restore verification checklist to the release checklist. |
| P1 | Add executable RLS restore verification checklist or SQL script. |
| P1 | Create staging seed data process. |
| P1 | Add automated backup monitoring and failed-backup alerts. |
| P1 | Document production restore approval chain with named roles/contacts. |

## 15. Final Validation Result

| Final item | Result |
| :--- | :--- |
| Database recovery validation report exists | YES |
| Restore process validated | PARTIAL |
| Exercise type | TABLETOP / DRY-RUN |
| Restore time measured | YES |
| Production touched | NO |
| Production data exported | NO |
| Database schema changed | NO |
| Runtime behavior changed | NO |
| Database dumps committed | NO |
| Secrets committed | NO |
