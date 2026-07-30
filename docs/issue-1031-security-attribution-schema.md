# Issue #1031 item 3: security-attribution database foundation

## Scope and status

This document describes implementation PR 1 for the approved authenticated
request-correlation design. It creates database storage, bounded RPC
interfaces, access controls, verification, and retention integration only.
It does not derive pseudonyms, create or rotate keys, instrument routes,
change request logging or metrics, resolve accounts, create investigator
tooling, or deploy anything.

The approved design remains
`docs/issue-1031-authenticated-request-correlation-design.md`. This document
records how its database foundation is implemented; it does not replace the
privacy decision.

## Schema

`public.security_request_attribution_events` is append-only security evidence:

- database-generated `id`;
- immutable unique application idempotency key `request_event_id`;
- finite, non-future `occurred_at`;
- exactly 43 unpadded Base64url characters in `account_pseudonym`;
- UTC `YYYY-MM` `pseudonym_epoch`, which must match `occurred_at`;
- positive `pseudonym_key_version`;
- closed environment, event, route, method, outcome, and failure values;
- optional server-generated `server_correlation_id`; and
- database-generated `created_at`.

It has no account UUID, target UUID, foreign key to users, PII, token,
credential, IP, request content, header, raw URL, query string, JSON, or
free-form metadata.

`public.security_investigation_access_events` is append-only access evidence:

- database-generated `id`;
- unique internally generated `access_event_id`;
- finite access time and required incident UUID;
- closed investigator capability and action;
- a valid query window no longer than 31 days;
- requested limit from 1 through 10,000;
- bounded result count;
- closed environment, outcome, and failure category; and
- database-generated `created_at`.

It stores no query results, pseudonym, account identity, investigator email or
username, SQL, predicate, or case notes.

## Closed taxonomies

Environments are `development`, `staging`, and `production`. Methods are
`GET`, `POST`, `PUT`, `PATCH`, and `DELETE`.

Attribution outcomes are `succeeded`, `denied`, `failed`, and `ambiguous`.
Failure categories are `authorization_denied`, `reauthentication_failed`,
`validation_rejected`, `conflict`, `not_found`, `rate_limited`,
`dependency_unavailable`, `outcome_unknown`, and `internal_error`.

The database validates the exact route-key, event-category, and method tuples
approved in design section H. The 48 route keys are:

- account security: `auth_logout`, `auth_account_methods_read`,
  `auth_google_link`, `auth_google_unlink`, `auth_password_set`,
  `auth_password_remove`, `auth_password_reset_confirm`,
  `auth_email_verify`, and `auth_account_delete`;
- private security reads/settings: `field_reports_mine_read`,
  `user_blocks_read`, `user_block_create`, `user_block_delete`,
  `notifications_private_read`, `notification_preferences_read`,
  `notification_preferences_update`, `push_token_bind`, and
  `push_token_unbind`;
- privileged reads: `admin_self_read`, `admin_users_read`,
  `admin_field_reports_read`, `admin_stats_read`, `admin_fields_read`,
  `admin_fields_pending_read`, `admin_field_duplicates_read`,
  `admin_games_read`, `admin_engagement_read`, `admin_monitoring_read`,
  `admin_content_reports_read`, and
  `admin_notification_candidates_read`; and
- privileged mutations: `admin_user_ban`, `admin_user_unban`,
  `admin_user_suspend`, `admin_user_unsuspend`,
  `admin_field_report_status`, `admin_field_report_resolve`,
  `admin_field_approve`, `admin_field_reject`, `admin_field_status`,
  `admin_field_update`, `admin_field_delete`,
  `admin_field_status_external`, `admin_reminders_run`,
  `admin_notification_cleanup`, `admin_game_close`,
  `admin_game_extend`, `admin_game_cancel`, and
  `admin_content_report_update`.

The corresponding event categories are
`session_security_change`, `credential_configuration_read`,
`credential_method_change`, `credential_recovery`,
`account_assurance_change`, `account_lifecycle_change`,
`private_security_record_read`, `access_control_read`,
`access_control_change`, `private_notification_read`,
`private_security_setting_read`, `private_security_setting_change`,
`notification_delivery_binding_change`, `admin_sensitive_read`,
`admin_account_control`, `admin_moderation_change`,
`admin_content_control`, and `admin_operational_action`.

Investigation access action is currently only `query`. Capabilities are
`owner_activation_gate` and the future `security_evidence_reader`. Access
outcomes are `succeeded`, `rejected`, and `failed`; failure categories are
`invalid_window`, `limit_out_of_range`, and `query_failed`.

## RPC contracts

`record_security_request_attribution_event(...)` is the only attribution
write path available to `service_role`. It validates every typed value and
the exact route/category/method tuple. It serializes concurrent retries by
`request_event_id`. The first insert returns `inserted`; an identical replay
returns `already_recorded`; reuse of the ID with another immutable payload
raises a fixed idempotency conflict. Unexpected persistence failures are
replaced with a bounded error and never expose the database response.

`query_security_request_attribution_events(...)` requires an incident UUID,
environment, finite half-open time window, and result limit. The window is at
most 31 days and the result limit at most 10,000. Results are ordered by
`(occurred_at, id)` and expose only the bounded status and pseudonymous
evidence columns. It accepts no SQL, category filter, route filter,
pagination expression, arbitrary predicate, or account identity.

Valid queries write `succeeded` access evidence with a result count. Invalid
window and limit calls write a `rejected` access row using canonical bounded
window/limit values rather than persisting unsafe inputs, then return a
rejected status with no evidence. An execution failure writes `failed` and
returns no evidence. If access-audit persistence fails, the function raises a
fixed error and returns no evidence.

PostgreSQL rejects callers without `EXECUTE` before entering a function, so
those attempts cannot be recorded by the function. A null/zero incident or
unknown environment also cannot create a conforming access row and is
rejected before audit insertion. Provider/database connection audit is still
required for those pre-entry denials. An access-store failure cannot record
its own failure; fail-closed behavior is the evidence.

## ACL, ownership, and RLS

The current trusted migration role owns both tables and all four functions.
It has exact table privileges `SELECT`, `INSERT`, and `DELETE`, plus
column-scoped `UPDATE(id)`. PostgreSQL requires an update privilege for
`SELECT ... FOR UPDATE SKIP LOCKED`; no table-wide `UPDATE` is granted.

Both tables have RLS enabled, `FORCE ROW LEVEL SECURITY` disabled, and zero
policies. `PUBLIC`, `anon`, and `authenticated` have no table, column, or
function privileges. `service_role` has no direct table privilege. It has
only `EXECUTE` on attribution ingestion and the two new cleanup RPCs.

All functions are `SECURITY DEFINER`, volatile, parallel-unsafe, owned by the
same trusted owner, and fixed to `search_path=pg_catalog`. They contain no
dynamic SQL.

No approved investigator PostgreSQL role exists in the repository. The query
RPC therefore grants `EXECUTE` only to its owner. Activating it requires a
separate reviewed change that provisions the approved no-login capability,
named/MFA-backed principals, and independent provider audit.

## Indexes

- unique `request_event_id`: ingestion idempotency;
- `(occurred_at, id)`: deterministic attribution cleanup;
- `(environment, occurred_at, id)`: bounded investigation window scans;
- `(account_pseudonym, pseudonym_epoch, occurred_at desc)`: within-epoch
  grouping;
- unique `access_event_id`: access-event identity;
- access `(occurred_at, id)`: deterministic access-evidence cleanup; and
- access `(incident_id, occurred_at desc, id desc)`: case audit review.

## Retention integration

Both tables use the existing fixed 180-day security retention policy.
Dedicated cleanup RPCs delete only `occurred_at < cutoff`, keep the cutoff
boundary, lock oldest rows first, accept 1–1,000 rows, and return only counts.
Each call is an independent transaction; failure retains that batch for retry.
`service_role` never receives direct `DELETE`.

The existing
`app.jobs.cleanup_authentication_audit_events` entry point now invokes three
separate targets with one fixed cutoff: authentication audit, request
attribution, and investigation access. It retains the established job name
and schedule, caps each target at 50 batches by default, continues to the next
target after one target fails, records only bounded counts/categories, and
returns failure if any target failed. There is no second scheduler.

Per table:

```text
cleanup_capacity_per_daily_run = 1,000 × 50 = 50,000 rows
retained_rows <= average_daily_events × 180 + expired_cleanup_backlog
```

The repository contains no production volume measurement. Capacity must be
checked from identity-free aggregate counts before route instrumentation is
enabled.

## Rollout and hosted-dev verification

No hosted action is performed by this PR.

1. Require green unit and zero-skip PostgreSQL CI.
2. Run `security_request_attribution_migration_preflight.sql` in isolated dev.
3. Apply the complete transactional
   `security_request_attribution.sql` migration.
4. Run rollback-only
   `verify_security_request_attribution_migration.sql`.
5. Preserve the bounded owner/ACL/RLS/function diagnostic evidence.
6. Perform one controlled service-role ingestion with synthetic values.
7. Run the owner-only bounded query under the activation gate.
8. Prove the investigation-access row was written.
9. Use rollback-only synthetic rows to verify both cleanup boundaries.
10. Keep the PR Draft until hosted evidence is reviewed.

## Rollback

Stop future instrumentation first; none is introduced by this PR. Keep the
investigator capability disabled. Preserve existing evidence unless a
separately approved deletion is required. An application-only rollback can
leave the additive tables inert. Remove functions or grants only through a
reviewed forward rollback migration. Already captured evidence cannot be made
unseen, and legitimately expired rows cannot be restored by this design.

## Remaining implementation PRs and gates

1. HMAC-SHA-256 derivation, canonical vectors, environment binding, and key
   lookup tests.
2. Independently approved monthly key custody and rotation operations.
3. Minimal allowlisted route instrumentation without changing general
   request metrics.
4. Investigator capability provisioning, named-principal audit, query
   runbook, and later resolver controls.
5. Hosted isolated-dev verification.
6. Production rollout documentation and approval.

No runtime instrumentation may begin until pseudonym key custody is approved.
No investigator query access may be granted until the investigator
capability, principal provider, MFA, and independent audit trail are approved.
