-- ISSUE-1031 item 3 security-attribution database-foundation rollout gate.
-- Read-only: run before security_request_attribution.sql.

do $security_attribution_preflight$
declare
    current_owner_id oid := pg_catalog.to_regrole(current_user);
    table_name text;
    table_oid pg_catalog.regclass;
    function_name text;
    function_oid pg_catalog.regprocedure;
    expected_acl_count integer;
begin
    if pg_catalog.to_regrole('anon') is null
       or pg_catalog.to_regrole('authenticated') is null
       or pg_catalog.to_regrole('service_role') is null then
        raise exception using
            errcode = 'P0001',
            message = 'security attribution preflight failed: application roles are missing';
    end if;

    if current_user in ('anon', 'authenticated', 'service_role') then
        raise exception using
            errcode = '42501',
            message = 'security attribution preflight failed: use a trusted database owner';
    end if;

    if not pg_catalog.has_schema_privilege(
        current_user,
        'public',
        'USAGE'
    )
       or not pg_catalog.has_schema_privilege(
           current_user,
           'public',
           'CREATE'
       ) then
        raise exception using
            errcode = '42501',
            message = 'security attribution preflight failed: owner requires schema USAGE and CREATE';
    end if;

    if not pg_catalog.has_schema_privilege('anon', 'public', 'USAGE')
       or not pg_catalog.has_schema_privilege(
           'authenticated',
           'public',
           'USAGE'
       )
       or not pg_catalog.has_schema_privilege(
           'service_role',
           'public',
           'USAGE'
       )
       or pg_catalog.has_schema_privilege('anon', 'public', 'CREATE')
       or pg_catalog.has_schema_privilege(
           'authenticated',
           'public',
           'CREATE'
       )
       or pg_catalog.has_schema_privilege(
           'service_role',
           'public',
           'CREATE'
       ) then
        raise exception using
            errcode = '42501',
            message = 'security attribution preflight failed: application-role schema privileges are unsafe';
    end if;

    foreach table_name in array array[
        'security_request_attribution_events',
        'security_investigation_access_events'
    ]
    loop
        table_oid := pg_catalog.to_regclass(
            pg_catalog.format('public.%I', table_name)
        );
        if table_oid is not null then
            if (
                select table_definition.relowner
                from pg_catalog.pg_class as table_definition
                where table_definition.oid = table_oid
            ) <> current_owner_id then
                raise exception using
                    errcode = '42501',
                    message = 'security attribution preflight failed: table owner differs';
            end if;

            if not (
                select
                    table_definition.relrowsecurity
                    and not table_definition.relforcerowsecurity
                from pg_catalog.pg_class as table_definition
                where table_definition.oid = table_oid
            )
               or exists (
                   select 1
                   from pg_catalog.pg_policy as policy_definition
                   where policy_definition.polrelid = table_oid
               ) then
                raise exception using
                    errcode = '42501',
                    message = 'security attribution preflight failed: table RLS state differs';
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
                raise exception using
                    errcode = '42501',
                    message = 'security attribution preflight failed: table ACL differs';
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
                raise exception using
                    errcode = '42501',
                    message = 'security attribution preflight failed: column ACL differs';
            end if;
        end if;
    end loop;

    foreach function_name in array array[
        'record_security_request_attribution_event',
        'query_security_request_attribution_events',
        'cleanup_security_request_attribution_events',
        'cleanup_security_investigation_access_events'
    ]
    loop
        if exists (
            select 1
            from pg_catalog.pg_proc as function_definition
            where function_definition.pronamespace =
                  'public'::pg_catalog.regnamespace
              and function_definition.proname = function_name
              and function_definition.proowner <> current_owner_id
        ) then
            raise exception using
                errcode = '42501',
                message = 'security attribution preflight failed: function owner differs';
        end if;
    end loop;

    function_oid := pg_catalog.to_regprocedure(
        'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)'
    );
    if (
        select pg_catalog.count(*)
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::pg_catalog.regnamespace
          and function_definition.proname =
              'record_security_request_attribution_event'
    ) <> (
        case when function_oid is null then 0 else 1 end
    ) then
        raise exception using
            errcode = '42501',
            message = 'security attribution preflight failed: ingestion RPC overload differs';
    end if;

    function_oid := pg_catalog.to_regprocedure(
        'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'
    );
    if (
        select pg_catalog.count(*)
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::pg_catalog.regnamespace
          and function_definition.proname =
              'query_security_request_attribution_events'
    ) <> (
        case when function_oid is null then 0 else 1 end
    ) then
        raise exception using
            errcode = '42501',
            message = 'security attribution preflight failed: query RPC overload differs';
    end if;

    foreach function_name in array array[
        'cleanup_security_request_attribution_events',
        'cleanup_security_investigation_access_events'
    ]
    loop
        function_oid := pg_catalog.to_regprocedure(
            pg_catalog.format(
                'public.%I(timestamptz,integer)',
                function_name
            )
        );
        if (
            select pg_catalog.count(*)
            from pg_catalog.pg_proc as function_definition
            where function_definition.pronamespace =
                  'public'::pg_catalog.regnamespace
              and function_definition.proname = function_name
        ) <> (
            case when function_oid is null then 0 else 1 end
        ) then
            raise exception using
                errcode = '42501',
                message = 'security attribution preflight failed: cleanup RPC overload differs';
        end if;
    end loop;

    foreach function_name in array array[
        'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)',
        'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)',
        'public.cleanup_security_request_attribution_events(timestamptz,integer)',
        'public.cleanup_security_investigation_access_events(timestamptz,integer)'
    ]
    loop
        function_oid := pg_catalog.to_regprocedure(function_name);
        if function_oid is null then
            continue;
        end if;

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
            raise exception using
                errcode = '42501',
                message = 'security attribution preflight failed: function security differs';
        end if;

        expected_acl_count := case
            when function_name like
                 'public.query_security_request_attribution_events(%'
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
            raise exception using
                errcode = '42501',
                message = 'security attribution preflight failed: function ACL differs';
        end if;
    end loop;
end;
$security_attribution_preflight$;

select
    current_user as migration_owner,
    pg_catalog.to_regclass(
        'public.security_request_attribution_events'
    ) is not null as attribution_table_present,
    pg_catalog.to_regclass(
        'public.security_investigation_access_events'
    ) is not null as access_table_present,
    pg_catalog.to_regprocedure(
        'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)'
    ) is not null as ingestion_rpc_present,
    pg_catalog.to_regprocedure(
        'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'
    ) is not null as query_rpc_present;
