-- E09-02 post-migration verification.
--
-- This script validates the live schema and exercises the service_role path.
-- All test writes, including the cleanup RPC deletion, are rolled back. The
-- repeatable-read snapshot plus the 365-day guard ensures cleanup can only
-- see and delete the synthetic event created by this transaction.
-- Run with psql -X -v ON_ERROR_STOP=1 after analytics_events.sql.

begin transaction isolation level repeatable read;
set local statement_timeout = '30s';
set local lock_timeout = '5s';

do $schema_verification$
declare
    service_role_id oid := (
        select oid from pg_catalog.pg_roles where rolname = 'service_role'
    );
    analytics_table regclass := to_regclass('public.analytics_events');
    metrics_function regprocedure := to_regprocedure(
        'public.get_analytics_event_metrics(timestamp with time zone,timestamp with time zone)'
    );
    cleanup_function regprocedure := to_regprocedure(
        'public.cleanup_analytics_events(integer)'
    );
    expected_columns_found integer;
    check_constraint_count integer;
    table_grant_count integer;
    function_grant_count integer;
    rls_enabled boolean;
    metrics_is_security_definer boolean;
    metrics_volatility "char";
    cleanup_is_security_definer boolean;
begin
    if service_role_id is null then
        raise exception 'analytics verification failed: role service_role does not exist';
    end if;

    if analytics_table is null then
        raise exception 'analytics verification failed: table public.analytics_events does not exist';
    end if;

    select c.relrowsecurity
    into rls_enabled
    from pg_catalog.pg_class as c
    where c.oid = analytics_table;

    if not rls_enabled then
        raise exception 'analytics verification failed: RLS is not enabled on public.analytics_events';
    end if;

    select count(*)
    into expected_columns_found
    from (
        values
            ('id', 'uuid'::regtype, true),
            ('recorded_at', 'timestamp with time zone'::regtype, true),
            ('event_name', 'text'::regtype, true),
            ('platform', 'text'::regtype, true),
            ('app_version', 'text'::regtype, false),
            ('properties', 'jsonb'::regtype, true),
            ('created_at', 'timestamp with time zone'::regtype, true)
    ) as expected(column_name, type_id, is_not_null)
    join pg_catalog.pg_attribute as attribute
      on attribute.attrelid = analytics_table
     and attribute.attname = expected.column_name
     and attribute.atttypid = expected.type_id
     and attribute.attnotnull = expected.is_not_null
     and not attribute.attisdropped;

    if expected_columns_found <> 7 then
        raise exception 'analytics verification failed: analytics_events columns or nullability do not match the migration';
    end if;

    if not exists (
        select 1
        from pg_catalog.pg_constraint as constraint_definition
        join pg_catalog.pg_attribute as id_attribute
          on id_attribute.attrelid = constraint_definition.conrelid
         and id_attribute.attname = 'id'
        where constraint_definition.conrelid = analytics_table
          and constraint_definition.contype = 'p'
          and constraint_definition.conkey = array[id_attribute.attnum]::smallint[]
    ) then
        raise exception 'analytics verification failed: analytics_events.id is not the primary key';
    end if;

    select count(*)
    into check_constraint_count
    from pg_catalog.pg_constraint as constraint_definition
    where constraint_definition.conrelid = analytics_table
      and constraint_definition.contype = 'c'
      and constraint_definition.convalidated;

    if check_constraint_count < 4 then
        raise exception 'analytics verification failed: expected analytics_events CHECK constraints are missing';
    end if;

    if to_regclass('public.idx_analytics_events_recorded_at') is null
       or to_regclass('public.idx_analytics_events_event_recorded_at') is null then
        raise exception 'analytics verification failed: expected analytics_events indexes are missing';
    end if;

    select count(distinct privilege.privilege_type)
    into table_grant_count
    from pg_catalog.pg_class as table_definition
    cross join lateral aclexplode(table_definition.relacl) as privilege
    where table_definition.oid = analytics_table
      and privilege.grantee = service_role_id
      and privilege.privilege_type in ('SELECT', 'INSERT', 'DELETE');

    if table_grant_count <> 3 then
        raise exception 'analytics verification failed: service_role requires direct SELECT, INSERT, and DELETE grants on analytics_events';
    end if;

    if metrics_function is null or cleanup_function is null then
        raise exception 'analytics verification failed: expected analytics RPC signatures do not exist';
    end if;

    select function_definition.prosecdef, function_definition.provolatile
    into metrics_is_security_definer, metrics_volatility
    from pg_catalog.pg_proc as function_definition
    where function_definition.oid = metrics_function;

    select function_definition.prosecdef
    into cleanup_is_security_definer
    from pg_catalog.pg_proc as function_definition
    where function_definition.oid = cleanup_function;

    if not metrics_is_security_definer or metrics_volatility <> 's' then
        raise exception 'analytics verification failed: get_analytics_event_metrics must be STABLE SECURITY DEFINER';
    end if;

    if not cleanup_is_security_definer then
        raise exception 'analytics verification failed: cleanup_analytics_events must be SECURITY DEFINER';
    end if;

    select count(*)
    into function_grant_count
    from (
        select function_definition.oid
        from pg_catalog.pg_proc as function_definition
        cross join lateral aclexplode(function_definition.proacl) as privilege
        where function_definition.oid in (metrics_function, cleanup_function)
          and privilege.grantee = service_role_id
          and privilege.privilege_type = 'EXECUTE'
        group by function_definition.oid
    ) as directly_executable_functions;

    if function_grant_count <> 2 then
        raise exception 'analytics verification failed: service_role requires direct EXECUTE grants on both analytics RPCs';
    end if;
end;
$schema_verification$;

-- A fixed rollout-only UUID makes it possible to prove exactly which row the
-- test owns. Refuse to proceed if that UUID or any production row eligible for
-- the widest permitted cleanup window already exists.
select set_config(
    'analytics_rollout.test_recorded_at',
    (transaction_timestamp() - interval '366 days')::text,
    true
);

do $cleanup_safety_guard$
begin
    if exists (
        select 1
        from public.analytics_events
        where recorded_at < transaction_timestamp() - interval '365 days'
    ) then
        raise exception using
            errcode = 'P0001',
            message = 'analytics verification stopped: pre-existing events older than 365 days would enter the cleanup test',
            hint = 'Investigate retention drift; the verification transaction has not written or deleted anything.';
    end if;

    if exists (
        select 1
        from public.analytics_events
        where id = '00000000-0000-4000-8000-000000000902'::uuid
    ) then
        raise exception 'analytics verification stopped: reserved test event UUID already exists';
    end if;
end;
$cleanup_safety_guard$;

set local role service_role;

select set_config(
    'analytics_rollout.metric_count_before',
    coalesce((
        select sum(event_count)::text
        from public.get_analytics_event_metrics(
            current_setting('analytics_rollout.test_recorded_at')::timestamptz - interval '1 microsecond',
            current_setting('analytics_rollout.test_recorded_at')::timestamptz + interval '1 microsecond'
        )
        where event_name = 'app_open'
          and platform = 'web'
    ), '0'),
    true
);

insert into public.analytics_events (
    id,
    recorded_at,
    event_name,
    platform,
    app_version,
    properties
)
values (
    '00000000-0000-4000-8000-000000000902'::uuid,
    current_setting('analytics_rollout.test_recorded_at')::timestamptz,
    'app_open',
    'web',
    'rollout-check',
    '{}'::jsonb
);

do $metrics_verification$
declare
    metric_count_after bigint;
begin
    select coalesce(sum(event_count), 0)
    into metric_count_after
    from public.get_analytics_event_metrics(
        current_setting('analytics_rollout.test_recorded_at')::timestamptz - interval '1 microsecond',
        current_setting('analytics_rollout.test_recorded_at')::timestamptz + interval '1 microsecond'
    )
    where event_name = 'app_open'
      and platform = 'web';

    if metric_count_after <> current_setting(
        'analytics_rollout.metric_count_before'
    )::bigint + 1 then
        raise exception 'analytics verification failed: get_analytics_event_metrics did not count the synthetic event';
    end if;
end;
$metrics_verification$;

-- Exercise every CHECK-constraint category. Each expected violation runs in
-- its own PL/pgSQL subtransaction; an unexpectedly accepted row aborts the
-- verification and the outer transaction is still rolled back.
do $constraint_verification$
begin
    begin
        insert into public.analytics_events (event_name, platform, properties)
        values ('unknown_event', 'web', '{}'::jsonb);
        raise exception 'analytics verification failed: invalid event_name was accepted';
    exception when check_violation then
        null;
    end;

    begin
        insert into public.analytics_events (event_name, platform, properties)
        values ('app_open', 'desktop', '{}'::jsonb);
        raise exception 'analytics verification failed: invalid platform was accepted';
    exception when check_violation then
        null;
    end;

    begin
        insert into public.analytics_events (
            event_name,
            platform,
            app_version,
            properties
        )
        values ('app_open', 'web', '', '{}'::jsonb);
        raise exception 'analytics verification failed: empty app_version was accepted';
    exception when check_violation then
        null;
    end;

    begin
        insert into public.analytics_events (event_name, platform, properties)
        values ('app_open', 'web', '{"screen":"map"}'::jsonb);
        raise exception 'analytics verification failed: app_open properties were accepted';
    exception when check_violation then
        null;
    end;

    begin
        insert into public.analytics_events (event_name, platform, properties)
        values (
            'screen_view',
            'web',
            '{"screen":"map","extra":"not-allowed"}'::jsonb
        );
        raise exception 'analytics verification failed: extra screen_view properties were accepted';
    exception when check_violation then
        null;
    end;

    begin
        insert into public.analytics_events (event_name, platform, properties)
        values (
            'screen_view',
            'web',
            '{"screen":"unapproved-screen"}'::jsonb
        );
        raise exception 'analytics verification failed: unapproved screen_view screen was accepted';
    exception when check_violation then
        null;
    end;
end;
$constraint_verification$;

do $cleanup_verification$
declare
    deleted_count integer;
begin
    select public.cleanup_analytics_events(365)
    into deleted_count;

    if deleted_count <> 1 then
        raise exception 'analytics verification failed: cleanup_analytics_events deleted % rows instead of the one synthetic event', deleted_count;
    end if;

    if exists (
        select 1
        from public.analytics_events
        where id = '00000000-0000-4000-8000-000000000902'::uuid
    ) then
        raise exception 'analytics verification failed: cleanup_analytics_events did not delete the synthetic event';
    end if;
end;
$cleanup_verification$;

reset role;

do $verification_complete$
begin
    raise notice 'analytics migration verification passed; synthetic changes are being rolled back';
end;
$verification_complete$;

rollback;
