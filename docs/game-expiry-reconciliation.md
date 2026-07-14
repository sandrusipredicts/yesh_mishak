# Game Expiry Reconciliation Job

## Purpose

`E03-01` adds a scheduled backend job that reconciles expired games without waiting for normal user reads. Games remain governed by the existing lifecycle model:

- Active statuses: `open`, `full`
- Terminal expiry status: `finished`
- Cancelled games remain `cancelled`
- Expiry cutoff: `expires_at <= cutoff`

The existing request-time expiry fallback remains in place as defense in depth, but the scheduled job is the primary production mechanism once configured.

## Repository Implementation

The job entry point is:

```bash
cd backend
python -m app.jobs.reconcile_game_expiry --batch-size 100 --max-batches 50
```

The reusable service is `app.services.game_expiry_reconciliation.reconcile_expired_games`.

The database primitive is `public.reconcile_expired_games(p_cutoff timestamptz, p_batch_size integer)`, defined in:

```text
backend/migrations/game_expiry_reconciliation.sql
```

Apply that migration before enabling the scheduler.

## Required Environment Variables

The job uses the existing backend settings loader. Configure the same required backend variables on the Railway cron service:

```text
SUPABASE_URL
SUPABASE_KEY
SUPABASE_SERVICE_ROLE_KEY
GOOGLE_CLIENT_ID
JWT_SECRET
```

The reconciliation code itself uses `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`; the other values are required because the current shared settings object validates required backend configuration at startup. Keep `SUPABASE_SERVICE_ROLE_KEY` and `JWT_SECRET` only in Railway/backend environments. Do not expose them to Vercel, frontend code, mobile code, logs, or screenshots.

## Reconciliation Semantics

Eligible rows satisfy all of:

```sql
status in ('open', 'full')
and expires_at is not null
and expires_at <= p_cutoff
```

The SQL function processes a bounded batch ordered by `expires_at, id`, locks candidates with `FOR UPDATE SKIP LOCKED`, and updates only rows that still satisfy the same predicate at mutation time. This protects against stale candidate reads when a game is concurrently extended, closed, or cancelled.

Running the job repeatedly is safe. Already-finished games, cancelled games, future games, and rows with null `expires_at` are untouched.

The job does not create notifications, audit rows, push messages, cleanup, or history records. Existing manual close/cancel/extend notification behavior is unchanged.

## Recommended Railway Schedule

Create a Railway cron service or scheduled job with:

```bash
cd backend && python -m app.jobs.reconcile_game_expiry --batch-size 100 --max-batches 50
```

Recommended schedule:

```text
*/5 * * * *
```

With this schedule, the expected maximum persisted expiry-state delay is approximately 5 minutes plus job runtime and any scheduler retry delay.

## Expected Output

Successful runs print a JSON summary and exit `0`, including when no games are expired:

```json
{"batch_count":1,"failed_count":0,"reconciled_count":0,"scanned_count":0}
```

Unrecoverable failures are logged with `event=jobs.game_expiry_reconciliation.failure` and exit non-zero so Railway can mark the run failed.

Logs include:

- `jobs.game_expiry_reconciliation.start`
- `jobs.game_expiry_reconciliation.batch_finish`
- `jobs.game_expiry_reconciliation.finish`
- `jobs.game_expiry_reconciliation.failure`

## Manual Verification

Use staging or local non-production data only.

1. Apply `backend/migrations/game_expiry_reconciliation.sql`.
2. Create or identify an `open` or `full` game with `expires_at` in the past.
3. Run:

   ```bash
   cd backend
   python -m app.jobs.reconcile_game_expiry --batch-size 100 --max-batches 50
   ```

4. Verify the row now has `status = 'finished'`.
5. Rerun the command and verify it reports zero reconciled rows.
6. Verify future, cancelled, and manually finished games are unchanged.
7. Verify the game no longer appears in active/upcoming buckets and appears in the existing finished/history bucket where applicable.
8. Verify joining the expired game is rejected.

## Failure Diagnosis

- Missing required env var: configure the required backend variables in the Railway cron service.
- RPC missing: apply `backend/migrations/game_expiry_reconciliation.sql`.
- Non-zero exit: inspect Railway logs for `jobs.game_expiry_reconciliation.failure`.
- Repeated `reached_max_batches=true`: temporarily increase `--max-batches` or run the command manually until backlog clears.

## Rollback

1. Disable the Railway cron service/job.
2. Redeploy the previous backend version if the CLI/service code is suspected.
3. Leave the SQL function and index in place unless a database owner explicitly decides to remove them; they are inert without the job and safe to re-run.
4. The request-time lazy fallback still preserves user-facing lifecycle correctness while the scheduler is disabled.

## Owner Production Actions

- [ ] Apply the Supabase migration in production.
- [ ] Create the Railway cron service/job.
- [ ] Configure `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_CLIENT_ID`, and `JWT_SECRET` on that service.
- [ ] Set schedule to `*/5 * * * *`.
- [ ] Run one staging/manual verification.
- [ ] Confirm production Railway logs show successful start/finish events.
