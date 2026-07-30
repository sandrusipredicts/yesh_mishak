-- ISSUE-1031 item 4 authentication-audit retention rollout gate.
-- Read-only: run before authentication_audit_retention.sql.

do $authentication_audit_retention_preflight$
declare
    anon_id oid := to_regrole('anon');
    authenticated_id oid := to_regrole('authenticated');
    service_role_id oid := to_regrole('service_role');
    audit_table regclass := to_regclass(
        'public.authentication_audit_events'
    );
    record_function regprocedure := to_regprocedure(
        'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
    );
    cleanup_function regprocedure := to_regprocedure(
        'public.cleanup_authentication_audit_events(timestamptz,integer)'
    );
    current_owner_id oid := to_regrole(current_user);
begin
    if anon_id is null
       or authenticated_id is null
       or service_role_id is null then
        raise exception using
            errcode = 'P0001',
            message = 'authentication audit retention preflight failed: application roles are missing';
    end if;

    if audit_table is null
       or record_function is null
       or to_regclass(
           'public.idx_authentication_audit_events_occurred_at'
       ) is null then
        raise exception using
            errcode = '42P01',
            message = 'authentication audit retention preflight failed: authentication audit prerequisites are incomplete';
    end if;

    if current_user in ('anon', 'authenticated', 'service_role') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: use the trusted audit owner';
    end if;

    if not has_schema_privilege(current_user, 'public', 'USAGE')
       or not has_schema_privilege(current_user, 'public', 'CREATE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: owner requires schema USAGE and CREATE';
    end if;

    if not has_schema_privilege('anon', 'public', 'USAGE')
       or not has_schema_privilege('authenticated', 'public', 'USAGE')
       or not has_schema_privilege('service_role', 'public', 'USAGE')
       or has_schema_privilege('anon', 'public', 'CREATE')
       or has_schema_privilege('authenticated', 'public', 'CREATE')
       or has_schema_privilege('service_role', 'public', 'CREATE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: application-role schema privileges are unsafe';
    end if;

    if not (
        select role_definition.rolsuper
        from pg_catalog.pg_roles as role_definition
        where role_definition.oid = current_owner_id
    )
       and not (
           case
               when pg_catalog.current_setting('server_version_num')::integer
                    >= 160000
                   then pg_catalog.pg_has_role(
                       current_user,
                       'service_role',
                       'SET'
                   )
               else pg_catalog.pg_has_role(
                   current_user,
                   'service_role',
                   'MEMBER'
               )
           end
       ) then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: owner cannot SET ROLE service_role';
    end if;

    if (
        select table_definition.relowner
        from pg_catalog.pg_class as table_definition
        where table_definition.oid = audit_table
    ) <> current_owner_id
       or (
           select function_definition.proowner
           from pg_catalog.pg_proc as function_definition
           where function_definition.oid = record_function
       ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: prerequisite ownership differs from current_user';
    end if;

    if cleanup_function is not null
       and (
           select function_definition.proowner
           from pg_catalog.pg_proc as function_definition
           where function_definition.oid = cleanup_function
       ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: cleanup RPC has an unrelated owner';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::pg_catalog.regnamespace
          and function_definition.proname =
              'cleanup_authentication_audit_events'
          and function_definition.oid is distinct from cleanup_function
    ) then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: unexpected cleanup RPC overload exists';
    end if;

    if not has_table_privilege(current_user, audit_table, 'SELECT')
       or not has_table_privilege(current_user, audit_table, 'INSERT')
       or not has_column_privilege(
           current_user,
           audit_table,
           'user_id',
           'UPDATE'
       )
       or not has_table_privilege(
           'service_role',
           audit_table,
           'SELECT'
       )
       or has_table_privilege(
           'service_role',
           audit_table,
           'DELETE'
       ) then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: prerequisite effective privileges are unsafe';
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
                  privilege.grantee = service_role_id
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
                     and privilege.privilege_type in (
                         'SELECT',
                         'INSERT',
                         'DELETE'
                     )
                     and not privilege.is_grantable
                 )
                 or (
                     privilege.grantee = service_role_id
                     and privilege.privilege_type = 'SELECT'
                     and not privilege.is_grantable
                 )
             )
       ) then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: table ACL is outside the pre- or post-repair allowlist';
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
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention preflight failed: column ACL differs';
    end if;

    if cleanup_function is null then
        raise notice 'authentication audit retention preflight passed: cleanup RPC is not yet applied';
    elsif not has_table_privilege(
        current_user,
        audit_table,
        'DELETE'
    ) then
        raise notice 'authentication audit retention preflight passed: owner DELETE is missing and will be repaired transactionally';
    else
        raise notice 'authentication audit retention preflight passed: transactional reapplication is allowed';
    end if;
end;
$authentication_audit_retention_preflight$;

-- Preserve this bounded, identifier-free row with rollout evidence. Before
-- repairing the first migration version it shows owner_delete = false while
-- service_execute = true; after migration it shows owner_delete = true.
select
    pg_catalog.pg_get_userbyid(table_definition.relowner) as table_owner,
    (
        select pg_catalog.pg_get_userbyid(function_definition.proowner)
        from pg_catalog.pg_proc as function_definition
        where function_definition.oid = to_regprocedure(
            'public.cleanup_authentication_audit_events(timestamptz,integer)'
        )
    ) as cleanup_function_owner,
    table_definition.relacl::text as table_acl,
    coalesce(
        (
            select pg_catalog.string_agg(
                attribute_definition.attname
                || '='
                || attribute_definition.attacl::text,
                ';'
                order by attribute_definition.attnum
            )
            from pg_catalog.pg_attribute as attribute_definition
            where attribute_definition.attrelid = table_definition.oid
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped
              and attribute_definition.attacl is not null
        ),
        ''
    ) as column_acl,
    has_table_privilege(
        pg_catalog.pg_get_userbyid(table_definition.relowner),
        table_definition.oid,
        'SELECT'
    ) as owner_select,
    has_table_privilege(
        pg_catalog.pg_get_userbyid(table_definition.relowner),
        table_definition.oid,
        'UPDATE'
    ) as owner_table_update,
    has_column_privilege(
        pg_catalog.pg_get_userbyid(table_definition.relowner),
        table_definition.oid,
        'user_id',
        'UPDATE'
    ) as owner_user_id_update,
    has_table_privilege(
        pg_catalog.pg_get_userbyid(table_definition.relowner),
        table_definition.oid,
        'DELETE'
    ) as owner_delete,
    has_table_privilege(
        'service_role',
        table_definition.oid,
        'SELECT'
    ) as service_select,
    has_table_privilege(
        'service_role',
        table_definition.oid,
        'DELETE'
    ) as service_delete,
    has_function_privilege(
        'service_role',
        to_regprocedure(
            'public.cleanup_authentication_audit_events(timestamptz,integer)'
        ),
        'EXECUTE'
    ) as service_execute,
    has_function_privilege(
        'anon',
        to_regprocedure(
            'public.cleanup_authentication_audit_events(timestamptz,integer)'
        ),
        'EXECUTE'
    ) as anon_execute,
    has_function_privilege(
        'authenticated',
        to_regprocedure(
            'public.cleanup_authentication_audit_events(timestamptz,integer)'
        ),
        'EXECUTE'
    ) as authenticated_execute,
    has_function_privilege(
        'public',
        to_regprocedure(
            'public.cleanup_authentication_audit_events(timestamptz,integer)'
        ),
        'EXECUTE'
    ) as public_execute,
    table_definition.relrowsecurity as rls_enabled,
    table_definition.relforcerowsecurity as force_rls
from pg_catalog.pg_class as table_definition
where table_definition.oid =
      'public.authentication_audit_events'::pg_catalog.regclass;
