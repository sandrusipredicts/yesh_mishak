-- E09-02 rollout gate. Read-only: safe to run against staging or production.
-- Run with psql -X -v ON_ERROR_STOP=1 before analytics_events.sql.

do $analytics_preflight$
declare
    service_role_id oid := (
        select oid from pg_catalog.pg_roles where rolname = 'service_role'
    );
    prerequisite_table regclass := to_regclass('public.api_request_metrics');
    prerequisite_cleanup regprocedure := to_regprocedure(
        'public.cleanup_api_request_metrics(integer)'
    );
    analytics_table regclass := to_regclass('public.analytics_events');
    metrics_function regprocedure := to_regprocedure(
        'public.get_analytics_event_metrics(timestamp with time zone,timestamp with time zone)'
    );
    cleanup_function regprocedure := to_regprocedure(
        'public.cleanup_analytics_events(integer)'
    );
    recorded_at_index regclass := to_regclass(
        'public.idx_analytics_events_recorded_at'
    );
    event_recorded_at_index regclass := to_regclass(
        'public.idx_analytics_events_event_recorded_at'
    );
    analytics_objects_present integer;
    prerequisite_rls_enabled boolean;
    prerequisite_grant_count integer;
begin
    if service_role_id is null then
        raise exception using
            errcode = 'P0001',
            message = 'analytics migration preflight failed: role service_role does not exist',
            hint = 'Run this workflow against the intended Supabase database as its database owner.';
    end if;

    if prerequisite_table is null or prerequisite_cleanup is null then
        raise exception using
            errcode = 'P0001',
            message = 'analytics migration preflight failed: api_request_metrics.sql is not fully applied',
            hint = 'Apply backend/migrations/api_request_metrics.sql first, then rerun this preflight.';
    end if;

    select c.relrowsecurity
    into prerequisite_rls_enabled
    from pg_catalog.pg_class as c
    where c.oid = prerequisite_table;

    select count(distinct privilege.privilege_type)
    into prerequisite_grant_count
    from pg_catalog.pg_class as c
    cross join lateral aclexplode(c.relacl) as privilege
    where c.oid = prerequisite_table
      and privilege.grantee = service_role_id
      and privilege.privilege_type in ('SELECT', 'INSERT', 'DELETE');

    if not prerequisite_rls_enabled or prerequisite_grant_count <> 3 then
        raise exception using
            errcode = 'P0001',
            message = 'analytics migration preflight failed: api_request_metrics.sql prerequisite is incomplete',
            hint = 'Restore its RLS and service_role grants before applying analytics_events.sql.';
    end if;

    select count(*)
    into analytics_objects_present
    from (
        values
            (analytics_table is not null),
            (metrics_function is not null),
            (cleanup_function is not null),
            (recorded_at_index is not null),
            (event_recorded_at_index is not null)
    ) as object_state(is_present)
    where is_present;

    if analytics_objects_present = 0 then
        raise notice 'analytics migration preflight passed: prerequisite is complete and analytics_events.sql is not yet applied';
    elsif analytics_objects_present = 5 then
        raise notice 'analytics migration preflight passed: analytics_events.sql core objects already exist; transactional re-application is allowed';
    else
        raise exception using
            errcode = 'P0001',
            message = format(
                'analytics migration preflight failed: partial analytics migration state (%s of 5 core objects present)',
                analytics_objects_present
            ),
            hint = 'Stop the rollout, inspect schema drift, and repair or transactionally re-apply analytics_events.sql only after review.';
    end if;
end;
$analytics_preflight$;
