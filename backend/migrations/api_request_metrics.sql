-- E05-01: Persistent API request metrics for admin monitoring.
-- Safe to re-run. Apply before relying on GET /admin/monitoring api_errors.

create table if not exists public.api_request_metrics (
    id uuid primary key default gen_random_uuid(),
    recorded_at timestamptz not null default now(),
    method text not null check (method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD')),
    normalized_path text not null check (length(normalized_path) between 1 and 240),
    status_code integer not null check (status_code between 100 and 599),
    duration_ms integer not null check (duration_ms >= 0),
    is_error boolean not null,
    created_at timestamptz not null default now()
);

alter table public.api_request_metrics enable row level security;

grant select, insert, delete on public.api_request_metrics to service_role;

create index if not exists idx_api_request_metrics_recorded_at
    on public.api_request_metrics(recorded_at desc);

create index if not exists idx_api_request_metrics_error_recorded_at
    on public.api_request_metrics(is_error, recorded_at desc);

create index if not exists idx_api_request_metrics_path_recorded_at
    on public.api_request_metrics(normalized_path, recorded_at desc);

create or replace function public.cleanup_api_request_metrics(retention_days integer default 14)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    deleted_count integer;
begin
    if retention_days is null or retention_days < 1 or retention_days > 365 then
        raise exception 'retention_days must be between 1 and 365';
    end if;

    delete from public.api_request_metrics
    where recorded_at < now() - make_interval(days => retention_days);

    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$;

grant execute on function public.cleanup_api_request_metrics(integer) to service_role;
