# Production Support Handbook

**Created:** 2026-06-23 (ISSUE-054)
**Status:** Approved
**Audience:** System operators, admins, and anyone on support rotation

This handbook covers day-to-day production support operations. A new operator should be able to follow it without knowing the full codebase.

---

## Table of Contents

1. [Handling User Reports](#1-handling-user-reports)
2. [Handling Incorrect Fields](#2-handling-incorrect-fields)
3. [Handling Problematic Games](#3-handling-problematic-games)
4. [Handling Abusive Users](#4-handling-abusive-users)
5. [Severity Levels](#5-severity-levels)
6. [Support Workflow](#6-support-workflow)
7. [Checklists](#7-checklists)
8. [Operational Commands and Tools](#8-operational-commands-and-tools)
9. [What Not to Do](#9-what-not-to-do)
10. [Documentation Templates](#10-documentation-templates)
11. [Related Documentation](#11-related-documentation)
12. [Future Improvements](#12-future-improvements)

---

## 1. Handling User Reports

### Where reports appear

User reports are stored in the `field_reports` table and visible to admins via:

| Endpoint | Purpose |
|---|---|
| `GET /admin/field-reports` | List all field reports |
| `PATCH /admin/field-reports/{id}/status` | Update report status (`open` → `in_review` → `resolved` / `rejected`) |

Report categories (from schema):
`wrong_location`, `field_does_not_exist`, `field_closed`, `under_renovation`, `private_field`, `duplicate_field`, `wrong_information`, `other`

### How to triage

| Step | Action |
|---|---|
| 1 | Read the report category and description |
| 2 | Identify the affected field (`field_id`) |
| 3 | Check the field's current status, approval_status, and verified flag |
| 4 | Cross-reference with GovMap or satellite imagery if location-related |
| 5 | Classify severity (see [Section 5](#5-severity-levels)) |
| 6 | Choose action per table below |

### Report actions

| Report category | Likely action | Field change needed? |
|---|---|---|
| `wrong_location` | Verify on map. If confirmed, correct field coordinates. | Yes — update lat/lng |
| `field_does_not_exist` | Verify on GovMap/satellite. If confirmed, reject or mark field closed. | Yes — reject or set status=closed |
| `field_closed` | Verify. If confirmed, set field status to `closed` per ISSUE-047. | Yes — `PATCH /admin/fields/{id}/status` → closed |
| `under_renovation` | Verify. If confirmed, set field status to `renovation`. | Yes — `PATCH /admin/fields/{id}/status` → renovation |
| `private_field` | Verify access restrictions. If confirmed, set status=closed. | Yes — close field |
| `duplicate_field` | Check `GET /admin/fields/duplicates`. If confirmed, reject the duplicate. | Possibly — reject one copy |
| `wrong_information` | Verify claim. If correct, update the field metadata. | Yes — correct metadata |
| `other` | Read description carefully. Classify manually. | Depends |

### When to escalate

- Report alleges safety hazard (broken glass, flooding, structural damage)
- Report accuses a specific person of misconduct
- Report suggests coordinated manipulation (multiple fake reports on same field)
- Report involves legal or privacy concerns

### Documenting actions

After handling a report, update its status via `PATCH /admin/field-reports/{id}/status`:
- `in_review` — investigation in progress
- `resolved` — action taken, issue addressed
- `rejected` — report is invalid, spam, or incorrect

Use the [Report Handling Note template](#report-handling-note) in Section 10.

Policy reference: [user-generated-content-policy.md](user-generated-content-policy.md) (ISSUE-052)

---

## 2. Handling Incorrect Fields

### Available admin endpoints

| Endpoint | Purpose |
|---|---|
| `GET /admin/fields` | List all fields (any status) |
| `GET /admin/fields/pending` | List fields awaiting approval |
| `POST /admin/fields/{id}/approve` | Approve field (sets verified=true, approval_status=approved) |
| `POST /admin/fields/{id}/reject` | Reject field (sets verified=false, approval_status=rejected) |
| `PATCH /admin/fields/{id}/status` | Change field status (open/closed/renovation) |
| `GET /admin/fields/duplicates` | List suspected duplicates |

### Decision table

| Problem | How to verify | Action |
|---|---|---|
| **Wrong location** | Compare coordinates to GovMap/satellite | Correct coordinates in DB, or reject if location is completely fake |
| **Duplicate field** | Check `/admin/fields/duplicates`; compare names, coordinates | Keep the better-quality record, reject the duplicate. Per ISSUE-041: Admin > GovMap > User submission |
| **Fake field** | Location doesn't exist on any map source | Reject via `POST /admin/fields/{id}/reject` |
| **Closed field** | Verify via report, GovMap, or site visit confirmation | `PATCH /admin/fields/{id}/status` → `closed` (per ISSUE-047) |
| **Renovation field** | Verify via report or local knowledge | `PATCH /admin/fields/{id}/status` → `renovation` |
| **Missing metadata** | Field approved but missing surface_type, city, etc. | Update metadata directly. Do not reject an otherwise valid field for missing optional data. |
| **Source-of-truth conflict** | User submission contradicts GovMap data | GovMap data takes precedence per ISSUE-041. Admin corrections override both. |
| **Reopening a closed field** | Report or evidence that field is accessible again | `PATCH /admin/fields/{id}/status` → `open` |

### Source-of-truth hierarchy (ISSUE-041)

1. **Admin corrections** — highest authority
2. **GovMap data** — trusted baseline
3. **User submissions** — require verification
4. **User reports** — supporting evidence only

When data conflicts, follow this hierarchy. Document the conflict in a note.

Policy references: [ISSUE-041](#11-related-documentation), [ISSUE-047](#11-related-documentation), [ISSUE-049](#11-related-documentation)

---

## 3. Handling Problematic Games

### Available admin endpoints

| Endpoint | Purpose |
|---|---|
| `GET /admin/games` | List games (supports `?filter=active`, `?filter=finished`, or all) |
| `POST /admin/games/{id}/close` | Admin-close an active game |
| `POST /admin/games/{id}/extend` | Extend an active game by 1 hour |
| `POST /admin/games/{id}/cancel` | Cancel an active scheduled game |

### Problem decision table

| Problem | How to detect | Action |
|---|---|---|
| **Game on wrong field** | User report; field_id doesn't match intended location | Cancel the game if active. Document the mismatch. |
| **Suspicious/fake game** | No real participants, fake-looking data | Cancel the game. Flag the creator for investigation. |
| **Invalid participant count** | `players_present < 0` or `players_present > max_players` | Run the [game data integrity audit](#8-operational-commands-and-tools). Document finding. Create remediation issue. |
| **Full/open status mismatch** | `status=full` but `players_present < max_players` (or vice versa) | Detected by audit. Document and create remediation issue. |
| **Game on inactive field** | Active game on a closed/renovation/unapproved field | Cancel the game via `POST /admin/games/{id}/cancel`. These are blocked by ISSUE-048 for new games but may exist for pre-existing data. |
| **Duplicate active games** | Two open games on the same field at the same time | Cancel the duplicate. Keep the one with more participants. |
| **Scheduled game past start time** | `scheduled_at` in the past, game still active | Game should auto-expire. If it doesn't, close via admin endpoint. |
| **Cancelled/finished issues** | Missing `cancelled_at`, inconsistent status | Document. Create remediation issue. Do not manually edit. |

### When to run the audit

- After receiving multiple game-related reports
- During weekly operational review (per ISSUE-049 schedule)
- After any production incident affecting game data
- Before and after any manual data remediation

Policy references: [ISSUE-050](#11-related-documentation), [ISSUE-051](#11-related-documentation)

---

## 4. Handling Abusive Users

### Currently available admin actions

| Endpoint | Purpose |
|---|---|
| `POST /admin/users/{id}/ban` | Ban a user (sets status=banned) |
| `POST /admin/users/{id}/unban` | Unban a user (sets status=active) |
| `POST /admin/users/{id}/suspend` | Suspend a user (sets status=suspended) |
| `POST /admin/users/{id}/unsuspend` | Unsuspend a user (sets status=active) |

### What to do today

| Situation | Evidence to collect | Action |
|---|---|---|
| **Repeated fake field submissions** | 3+ rejected fake submissions from same user | Suspend user. Document evidence. |
| **Repeated spam** | 3+ rejected spam submissions | Suspend user. Document evidence. |
| **Offensive content** | 2+ content violations (ISSUE-053 moderation rejects these automatically now, but previously submitted content may exist) | Suspend or ban user. Document evidence. |
| **Coordinated abuse** | Multiple accounts submitting similar fake/spam content | Escalate immediately. Ban all involved accounts. |
| **Field status manipulation** | Repeated false reports trying to close a legitimate field | Reject all pending reports from user. Suspend user. |
| **Single minor offense** | One borderline submission | Note the incident. Do not punish for a single minor issue. |

### Evidence to collect before action

- [ ] User ID and email
- [ ] List of rejected submissions with dates
- [ ] Screenshots or content of violations (store internally, do not share)
- [ ] Pattern analysis (timing, targets, content similarity)
- [ ] Whether content moderation (ISSUE-053) flagged any submissions

### What NOT to do

- Do not ban a user without documented evidence
- Do not expose the user's private data in any report
- Do not contact the user directly through any unofficial channel
- Do not delete the user's account or data — only change status

### Not yet implemented

The following would improve abuse handling but do not exist yet:
- User trust/reputation score
- Moderation audit log (who banned whom, when, why)
- Support ticket tracking
- User-facing appeal process
- Automated abuse detection alerts

Policy references: [ISSUE-052](#11-related-documentation), [ISSUE-053](#11-related-documentation)

---

## 5. Severity Levels

| Level | Definition | Response time | Examples |
|---|---|---|---|
| **Critical** | Safety risk, data loss, or system-wide impact | **Same day** | Threats of violence in content, mass fake data injection, security breach, system outage |
| **High** | Clear policy violation or significant data integrity issue | **Within 2 business days** | Fake fields approved and visible, offensive content live on platform, active game on deleted field |
| **Medium** | Data inconsistency or moderate policy concern | **Within 5 business days** | Duplicate fields, wrong metadata, participant count mismatch, report requiring investigation |
| **Low** | Minor issue, cosmetic, or informational | **Next review cycle** | Slightly wrong coordinates, missing optional metadata, info-level audit finding |

### Escalation conditions

| Condition | Escalate to |
|---|---|
| Safety risk to any person | Team lead / product owner immediately |
| Legal or privacy concern | Team lead + legal if available |
| Coordinated abuse (multiple accounts) | Team lead for investigation |
| System-wide data integrity failure (many critical audit findings) | Engineering team |
| Unclear policy decision (none of the existing policies cover the situation) | Product owner for policy clarification |

---

## 6. Support Workflow

Follow this flow for every incoming report or issue:

```
1. RECEIVE
   └─ Report via field_reports, admin observation, or audit finding

2. IDENTIFY
   └─ What entity is affected? (field, game, user, system)
   └─ Look up the entity in admin endpoints

3. VERIFY
   └─ Is the report accurate?
   └─ Cross-reference with GovMap, satellite, audit data
   └─ Check related entities (games on this field, reports from this user)

4. CLASSIFY
   └─ Severity: Critical / High / Medium / Low
   └─ Type: field issue / game issue / user issue / data issue

5. CHOOSE ACTION
   └─ Use the decision tables in Sections 1-4
   └─ If no table covers this case, escalate

6. APPLY
   └─ Use admin API endpoints only
   └─ Do not modify DB directly
   └─ Do not delete records

7. DOCUMENT
   └─ Use templates from Section 10
   └─ Record what was done, why, and by whom

8. ESCALATE (if needed)
   └─ See escalation conditions in Section 5

9. FOLLOW UP
   └─ If the issue is systemic, create a follow-up issue
   └─ If similar issues recur, propose a process improvement
```

---

## 7. Checklists

### User Report Triage

- [ ] Read report category and description
- [ ] Identify affected field (field_id)
- [ ] Check field current status (open/closed/renovation)
- [ ] Check field approval_status and verified flag
- [ ] Verify claim against map data or other sources
- [ ] Classify severity
- [ ] Choose action from Section 1 decision table
- [ ] Update report status via admin endpoint
- [ ] Document action taken

### Field Correction

- [ ] Identify what is wrong (location, name, status, metadata)
- [ ] Verify the correct data from authoritative source (GovMap > user report)
- [ ] Check for active games on this field
- [ ] If changing status to closed/renovation: any active games will be blocked from new joins
- [ ] Apply correction via admin endpoint
- [ ] If rejecting: ensure no active games depend on this field
- [ ] Document the correction and source of truth used

### Problematic Game Investigation

- [ ] Identify the game (game_id, field_id, status)
- [ ] Check field status (is it open/approved/verified?)
- [ ] Check participant count vs max_players
- [ ] Check if game is expired (expires_at vs now)
- [ ] Check scheduled_at if it's a scheduled game
- [ ] Decide: close, cancel, or leave and document
- [ ] If cancelling: note the reason
- [ ] Run audit if multiple games are suspicious

### Abusive User Investigation

- [ ] Identify user (user_id)
- [ ] List all submissions by this user (fields, reports)
- [ ] Count rejected submissions
- [ ] Check for pattern (timing, targets, content)
- [ ] Check if content moderation (ISSUE-053) flagged any submissions
- [ ] Determine if threshold is met (3+ fake/spam or 2+ offensive)
- [ ] Choose action: warn (no mechanism yet), suspend, or ban
- [ ] Document evidence before acting
- [ ] Apply user moderation via admin endpoint

### Post-Incident Review

- [ ] What happened?
- [ ] When was it detected?
- [ ] How was it resolved?
- [ ] How long was the impact?
- [ ] Could it have been detected earlier?
- [ ] Is a process change needed?
- [ ] Is a code change needed? (create issue if yes)
- [ ] Document in a post-incident note

---

## 8. Operational Commands and Tools

### Game Data Integrity Audit (ISSUE-050)

```bash
cd backend

# Human-readable output
python -m scripts.audit_game_data_integrity

# Machine-readable JSON
python -m scripts.audit_game_data_integrity --json
```

- **Requires:** `SUPABASE_URL` and `SUPABASE_KEY` environment variables
- **Exit code:** `0` = no critical findings, `1` = critical findings exist
- **Documentation:** [game-data-integrity-audit.md](game-data-integrity-audit.md)
- **Last execution:** [audit results 2026-06-23](game-data-integrity-audit-results-2026-06-23.md)

### Admin API Endpoints Quick Reference

| Category | Endpoint | Method |
|---|---|---|
| **Users** | `/admin/users` | GET |
| | `/admin/users/{id}/ban` | POST |
| | `/admin/users/{id}/unban` | POST |
| | `/admin/users/{id}/suspend` | POST |
| | `/admin/users/{id}/unsuspend` | POST |
| **Fields** | `/admin/fields` | GET |
| | `/admin/fields/pending` | GET |
| | `/admin/fields/{id}/approve` | POST |
| | `/admin/fields/{id}/reject` | POST |
| | `/admin/fields/{id}/status` | PATCH |
| | `/admin/fields/duplicates` | GET |
| **Field Reports** | `/admin/field-reports` | GET |
| | `/admin/field-reports/{id}/status` | PATCH |
| **Games** | `/admin/games` | GET |
| | `/admin/games/{id}/close` | POST |
| | `/admin/games/{id}/extend` | POST |
| | `/admin/games/{id}/cancel` | POST |
| **Operations** | `/admin/reminders/scheduled-games/run` | POST |
| | `/admin/notifications/cleanup` | POST |
| **Stats** | `/admin/stats` | GET |

### Tools That Do NOT Exist Yet

| Tool | Purpose | Status |
|---|---|---|
| Admin dashboard UI | Visual moderation interface | Not implemented |
| Moderation audit log | Track who approved/rejected what | Not implemented |
| User activity log | View all submissions by a user | Not implemented — requires manual DB query |
| Automated alerts | Notify admins of critical audit findings | Not implemented |
| Support ticket system | Track report-to-resolution lifecycle | Not implemented |

---

## 9. What Not to Do

| Rule | Why |
|---|---|
| **Do not modify the production database directly** unless explicitly approved by engineering | Direct DB edits bypass validation, audit trails, and can break referential integrity |
| **Do not delete records** without a documented reason and approval | `ON DELETE CASCADE` on games.field_id means deleting a field destroys all its game history |
| **Do not expose user private data** in any report, note, or external communication | Privacy obligation — user emails, phone numbers, and IDs are internal only |
| **Do not bypass the UGC moderation policy** (ISSUE-052) | The policy exists to protect users and the platform |
| **Do not change field lifecycle policy ad hoc** | Follow ISSUE-047 policy. If the policy is wrong, create an issue to change it. |
| **Do not auto-fix audit findings** without creating a remediation issue first | Fixes need review. The audit is read-only for a reason. |
| **Do not punish users without evidence** | Collect and document evidence before any ban/suspend action |
| **Do not approve fields without verification** | Every approval should pass the admin checklist (ISSUE-052, Section 8) |
| **Do not run destructive SQL** (DELETE, TRUNCATE, DROP) in production | Always use admin API endpoints instead |
| **Do not share admin credentials** | Each admin should use their own account |

---

## 10. Documentation Templates

### Report Handling Note

```
Date: YYYY-MM-DD
Operator: [name/admin ID]
Report ID: [field_report ID]
Field ID: [affected field ID]
Report category: [category]
Severity: [critical/high/medium/low]

Summary: [What was reported]
Verification: [How the claim was verified — GovMap, satellite, etc.]
Action taken: [approved/rejected/in_review/resolved + specific changes]
Field changes: [If any field status/data was changed, list here]
Escalated: [yes/no — if yes, to whom]
Follow-up needed: [yes/no — if yes, describe]
```

### Field Correction Note

```
Date: YYYY-MM-DD
Operator: [name/admin ID]
Field ID: [field ID]
Field name: [field name]

Problem: [What was wrong — location, status, metadata, etc.]
Source of truth used: [GovMap / admin knowledge / user report / other]
Previous state: [What the field data was before correction]
New state: [What the field data is after correction]
Active games affected: [List game IDs if any, or "none"]
Related reports: [List report IDs if triggered by a report]
```

### Game Issue Note

```
Date: YYYY-MM-DD
Operator: [name/admin ID]
Game ID: [game ID]
Field ID: [field ID]
Game status: [open/full/finished/cancelled]

Problem: [What was wrong]
Detection method: [audit / user report / manual review]
Action taken: [closed / cancelled / documented only]
Reason: [Why this action was chosen]
Audit run: [yes/no — if yes, attach or link results]
```

### Abusive User Escalation Note

```
Date: YYYY-MM-DD
Operator: [name/admin ID]
User ID: [user ID]
User email: [INTERNAL ONLY — do not share externally]

Pattern: [What abuse pattern was observed]
Evidence:
  - [Date]: [Rejected submission / report — category and ID]
  - [Date]: [Rejected submission / report — category and ID]
  - [Date]: [Rejected submission / report — category and ID]
Threshold met: [Which threshold — 3+ fake, 3+ spam, 2+ offensive, coordinated]
Action taken: [suspended / banned / escalated / documented only]
Escalated to: [Name/role, if escalated]
```

### Follow-Up Issue Template

```
Title: [Short description of systemic problem]

## Context
- Discovered during: [report handling / audit / routine review]
- Date discovered: YYYY-MM-DD
- Affected entities: [field IDs, game IDs, user IDs]

## Problem
[Description of the systemic issue]

## Evidence
[Audit results, report IDs, or other supporting data]

## Recommended Fix
[What should be implemented or changed]

## Urgency
[Critical / High / Medium / Low]

## Related Issues
[List related ISSUE numbers]
```

---

## 11. Related Documentation

| Document | Relevance |
|---|---|
| [ISSUE-041: Source-of-Truth Policy](product-decisions.md) | Data authority hierarchy for fields |
| [ISSUE-047: Inactive Field Handling](product-decisions.md) | When to mark fields closed/renovation |
| [ISSUE-048: Inactive Field Lifecycle](product-decisions.md) | Runtime enforcement of field status |
| [ISSUE-049: Operational Field Review Schedule](operational-field-review-schedule.md) | Review cadence and SLA targets |
| [ISSUE-050: Game Data Integrity Audit](game-data-integrity-audit.md) | Audit tool documentation |
| [ISSUE-051: Audit Execution Results](game-data-integrity-audit-results-2026-06-23.md) | Most recent audit results |
| [ISSUE-052: UGC Policy](user-generated-content-policy.md) | Content moderation rules and admin checklist |
| [ISSUE-053: Content Moderation Validation](product-decisions.md) | Automated content validation in API |

---

## 12. Future Improvements

| Improvement | Description | Priority |
|---|---|---|
| **Admin support dashboard** | Web UI for viewing reports, fields, games, and user status in one place | High |
| **User blocking workflow** | Structured flow with required evidence, cooling period, appeal process | High |
| **Moderation audit log** | Persistent log of every admin action (approve, reject, ban, status change) with timestamp and admin ID | High |
| **Support ticket tracking** | Track report-to-resolution lifecycle with status, assignee, and SLA | Medium |
| **Automated alerts** | Notify admins when the game integrity audit finds critical issues | Medium |
| **Operator activity log** | Record all admin API calls for accountability | Medium |
| **Field duplicate merge workflow** | Safe merge of duplicate fields preserving game history from both | Medium |
| **User activity view** | Admin endpoint to list all submissions, reports, and games by a user | Medium |
| **Bulk moderation actions** | Approve/reject multiple pending fields or reports at once | Low |
| **Scheduled audit runs** | Cron job that runs game integrity audit weekly and saves results | Low |
