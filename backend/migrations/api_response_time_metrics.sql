-- E05-02: Database-side response-time aggregation for admin monitoring.
-- Safe to re-run. Apply after backend/migrations/api_request_metrics.sql.

create or replace function public.get_api_response_time_metrics(
    window_start timestamptz,
    window_end timestamptz
)
returns table (
    sample_count bigint,
    average_ms numeric,
    p50_ms numeric,
    p95_ms numeric,
    max_ms numeric
)
language sql
stable
security definer
set search_path = public
as $$
    select
        count(*)::bigint as sample_count,
        coalesce(round(avg(duration_ms)::numeric, 2), 0.0)::numeric as average_ms,
        coalesce(
            round((percentile_cont(0.50) within group (order by duration_ms))::numeric, 2),
            0.0
        )::numeric as p50_ms,
        coalesce(
            round((percentile_cont(0.95) within group (order by duration_ms))::numeric, 2),
            0.0
        )::numeric as p95_ms,
        coalesce(max(duration_ms), 0)::numeric as max_ms
    from public.api_request_metrics
    where recorded_at >= window_start
      and recorded_at < window_end;
$$;

grant execute on function public.get_api_response_time_metrics(timestamptz, timestamptz) to service_role;
