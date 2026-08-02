# Issue #1031 item 3: next high-risk authenticated mutation routes

## Scope and status

This document records one narrow route-instrumentation PR based on `dev`
commit `dc3a09095963d77beff2f246cb14428629bcb155`, which contains merged PRs
#1039 through #1042. Draft PR #1043 is not a dependency of this route batch
and is not modified.

The PR instruments exactly five database-approved authenticated mutations:

1. `POST /admin/users/{user_id}/ban` (`admin_user_ban`);
2. `POST /admin/users/{user_id}/unban` (`admin_user_unban`);
3. `POST /admin/users/{user_id}/suspend` (`admin_user_suspend`);
4. `POST /admin/users/{user_id}/unsuspend` (`admin_user_unsuspend`); and
5. `DELETE /admin/fields/{field_id}` (`admin_field_delete`).

It does not instrument reads, add routes, change authorization, change the
database schema, change retention, add investigator access, change general
request metrics, deploy, or enable production attribution.

## Remaining approved-route inventory and risk ranking

The merged application registry contains six routes: logout, Google link and
unlink, password set and removal, and account deletion. The other 42 tuples
approved by the database are ranked below. Rank considers account-wide access
impact first, then destructive/moderation scope, security-setting changes,
private-data exposure, and finally aggregate or operational reads.

| Rank | Approved route key | Method and path | Risk reason | This PR |
| ---: | --- | --- | --- | --- |
| 1 | `admin_user_ban` | `POST /admin/users/{user_id}/ban` | Indefinitely removes a principal's application-wide access. | Selected |
| 2 | `admin_user_unban` | `POST /admin/users/{user_id}/unban` | Restores access after the strongest moderation restriction. | Selected |
| 3 | `admin_user_suspend` | `POST /admin/users/{user_id}/suspend` | Removes application-wide access through temporary enforcement. | Selected |
| 4 | `admin_user_unsuspend` | `POST /admin/users/{user_id}/unsuspend` | Reactivates a principal after a security/moderation restriction. | Selected |
| 5 | `admin_field_delete` | `DELETE /admin/fields/{field_id}` | Destructive admin action that removes a field from active use. | Selected |
| 6 | `auth_password_reset_confirm` | `POST /auth/password-reset/confirm` | Replaces a credential, but the handler has only a recovery token and no trusted authenticated actor UUID. | Deferred identity boundary |
| 7 | `auth_email_verify` | `POST /auth/verify-email` | Changes account assurance, but the handler has only a one-time token and no trusted authenticated actor UUID. | Deferred identity boundary |
| 8 | `admin_content_report_update` | `PATCH /admin/content-reports/{report_id}` | Applies a moderation decision to reported content. | Deferred |
| 9 | `admin_field_report_resolve` | `PATCH /admin/field-reports/{report_id}/resolve` | Closes a field-safety/moderation case. | Deferred |
| 10 | `admin_field_report_status` | `PATCH /admin/field-reports/{report_id}/status` | Changes field-report enforcement state. | Deferred |
| 11 | `admin_field_reject` | `POST /admin/fields/{field_id}/reject` | Prevents a submitted field from being published. | Deferred |
| 12 | `admin_field_approve` | `POST /admin/fields/{field_id}/approve` | Publishes and verifies submitted location content. | Deferred |
| 13 | `admin_field_status_external` | `PATCH /fields/{field_id}/status` | Changes field availability outside the admin router. | Deferred |
| 14 | `admin_field_status` | `PATCH /admin/fields/{field_id}/status` | Changes an approved field's operational availability. | Deferred |
| 15 | `admin_field_update` | `PATCH /admin/fields/{field_id}` | Mutates trusted location content. | Deferred |
| 16 | `admin_game_cancel` | `POST /admin/games/{game_id}/cancel` | Cancels a scheduled game and affects its participants. | Deferred |
| 17 | `admin_notification_cleanup` | `POST /admin/notifications/cleanup` | Performs bounded bulk deletion of notification data. | Deferred |
| 18 | `admin_game_close` | `POST /admin/games/{game_id}/close` | Terminates an active game. | Deferred |
| 19 | `admin_reminders_run` | `POST /admin/reminders/scheduled-games/run` | Initiates a bulk notification-producing operation. | Deferred |
| 20 | `push_token_bind` | `POST /notifications/push-token` | Associates a delivery destination with an account. | Deferred |
| 21 | `push_token_unbind` | `DELETE /notifications/push-token` | Removes an account delivery destination. | Deferred |
| 22 | `notification_preferences_update` | `PUT /notifications/preferences` | Changes private notification/security-adjacent settings. | Deferred |
| 23 | `user_block_create` | `POST /moderation/blocks/{blocked_user_id}` | Enforces a private account-to-account access control. | Deferred |
| 24 | `user_block_delete` | `DELETE /moderation/blocks/{blocked_user_id}` | Removes a private account-to-account access control. | Deferred |
| 25 | `admin_game_extend` | `POST /admin/games/{game_id}/extend` | Extends an active game's lifetime. | Deferred |
| 26 | `admin_users_read` | `GET /admin/users` | Exposes private account and restriction data. | Deferred read |
| 27 | `admin_field_reports_read` | `GET /admin/field-reports` | Exposes reporter identity and private moderation reports. | Deferred read |
| 28 | `admin_content_reports_read` | `GET /admin/content-reports` | Exposes private moderation evidence. | Deferred read |
| 29 | `admin_notification_candidates_read` | `POST /notifications/candidates` | Computes a privileged private notification audience. | Deferred read |
| 30 | `notifications_private_read` | `GET /notifications` | Reads private account notifications. | Deferred read |
| 31 | `user_blocks_read` | `GET /moderation/blocks` | Reads a private access-control list. | Deferred read |
| 32 | `field_reports_mine_read` | `GET /field-reports/mine` | Reads one account's private reports. | Deferred read |
| 33 | `admin_monitoring_read` | `GET /admin/monitoring` | Reads privileged operational and security aggregates. | Deferred read |
| 34 | `auth_account_methods_read` | `GET /auth/account-methods` | Reads configured credential methods. | Deferred read |
| 35 | `notification_preferences_read` | `GET /notifications/preferences` | Reads private notification settings. | Deferred read |
| 36 | `admin_self_read` | `GET /admin/me` | Reads the current admin profile only. | Deferred read |
| 37 | `admin_fields_pending_read` | `GET /admin/fields/pending` | Reads unpublished submitted fields. | Deferred read |
| 38 | `admin_field_duplicates_read` | `GET /admin/fields/duplicates` | Reads duplicate-detection moderation candidates. | Deferred read |
| 39 | `admin_fields_read` | `GET /admin/fields` | Reads the admin field inventory. | Deferred read |
| 40 | `admin_games_read` | `GET /admin/games` | Reads the privileged game inventory. | Deferred read |
| 41 | `admin_stats_read` | `GET /admin/stats` | Reads aggregate administrative counts. | Deferred read |
| 42 | `admin_engagement_read` | `GET /admin/engagement` | Reads aggregate engagement metrics. | Deferred read |

There is no approved or implemented promote, demote, or role-change endpoint.
Existing tests explicitly assert that those endpoints do not exist, so this
PR does not invent one.

## Why these five precede the other routes

The four account-control operations determine whether another principal may
use the entire application. Both restriction and reactivation are high risk:
an abusive restriction is an account-wide denial of service, while an
unauthorized reactivation bypasses an established enforcement decision.

Field removal is the next eligible authenticated mutation because it is the
only remaining approved route with explicit destructive semantics. It
soft-deletes the field from active listings and records the admin actor and
reason. The next two inherently security-sensitive routes—password-reset
confirmation and email verification—cannot be selected safely: their current
handlers do not receive a trusted authenticated internal account UUID, and
the approved design forbids deriving attribution identity from a recovery or
verification token.

All lower-ranked eligible mutations have narrower content, game,
notification, preference, or per-user block scope. Read-only routes are
deliberately excluded from this mutation-only batch.

## Execution plan

1. Start from the exact merged `dev` foundation and leave Draft PR #1043
   untouched.
2. Extend only the application recorder's closed category, route-key, and
   tuple registry from six to eleven entries. The database registry already
   contains all five tuples, so no migration is required.
3. Wrap the existing shared user-moderation operation once so ban, unban,
   suspend, and unsuspend remain behaviorally identical.
4. Attribute the authenticated active admin UUID from `require_admin`; never
   use the target user ID, path field ID, body, email, reason, or token.
5. Instrument only the existing field-removal handler after admin admission.
6. Record exact business rejections with closed categories. Treat unexpected
   user-moderation transport errors and field-removal database failures as
   `ambiguous`/`outcome_unknown`, because the existing database calls cannot
   prove whether a remote write committed.
7. Keep attribution fail-open through a bounded helper. Recorder failure must
   not alter success, business-error, status-code, or response payload.
8. Add focused tests for registry scope, every success tuple, actor-vs-target
   identity, no body/PII, bounded failure mapping, ambiguous failures,
   authorization-before-attribution, and fail-open behavior.
9. Run existing account-attribution, admin moderation, field deletion,
   runtime, HMAC, retention, authentication-audit, and full backend tests.
10. Run Python compilation, `git diff --check`, secret scanning, and a
    changed-file/scope review before publishing a Draft PR to `dev`.

## Failure and privacy semantics

- Successful authoritative operation: `succeeded`, null failure category.
- Authorization rejection admitted by the handler: `denied`,
  `authorization_denied`.
- Validation, missing-resource, and conflict errors: `failed` with the
  corresponding closed category.
- Uncertain remote mutation outcome: `ambiguous`, `outcome_unknown`.
- Attribution configuration, derivation, RPC, or monitoring failure: bounded
  warning from the existing recorder; original admin behavior is unchanged.
- Authentication and admin authorization rejection occurs before handler
  entry and creates no attribution row in this route-level PR.

No raw actor UUID is persisted. The recorder derives the existing monthly,
environment-bound HMAC pseudonym before the service-role ingestion RPC. No
target ID, field ID, email, username, phone, reason, request body, token,
header, IP, user agent, raw URL, provider error, pseudonym, or key is added to
logs, monitoring, the RPC payload, or general-purpose metrics.

## Remaining scope after this PR

Thirty-seven approved tuples remain absent from the application registry:
the two token-bound recovery/verification mutations, eighteen other
authenticated mutations, and seventeen privileged/private reads. They must
be implemented only in further small reviewed batches after applying the
same trusted-identity and privacy analysis.

## Rollout and rollback

No deployment or Railway change is part of this PR. Production attribution
remains disabled. A later isolated-development check may enable the existing
runtime with a current dev-only key, exercise synthetic admin/target accounts
and a synthetic field, query evidence through the owner activation gate, and
then disable the runtime.

Rollback is configuration-first: set `SECURITY_ATTRIBUTION_ENABLED=false`.
Code rollback reverts this route/registry commit. Existing pseudonymous
evidence remains under the merged 180-day retention policy; rollback must not
delete evidence or alter database ACLs, RLS, keys, or cleanup behavior.

## Test evidence

All commands were run from `backend/` with dummy local Supabase, Google, and
JWT settings. No hosted environment or real credential was used.

- Focused route-attribution tests:
  `python -m pytest -q tests/test_security_attribution_admin_mutation_routes.py tests/test_security_attribution_account_routes.py -p no:cacheprovider`
  — 95 passed, 0 failed, 0 skipped.
- Preservation tests for existing admin authorization/moderation, field
  deletion, attribution runtime/configuration/HMAC, authentication audit, and
  retention:
  `python -m pytest -q tests/test_admin_me.py tests/test_admin_user_moderation.py tests/test_field_delete.py tests/test_security_attribution_admin_mutation_routes.py tests/test_security_attribution_account_routes.py tests/test_security_request_attribution.py tests/test_security_attribution_config.py tests/test_security_account_pseudonym.py tests/test_authentication_audit_events.py tests/test_authentication_audit_revocation_phase_2.py tests/test_authentication_audit_retention.py -p no:cacheprovider`
  — 531 passed, 0 failed, 0 skipped.
- Canonical full backend suite with the repository's coverage gate:
  `python -m pytest tests/ --cov=app --cov-fail-under=89 --cov-report=term-missing --cov-report=xml:<temporary-path> -p no:cacheprovider --basetemp=<temporary-path>`
  — 1,675 passed, 0 failed, 152 skipped; 90.96% coverage, above the
  required 89%.
- PostgreSQL-only test disclosure:
  `python -m pytest -q <all tests/*postgres.py files> -rs -p no:cacheprovider`
  — 0 passed, 0 failed, 152 skipped. The skips are explicit because the local
  `ANALYTICS_EVENTS_DATABASE_URL`, `AUTHENTICATION_AUDIT_DATABASE_URL`,
  `PASSWORD_RESET_DATABASE_URL`, and `SECURITY_ATTRIBUTION_DATABASE_URL`
  integration-test settings are not configured. This PR has no migration.
- Python compilation:
  `python -m py_compile app/api/admin.py app/services/security_request_attribution.py tests/test_security_attribution_admin_mutation_routes.py tests/test_security_attribution_account_routes.py`
  — passed.
- `git diff --check` — passed.

The repository does not configure a standalone Python formatter, linter, or
type checker, and no `gitleaks` or `detect-secrets` executable is installed in
this environment. A changed-file secret-pattern scan and manual privacy/scope
review are therefore required immediately before commit.
