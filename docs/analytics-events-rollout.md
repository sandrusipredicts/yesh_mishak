# Analytics Events Migration Rollout

## Scope and safety properties

This is the rollout runbook for `backend/migrations/analytics_events.sql`.
It does not change the event registry, accepted properties, retention policy,
or API behavior.

The rollout has three database gates:

1. `backend/scripts/analytics_events_migration_preflight.sql` is read-only. It
   proves `api_request_metrics.sql` was applied first and rejects partial
   analytics migration state.
2. `analytics_events.sql` is applied with `psql --single-transaction` and
   `ON_ERROR_STOP`, so any statement failure rolls back the whole migration.
3. `backend/scripts/verify_analytics_events_migration.sql` checks the table,
   columns, primary key and CHECK constraints, RLS, indexes, direct
   `service_role` table/function grants, and both RPCs. It inserts one reserved
   anonymous test event, proves metrics count it, proves invalid events are
   rejected, proves cleanup deletes it, and then rolls back the entire test.

The verification uses a repeatable-read snapshot and first refuses to run if
any real event is older than 365 days. Therefore the cleanup RPC can see only
the synthetic cleanup-eligible event. A 30-second statement timeout and
5-second lock timeout prevent the check from waiting indefinitely.

## Prerequisites

- Use a Supabase database-owner connection from the project **Connect** panel.
  Prefer the direct connection for migrations; use the session pooler on port
  5432 when the operator network cannot reach the direct IPv6 endpoint. Do not
  use transaction-pooler port 6543 for this workflow.
- Install PostgreSQL `psql` and use SSL. Keep the connection string out of
  source control, logs, screenshots, and shell scripts.
- Run from a clean checkout of the reviewed release commit at the repository
  root. Staging and production must be different Supabase projects.
- Confirm a usable backup/PITR point exists before the production gate.
- Replace `staging`/`production` and `backend` below only if the Railway project
  uses different names.

Set the connection string obtained from Supabase as a temporary secret. Append
`?sslmode=require` if the copied URL has no query string. The hidden prompt
keeps the URL out of shell history; the examples use `SUPABASE_DB_URL` and
unset it as soon as each environment finishes.

```bash
read -rsp 'Supabase DB URL: ' SUPABASE_DB_URL
export SUPABASE_DB_URL
printf '\n'
```

If direct IPv6 connectivity is unavailable, use the session-pooler URL from
the same Connect panel instead.

## Staging rollout

First confirm the database endpoint shown by `psql` is the staging project:

```bash
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 -c '\conninfo'
```

Run the read-only order/state preflight:

```bash
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 -f backend/scripts/analytics_events_migration_preflight.sql
```

Expected first-rollout notice: `prerequisite is complete and
analytics_events.sql is not yet applied`. A missing `api_request_metrics.sql`
or partial analytics state is a hard stop; do not bypass it.

Apply the migration atomically:

```bash
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 --single-transaction -f backend/migrations/analytics_events.sql
```

Run the rollback-only verification:

```bash
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 -f backend/scripts/verify_analytics_events_migration.sql
```

Success ends with both `verification passed` and `ROLLBACK`. Confirm the
reserved UUID is absent if the connection terminates unexpectedly:

```bash
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 -Atc "select count(*) from public.analytics_events where id = '00000000-0000-4000-8000-000000000902'::uuid"
```

The expected result is `0`.

Deploy the reviewed backend to the Railway staging environment only after the
database verification passes:

```bash
railway status
railway up --service backend --environment staging
railway logs --service backend --environment staging
```

Confirm the health endpoint returns `{"status":"ok"}`, ingest one normal
staging `app_open` through the authenticated API, and confirm the admin
monitoring response reports `analytics_events.source_available: true`.

Remove the staging database secret from the shell:

```bash
unset SUPABASE_DB_URL
```

## Production rollout

Obtain the production connection string separately; never reuse the staging
value. Set it with the same hidden prompt, then re-run the target check,
preflight, atomic migration, and verification against production in exactly
the same order:

```bash
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 -c '\conninfo'
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 -f backend/scripts/analytics_events_migration_preflight.sql
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 --single-transaction -f backend/migrations/analytics_events.sql
psql "$SUPABASE_DB_URL" -X -v ON_ERROR_STOP=1 -f backend/scripts/verify_analytics_events_migration.sql
```

With the normal repository integration, merge the approved release and let
Railway deploy it. For an authorized manual deployment, use:

```bash
railway status
railway up --service backend --environment production
railway logs --service backend --environment production
```

Then verify the API health check, authenticated ingestion, admin monitoring,
and absence of new `ANALYTICS_UNAVAILABLE` errors. Finally:

```bash
unset SUPABASE_DB_URL
```

Enable the daily Railway cleanup job only after production verification. Its
command remains:

```bash
cd backend && python -m app.jobs.cleanup_analytics_events --retention-days 90
```

## Failure and rollback behavior

- **Preflight fails:** it is read-only; no rollback is needed. A missing
  prerequisite means apply `api_request_metrics.sql` first. A partial analytics
  state means stop, capture catalog evidence, and review the drift. Do not
  deploy the backend or blindly drop objects.
- **Migration fails:** `--single-transaction` plus `ON_ERROR_STOP` rolls back
  every migration statement. Fix the cause, rerun preflight, and retry the
  complete migration. If a prior operator ran the migration without these
  flags and left partial state, treat it as schema drift and repair through a
  reviewed forward migration or reviewed transactional re-application.
- **Verification fails:** its connection remains inside an aborted transaction
  and PostgreSQL rolls it back when `psql` exits. The synthetic event and any
  cleanup effect are not committed. Confirm the reserved UUID count is `0`,
  inspect the reported missing object/grant/constraint, and keep the backend
  rollout stopped.
- **Backend deployment fails after database success:** disable the analytics
  cleanup cron if it was enabled and roll Railway back to the last known-good
  deployment from the deployment list. The additive analytics table, indexes,
  and functions are inert for the previous backend and should remain in place.
  Do not drop the table; it may already contain production events.
- **Database rollback is explicitly approved:** take a fresh logical backup
  and use a reviewed forward/compensating migration. Restore from the confirmed
  Supabase backup/PITR point only for actual database corruption. Never use an
  ad-hoc `DROP TABLE ... CASCADE` as release rollback.

## Automated check

The focused PostgreSQL integration test recreates `public` and is destructive;
run it only with a disposable local database:

```bash
cd backend
ANALYTICS_EVENTS_DATABASE_URL='postgresql://postgres:postgres@localhost:5432/analytics_events_test' python -m pytest tests/test_analytics_events_migration_postgres.py -q
```

GitHub Actions runs the same test against an ephemeral PostgreSQL 16 service
when the migration-safety files change.
