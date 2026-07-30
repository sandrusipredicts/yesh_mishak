# Issue #1031 item 4: authentication-audit retention

## Policy decision

`public.authentication_audit_events` is retained for **180 days**. Cleanup runs
once daily and deletes only rows whose `occurred_at` is strictly earlier than
the fixed cutoff. A row exactly at the cutoff remains retained.

The retention duration is fixed in
`app.services.authentication_audit_retention`; it is not an environment
variable or a cleanup-job command-line option. The only operational controls
are bounded work controls:

| Control | Default | Accepted range |
| --- | ---: | ---: |
| Retention | 180 days | fixed |
| Batch size | 1,000 rows | 1–1,000 |
| Batches per run | 50 | 1–100 |
| Schedule | daily | deployment configuration |

There is no legal-hold mechanism in this scope. An approved legal-hold
requirement must therefore stop the cleanup schedule before affected rows age
past 180 days and must be implemented as a separately reviewed change. The
table is not partitioned: the bounded row projection below does not justify
the operational complexity yet.

## Why 180 days

The exposure-window audit that opened Issue #1031 was unable to investigate an
older event after a rolling platform log had expired. A six-month window lets
an investigation look across approximately two quarterly review cycles and
covers delayed discovery of credential exposure without keeping
authentication-linked evidence indefinitely.

- A materially shorter 90-day policy would halve storage, but it could remove
  the preceding quarter before a delayed exposure is investigated.
- A 365-day policy would retain twice the approved 180-day population and
  privacy exposure. Under the planning model below it would retain about
  3.65 million rows (about 3.48 GiB at the conservative size assumption)
  without evidence that a full year is needed.
- 180 days is operationally simple: one time rule applies in code, tests,
  verification, and this runbook. It also minimizes linked security data once
  the chosen investigation window ends.

No repository evidence makes 180 days incompatible. The repository contains
no production daily-volume measurement, and this work neither accesses nor
claims production traffic.

## Volume and storage model

### Measured repository facts

- A login attempt emits one authentication audit event.
- An authenticated logout can emit two correlated rows: logout and token
  revocation.
- Each other implemented token-revocation operation emits one row.
- The table has ten fixed scalar columns and four existing indexes including
  its primary key. It has no request body, header, token, email, username, IP
  address, user agent, or free-form metadata column.
- No representative current events-per-day or `pg_total_relation_size`
  measurement is committed in the repository.

### Explicit planning assumptions

These are capacity assumptions, not statements about production traffic:

- `average_daily_events (E) = 10,000 rows/day`
- `conservative_bytes_per_row = 1,024 bytes`, including heap, indexes, and
  ordinary tuple overhead
- one cleanup run per day
- default cleanup capacity
  `C = 1,000 rows/batch × 50 batches = 50,000 rows/run/day`

The planning estimate is:

| Quantity | Calculation | Estimate |
| --- | --- | ---: |
| Annual rows without cleanup | `E × 365` | 3,650,000 |
| Rows inside 180-day window | `E × 180` | 1,800,000 |
| Retained storage after cleanup | `1,800,000 × 1,024` | about 1.72 GiB |
| One normal day of cleanup lag | `E × 1 day` | 10,000 rows / 9.77 MiB |
| Maximum rows deleted per run/day | `1,000 × 50` | 50,000 |

The bound is a function, not an unconditional traffic claim:

```text
retained_rows <= average_daily_events × retention_days + cleanup_backlog
cleanup_capacity_per_run = batch_size × max_batches
```

With a healthy daily schedule and `E <= C`, the expired backlog immediately
before a run is normally at most one day of events; after a run that reaches
an explicit zero result, it is zero. Finite outage recovery requires `E < C`.
For an outage lasting `d` days:

```text
initial_backlog = E × d
net_daily_backlog_reduction = C - E
recovery_days = ceil((E × d) / (C - E))
```

At the planning values, a 30-day outage creates about 300,000 expired rows.
One scheduled run can delete at most 50,000 rows, and the net recovery rate
while 10,000 more rows age out each day is 40,000 rows/day, so recovery takes
at most eight daily runs. If measured `E >= C`, or consecutive runs record
`reached_max_batches = true`, this capacity assumption is invalid and the
operator must review volume and batching in a new change; the job never
silently removes its cap.

After isolated-dev rollout, replace assumptions with aggregate measurements
that expose no row contents or identifiers:

```sql
select
    date_trunc('day', occurred_at) as event_day,
    count(*) as event_count
from public.authentication_audit_events
where occurred_at >= pg_catalog.now() - interval '30 days'
group by 1
order by 1;

select
    pg_catalog.pg_total_relation_size(
        'public.authentication_audit_events'::regclass
    ) as relation_bytes,
    count(*) as row_count
from public.authentication_audit_events;
```

## Database cleanup boundary

`public.cleanup_authentication_audit_events(timestamptz, integer)` is
`SECURITY DEFINER`, volatile, parallel-unsafe, and fixed to
`search_path=pg_catalog`. It:

- rejects null, infinite, or future cutoffs;
- accepts only batch limits from 1 through 1,000;
- locks candidates in deterministic `(occurred_at, id)` oldest-first order
  with `FOR UPDATE SKIP LOCKED`;
- deletes only `occurred_at < p_cutoff`;
- returns only the deleted row count; and
- can be called repeatedly until it returns zero.

`PUBLIC`, `anon`, and `authenticated` have no execute privilege. `service_role`
has execute privilege but still has no direct `DELETE` privilege on the audit
table. The trusted audit table owner also owns the function. Existing RLS, the
no-policy client denial, the append-only record RPC, table ACLs, and event
taxonomy remain unchanged.

Each RPC call is one database transaction. A failed call retains that batch
for retry. Rows committed by an earlier successful batch were already expired
and remain legitimately deleted. Concurrent cleanup calls skip locked rows and
converge through repeated execution.

## Cleanup job and failure evidence

The entry point is:

```text
cd backend && python -m app.jobs.cleanup_authentication_audit_events --batch-size 1000 --max-batches 50
```

It computes one UTC cutoff at run start from the fixed 180-day rule and reuses
that cutoff for every batch. It stops only after the RPC returns zero or the
maximum batch count is reached.

The job reuses `JobRunRecorder` with job name
`authentication_audit_retention_cleanup`. The start record contains only the
retention days, bounded work controls, and entry-point category. Completion
records processed count, batch count, and `reached_max_batches`; no row,
user, event, or correlation identifiers are recorded.

RPC failure returns a nonzero process exit, attempts to persist a failed job
run with only `cleanup_rpc_failure` or `unexpected_response`, and emits a
sanitized warning without raw exception text. Logger or `job_runs` monitoring
failure cannot stop cleanup or replace its exit result. Failed work is retried
by the next daily run; there is no internal tight retry loop.

The repository has no committed Railway scheduler file. Existing scheduled
jobs use Railway console configuration, so deployment integration remains an
explicit operator step: create or update one Railway cron job with schedule
`0 3 * * *` (daily at 03:00 UTC) and the command above. Do not create a second
schedule for the same environment.

## Proving the policy is functioning

The post-migration verifier checks owner, exact function signature and body
guards, function ACL, table ACL, RLS/no-policy state, direct-delete denial, and
the healthy `occurred_at` index. Inside a transaction it inserts reserved
synthetic rows around `2000-01-01`, proves oldest-first batching and the exact
cutoff boundary through `service_role`, proves client execution and direct
deletion are denied, reaches a zero result, and rolls everything back.

During an incident, use aggregate evidence rather than row contents to confirm
enforcement:

```sql
select
    status,
    started_at,
    finished_at,
    processed_count,
    batch_count,
    reached_max_batches,
    metadata ->> 'retention_days' as retention_days,
    metadata ->> 'batch_size' as batch_size,
    metadata ->> 'max_batches' as max_batches
from public.job_runs
where job_name = 'authentication_audit_retention_cleanup'
order by started_at desc
limit 14;

select
    count(*) as expired_backlog
from public.authentication_audit_events
where occurred_at
      < pg_catalog.now() - interval '180 days';
```

A recent succeeded run with `retention_days = 180`, an explicit zero-proven
completion (`reached_max_batches = false`), and zero expired backlog proves the
configured policy is functioning at that observation time. A failed run, a
nonzero backlog, or repeated capacity flags is evidence requiring
investigation, not a reason to widen the cutoff.

## Database-first rollout

Production rollout is documentation only in this change.

1. Confirm the reviewed branch, clean diff, and zero-skip CI evidence.
2. Against an isolated dev database, run
   `authentication_audit_retention_migration_preflight.sql`.
3. Apply the complete transactional
   `authentication_audit_retention.sql` migration.
4. Run `verify_authentication_audit_retention_migration.sql`; use its
   rollback-only synthetic cleanup as the controlled safety run.
5. Deploy the cleanup-job code only after database verification succeeds.
6. Configure the single daily Railway schedule and command documented above.
7. Trigger one controlled job execution and confirm a succeeded `job_runs`
   record, bounded counts, and no persistence or monitoring warning.
8. Observe at least one normal scheduled execution and confirm the aggregate
   expired-backlog query.
9. Only then consider making the Draft PR ready.

## Rollback

1. Roll the application/job code back first.
2. Disable the Railway schedule so no new cleanup calls occur.
3. Retain `authentication_audit_events`, all remaining rows, its indexes, and
   the append-only record RPC.
4. Leave the cleanup RPC in place because it is inert without a caller. Drop
   it only through a separately reviewed forward migration with explicit
   approval.
5. Confirm no later cleanup job run exists after schedule disablement, the
   prior application still records audit events, direct service-role deletion
   remains denied, and the remaining row count no longer falls due to cleanup.

Rows already and legitimately deleted after crossing the approved cutoff
cannot be guaranteed restorable. Database recovery is reserved for actual
corruption and follows the existing backup/PITR process, not routine feature
rollback.

## Privacy and scope

This change adds no audit columns, event types, user attribution, request
correlation, admin endpoint, external sink, queue, partition, or legal-hold
store. RPC payloads contain only a cutoff timestamp and bounded integer.
Logs, job metadata, and monitoring contain only bounded counts and categories.
Authentication behavior and its non-fatal audit-persistence boundary are
unchanged.
