-- E03-02: Persistent scheduled job run monitoring.
-- Safe to re-run. Apply before relying on Admin scheduled-job monitoring.

create table if not exists public.job_runs (
    id uuid primary key default gen_random_uuid(),
    job_name text not null check (length(job_name) between 1 and 120),
    status text not null check (status in ('running', 'succeeded', 'failed')),
    started_at timestamptz not null,
    finished_at timestamptz,
    duration_ms integer check (duration_ms is null or duration_ms >= 0),
    processed_count integer check (processed_count is null or processed_count >= 0),
    scanned_count integer check (scanned_count is null or scanned_count >= 0),
    reconciled_count integer check (reconciled_count is null or reconciled_count >= 0),
    skipped_count integer check (skipped_count is null or skipped_count >= 0),
    failed_count integer check (failed_count is null or failed_count >= 0),
    batch_count integer check (batch_count is null or batch_count >= 0),
    reached_max_batches boolean,
    error_type text check (error_type is null or length(error_type) <= 120),
    error_message text check (error_message is null or length(error_message) <= 500),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (
        (status = 'running' and finished_at is null)
        or (status in ('succeeded', 'failed') and finished_at is not null)
    )
);

alter table public.job_runs enable row level security;

grant select, insert, update on public.job_runs to service_role;

create index if not exists idx_job_runs_job_name_started_at
    on public.job_runs(job_name, started_at desc);

create index if not exists idx_job_runs_status_started_at
    on public.job_runs(status, started_at desc);

create index if not exists idx_job_runs_started_at
    on public.job_runs(started_at desc);
