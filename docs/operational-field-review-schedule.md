# Operational Field Review Schedule

## 1. Purpose

This document defines the operational maintenance and review schedule for sports fields in the Yesh Mishak application. Real-world facilities change continuously: new fields open, existing ones close permanently or temporarily for renovations, data discrepancies arise, and duplicate or invalid submissions are made. This policy ensures our fields database remains clean, accurate, complete, and safe for user gameplay.

## 2. Scope

This schedule covers the management and triage of:
- User-submitted fields (`approval_status = 'pending'`)
- User-submitted field reports (`field_reports` table)
- GovMap field imports and bulk data reconciliation
- Verification of inactive, closed, or under renovation fields
- Duplicate candidate identification and resolution
- Identifying data completeness issues (missing sports types, attributes, coordinates)
- Source-of-truth conflict resolution between GovMap, user submissions, and admin edits.

This schedule does not cover software development tasks, schema updates, or automated code runs, which are covered by separate engineering specifications.

## 3. Review Cadence

Operational maintenance is structured around three distinct cadences:
- **Weekly Operational Review:** Actioning active moderation queues, user submissions, and reports.
- **Monthly Quality Review:** Sweeping the database for stale records, duplicate candidates, and missing data attributes.
- **Quarterly Strategic Audit:** Assessing source-of-truth integrity, conflict patterns, and overall lifecycle policy adjustments.

---

## 4. Weekly Review

* **Owner:** Junior Admin / Moderation Operator
* **Focus:** Maintain zero-backlog of active incoming items.
* **Tasks:**
  1. **User Submission Queue:** Triage all pending field submissions (`GET /admin/fields/pending` or filtered list). Approve valid submissions (verify coordinates, name accuracy) or reject spam/duplicates.
  2. **Field Reports Triage:** Review incoming reports (`GET /admin/field-reports?status=open`).
     - Triage reports based on their categories (e.g., `wrong_location`, `field_closed`, `under_renovation`, `duplicate_field`).
     - Mark reports as `in_review` while investigating, then `resolved` or `rejected` upon resolution.
  3. **Immediate Closures & Renovations:** If reports or submissions indicate an active field is closed or under renovation, verify using quick tools (satellite imagery, municipal social media, local news) and update status via `PATCH /admin/fields/{id}/status`.
  4. **Active/Upcoming Game Management on Closed Fields:** Ensure that closing a field does not leave active or scheduled games orphaned. Manually close active games and cancel scheduled upcoming games on newly closed fields.

---

## 5. Monthly Review

* **Owner:** Senior Admin / Quality Assurance Lead
* **Focus:** Data quality cleanup and proactive maintenance.
* **Tasks:**
  1. **Stale Field Detection:** Scan fields with no game activity in the last 90 days. Proactively verify if these fields still exist and are accessible, or if they have fallen out of use.
  2. **Proactive Duplicate Search:** Run duplicate detection checks (`GET /admin/fields/duplicates` or manual proximity scans). Review overlapping user submissions and GovMap fields.
  3. **Attribute Verification:** Filter fields with missing details (e.g., missing street address, missing opening hours, or sport type marked as "both" but lacking clarity).
  4. **Stale Renovations Audit:** Review all fields with `status="renovation"`. If a field has been under renovation for more than 60 days, contact the relevant local authority or inspect local status. Update status to `open` (if completed) or transition to `closed` (if renovation is abandoned or indefinitely stalled).

---

## 6. Quarterly Review

* **Owner:** Lead Admin / Operations Director
* **Focus:** System-wide integrity, policy validation, and external database updates.
* **Tasks:**
  1. **GovMap Sync & Conflict Audit:** Perform a reconciliation scan comparing the database against the latest GovMap bulk dataset.
     - Review cases where GovMap has removed a field that exists in Yesh Mishak (verify if demolished or GovMap data gap).
     - Audit conflict flags (GovMap updates vs admin-edited fields) and manually reconcile using the hierarchy rules from ISSUE-041.
  2. **Audit Log Inspection:** Review the moderation audit logs (`user_moderation_audit` and report triage history) to identify patterns of systematic abuse, high-volume reporting errors, or admin errors.
  3. **Policy Performance Review:** Assess whether SLA targets are being met and whether the classification categories (ISSUE-006) remain sufficient.

---

## 7. SLA Targets

To maintain a high-quality product, administrators must resolve tasks within the following Service Level Agreement (SLA) windows:

| Task Type | Definition / Category | SLA Target | Escalation Trigger |
| --- | --- | --- | --- |
| **Urgent Reports** | Reports claiming a field is `private_field` (liability risk), `wrong_location` (causing immediate user confusion), or `field_does_not_exist`. | **24 Hours** | Exceeds 24 hours without triage → Notify Lead Admin. |
| **Normal Reports** | Reports indicating `wrong_information` or minor data errors. | **72 Hours** | Exceeds 72 hours → Add to priority weekly backlog. |
| **Pending Submissions** | Proposer submissions in `pending` state awaiting verification. | **5 Business Days** | Exceeds 5 days → Triage automatically flagged as high priority. |
| **Inactive / Renovation Reviews** | Monthly sweep of fields marked `renovation` (to verify if reopened) or `closed` (checking if reopened). | **Monthly (30 Days)** | Renovation exceeds 90 days without review → Move to permanent `closed` review. |

---

## 8. Admin Decision Rules

Admins must follow strict decision rules to maintain data integrity and prevent conflicts.

1. **When a field remains OPEN:**
   - The field is physically verified as real, accessible, and functional.
   - User reports are resolved as `rejected` (inaccurate or invalid reports).
   - GovMap registers the field as active, and no local reports contradict this.

2. **When a field becomes CLOSED:**
   - Conclusive evidence is found (satellite imagery, local reports, municipality updates) that the field is demolished, permanently shut down, or converted.
   - GovMap removed the field and admin verification confirms it no longer exists.
   - *Action Required:* Set `status="closed"`. Do NOT physically delete the field (preserves game history per ISSUE-047). Manually cancel any upcoming scheduled games.

3. **When a field becomes RENOVATION:**
   - Reliable evidence (reports, city notices) indicates temporary closure for maintenance/renovation with an expected reopening date.
   - *Action Required:* Set `status="renovation"`. Manually cancel upcoming scheduled games.

4. **When user reports trigger admin review:**
   - A single report of `private_field` or `field_does_not_exist` triggers weekly queue action.
   - Three or more reports of `field_closed` or `under_renovation` within 7 days automatically flags the field for immediate verification.

5. **GovMap Source of Truth Rules (ISSUE-041 / ISSUE-047):**
   - **Admin Wins:** Manual admin corrections/edits always override GovMap. Never overwrite an admin-modified field during bulk GovMap imports.
   - **GovMap Trust:** Trust GovMap for coordinates and existence unless local user reports or admin verification prove GovMap data is obsolete.
   - **No Auto-Delete:** If GovMap deletes a record, do not delete it in the database. Mark for manual review and possible closure.

---

## 9. Escalation Rules

1. **Unresolved GovMap Conflict:** When new GovMap data conflicts with an admin-edited field, and the admin cannot verify the ground truth via satellite or remote checks:
   - *Escalation:* Escalate to Lead Admin to initiate local verification or contact local players.
2. **Abuse / Systemic Report Spam:** If a specific user or group is spamming false reports (e.g. marking a popular open field as `closed` to troll):
   - *Escalation:* Escalate to Lead Admin. Suspend or ban the offending user account under the user moderation framework (ISSUE-015).
3. **High SLA Backlog:** If pending submissions exceed 20 fields or reports exceed 50 items past SLA:
   - *Escalation:* Escalate to Operations Director to re-allocate moderation staff or temporary resources.

---

## 10. Review Checklist

### Weekly Triage Checklist
- [ ] Check `/admin/fields/pending` and process all user submissions.
- [ ] Check `/admin/field-reports` for open reports, triaging urgent reports first.
- [ ] For any newly closed/renovated fields, verify upcoming games and manually cancel them.
- [ ] Ensure closed fields are kept in database (do not delete).

### Monthly Quality Checklist
- [ ] Identify duplicate candidates using proximity sweeps.
- [ ] Review fields under `renovation` for > 30 days and update status.
- [ ] Review fields with no game activity in 90 days (stale fields).
- [ ] Check for fields with missing addresses or sport types and enrich data.

### Quarterly Strategic Checklist
- [ ] Run GovMap dataset reconciliation report.
- [ ] Review user moderation logs and reports to identify trends or spammers.
- [ ] Validate moderation guidelines and adjust SLA targets if necessary.

---

## 11. Metrics to Track

The admin dashboard should track the following Operational KPIs:
1. **Queue Backlog Size:** Number of open reports and pending submissions.
2. **SLA Adherence Rate:** Percentage of reports resolved within target SLA.
3. **Closure Rate:** Number of fields closed vs. newly approved fields monthly.
4. **Data Accuracy Error Rate:** Percentage of approved fields subsequently flagged as `wrong_location` or `field_does_not_exist`.
5. **Admin Action Volume:** Count of manual updates, approvals, and rejections.

---

## 12. Future Automation Opportunities

1. **Automatic Reminders:** Send scheduled in-app notifications or emails to admins when fields remain in `renovation` status for over 60 days.
2. **Report Threshold Flags:** Automatically escalate fields to a high-priority review queue when they receive 3+ reports of `field_closed` within 48 hours.
3. **Stale Field Alerting:** Automatically flag fields in the admin dashboard that have `status="open"` but zero games played or scheduled within the past 120 days.
4. **FCM Push Error Cleanup:** Automatically deactivate push tokens when FCM returns unregistered errors (already done at code level, but add dashboard reporting).
5. **Moderation Audit Log Viewer:** A dedicated UI filter for admins to review all moderation actions taken on a specific field or by a specific admin.

---

## 13. Relationship to ISSUE-041 / ISSUE-047 / ISSUE-048

- **ISSUE-041 (Source of Truth Hierarchy):** This schedule enforces the priority rules (Admin > GovMap > User). It defines the routine processes by which conflicts identified in ISSUE-041 are manually resolved during quarterly strategic reviews.
- **ISSUE-047 (Inactive Field Policy):** This schedule provides the operational calendar and workflow for implementing the inactive field decisions, ensuring fields are marked `closed` rather than deleted, preserving game history.
- **ISSUE-048 (Inactive Field Lifecycle Implementation):** Once ISSUE-048 implements the backend rules to block game creation on closed fields and hide closed fields from the public map, this schedule serves as the operational manual for how admins transition fields to those states and clean up games.
