-- ISSUE-1031 item 4 post-migration verification.
-- All synthetic rows and cleanup effects are rolled back.

begin;
set local statement_timeout = '30s';
set local lock_timeout = '5s';

do $authentication_audit_retention_catalog_verification$
declare
    audit_table regclass := to_regclass(
        'public.authentication_audit_events'
    );
    cleanup_function regprocedure := to_regprocedure(
        'public.cleanup_authentication_audit_events(timestamptz,integer)'
    );
    current_owner_id oid := to_regrole(current_user);
    cleanup_source text;
begin
    if audit_table is null or cleanup_function is null then
        raise exception 'authentication audit retention verification failed: required object is missing';
    end if;

    if (
        select table_definition.relowner
        from pg_catalog.pg_class as table_definition
        where table_definition.oid = audit_table
    ) <> current_owner_id
       or (
           select function_definition.proowner
           from pg_catalog.pg_proc as function_definition
           where function_definition.oid = cleanup_function
       ) <> current_owner_id then
        raise exception 'authentication audit retention verification failed: owner mismatch';
    end if;

    if (
        select count(*)
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::pg_catalog.regnamespace
          and function_definition.proname =
              'cleanup_authentication_audit_events'
    ) <> 1 then
        raise exception 'authentication audit retention verification failed: unexpected function overload';
    end if;

    if not exists (
        select 1
        from pg_catalog.pg_proc as function_definition
        where function_definition.oid = cleanup_function
          and function_definition.prokind = 'f'
          and function_definition.prosecdef
          and function_definition.provolatile = 'v'
          and function_definition.proparallel = 'u'
          and not function_definition.proleakproof
          and not function_definition.proisstrict
          and function_definition.proconfig =
              array['search_path=pg_catalog']::text[]
          and pg_catalog.pg_get_function_identity_arguments(
              function_definition.oid
          ) = 'p_cutoff timestamp with time zone, p_batch_limit integer'
          and pg_catalog.pg_get_function_result(
              function_definition.oid
          ) = 'integer'
    ) then
        raise exception 'authentication audit retention verification failed: function security properties differ';
    end if;

    select function_definition.prosrc
    into cleanup_source
    from pg_catalog.pg_proc as function_definition
    where function_definition.oid = cleanup_function;

    if pg_catalog.strpos(cleanup_source, 'p_cutoff is null') = 0
       or pg_catalog.strpos(
           cleanup_source,
           'not pg_catalog.isfinite(p_cutoff)'
       ) = 0
       or pg_catalog.strpos(
           cleanup_source,
           'p_cutoff > pg_catalog.now()'
       ) = 0
       or pg_catalog.strpos(cleanup_source, 'p_batch_limit < 1') = 0
       or pg_catalog.strpos(cleanup_source, 'p_batch_limit > 1000') = 0
       or pg_catalog.strpos(
           cleanup_source,
           'audit_event.occurred_at < p_cutoff'
       ) = 0
       or pg_catalog.strpos(
           cleanup_source,
           'order by audit_event.occurred_at asc, audit_event.id asc'
       ) = 0
       or pg_catalog.strpos(cleanup_source, 'limit p_batch_limit') = 0
       or pg_catalog.strpos(
           cleanup_source,
           'for update of audit_event skip locked'
       ) = 0
       or pg_catalog.strpos(
           cleanup_source,
           'delete from public.authentication_audit_events as audit_event'
       ) = 0
       or pg_catalog.strpos(
           cleanup_source,
           'returning audit_event.id'
       ) = 0 then
        raise exception 'authentication audit retention verification failed: cleanup body differs';
    end if;

    if (
        select count(*)
        from pg_catalog.pg_proc as function_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                function_definition.proacl,
                pg_catalog.acldefault('f', function_definition.proowner)
            )
        ) as privilege
        where function_definition.oid = cleanup_function
          and privilege.grantee in (
              current_owner_id,
              to_regrole('service_role')
          )
          and privilege.privilege_type = 'EXECUTE'
          and not privilege.is_grantable
    ) <> 2
       or exists (
           select 1
           from pg_catalog.pg_proc as function_definition
           cross join lateral pg_catalog.aclexplode(
               coalesce(
                   function_definition.proacl,
                   pg_catalog.acldefault('f', function_definition.proowner)
               )
           ) as privilege
           where function_definition.oid = cleanup_function
             and (
                 privilege.grantee not in (
                     current_owner_id,
                     to_regrole('service_role')
                 )
                 or privilege.privilege_type <> 'EXECUTE'
                 or privilege.is_grantable
             )
       ) then
        raise exception 'authentication audit retention verification failed: function ACL differs';
    end if;

    if not has_function_privilege(
        'service_role',
        cleanup_function,
        'EXECUTE'
    )
       or has_function_privilege('anon', cleanup_function, 'EXECUTE')
       or has_function_privilege(
           'authenticated',
           cleanup_function,
           'EXECUTE'
       )
       or has_table_privilege(
           'service_role',
           audit_table,
           'DELETE'
       ) then
        raise exception 'authentication audit retention verification failed: effective privileges differ';
    end if;

    if not exists (
        select 1
        from pg_catalog.pg_class as table_definition
        where table_definition.oid = audit_table
          and table_definition.relrowsecurity
          and not table_definition.relforcerowsecurity
    )
       or exists (
           select 1
           from pg_catalog.pg_policy as policy_definition
           where policy_definition.polrelid = audit_table
       ) then
        raise exception 'authentication audit retention verification failed: RLS state differs';
    end if;

    if (
        select count(*)
        from pg_catalog.pg_class as table_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                table_definition.relacl,
                pg_catalog.acldefault('r', table_definition.relowner)
            )
        ) as privilege
        where table_definition.oid = audit_table
          and (
              (
                  privilege.grantee = current_owner_id
                  and privilege.privilege_type in ('SELECT', 'INSERT')
                  and not privilege.is_grantable
              )
              or (
                  privilege.grantee = to_regrole('service_role')
                  and privilege.privilege_type = 'SELECT'
                  and not privilege.is_grantable
              )
          )
    ) <> 3
       or exists (
           select 1
           from pg_catalog.pg_class as table_definition
           cross join lateral pg_catalog.aclexplode(
               coalesce(
                   table_definition.relacl,
                   pg_catalog.acldefault('r', table_definition.relowner)
               )
           ) as privilege
           where table_definition.oid = audit_table
             and not (
                 (
                     privilege.grantee = current_owner_id
                     and privilege.privilege_type in ('SELECT', 'INSERT')
                     and not privilege.is_grantable
                 )
                 or (
                     privilege.grantee = to_regrole('service_role')
                     and privilege.privilege_type = 'SELECT'
                     and not privilege.is_grantable
                 )
             )
       ) then
        raise exception 'authentication audit retention verification failed: table ACL differs';
    end if;

    if (
        select count(*)
        from pg_catalog.pg_attribute as attribute_definition
        cross join lateral pg_catalog.aclexplode(
            attribute_definition.attacl
        ) as privilege
        where attribute_definition.attrelid = audit_table
          and attribute_definition.attnum > 0
          and not attribute_definition.attisdropped
          and attribute_definition.attname = 'user_id'
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
           where attribute_definition.attrelid = audit_table
             and attribute_definition.attnum > 0
             and not attribute_definition.attisdropped
             and not (
                 attribute_definition.attname = 'user_id'
                 and privilege.grantee = current_owner_id
                 and privilege.privilege_type = 'UPDATE'
                 and not privilege.is_grantable
             )
       ) then
        raise exception 'authentication audit retention verification failed: column ACL differs';
    end if;

    if not exists (
        select 1
        from pg_catalog.pg_index as index_definition
        join pg_catalog.pg_class as index_relation
          on index_relation.oid = index_definition.indexrelid
        where index_relation.oid = to_regclass(
              'public.idx_authentication_audit_events_occurred_at'
          )
          and index_definition.indrelid = audit_table
          and index_relation.relowner = current_owner_id
          and index_definition.indisvalid
          and index_definition.indisready
          and index_definition.indislive
          and not index_definition.indisunique
          and index_definition.indnkeyatts = 1
          and pg_catalog.pg_get_indexdef(
              index_definition.indexrelid,
              1,
              true
          ) = 'occurred_at'
          and (index_definition.indoption[0] & 1) = 1
          and (index_definition.indoption[0] & 2) = 2
    ) then
        raise exception 'authentication audit retention verification failed: occurred_at index differs';
    end if;
end;
$authentication_audit_retention_catalog_verification$;

do $authentication_audit_retention_synthetic_precheck$
begin
    if exists (
        select 1
        from public.authentication_audit_events
        where occurred_at < '2000-01-01 00:00:00+00'::timestamptz
           or id between
              '00000000-0000-4000-8000-000000001041'::uuid
              and '00000000-0000-4000-8000-000000001045'::uuid
    ) then
        raise exception 'authentication audit retention verification failed: reserved synthetic window is not empty';
    end if;
end;
$authentication_audit_retention_synthetic_precheck$;

insert into public.authentication_audit_events (
    id,
    occurred_at,
    event_type,
    outcome,
    auth_method,
    user_id,
    failure_category,
    revocation_reason,
    correlation_id,
    source_environment
)
values
    (
        '00000000-0000-4000-8000-000000001041',
        '1999-12-31 23:59:57+00',
        'login',
        'succeeded',
        'password',
        null,
        null,
        null,
        'retention-check-1041',
        'verification'
    ),
    (
        '00000000-0000-4000-8000-000000001042',
        '1999-12-31 23:59:58+00',
        'login',
        'succeeded',
        'password',
        null,
        null,
        null,
        'retention-check-1042',
        'verification'
    ),
    (
        '00000000-0000-4000-8000-000000001043',
        '1999-12-31 23:59:59+00',
        'login',
        'succeeded',
        'password',
        null,
        null,
        null,
        'retention-check-1043',
        'verification'
    ),
    (
        '00000000-0000-4000-8000-000000001044',
        '2000-01-01 00:00:00+00',
        'login',
        'succeeded',
        'password',
        null,
        null,
        null,
        'retention-check-1044',
        'verification'
    ),
    (
        '00000000-0000-4000-8000-000000001045',
        '2000-01-01 00:00:01+00',
        'login',
        'succeeded',
        'password',
        null,
        null,
        null,
        'retention-check-1045',
        'verification'
    );

set local role service_role;
do $authentication_audit_retention_first_batch$
declare
    actual integer;
begin
    actual := public.cleanup_authentication_audit_events(
        '2000-01-01 00:00:00+00'::timestamptz,
        2
    );
    if actual <> 2 then
        raise exception 'authentication audit retention verification failed: first batch returned %', actual;
    end if;
end;
$authentication_audit_retention_first_batch$;
reset role;

do $authentication_audit_retention_oldest_first$
begin
    if exists (
        select 1
        from public.authentication_audit_events
        where id in (
            '00000000-0000-4000-8000-000000001041'::uuid,
            '00000000-0000-4000-8000-000000001042'::uuid
        )
    )
       or not exists (
           select 1
           from public.authentication_audit_events
           where id = '00000000-0000-4000-8000-000000001043'::uuid
       ) then
        raise exception 'authentication audit retention verification failed: oldest-first ordering differs';
    end if;
end;
$authentication_audit_retention_oldest_first$;

set local role service_role;
do $authentication_audit_retention_remaining_batches$
declare
    actual integer;
begin
    actual := public.cleanup_authentication_audit_events(
        '2000-01-01 00:00:00+00'::timestamptz,
        2
    );
    if actual <> 1 then
        raise exception 'authentication audit retention verification failed: second batch returned %', actual;
    end if;

    actual := public.cleanup_authentication_audit_events(
        '2000-01-01 00:00:00+00'::timestamptz,
        2
    );
    if actual <> 0 then
        raise exception 'authentication audit retention verification failed: zero batch returned %', actual;
    end if;
end;
$authentication_audit_retention_remaining_batches$;
reset role;

set local role anon;
do $authentication_audit_retention_anon_denied$
begin
    begin
        perform public.cleanup_authentication_audit_events(
            '2000-01-01 00:00:00+00'::timestamptz,
            1
        );
        raise exception 'authentication audit retention verification failed: anon executed cleanup';
    exception
        when insufficient_privilege then null;
    end;
end;
$authentication_audit_retention_anon_denied$;
reset role;

set local role authenticated;
do $authentication_audit_retention_authenticated_denied$
begin
    begin
        perform public.cleanup_authentication_audit_events(
            '2000-01-01 00:00:00+00'::timestamptz,
            1
        );
        raise exception 'authentication audit retention verification failed: authenticated executed cleanup';
    exception
        when insufficient_privilege then null;
    end;
end;
$authentication_audit_retention_authenticated_denied$;
reset role;

set local role service_role;
do $authentication_audit_retention_direct_delete_denied$
begin
    begin
        delete from public.authentication_audit_events
        where id = '00000000-0000-4000-8000-000000001044'::uuid;
        raise exception 'authentication audit retention verification failed: service_role deleted directly';
    exception
        when insufficient_privilege then null;
    end;
end;
$authentication_audit_retention_direct_delete_denied$;
reset role;

do $authentication_audit_retention_boundary_check$
begin
    if (
        select pg_catalog.count(*)
        from public.authentication_audit_events
        where id in (
            '00000000-0000-4000-8000-000000001044'::uuid,
            '00000000-0000-4000-8000-000000001045'::uuid
        )
    ) <> 2
       or exists (
           select 1
           from public.authentication_audit_events
           where id between
                 '00000000-0000-4000-8000-000000001041'::uuid
                 and '00000000-0000-4000-8000-000000001043'::uuid
       ) then
        raise exception 'authentication audit retention verification failed: cutoff boundary differs';
    end if;
end;
$authentication_audit_retention_boundary_check$;

do $authentication_audit_retention_invalid_arguments$
begin
    begin
        perform public.cleanup_authentication_audit_events(null, 1);
        raise exception 'authentication audit retention verification failed: null cutoff accepted';
    exception
        when invalid_parameter_value then null;
    end;

    begin
        perform public.cleanup_authentication_audit_events(
            'infinity'::timestamptz,
            1
        );
        raise exception 'authentication audit retention verification failed: infinite cutoff accepted';
    exception
        when invalid_parameter_value then null;
    end;

    begin
        perform public.cleanup_authentication_audit_events(
            pg_catalog.now() + interval '1 day',
            1
        );
        raise exception 'authentication audit retention verification failed: future cutoff accepted';
    exception
        when invalid_parameter_value then null;
    end;

    begin
        perform public.cleanup_authentication_audit_events(
            '2000-01-01 00:00:00+00'::timestamptz,
            0
        );
        raise exception 'authentication audit retention verification failed: zero limit accepted';
    exception
        when invalid_parameter_value then null;
    end;

    begin
        perform public.cleanup_authentication_audit_events(
            '2000-01-01 00:00:00+00'::timestamptz,
            1001
        );
        raise exception 'authentication audit retention verification failed: oversized limit accepted';
    exception
        when invalid_parameter_value then null;
    end;
end;
$authentication_audit_retention_invalid_arguments$;

do $authentication_audit_retention_verification_passed$
begin
    raise notice 'authentication audit retention verification passed; synthetic changes will be rolled back';
end;
$authentication_audit_retention_verification_passed$;

rollback;
