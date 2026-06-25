# Database Backup Strategy

## 1. Purpose

The database is the most critical asset in the yesh_mishak system. It contains users, fields, games, participation records, notification preferences, notifications, push tokens, field reports, moderation audit logs, and admin-related data.

This document defines the complete database backup and restore strategy. It is the source of truth for backup frequency, retention, restore process, and approval rules.

Key principles:
- Backup without restore testing is not enough. Backups must be verified.
- Production data must be protected from accidental loss, corruption, bad migrations, and security incidents.
- Restore procedures must be documented, practiced, and approved before execution.

## 2. Scope

| Area | Included |
| :--- | :--- |
| Production Supabase database | YES |
| Future staging Supabase database | YES (when provisioned) |
| Local development database | NO (disposable) |
| Schema (`backend/schema.sql`) | YES |
| Migrations (`backend/migrations/`) | YES |
| RLS policies | YES |
| User data | YES |
| Games and fields data | YES |
| Notifications and preferences | YES |
| Push tokens | YES |
| Field reports and moderation data | YES |
| Admin/user management audit data | YES |

## 3. Data Criticality Classification

| Table | Business Importance | Personal Data? | Recovery Priority | Data Loss Impact | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `users` | Critical | YES (email, phone, Google sub, name, picture) | P0 | Users cannot log in or be identified | Core identity table |
| `fields` | Critical | Minimal (added_by UUID) | P0 | Map is empty, all game context lost | Core product data |
| `games` | Critical | Minimal (created_by UUID) | P0 | Active/scheduled games disappear | Core product data |
| `game_players` | Critical | YES (user-game association) | P0 | Participant data lost, counts wrong | Join/leave state |
| `notification_preferences` | High | YES (location prefs, field prefs) | P1 | Users stop receiving relevant notifications | User preferences |
| `notifications` | Medium | YES (user_id, content) | P2 | Notification history lost, unread counts reset | Historical, can regenerate |
| `push_tokens` | High | YES (device tokens linked to users) | P1 | Push notifications stop until re-registration | Re-registerable on next app visit |
| `field_reports` | Medium | YES (user_id, descriptions) | P2 | Moderation queue lost | Operational, not user-facing |
| `user_moderation_audit` | High | YES (user actions, admin actions) | P1 | Audit trail lost | Compliance/accountability |
| Schema / RLS policies | Critical | N/A | P0 | App cannot function, security policies lost | Must match deployed code |

## 4. Backup Objectives

| Metric | Target | Notes |
| :--- | :--- | :--- |
| **RPO** (Recovery Point Objective) | ≤ 24 hours (initial target) | Maximum acceptable data loss window |
| **RTO** (Recovery Time Objective) | ≤ 4 hours (initial target) | Maximum time to restore service |
| **Critical incident decision** | ≤ 30 minutes | Time to decide restore approach |
| **Future mature target** | PITR or ≤ 1 hour RPO | If Supabase plan supports Point-in-Time Recovery |

These are targets, not verified current capabilities. Actual RPO depends on Supabase backup frequency, which requires dashboard confirmation.

## 5. Backup Frequency Strategy

| Trigger | Frequency | Environment | Required? |
| :--- | :--- | :--- | :--- |
| Automated daily backup | Daily (minimum) | Production | YES |
| Before risky migration | Manual pre-change snapshot | Production | YES |
| Before major release | Verify latest backup exists | Production | YES |
| Before destructive data operation | Explicit backup/export | Production | YES |
| Staging backup | Daily or weekly | Staging (when live) | Optional |
| Local backup | None | Local | NO |

### Pre-Migration Backup Rule
Before any migration that adds, removes, or modifies columns, tables, constraints, or RLS policies in production:
1. Verify the latest automated backup exists and is recent.
2. If the migration is destructive (DROP, ALTER column type, remove constraint), take a manual snapshot first.
3. Document the backup timestamp in the migration PR.

## 6. Retention Strategy

| Backup Type | Retention | Notes |
| :--- | :--- | :--- |
| Daily automated backups | ≥ 7 days | Minimum retention for operational recovery |
| Weekly backups | ≥ 4 weeks | Longer-term recovery window |
| Monthly backups | ≥ 3 months | If supported and cost-effective |
| Pre-migration snapshots | Until post-release verification passes | At least 7 days after successful release |
| Security incident snapshots | Per incident/evidence policy | May need extended retention for investigation |

**Note**: Exact Supabase retention depends on the project plan level. This requires dashboard confirmation — see section 19.

## 7. Backup Types

| Type | What It Protects Against | Limitations |
| :--- | :--- | :--- |
| **Automated provider backups** | Accidental deletion, corruption, failed migrations | Frequency depends on Supabase plan; may not be real-time |
| **Point-in-Time Recovery (PITR)** | Any incident with precise recovery point | Only available on certain Supabase plans; requires confirmation |
| **Manual SQL/schema export** | Schema loss, need to recreate DB structure | Does not include data unless explicitly exported |
| **Logical dumps** (`pg_dump`) | Full data + schema recovery | Requires direct DB access; dump files contain PII |
| **Pre-migration snapshots** | Bad migration rollback | Must be taken manually before risky changes |
| **Configuration backups** (env/schema/RLS) | Environment drift, policy loss | Schema is in `backend/schema.sql`; RLS policies in migrations |

## 8. Supabase Backup Strategy

### Required Dashboard Checks
The following must be verified by the Supabase project owner:

- [ ] Automated backups are enabled for the production project.
- [ ] Backup frequency is confirmed (daily minimum).
- [ ] Retention period is confirmed.
- [ ] PITR availability is confirmed (depends on Supabase plan).
- [ ] Restore options are confirmed (full restore, table-level, PITR).
- [ ] Backups include schema, data, extensions, and RLS policies.
- [ ] Backup access is restricted to authorized team members.

### What Cannot Be Confirmed From Repository Alone
- Supabase plan level (Free, Pro, Team, Enterprise)
- Whether automated backups are enabled
- Backup frequency and retention
- Whether PITR is available
- Restore process and options in the dashboard
- Backup encryption details

**Status**: Requires Supabase dashboard access for confirmation.

### Required Owner
The Supabase project owner (Lead Architect / DevOps Owner) is responsible for verifying and maintaining backup settings.

## 9. Schema / Migration Backup Strategy

### Schema Source of Truth
- `backend/schema.sql` contains the base database schema.
- `backend/migrations/` contains incremental migration files.
- Both are version-controlled in git and can be used to recreate the schema from scratch.

### Current Migrations
The following migration files exist in `backend/migrations/`:
- `field_reports.sql`
- `fields_has_nets.sql`
- `game_cancellation.sql`
- `in_app_notifications.sql`
- `issue_079_missing_indexes.sql`
- `join_game_atomic.sql`
- `jwt_token_revocation.sql`
- `manual_auth.sql`
- `notification_preferences_service_role_grants.sql`
- `push_notifications.sql`
- `scheduled_games.sql`
- `user_moderation.sql`

### Migration Rules
1. Review all migrations before applying to production.
2. Take a backup or verify latest backup before destructive migrations.
3. Prefer forward-fix migrations over rollback (add new migration to correct, do not drop).
4. Never blindly DROP tables, columns, or constraints in production.
5. RLS policy changes must be reviewed for security impact before and after application.
6. See [docs/rollback-procedure.md](rollback-procedure.md) section 10 for database rollback guidance.

## 10. Restore Process

### Step-by-Step Restore Procedure

1. **Declare restore incident** — announce to team that a database restore may be needed.
2. **Assign restore owner** — one person leads the restore process.
3. **Freeze deployments** — stop all merges and deployments.
4. **Preserve evidence/logs** — capture error logs, screenshots, and user reports before making changes.
5. **Identify affected environment** — production or staging.
6. **Identify restore reason** — accidental deletion, bad migration, corruption, security incident, etc.
7. **Identify target restore point** — which backup to restore to (timestamp).
8. **Confirm backup availability** — verify the target backup exists in Supabase dashboard.
9. **Confirm data-loss window** — calculate how much data will be lost between backup and now.
10. **Obtain approval** — see section 11 for approval rules.
11. **Restore in staging/isolated environment first** — if possible, test the restore before applying to production.
12. **Validate restored database** — run verification checklist (section 12).
13. **Decide: restore production or forward-fix** — based on validation results.
14. **Restore production if approved** — apply the restore to the production database.
15. **Run smoke tests** — full application verification after restore.
16. **Monitor logs** — watch for 30-60 minutes for errors.
17. **Communicate status** — send update to team and users if impacted.
18. **Open follow-up issues** — document root cause and remediation.

## 11. Restore Approval Rules

| Scenario | Approval Required From |
| :--- | :--- |
| Production restore (any) | Technical Lead + Database Owner |
| Restore with data loss | Technical Lead + Database Owner + Product Owner |
| Security incident restore | Technical Lead + Security Owner |
| Restore affecting user accounts | Product Owner (user communication may be required) |
| Staging restore | Database Owner (no additional approval) |
| Local restore | Developer (no approval needed) |

### Rules
- Production restore always requires at least two approvals.
- Data-loss restore requires product/business owner awareness.
- Security incident restore follows the security incident handling process.
- User communication may be required if data loss affects user-visible state.

## 12. Restore Verification Checklist

After any restore, verify:

- [ ] Backend connects to the database without errors.
- [ ] Auth / user records are available (login works).
- [ ] Admin users have correct roles.
- [ ] Fields load via API (`GET /fields/`).
- [ ] Games load via API.
- [ ] Game participants (`game_players`) are correct.
- [ ] Notification preferences are available.
- [ ] Notifications are available (if expected).
- [ ] Push tokens are valid or safely invalidated (users can re-register).
- [ ] RLS policies are active and enforced.
- [ ] Critical API endpoints pass (health, auth, fields, games, notifications).
- [ ] Frontend smoke test passes (map loads, login works, game creation works).
- [ ] No obvious data corruption (spot-check key records).
- [ ] Backend logs are clean after restore.

## 13. Scenario Coverage

### Accidental Row Deletion
- **Impact**: Specific records lost (user, field, game, etc.)
- **Action**: Restore from latest backup if within RPO, or manually re-insert if data is known.
- **Data-loss risk**: Low if caught quickly and backup is recent.
- **Response**: Identify scope, restore targeted data if possible, full restore if widespread.
- **Follow-up**: Document cause, add safeguards (confirmation prompts, soft-delete).

### Bad Migration
- **Impact**: Schema mismatch, broken queries, potential data corruption.
- **Action**: Prefer forward-fix migration. If not possible, restore pre-migration snapshot.
- **Data-loss risk**: Medium — data written after migration may be lost on restore.
- **Response**: Roll back application code first (see rollback-procedure.md), then assess DB.
- **Follow-up**: Improve migration review process, require pre-migration backup verification.

### Dropped Table
- **Impact**: Complete loss of table data. Application errors on all related endpoints.
- **Action**: Restore from backup immediately. This is a SEV-0 incident.
- **Data-loss risk**: High — all data in the table since last backup is lost.
- **Response**: Declare incident, freeze deploys, restore, verify.
- **Follow-up**: Add DROP protection (require explicit approval, add migration review gate).

### Corrupted Data
- **Impact**: Invalid data in tables, broken constraints, inconsistent state.
- **Action**: Identify scope. If localized, fix with targeted queries. If widespread, restore from backup.
- **Data-loss risk**: Depends on scope and backup recency.
- **Response**: Assess scope, decide targeted fix vs full restore.
- **Follow-up**: Root cause analysis, add data validation.

### Wrong Environment Connected to Production DB
- **Impact**: Staging or local code writing test data to production, or production code reading staging data.
- **Action**: Immediately disconnect the wrong environment. Assess data contamination. Restore if needed.
- **Data-loss risk**: Medium — production data may be contaminated with test records.
- **Response**: Identify contaminated records, clean up or restore.
- **Follow-up**: Enforce environment variable separation (ISSUE-114), add startup environment verification.

### Supabase Outage
- **Impact**: All database operations fail. Application is fully down.
- **Action**: Wait for Supabase recovery. No local restore possible (managed service).
- **Data-loss risk**: Low — Supabase maintains redundancy.
- **Response**: Monitor Supabase status page. Communicate to users. No action on our side.
- **Follow-up**: Evaluate SLA requirements, consider multi-region if critical.

### Credential / Service-Role Key Leak
- **Impact**: Attacker has full database access bypassing RLS.
- **Action**: Rotate `SUPABASE_SERVICE_ROLE_KEY` immediately. Audit database for unauthorized changes. Restore if tampering detected.
- **Data-loss risk**: Depends on attacker actions.
- **Response**: Follow security incident process. Rotate all secrets. Audit and restore if needed.
- **Follow-up**: Investigate leak source, improve secret management.

### Malicious Admin Action
- **Impact**: Unauthorized data modification or deletion by a compromised or rogue admin.
- **Action**: Audit `user_moderation_audit` table. Identify affected records. Restore from backup if needed.
- **Data-loss risk**: Depends on scope of actions.
- **Response**: Revoke admin access, audit changes, restore affected data.
- **Follow-up**: Review admin access controls, add audit log alerts.

### Broken RLS Policy
- **Impact**: Users can read/write data they should not access.
- **Action**: Fix RLS policy immediately (forward-fix preferred). If data was exposed, follow security incident process.
- **Data-loss risk**: Low (data exposure, not loss).
- **Response**: Apply corrected policy, audit access logs.
- **Follow-up**: Add RLS policy testing to migration review.

### Notification Table Corruption / Spam
- **Impact**: Users receive incorrect or excessive notifications. Notification history corrupted.
- **Action**: Fix notification data. Disable notifications temporarily if spam (`DISABLE_GAME_CREATED_NOTIFICATIONS=True`).
- **Data-loss risk**: Low — notification data is regenerable.
- **Response**: Clean up bad records, restore preferences if corrupted.
- **Follow-up**: Add notification rate limits (ISSUE-099), improve validation.

### Push Token Data Issue
- **Impact**: Push notifications fail or go to wrong devices.
- **Action**: Invalidate affected tokens. Users re-register on next app visit.
- **Data-loss risk**: Low — tokens are re-registerable.
- **Response**: Clear affected tokens, monitor re-registration.
- **Follow-up**: Add token validation, separate staging/production tokens.

### User Account Data Corruption
- **Impact**: Users cannot log in, profile data incorrect, roles wrong.
- **Action**: Restore from backup. This is a SEV-0 incident if widespread.
- **Data-loss risk**: High — user account changes since backup are lost.
- **Response**: Restore, verify auth, communicate to affected users.
- **Follow-up**: Root cause analysis, add user data integrity checks.

### Field / Game Data Corruption
- **Impact**: Map shows incorrect fields, games have wrong state/participants.
- **Action**: Targeted data fix if localized. Full restore if widespread.
- **Data-loss risk**: Medium.
- **Response**: Run `scripts/audit_game_data_integrity.py`, fix or restore.
- **Follow-up**: Add data integrity monitoring.

### Staging Reset from Seed Data
- **Impact**: None on production. Staging data is reset.
- **Action**: Re-run seed scripts against staging Supabase project.
- **Data-loss risk**: None (staging data is synthetic).
- **Response**: Standard staging maintenance.
- **Follow-up**: Create seed data scripts (ISSUE-131).

### Local DB Rebuild from Schema
- **Impact**: None on production. Developer rebuilds local environment.
- **Action**: Run `backend/schema.sql` and migration files against local database.
- **Data-loss risk**: None (local data is disposable).
- **Response**: Standard development workflow.

## 14. Staging and Local Backup Strategy

- **Staging**: When implemented (ISSUE-114), staging must use a separate Supabase project. Staging data is synthetic and can be reset from seed scripts. Formal backups are optional but recommended for test continuity.
- **Local**: Local development databases are disposable. Developers can rebuild from `backend/schema.sql` and migration files. No formal backup is required.
- **Production PII**: Never copy production data to staging or local environments. Always use synthetic test data.
- **Seed data**: A staging seed data process is a follow-up task (ISSUE-131).

## 15. Security and Privacy Considerations

- **Backups contain personal data** (emails, phone numbers, names, Google IDs, location preferences, device tokens). Treat backups with the same security as production data.
- **Access to backups must be restricted** to authorized team members (Database Owner, Technical Lead).
- **Backup exports (SQL dumps, CSV exports) must never be committed** to the repository.
- **Do not send backups over insecure channels** (unencrypted email, public Slack channels, etc.).
- **Minimize who can restore production** — only pre-approved roles per section 11.
- **Restore process may expose PII** in logs or output. Ensure restore is performed in a secure environment.
- **Security incidents require evidence preservation** — do not delete or overwrite backups that may contain evidence of unauthorized access.
- **Retention must balance recovery needs and data minimization** — do not retain backups longer than necessary without justification.

## 16. Backup Monitoring / Audit

### Regular Verification Cadence

| Cadence | Action | Owner |
| :--- | :--- | :--- |
| Monthly | Verify backup exists and is recent in Supabase dashboard | Database Owner |
| Monthly | Confirm retention settings are unchanged | Database Owner |
| Quarterly | Perform restore drill (tabletop or live staging) | Database Owner + Technical Lead |
| Before each release | Verify latest backup exists | Release Owner |

### Backup Audit Record

| Field | Value |
| :--- | :--- |
| Date | |
| Backup timestamp verified | |
| Retention confirmed | |
| Restore option confirmed | |
| Owner | |
| Notes | |

## 17. Restore Drill Policy

| Drill Type | Frequency | Environment | What to Measure |
| :--- | :--- | :--- | :--- |
| Tabletop restore drill | Quarterly | Simulated | Procedure clarity, decision time, role assignments |
| Live staging restore drill | Semi-annually (after staging is live) | Staging | Actual restore time, verification completeness |

### Success Criteria
A restore drill is successful if:
- Restore owner can follow the procedure without ambiguity.
- Backup is located within 5 minutes.
- Approval chain is completed within 15 minutes.
- Restore is executed within the target RTO.
- Verification checklist passes.
- Total time is documented.

### What Must Be Measured
- Time to identify the correct backup
- Time to obtain approval
- Time to execute restore
- Time to verify restored database
- Total RTO achieved

## 18. Emergency Restore Checklist

Copy this for each restore event:

```
## Database Restore — <date> — <scenario>

- [ ] Freeze deployments
- [ ] Assign restore owner
- [ ] Identify incident/scenario
- [ ] Preserve evidence (logs, screenshots, user reports)
- [ ] Identify target restore point (backup timestamp)
- [ ] Confirm backup availability in Supabase dashboard
- [ ] Estimate data-loss window (time between backup and incident)
- [ ] Get approval (Technical Lead + Database Owner; add Product Owner if data loss)
- [ ] Restore in staging/isolated environment first (if possible)
- [ ] Verify restored DB (run checklist from section 12)
- [ ] Restore/fix production if approved
- [ ] Run smoke tests (auth, fields, games, notifications, admin)
- [ ] Monitor logs for 30-60 minutes
- [ ] Communicate status to team
- [ ] Open post-incident follow-up issues

Restore owner: ___
Approved by: ___
Completed at: ___
Data-loss window: ___
Verified by: ___
```

## 19. Known Gaps / Needs Confirmation

| Gap | Status | Required Action |
| :--- | :--- | :--- |
| Supabase plan level | Needs confirmation | Check Supabase dashboard |
| Automated backups enabled | Needs confirmation | Verify in Supabase dashboard |
| Backup frequency | Needs confirmation | Verify in Supabase dashboard |
| Retention period | Needs confirmation | Verify in Supabase dashboard |
| PITR availability | Needs confirmation | Depends on Supabase plan |
| Backup encryption details | Needs confirmation | Check Supabase documentation for plan |
| Restore process in dashboard | Needs confirmation | Test or document with screenshots |
| Backup dashboard owner | Needs confirmation | Assign explicitly |
| Restore permissions | Needs confirmation | Document who has access |
| Staging live status | Not live (ISSUE-114) | Waiting for external dashboard setup |
| Seed data process | Not implemented | ISSUE-131 |
| Automated backup monitoring | Not implemented | Future follow-up |
| Restore drill not yet performed live | Not done | Requires staging environment |

## 20. Recommended Follow-Up Issues

1. **Confirm Supabase backup settings and retention** — verify plan, frequency, retention, PITR in dashboard (P1).
2. **Document Supabase restore owner/access** — assign named owner, document who has dashboard access (P1).
3. **Create staging seed data process** — ISSUE-131 (P2).
4. **Run database restore tabletop drill** — simulate a restore scenario with the team (P2).
5. **Run live staging restore drill** — after staging is live, perform actual restore (P2).
6. **Add backup verification to release checklist** — verify latest backup exists before each release (P2).
7. **Define database migration preflight checklist** — require backup verification before destructive migrations (P2).
8. **Document RLS restore verification steps** — ensure policies are validated after any restore (P2).
9. **Create dashboard access inventory** — who has Supabase, Railway, Vercel, Firebase, Google Cloud access (P1).
10. **Define production data export prohibition policy** — document rules against exporting production PII (P2).

## 21. Final Result

| Item | Status |
| :--- | :--- |
| Backup strategy exists | YES |
| Frequency defined | YES (daily minimum, pre-migration snapshots) |
| Retention defined | YES (7-day daily, 4-week weekly, 3-month monthly targets) |
| Restore process defined | YES (18-step procedure) |
| Scenarios covered | YES (15 scenarios) |
| Restore approval rules defined | YES |
| Restore verification checklist defined | YES |
| Emergency restore checklist included | YES |
| Restore drill policy defined | YES |
| Runtime behavior changed | NO |
| DB schema changed | NO |
| Production backup/restore performed | NO |
