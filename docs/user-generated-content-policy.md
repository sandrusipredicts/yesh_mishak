# User-Generated Content Moderation Policy

**Created:** 2026-06-23 (ISSUE-052)
**Status:** Approved
**Scope:** Manual admin moderation — no automated enforcement in this version

---

## 1. Scope

This policy covers all user-submitted content in the application:

| Content type | Current status | Examples |
|---|---|---|
| Field submissions | Active | Name, location, sport type, surface, amenities |
| Field names | Active | Text entered by user when submitting a field |
| Field reports | Active | Reports with categories: wrong_location, field_does_not_exist, field_closed, under_renovation, private_field, duplicate_field, wrong_information, other |
| Report descriptions | Active | Free-text description in field reports |
| Game notes | Active | `age_note` field on games |
| Cancel reasons | Active | Free-text `cancel_reason` on cancelled games |
| User display names | Active | `name` field on user profiles |
| Usernames | Active | `username` field on user profiles |
| Future comments | Not yet implemented | Game chat, field reviews, etc. |
| Uploaded images | Not yet implemented | Field photos via `image_url` |

---

## 2. Allowed Content

Content that should be **approved without hesitation**:

- Accurate field names matching real locations (e.g., "מגרש הכדורסל ברחוב הרצל")
- Factual descriptions of field conditions, surface type, amenities
- Legitimate reports about field closures, renovations, location errors, duplicates
- Neutral operational notes (e.g., "open until 22:00", "no lighting")
- Age-appropriate game notes (e.g., "ages 18-30 preferred", "beginners welcome")
- Real location coordinates that match the named field
- Reports with specific, verifiable claims (e.g., "field is permanently closed, gate locked")

---

## 3. Disallowed Content

Content that must be **rejected immediately**:

| Category | Examples | Severity |
|---|---|---|
| Hate speech | Slurs, ethnic/religious/gender-based attacks | Critical |
| Harassment | Targeting specific users, bullying, intimidation | Critical |
| Threats or violence | Physical threats, encouraging harm | Critical |
| Sexual content | Explicit material, sexual solicitation | Critical |
| Doxxing / personal data | Publishing someone's phone, address, ID number, full name without consent | Critical |
| Illegal activity | Coordinating illegal acts, drug deals, trespassing instructions | Critical |
| Dangerous instructions | Content that could cause physical harm if followed | Critical |
| Impersonation | Pretending to be an admin, official, or another user | High |
| Malicious links | URLs to phishing, malware, or scam sites | Critical |
| Fake fields | Submitting locations that do not exist | High |
| Spam | Repeated identical submissions, gibberish, test data in production | High |
| Ads / scams | Commercial promotion disguised as field data | High |
| Misleading location | Deliberately incorrect coordinates | High |
| Duplicate abuse | Repeatedly submitting the same field to inflate listings | Medium |
| Irrelevant content | Content unrelated to sports fields or games | Medium |

---

## 4. Restricted Content (Needs Review)

Content that is **not obviously wrong but requires admin investigation** before a decision:

| Scenario | Why it needs review | What to check |
|---|---|---|
| Unclear field location | Coordinates don't match a known field on map/GovMap | Verify on GovMap or satellite imagery |
| Suspicious but not obviously fake field | Name and location are plausible but unverifiable | Check GovMap, search for field name online |
| Report accusing a specific person | "The field manager kicked us out" | Verify claim is about field access, not personal conflict |
| Safety claim requiring verification | "Field has broken glass" or "flooding hazard" | May warrant temporary field closure if credible |
| Field near sensitive location | Near military base, school, private property | Confirm public access |
| Commercial/promotional content | "Best field in town! Call 054-XXX for booking" | Strip promotional parts, keep factual field data |
| Repeated reports from same user | 5 reports from one user in one day | Check for pattern — legitimate power user or abuse? |
| Field name in unexpected language | Name doesn't match the city/region convention | Check if it's a real name or trolling |
| Report contradicting GovMap data | User says field doesn't exist but GovMap lists it | GovMap is higher authority per ISSUE-041, but may be outdated |

---

## 5. Moderation Actions

| Action | When to use | Effect |
|---|---|---|
| **Approve** | Content is accurate, appropriate, and follows policy | Content becomes visible; field gets `approval_status = "approved"`, `verified = true` |
| **Reject** | Content violates disallowed rules or is clearly fake | Content stays hidden; field gets `approval_status = "rejected"`, `verified = false` |
| **Mark as in review** | Content needs investigation before a decision | Field report status set to `in_review`; no public-facing change |
| **Resolve report** | Report has been acted on (field updated, closed, etc.) | Field report status set to `resolved` |
| **Reject report** | Report is invalid, spam, or incorrect | Field report status set to `rejected` |
| **Change field status** | Report reveals field is closed/under renovation | Set field `status` to `closed` or `renovation` per ISSUE-047 policy |
| **Escalate** | Content involves legal risk, physical safety, or coordinated abuse | Flag for team discussion before acting |

### Actions Not Yet Implemented

These are referenced for future development:

- **Request more information** — ask the submitter for clarification
- **Temporarily hide content** — hide while investigating without full rejection
- **Mark user as suspicious** — flag user account for increased scrutiny
- **Issue warning** — notify user their content was borderline

---

## 6. Decision Matrix

| Content Type | Example | Severity | Action | Notes |
|---|---|---|---|---|
| Field name: accurate Hebrew | "מגרש כדורגל נווה שאנן" | None | Approve | Standard submission |
| Field name: accurate English | "Herzliya Basketball Court" | None | Approve | Standard submission |
| Field name: offensive slur | "[slur] field" | Critical | Reject | Immediate rejection |
| Field name: gibberish | "asdfghjkl" | High | Reject | Spam/test data |
| Field name: promotional | "Best Courts - Call Now!" | High | Reject | Ad disguised as field |
| Field location: matches map | Coords match visible field | None | Approve | Standard submission |
| Field location: middle of sea | Coords in Mediterranean | High | Reject | Fake or error |
| Field location: slightly off | 50m from actual field | Low | Approve with correction | Admin corrects coords |
| Field report: field closed | "Gate locked, sign says permanently closed" | Medium | Mark in review | Verify, then change field status per ISSUE-047 |
| Field report: duplicate | "Same as field X" | Low | Mark in review | Check duplicate detection per ISSUE-042 |
| Field report: wrong info | "Surface is grass not concrete" | Low | Mark in review | Verify and correct |
| Field report: personal attack | "The guy who runs this field is a [slur]" | Critical | Reject report | Not about field condition |
| Game note: age preference | "18+ only" | None | Allow | Standard game configuration |
| Game note: offensive | "[offensive text]" | Critical | Reject / escalate | May require admin game cancellation |
| User name: real name | "אורל דדון" | None | Allow | Standard |
| User name: offensive | "[slur]" | Critical | Reject / escalate | May require user moderation |
| Cancel reason: factual | "Not enough players showed up" | None | Allow | Standard |
| Cancel reason: threatening | "I'll find you all" | Critical | Reject / escalate | Safety concern |

---

## 7. Severity Levels

| Level | Definition | Response time | Examples |
|---|---|---|---|
| **Critical** | Safety risk, legal exposure, or severe policy violation | Same day | Threats, doxxing, hate speech, malicious links |
| **High** | Clear policy violation without immediate safety risk | Within 2 business days | Fake fields, spam, impersonation, ads |
| **Medium** | Likely violation requiring investigation | Within 5 business days | Duplicate abuse, repeated borderline reports |
| **Low** | Minor issue, could be user error | Next review cycle | Slightly wrong location, minor formatting issues |

---

## 8. Admin Checklist

Before approving any user-generated content, verify:

- [ ] **Is it real?** Does the field/location actually exist? Cross-reference with GovMap or satellite imagery.
- [ ] **Is the location plausible?** Are the coordinates in Israel and near a populated area?
- [ ] **Is it a duplicate?** Does a field with the same or similar name/location already exist? (See ISSUE-042 duplicate detection.)
- [ ] **Is it offensive?** Does the name, description, or notes contain hate speech, slurs, threats, or harassment?
- [ ] **Does it expose personal data?** Phone numbers, addresses, ID numbers, or other PII in text fields?
- [ ] **Does it conflict with source-of-truth policy?** If the field exists in GovMap, does the submission contradict GovMap data? (Per ISSUE-041, GovMap > user submission.)
- [ ] **Does it require a field lifecycle change?** Should the field be marked closed or renovation based on a report? (Per ISSUE-047.)
- [ ] **Does it need escalation?** Legal risk, safety concern, or coordinated abuse pattern?
- [ ] **Is the submitter a repeat offender?** Check if this user has had previous rejections.

---

## 9. Repeat Abuse Policy

| Pattern | Threshold | Action |
|---|---|---|
| Repeated fake field submissions | 3+ rejected fake submissions | Flag user for review; consider suspension |
| Repeated spam | 3+ rejected spam submissions | Flag user for review; consider suspension |
| Repeated offensive content | 2+ rejected for hate/threats/harassment | Flag user for review; likely suspension |
| Coordinated abuse | Multiple accounts submitting same fake/spam content | Escalate immediately; investigate all involved accounts |
| Field status manipulation | Repeated false reports to close a legitimate field | Flag user for review; reject all pending reports from user |
| Report flooding | 10+ reports in 24 hours from one user | Review all reports; if pattern is abusive, flag user |

### Escalation Path

1. Individual violations: admin handles per this policy
2. Repeat violations (2-3): admin flags user account, increases scrutiny
3. Persistent violations (4+): admin suspends user (existing user moderation flow)
4. Coordinated/severe abuse: escalate to team for discussion and potential ban

User moderation actions (ban, suspend) follow the existing moderation flow documented in the admin API (`POST /admin/users/{id}/ban`, `POST /admin/users/{id}/suspend`).

---

## 10. Relationship to Existing Policies

| Policy | Relationship |
|---|---|
| **ISSUE-041: Source-of-Truth Policy** | Defines data authority hierarchy: Admin > GovMap > User submission > User report. UGC moderation must respect this — user submissions cannot override GovMap data without admin approval. |
| **ISSUE-047: Inactive Field Handling** | Defines when fields should be marked closed/renovation. Field reports about closures should follow ISSUE-047 policy for status changes. |
| **ISSUE-049: Operational Field Review Schedule** | Defines review cadence for field data. UGC review (pending submissions, open reports) should align with these operational cycles. |
| **ISSUE-050/051: Game Data Integrity Audit** | Audit detects data anomalies. UGC policy prevents bad data from entering; audit catches what slips through. Complementary controls. |
| **ISSUE-046: Field Moderation Guidelines** | Defines specific approval/rejection criteria for field submissions. This UGC policy is the broader umbrella; ISSUE-046 is the field-specific subset. |

---

## 11. Future Automation Opportunities

These are **not implemented in this issue** but are documented for future work:

| Opportunity | Description | Priority |
|---|---|---|
| Profanity/slur detection | Auto-flag or auto-reject submissions containing known offensive terms | High |
| Spam scoring | Score submissions based on patterns (gibberish, repeated text, known spam phrases) | Medium |
| Duplicate field detection | Automated matching per ISSUE-042 detection strategy | Medium |
| Report abuse scoring | Track rejection rate per user, auto-flag high-rejection users | Medium |
| Moderation audit log | Log every approve/reject decision with admin ID, timestamp, reason | High |
| User trust score | Score users based on submission quality history; fast-track trusted users | Low |
| Admin queue filters | Filter pending items by severity, content type, date, submitter history | Medium |
| Rate limiting | Limit submissions per user per time window (e.g., max 5 field submissions per day) | Medium |
| Auto-block dangerous content | Block submissions containing known malicious URL patterns | High |
| Image moderation | Scan uploaded field photos for offensive/inappropriate content | Low (images not yet implemented) |

---

## 12. Non-Goals

This policy explicitly does **not**:

- Implement any automated moderation or content filtering
- Add user bans or suspensions as part of this issue (existing moderation flow already supports this)
- Create content repair or remediation logic
- Replace any legal or regulatory compliance policy
- Define terms of service or privacy policy (those are separate legal documents)
- Change any backend code, API behavior, or database schema
- Apply to system-generated content (notifications, automated messages)

---

## Open Questions

These items are intentionally left unresolved for future discussion:

1. **Should rejected content be permanently deleted or soft-deleted?** Current schema does not distinguish — rejected fields remain in the database with `approval_status = "rejected"`. No change proposed.
2. **Should users be notified when their content is rejected?** No notification mechanism exists for this. Future issue if needed.
3. **Should there be an appeals process?** Not defined. Could be added as a future issue.
4. **What is the legal obligation for content removal requests?** Requires legal review, out of scope for this policy.
