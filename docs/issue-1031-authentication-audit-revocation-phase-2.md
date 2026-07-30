# Issue #1031 authentication audit events: phase 2 revocation sources

## Scope

Phase 2 adds durable `token_revocation` events for the five remaining
operations that advance `users.tokens_valid_after`: Google unlink, set
password, remove password, password reset, and account deletion. It reuses the
phase-1 table, SECURITY DEFINER RPC, service-role writer, identifier generation,
source-environment normalization, privacy exclusions, and non-throwing
observability.

Request attribution, retention, cleanup, general request metrics, admin
querying, reauthentication events, and additional revocation sources remain
out of scope.

## Authoritative insertion points

- `account_linking.unlink_google`: after `unlink_google_identity` returns
  `unlinked`, before account-method lookup or JWT reissue.
- `account_linking.set_password_for_user`: after `set_account_password`
  returns `set`, before account-method lookup or JWT reissue.
- `account_linking.remove_password_for_user`: after
  `remove_account_password` returns `removed`, before account-method lookup or
  JWT reissue.
- `PasswordResetService.confirm_password_reset`: after
  `consume_password_reset_token` returns `success`, before cache invalidation
  or the HTTP response.
- `account_deletion.delete_account`: after `delete_user_account` returns a
  mapping with `deleted=true`.

Business preconditions and failed reauthentication do not emit revocation
events. Authoritative mutation handling uses three outcomes:

- `confirmed_succeeded`: a validated successful RPC result confirms token
  revocation; one succeeded event is written.
- `confirmed_failed`: a decoded non-success PostgREST response with a bounded
  PostgREST error code or PostgreSQL SQLSTATE proves that the transactional RPC
  rolled back; one failed event is written with `service_unavailable`,
  `invalid_state`, or `internal_error`.
- `outcome_ambiguous`: transport failure, response validation/decoding failure,
  or a malformed successful payload cannot prove commit status; no durable
  outcome event is written and only sanitized, non-throwing observability is
  emitted.

An exception class by itself never establishes the database outcome.
Operation-specific validators require the exact bounded response shape before
an HTTP success becomes `confirmed_succeeded`; null, empty, multi-row,
contradictory, or otherwise malformed success payloads remain ambiguous.

## Event mapping

| Operation | `auth_method` | `revocation_reason` |
| --- | --- | --- |
| Google unlink | `password` | `google_unlinked` |
| Set password | `google` | `password_set` |
| Remove password | `google` | `password_removed` |
| Password reset | `recovery` | `password_reset` |
| Account deletion | `password` or `google` | `account_deleted` |

Each durable event receives one application-generated event UUID and one
correlation ID. The event is written synchronously through the existing
service-role-only RPC. Persistence, logging, monitoring, and post-commit cache
cleanup failures remain non-fatal to the authoritative operation.

## Account deletion ordering

The deletion RPC advances `tokens_valid_after` and deletes the user in one
database transaction. Phase 2 then writes the audit event in a separate
transaction with `user_id=NULL`, because the referenced user no longer exists.
This respects the existing `ON DELETE SET NULL` privacy model without retaining
a deleted-user identifier and guarantees that an audit row can never claim a
deletion before the authoritative deletion succeeds.

The accepted tradeoff is a post-delete crash window: the process can terminate
after deletion commits and before the audit RPC commits, leaving a completed
deletion without its audit event. Writing before deletion would invert that
risk and could create a false durable deletion claim, so it is not used.

## Other crash windows

All audit writes remain separate from the authoritative mutation transaction.
For Google unlink, password set/remove, and password reset, a process crash
after mutation commit but before audit persistence can omit the event. A crash
after the event commits but before JWT reissue or response construction leaves
the successful event intact even though the client receives an error or no
response. A transport or response-processing failure can also be ambiguous
after the mutation committed; phase 2 deliberately writes no durable outcome
in that case rather than risk a false success or failure claim. No retry,
outbox, queue, background writer, or external sink is added in phase 2.

## Privacy boundary

Audit rows, audit RPC arguments, logs, monitoring tags, error responses, and
sanitized exception boundaries exclude passwords and hashes, reset tokens and
hashes, Google credentials and provider subjects, JWTs, headers, request
bodies, email, username, phone, IP, user-agent, and raw exception or
provider/database diagnostics. Successful authorized Google unlink, password
set, and password removal responses may intentionally contain a replacement
access token; that token never enters audit persistence or observability.
High-cardinality event, correlation, request, and user identifiers are not
monitoring tags.

## Database rollout and verification

Deploy the database constraint before the phase-2 application:

1. Run the existing authentication-audit preflight.
2. On an existing phase-1 database, apply
   `authentication_audit_revocation_phase_2.sql` as one complete transaction.
   For a fresh database, `schema.sql` is the supported bootstrap and contains
   the same phase-2 audit constraint and canonical account-deletion RPC. The
   schema installer owns the account-deletion SECURITY DEFINER function; only
   `service_role` receives execution while `PUBLIC`, `anon`, and
   `authenticated` are revoked.
3. Run `verify_authentication_audit_events_migration.sql`.
4. In isolated development, exercise the audit RPC through the production
   Supabase/PostgREST client and verify its supported boolean response shape.
5. Deploy the application only after database and PostgREST verification pass.

The PostgreSQL CI job writes and validates separate JUnit reports for the
analytics and authentication-audit modules. Missing dependencies or database
URLs, connection failures, a missing/empty module, skips, failures, or errors
fail the job; a passing aggregate from only one module is not accepted.

Application rollback is safe after this database-first rollout because the
phase-1 application emits only the already-approved logout/bearer mapping. The
phase-2 constraint remains backward-compatible with that mapping.
