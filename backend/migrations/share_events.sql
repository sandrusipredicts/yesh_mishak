-- E06-02: First-party sharing and deep-link analytics events.
-- Safe to re-run. Apply after api_request_metrics.sql.
--
-- Privacy envelope: this table intentionally stores only first-party
-- mechanism/category metrics. It must not store user IDs, game IDs, field IDs,
-- raw URLs, query parameters, coordinates, receiving applications, or generic
-- metadata.

create table if not exists public.share_events (
    id uuid primary key default gen_random_uuid(),
    recorded_at timestamptz not null default now(),
    event_name text not null check (event_name in ('share_action', 'link_open')),
    entity_type text not null check (entity_type in ('game', 'field')),
    platform text not null check (platform in ('web', 'android', 'ios')),
    mechanism text check (
        mechanism is null
        or mechanism in ('native_share', 'copy_link')
    ),
    outcome text not null check (
        outcome in (
            'shared',
            'copied',
            'cancelled',
            'unavailable',
            'failed',
            'valid',
            'invalid',
            'not_found',
            'deferred_for_auth'
        )
    ),
    error_category text check (
        error_category is null
        or error_category in (
            'invalid_resource',
            'unsupported_platform',
            'share_unavailable',
            'share_failed',
            'clipboard_failed',
            'malformed_link',
            'unsupported_link',
            'resource_not_found',
            'resolution_failed'
        )
    ),
    created_at timestamptz not null default now(),
    check (
        (
            event_name = 'share_action'
            and mechanism is not null
            and outcome in ('shared', 'copied', 'cancelled', 'unavailable', 'failed')
        )
        or (
            event_name = 'link_open'
            and mechanism is null
            and outcome in ('valid', 'invalid', 'not_found', 'deferred_for_auth')
        )
    )
);

alter table public.share_events enable row level security;

grant select, insert, delete on public.share_events to service_role;

create index if not exists idx_share_events_recorded_at
    on public.share_events(recorded_at desc);

create index if not exists idx_share_events_event_recorded_at
    on public.share_events(event_name, recorded_at desc);

create index if not exists idx_share_events_entity_recorded_at
    on public.share_events(entity_type, recorded_at desc);

create or replace function public.get_share_event_metrics(
    window_start timestamptz,
    window_end timestamptz
)
returns table (
    event_name text,
    entity_type text,
    platform text,
    mechanism text,
    outcome text,
    error_category text,
    event_count bigint
)
language sql
stable
security definer
set search_path = public
as $$
    select
        share_events.event_name,
        share_events.entity_type,
        share_events.platform,
        share_events.mechanism,
        share_events.outcome,
        share_events.error_category,
        count(*)::bigint as event_count
    from public.share_events
    where recorded_at >= window_start
      and recorded_at < window_end
    group by
        share_events.event_name,
        share_events.entity_type,
        share_events.platform,
        share_events.mechanism,
        share_events.outcome,
        share_events.error_category
    order by
        share_events.event_name,
        share_events.entity_type,
        share_events.platform,
        share_events.mechanism,
        share_events.outcome,
        share_events.error_category;
$$;

grant execute on function public.get_share_event_metrics(timestamptz, timestamptz) to service_role;

create or replace function public.cleanup_share_events(retention_days integer default 90)
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

    delete from public.share_events
    where recorded_at < now() - make_interval(days => retention_days);

    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$;

grant execute on function public.cleanup_share_events(integer) to service_role;
