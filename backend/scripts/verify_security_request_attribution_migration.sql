-- ISSUE-1031 item 3 post-migration verification.
-- All synthetic rows, access-audit rows, and cleanup effects are rolled back.

begin;
set local statement_timeout = '30s';
set local lock_timeout = '5s';

do $security_attribution_catalog_verification$
declare
    current_owner_id oid := pg_catalog.to_regrole(current_user);
    table_name text;
    table_oid pg_catalog.regclass;
    function_oid pg_catalog.regprocedure;
    expected_acl_count integer;
    constraint_definition text;
begin
    foreach table_name in array array[
        'security_request_attribution_events',
        'security_investigation_access_events'
    ]
    loop
        table_oid := pg_catalog.to_regclass(
            pg_catalog.format('public.%I', table_name)
        );
        if table_oid is null then
            raise exception 'security attribution verification failed: table is missing';
        end if;

        if not exists (
            select 1
            from pg_catalog.pg_class as table_definition
            where table_definition.oid = table_oid
              and table_definition.relowner = current_owner_id
              and table_definition.relrowsecurity
              and not table_definition.relforcerowsecurity
        )
           or exists (
               select 1
               from pg_catalog.pg_policy as policy_definition
               where policy_definition.polrelid = table_oid
           ) then
            raise exception 'security attribution verification failed: table security differs';
        end if;

        if (
            select pg_catalog.count(*)
            from pg_catalog.pg_class as table_definition
            cross join lateral pg_catalog.aclexplode(
                coalesce(
                    table_definition.relacl,
                    pg_catalog.acldefault(
                        'r',
                        table_definition.relowner
                    )
                )
            ) as privilege
            where table_definition.oid = table_oid
              and privilege.grantee = current_owner_id
              and privilege.privilege_type in (
                  'SELECT',
                  'INSERT',
                  'DELETE'
              )
              and not privilege.is_grantable
        ) <> 3
           or exists (
               select 1
               from pg_catalog.pg_class as table_definition
               cross join lateral pg_catalog.aclexplode(
                   coalesce(
                       table_definition.relacl,
                       pg_catalog.acldefault(
                           'r',
                           table_definition.relowner
                       )
                   )
               ) as privilege
               where table_definition.oid = table_oid
                 and not (
                     privilege.grantee = current_owner_id
                     and privilege.privilege_type in (
                         'SELECT',
                         'INSERT',
                         'DELETE'
                     )
                     and not privilege.is_grantable
                 )
           ) then
            raise exception 'security attribution verification failed: table ACL differs';
        end if;

        if (
            select pg_catalog.count(*)
            from pg_catalog.pg_attribute as attribute_definition
            cross join lateral pg_catalog.aclexplode(
                attribute_definition.attacl
            ) as privilege
            where attribute_definition.attrelid = table_oid
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped
              and attribute_definition.attname = 'id'
              and privilege.grantee = current_owner_id
              and privilege.privilege_type = 'UPDATE'
              and not privilege.is_grantable
        ) <> 1
           or exists (
               select 1
               from pg_catalog.pg_attribute as attribute_definition
               cross join lateral pg_catalog.aclexplode(
                   attribute_definition.attacl
               ) as privilege
               where attribute_definition.attrelid = table_oid
                 and attribute_definition.attnum > 0
                 and not attribute_definition.attisdropped
                 and not (
                     attribute_definition.attname = 'id'
                     and privilege.grantee = current_owner_id
                     and privilege.privilege_type = 'UPDATE'
                     and not privilege.is_grantable
                 )
           ) then
            raise exception 'security attribution verification failed: column ACL differs';
        end if;

        if pg_catalog.has_table_privilege(
            'service_role',
            table_oid,
            'SELECT'
        )
           or pg_catalog.has_table_privilege(
               'service_role',
               table_oid,
               'INSERT'
           )
           or pg_catalog.has_table_privilege(
               'service_role',
               table_oid,
               'UPDATE'
           )
           or pg_catalog.has_table_privilege(
               'service_role',
               table_oid,
               'DELETE'
           )
           or pg_catalog.has_table_privilege('anon', table_oid, 'SELECT')
           or pg_catalog.has_table_privilege(
               'authenticated',
               table_oid,
               'SELECT'
           ) then
            raise exception 'security attribution verification failed: direct access differs';
        end if;
    end loop;

    foreach function_oid in array array[
        'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)'::pg_catalog.regprocedure,
        'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'::pg_catalog.regprocedure,
        'public.cleanup_security_request_attribution_events(timestamptz,integer)'::pg_catalog.regprocedure,
        'public.cleanup_security_investigation_access_events(timestamptz,integer)'::pg_catalog.regprocedure
    ]
    loop
        if not exists (
            select 1
            from pg_catalog.pg_proc as function_definition
            where function_definition.oid = function_oid
              and function_definition.proowner = current_owner_id
              and function_definition.prosecdef
              and function_definition.provolatile = 'v'
              and function_definition.proparallel = 'u'
              and not function_definition.proleakproof
              and not function_definition.proisstrict
              and function_definition.proconfig =
                  array['search_path=pg_catalog']::text[]
        ) then
            raise exception 'security attribution verification failed: function security differs';
        end if;

        expected_acl_count := case
            when function_oid =
                 'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'::pg_catalog.regprocedure
                then 1
            else 2
        end;

        if (
            select pg_catalog.count(*)
            from pg_catalog.pg_proc as function_definition
            cross join lateral pg_catalog.aclexplode(
                coalesce(
                    function_definition.proacl,
                    pg_catalog.acldefault(
                        'f',
                        function_definition.proowner
                    )
                )
            ) as privilege
            where function_definition.oid = function_oid
              and privilege.privilege_type = 'EXECUTE'
              and not privilege.is_grantable
              and (
                  privilege.grantee = current_owner_id
                  or (
                      expected_acl_count = 2
                      and privilege.grantee =
                          pg_catalog.to_regrole('service_role')
                  )
              )
        ) <> expected_acl_count
           or exists (
               select 1
               from pg_catalog.pg_proc as function_definition
               cross join lateral pg_catalog.aclexplode(
                   coalesce(
                       function_definition.proacl,
                       pg_catalog.acldefault(
                           'f',
                           function_definition.proowner
                       )
                   )
               ) as privilege
               where function_definition.oid = function_oid
                 and not (
                     privilege.privilege_type = 'EXECUTE'
                     and not privilege.is_grantable
                     and (
                         privilege.grantee = current_owner_id
                         or (
                             expected_acl_count = 2
                             and privilege.grantee =
                                 pg_catalog.to_regrole('service_role')
                         )
                     )
                 )
           ) then
            raise exception 'security attribution verification failed: function ACL differs';
        end if;
    end loop;

    if (
        select pg_catalog.count(*)
        from pg_catalog.pg_class as index_definition
        where index_definition.oid in (
            'public.security_request_attribution_events_pkey'::pg_catalog.regclass,
            'public.security_request_attribution_events_request_event_id_key'::pg_catalog.regclass,
            'public.idx_security_attribution_cleanup'::pg_catalog.regclass,
            'public.idx_security_attribution_environment_window'::pg_catalog.regclass,
            'public.idx_security_attribution_pseudonym_epoch'::pg_catalog.regclass,
            'public.security_investigation_access_events_pkey'::pg_catalog.regclass,
            'public.security_investigation_access_events_access_event_id_key'::pg_catalog.regclass,
            'public.idx_security_investigation_access_cleanup'::pg_catalog.regclass,
            'public.idx_security_investigation_access_incident'::pg_catalog.regclass
        )
          and index_definition.relkind = 'i'
    ) <> 9 then
        raise exception 'security attribution verification failed: index set differs';
    end if;

    if (
        select pg_catalog.count(*)
        from pg_catalog.pg_constraint as catalog_constraint
        where catalog_constraint.conrelid in (
            'public.security_request_attribution_events'::pg_catalog.regclass,
            'public.security_investigation_access_events'::pg_catalog.regclass
        )
    ) <> 27
       or exists (
           select 1
           from pg_catalog.pg_constraint as catalog_constraint
           where catalog_constraint.conrelid in (
               'public.security_request_attribution_events'::pg_catalog.regclass,
               'public.security_investigation_access_events'::pg_catalog.regclass
           )
             and catalog_constraint.conname not in (
                 'security_attribution_environment_check',
                 'security_attribution_epoch_check',
                 'security_attribution_failure_category_check',
                 'security_attribution_key_version_check',
                 'security_attribution_method_check',
                 'security_attribution_outcome_check',
                 'security_attribution_outcome_failure_check',
                 'security_attribution_pseudonym_check',
                 'security_attribution_request_event_nonzero',
                 'security_attribution_route_registry_check',
                 'security_attribution_server_correlation_nonzero',
                 'security_attribution_timestamp_check',
                 'security_request_attribution_events_pkey',
                 'security_request_attribution_events_request_event_id_key',
                 'security_investigation_access_action_check',
                 'security_investigation_access_capability_check',
                 'security_investigation_access_environment_check',
                 'security_investigation_access_events_access_event_id_key',
                 'security_investigation_access_events_pkey',
                 'security_investigation_access_failure_check',
                 'security_investigation_access_ids_nonzero',
                 'security_investigation_access_limit_check',
                 'security_investigation_access_outcome_check',
                 'security_investigation_access_outcome_failure_check',
                 'security_investigation_access_result_count_check',
                 'security_investigation_access_timestamp_check',
                 'security_investigation_access_window_check'
             )
       ) then
        raise exception 'security attribution verification failed: constraint set differs';
    end if;

    select pg_catalog.pg_get_constraintdef(
        catalog_constraint.oid,
        true
    )
    into constraint_definition
    from pg_catalog.pg_constraint as catalog_constraint
    where catalog_constraint.conrelid =
          'public.security_request_attribution_events'::pg_catalog.regclass
      and catalog_constraint.conname =
          'security_attribution_route_registry_check';

    if pg_catalog.strpos(
        constraint_definition,
        'auth_logout'
    ) = 0
       or pg_catalog.strpos(
           constraint_definition,
           'admin_content_report_update'
       ) = 0
       or pg_catalog.strpos(
           constraint_definition,
           'session_security_change'
       ) = 0
       or pg_catalog.strpos(
           constraint_definition,
           'admin_moderation_change'
       ) = 0 then
        raise exception 'security attribution verification failed: route taxonomy differs';
    end if;

    select pg_catalog.pg_get_constraintdef(
        catalog_constraint.oid,
        true
    )
    into constraint_definition
    from pg_catalog.pg_constraint as catalog_constraint
    where catalog_constraint.conrelid =
          'public.security_investigation_access_events'::pg_catalog.regclass
      and catalog_constraint.conname =
          'security_investigation_access_capability_check';

    if pg_catalog.strpos(
        constraint_definition,
        'owner_activation_gate'
    ) = 0
       or pg_catalog.strpos(
           constraint_definition,
           'security_evidence_reader'
       ) = 0 then
        raise exception 'security attribution verification failed: access taxonomy differs';
    end if;
end;
$security_attribution_catalog_verification$;

set local role service_role;

do $security_attribution_service_role_ingestion$
declare
    first_status text;
    replay_status text;
begin
    first_status := public.record_security_request_attribution_event(
        '00000000-0000-4000-8000-000000001301'::uuid,
        '2000-01-01 00:00:00+00'::timestamptz,
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
        '2000-01',
        1::smallint,
        'development',
        'session_security_change',
        'auth_logout',
        'POST',
        'succeeded',
        null,
        '00000000-0000-4000-8000-000000001302'::uuid
    );
    replay_status := public.record_security_request_attribution_event(
        '00000000-0000-4000-8000-000000001301'::uuid,
        '2000-01-01 00:00:00+00'::timestamptz,
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',
        '2000-01',
        1::smallint,
        'development',
        'session_security_change',
        'auth_logout',
        'POST',
        'succeeded',
        null,
        '00000000-0000-4000-8000-000000001302'::uuid
    );

    if first_status <> 'inserted'
       or replay_status <> 'already_recorded' then
        raise exception 'security attribution verification failed: ingestion status differs';
    end if;

    begin
        perform 1
        from public.security_request_attribution_events;
        raise exception 'security attribution verification failed: service SELECT succeeded';
    exception
        when insufficient_privilege then null;
    end;

    begin
        delete from public.security_request_attribution_events;
        raise exception 'security attribution verification failed: service DELETE succeeded';
    exception
        when insufficient_privilege then null;
    end;

    begin
        perform public.query_security_request_attribution_events(
            '00000000-0000-4000-8000-000000001303'::uuid,
            'development',
            '2000-01-01 00:00:00+00'::timestamptz,
            '2000-01-02 00:00:00+00'::timestamptz,
            10
        );
        raise exception 'security attribution verification failed: owner-only query executed as service_role';
    exception
        when insufficient_privilege then null;
    end;
end;
$security_attribution_service_role_ingestion$;

reset role;

do $security_attribution_owner_query$
declare
    returned_status text;
    returned_count integer;
    audit_count integer;
begin
    select
        pg_catalog.min(query_result.query_status),
        pg_catalog.count(*) filter (
            where query_result.request_event_id is not null
        )::integer
    into returned_status, returned_count
    from public.query_security_request_attribution_events(
        '00000000-0000-4000-8000-000000001303'::uuid,
        'development',
        '2000-01-01 00:00:00+00'::timestamptz,
        '2000-01-02 00:00:00+00'::timestamptz,
        10
    ) as query_result;

    select pg_catalog.count(*)::integer
    into audit_count
    from public.security_investigation_access_events
    where incident_id =
          '00000000-0000-4000-8000-000000001303'::uuid
      and outcome = 'succeeded'
      and result_count = 1;

    if returned_status <> 'succeeded'
       or returned_count <> 1
       or audit_count <> 1 then
        raise exception 'security attribution verification failed: bounded query/audit differs';
    end if;

    select pg_catalog.min(query_result.query_status)
    into returned_status
    from public.query_security_request_attribution_events(
        '00000000-0000-4000-8000-000000001304'::uuid,
        'development',
        '2000-01-02 00:00:00+00'::timestamptz,
        '2000-01-01 00:00:00+00'::timestamptz,
        10
    ) as query_result;

    if returned_status <> 'rejected'
       or not exists (
           select 1
           from public.security_investigation_access_events
           where incident_id =
                 '00000000-0000-4000-8000-000000001304'::uuid
             and outcome = 'rejected'
             and failure_category = 'invalid_window'
       ) then
        raise exception 'security attribution verification failed: rejected access audit differs';
    end if;
end;
$security_attribution_owner_query$;

insert into public.security_request_attribution_events (
    request_event_id,
    occurred_at,
    account_pseudonym,
    pseudonym_epoch,
    pseudonym_key_version,
    environment,
    event_category,
    route_key,
    http_method,
    outcome,
    failure_category
)
values
    (
        '00000000-0000-4000-8000-000000001305'::uuid,
        '2000-01-01 00:00:01+00'::timestamptz,
        'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB',
        '2000-01',
        1,
        'development',
        'session_security_change',
        'auth_logout',
        'POST',
        'succeeded',
        null
    ),
    (
        '00000000-0000-4000-8000-000000001306'::uuid,
        '2000-01-02 00:00:00+00'::timestamptz,
        'CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC',
        '2000-01',
        1,
        'development',
        'session_security_change',
        'auth_logout',
        'POST',
        'succeeded',
        null
    );

insert into public.security_investigation_access_events (
    access_event_id,
    occurred_at,
    incident_id,
    investigator_capability,
    action_category,
    query_window_start,
    query_window_end,
    requested_limit,
    result_count,
    environment,
    outcome,
    failure_category
)
values
    (
        '00000000-0000-4000-8000-000000001307'::uuid,
        '2000-01-01 00:00:00+00'::timestamptz,
        '00000000-0000-4000-8000-000000001308'::uuid,
        'owner_activation_gate',
        'query',
        '2000-01-01 00:00:00+00'::timestamptz,
        '2000-01-01 00:00:01+00'::timestamptz,
        10,
        0,
        'development',
        'succeeded',
        null
    ),
    (
        '00000000-0000-4000-8000-000000001309'::uuid,
        '2000-01-02 00:00:00+00'::timestamptz,
        '00000000-0000-4000-8000-000000001310'::uuid,
        'owner_activation_gate',
        'query',
        '2000-01-01 00:00:00+00'::timestamptz,
        '2000-01-01 00:00:01+00'::timestamptz,
        10,
        0,
        'development',
        'succeeded',
        null
    );

set local role service_role;

do $security_attribution_retention_verification$
declare
    attribution_deleted integer;
    access_deleted integer;
begin
    attribution_deleted :=
        public.cleanup_security_request_attribution_events(
            '2000-01-02 00:00:00+00'::timestamptz,
            2
        );
    access_deleted :=
        public.cleanup_security_investigation_access_events(
            '2000-01-02 00:00:00+00'::timestamptz,
            1
        );

    if attribution_deleted <> 2
       or access_deleted <> 1
       or public.cleanup_security_request_attribution_events(
           '2000-01-02 00:00:00+00'::timestamptz,
           2
       ) <> 0
       or public.cleanup_security_investigation_access_events(
           '2000-01-02 00:00:00+00'::timestamptz,
           1
       ) <> 0 then
        raise exception 'security attribution verification failed: cleanup counts differ';
    end if;
end;
$security_attribution_retention_verification$;

reset role;

do $security_attribution_boundary_verification$
begin
    if not exists (
        select 1
        from public.security_request_attribution_events
        where request_event_id =
              '00000000-0000-4000-8000-000000001306'::uuid
          and occurred_at =
              '2000-01-02 00:00:00+00'::timestamptz
    )
       or not exists (
           select 1
           from public.security_investigation_access_events
           where access_event_id =
                 '00000000-0000-4000-8000-000000001309'::uuid
             and occurred_at =
                 '2000-01-02 00:00:00+00'::timestamptz
       ) then
        raise exception 'security attribution verification failed: cutoff row was deleted';
    end if;
end;
$security_attribution_boundary_verification$;

select
    current_user as trusted_owner,
    pg_catalog.has_function_privilege(
        'service_role',
        'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)',
        'EXECUTE'
    ) as service_ingestion_execute,
    pg_catalog.has_function_privilege(
        'service_role',
        'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)',
        'EXECUTE'
    ) as service_query_execute,
    pg_catalog.has_table_privilege(
        'service_role',
        'public.security_request_attribution_events',
        'SELECT'
    ) as service_direct_select,
    pg_catalog.has_table_privilege(
        'service_role',
        'public.security_request_attribution_events',
        'DELETE'
    ) as service_direct_delete;

do $security_attribution_verification_passed$
begin
    raise notice 'security attribution verification passed; synthetic changes will be rolled back';
end;
$security_attribution_verification_passed$;

rollback;
