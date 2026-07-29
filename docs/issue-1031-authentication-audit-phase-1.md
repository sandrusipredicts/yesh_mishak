# Issue #1031 authentication audit events: phase 1

## Scope and outcome boundaries

Phase 1 records password-login, Google-login, authenticated logout, and the
logout-triggered token revocation. The authentication audit store remains
separate from anonymous request metrics.

The logout audit taxonomy begins only after `require_active_user` has accepted
the bearer credential and the `POST /auth/logout` operation starts. Missing,
malformed, expired, revoked, banned, suspended, or otherwise rejected bearer
credentials do not create logout or token-revocation events. Those requests
remain ordinary authentication-dependency rejections and are not durable
logout attempts.

## Accepted phase-1 reliability boundary

Authentication audit persistence is synchronous and non-fatal. Password login,
Google login, and logout keep their authoritative HTTP behavior if the audit
RPC is missing or unavailable.

Logout token revocation, the token-revocation audit event, and the logout audit
event use separate database transactions. A process crash or database failure
can therefore leave either no durable audit event or exactly one of the two
correlated events after token revocation has committed. Phase 1 accepts this
partial-persistence window. There is no outbox, retry queue, compound
transaction, or external sink in this phase.

The two logout events use distinct application-generated event IDs and one
shared correlation ID. Exact retries of an event ID and immutable payload are
idempotent. Reusing the ID with different immutable data is a sanitized
conflict and remains non-fatal to authentication.

Token revocation is authoritative once `revoke_user_tokens` commits.
Best-effort local user-cache invalidation happens afterward. Its failure does
not change the successful logout response or either successful audit outcome.
Authentication dependencies reread revocation security fields, including
`tokens_valid_after`, from the database on every request (also on cache hits),
so a stale profile cache cannot restore a revoked token.

`ON DELETE SET NULL` deliberately removes the audit row's user link after a
user is deleted. A later retry using the original event ID and former user UUID
no longer matches the stored immutable payload and is reported as the same
stable sanitized conflict. Phase 1 does not retain another deleted-user
identifier.

## Database-first rollout

Use the same trusted migration role for every step. It may be a non-superuser,
but it must have `USAGE` and `CREATE` on `public`, `REFERENCES` plus the
verification script's bounded DML privileges on `public.users`, and must own
any pre-existing audit table and exact RPC. It must not be `anon`,
`authenticated`, or `service_role`. The verification step also requires
authorization to `SET ROLE service_role` so it can exercise the deployed RPC;
this does not require superuser status. An audit object owned by another role,
or an unexpected RPC overload, is rejected before DDL. The hosted application
roles must already have `USAGE` without `CREATE` or schema grant options; the
migration intentionally does not rewrite unrelated Supabase schema grants.

That trusted migration role is also the table owner and SECURITY DEFINER RPC
owner. Its exact direct audit-table privileges are `SELECT` and `INSERT`, and
its exact RPC privilege is `EXECUTE`; the function needs both table privileges
to insert new events and compare an existing immutable payload during replay.
`service_role` has table `SELECT` and RPC `EXECUTE` only. `PUBLIC`, `anon`,
`authenticated`, and every other non-superuser role have no table, column, or
RPC privileges. No application role has schema `CREATE`. Reapplication revokes
permitted table, column, and function ACL drift and restores this allowlist;
ownership drift is rejected before any DDL.

Then:

1. Run `backend/scripts/authentication_audit_events_migration_preflight.sql`.
2. Run the complete `backend/migrations/authentication_audit_events.sql` file.
   The file contains its own `BEGIN` and `COMMIT`; do not split or copy
   individual statements.
3. Run `backend/scripts/verify_authentication_audit_events_migration.sql`.
4. In the isolated dev Supabase project, call
   `record_authentication_audit_event` through the production Supabase client
   path and verify the real PostgREST response is a scalar boolean or the
   supported one-element boolean list.
5. Verify an exact replay returns false, a conflicting replay produces the
   sanitized conflict warning, and no secret or personal-data sentinel reaches
   the row, RPC arguments, logs, monitoring, or exception chain.
6. Deploy the application only after these checks pass.

The repository has no local PostgREST integration stack, so phase 1 does not
introduce one. The isolated dev verification is required before merge.

Application rollback is safe after the database-first rollout: the previous
application version does not call the new RPC, while the append-only table and
restricted RPC can remain deployed.
