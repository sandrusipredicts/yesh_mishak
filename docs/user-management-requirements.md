# User Management Requirements

## Purpose

Define the required pre-launch user management capabilities for the Admin system.

This document answers the launch-scope questions for Ban, Unban, Suspend, Promote Admin, and Demote Admin. It is a product requirements document only; it does not define implementation details for UI, backend endpoints, or database schema changes.

## Scope

Included in this requirements decision:

* Final pre-launch decision for each user management capability.
* Practical definitions for Ban, Unban, and Suspend.
* MVP requirements for a future implementation issue.
* Risks, safeguards, and future audit fields.
* Acceptance criteria for future implementation work.

Not included:

* UI design.
* Backend endpoint design.
* Database migration design.
* Permission model implementation.
* Audit logging implementation.

## Final Decisions Table

| Capability | Required Before Launch | Admin UI Before Launch | Final Decision |
| --- | --- | --- | --- |
| Ban | Yes | Yes | Required before launch as an admin moderation action. |
| Unban | Yes | Yes | Required before launch so mistaken or resolved bans can be reversed. |
| Suspend | Yes | Yes | Required before launch for temporary or reversible moderation. |
| Promote Admin | No | No | Not required in Admin UI before launch; keep manual/super-admin controlled. |
| Demote Admin | No | No | Not required in Admin UI before launch; keep manual/super-admin controlled. |

## Definition Of Ban

Ban is a strong moderation action that prevents a user from using the product as a normal user.

A banned user should not be able to:

* Create or join games.
* Submit fields.
* Submit field reports.
* Use normal authenticated user workflows.

Ban should be used for:

* Abuse, spam, harassment, or clearly malicious behavior.
* Repeated submission of harmful or false data.
* Safety, trust, or legal concerns.

Ban should be reversible through Unban.

## Definition Of Unban

Unban reverses a Ban and restores the user to normal account access unless another restriction still applies.

Unban should be used when:

* A ban was made by mistake.
* The issue was resolved after review.
* A temporary operational ban is no longer needed.

Unban must not promote the user, change their role, or grant admin permissions.

## Definition Of Suspend

Suspend is a temporary or reversible restriction that limits a user's access without treating the account as permanently banned.

Suspend should be used for:

* Investigations.
* Cooling-off periods.
* Unclear abuse reports.
* Repeated low-quality submissions where full ban may be too strong.

Future implementation should support a clear suspended state and, ideally, a reason and expiration date. If expiration support is not included in the first implementation, the suspension must still be manually reversible.

## Decision On Promote Admin

Promote Admin is not required as an Admin UI feature before launch.

Admin promotion should remain manual or super-admin controlled until the product has stronger safeguards, including:

* Audit logging.
* Clear permission boundaries.
* Protection against self-promotion.
* Protection against one admin promoting untrusted accounts.
* Operational review for who is allowed to receive admin access.

This avoids turning normal admin moderation tools into privilege-management tools before the platform has the controls needed to make that safe.

## Decision On Demote Admin

Demote Admin is not required as an Admin UI feature before launch.

Admin demotion should remain manual or super-admin controlled until the product has stronger safeguards, including:

* Audit logging.
* Clear permission boundaries.
* Protection against self-demotion lockout.
* Protection against one admin removing another admin without review.
* A recovery process for accidental permission changes.

Demotion is important operationally, but it should not be exposed as a regular Admin UI action for the pre-launch MVP.

## MVP Requirements

A future implementation issue for pre-launch user management should include:

* Admin can ban a non-admin user.
* Admin can unban a banned non-admin user.
* Admin can suspend a non-admin user.
* Admin can reverse a suspension.
* Admin can see the user's current restriction state.
* Admin must provide or select a reason when applying Ban or Suspend.
* Admin must not be able to ban, suspend, promote, or demote admin users through the regular Admin UI.
* Non-admin users must not be able to perform user management actions.
* Restricted users must be blocked from normal authenticated user workflows.
* User-facing behavior for restricted users should be clear enough to avoid confusing generic errors.

## Out-Of-Scope Items

Out of scope for the pre-launch Admin UI:

* Promote Admin.
* Demote Admin.
* Role management UI.
* Bulk user moderation.
* Automated abuse detection.
* Appeals workflow.
* Public moderation transparency page.
* Full audit log viewer.
* Permanent deletion of users.
* Editing user profile details from Admin UI.

## Risks And Safeguards

| Risk | Safeguard |
| --- | --- |
| Admin accidentally bans a legitimate user. | Require a reason and provide Unban. |
| Admin suspends the wrong account. | Show clear user identity fields before action, such as name, email, phone, and user ID. |
| Admin uses moderation controls on another admin. | Block regular Admin UI moderation actions on admin users. |
| Restricted user keeps using protected workflows. | Enforce restriction checks server-side, not only in UI. |
| No record of why action happened. | Store audit fields for who acted, when, action type, reason, and previous state. |
| Role changes are abused or accidental. | Keep Promote/Demote Admin manual or super-admin controlled before launch. |

## Required Audit Fields For Future Implementation

Future implementation should store enough audit data to answer who did what, when, and why.

Required audit fields:

* `action_id`
* `target_user_id`
* `actor_user_id`
* `action_type`
* `previous_state`
* `new_state`
* `reason`
* `notes`
* `created_at`
* `expires_at`, for temporary suspensions if supported
* `reversed_by`
* `reversed_at`
* `reversal_reason`

Recommended action types:

* `ban`
* `unban`
* `suspend`
* `unsuspend`

## Acceptance Criteria For A Future Implementation Issue

A future implementation issue should be accepted only when:

* Admin can ban a regular user.
* Admin can unban a banned regular user.
* Admin can suspend a regular user.
* Admin can reverse a suspension.
* Ban and Suspend require a reason.
* User restriction state is persisted.
* Restricted users are blocked from normal authenticated workflows.
* Non-admin users cannot perform any user management action.
* Admin users cannot be banned, suspended, promoted, or demoted through the regular Admin UI.
* Promote Admin and Demote Admin are not exposed in the pre-launch Admin UI.
* Audit fields are captured for every restriction state change.
* Tests cover admin success cases, non-admin rejection, admin-target safeguards, invalid state changes, and persistence.

## No Open Questions

ISSUE-013 has no remaining open questions.

Final answers:

* Ban is required before launch.
* Unban is required before launch.
* Suspend is required before launch.
* Promote Admin is not required as an Admin UI feature before launch.
* Demote Admin is not required as an Admin UI feature before launch.
