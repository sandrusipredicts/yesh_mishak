-- E09-02: First-party event-analytics ingestion pipeline.
-- Safe to re-run. Apply after api_request_metrics.sql.
--
-- Privacy envelope (owner decision D1): events are strictly anonymous.
-- This table intentionally stores only event volume dimensions. It must not
-- store user IDs (raw or hashed), resource IDs, raw URLs, query parameters,
-- coordinates, free text, or any other personal data.
--
-- The event/property contract is owned by the backend registry
-- (backend/app/analytics/registry.py); the CHECK constraints below are
-- defense in depth for the seed events approved in owner decision D2.

create table if not exists public.analytics_events (
    id uuid primary key default gen_random_uuid(),
    recorded_at timestamptz not null default now(),
    event_name text not null check (event_name in ('app_open', 'screen_view')),
    platform text not null check (platform in ('web', 'android', 'ios')),
    app_version text check (
        app_version is null
        or (char_length(app_version) between 1 and 32)
    ),
    properties jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    check (
        (
            event_name = 'app_open'
            and properties = '{}'::jsonb
        )
        or (
            event_name = 'screen_view'
            and properties - 'screen' = '{}'::jsonb
            and properties ->> 'screen' in (
                'map',
                'game_details',
                'profile',
                'notifications',
                'admin'
            )
        )
    )
);

alter table public.analytics_events enable row level security;

grant select, insert, delete on public.analytics_events to service_role;

create index if not exists idx_analytics_events_recorded_at
    on public.analytics_events(recorded_at desc);

create index if not exists idx_analytics_events_event_recorded_at
    on public.analytics_events(event_name, recorded_at desc);

create or replace function public.get_analytics_event_metrics(
    window_start timestamptz,
    window_end timestamptz
)
returns table (
    event_day date,
    event_name text,
    platform text,
    event_count bigint
)
language sql
stable
security definer
set search_path = public
as $$
    select
        (date_trunc('day', analytics_events.recorded_at))::date as event_day,
        analytics_events.event_name,
        analytics_events.platform,
        count(*)::bigint as event_count
    from public.analytics_events
    where recorded_at >= window_start
      and recorded_at < window_end
    group by
        (date_trunc('day', analytics_events.recorded_at))::date,
        analytics_events.event_name,
        analytics_events.platform
    order by
        event_day,
        event_name,
        platform;
$$;

grant execute on function public.get_analytics_event_metrics(timestamptz, timestamptz) to service_role;

create or replace function public.cleanup_analytics_events(retention_days integer default 90)
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

    delete from public.analytics_events
    where recorded_at < now() - make_interval(days => retention_days);

    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$;

grant execute on function public.cleanup_analytics_events(integer) to service_role;
