-- ISSUE-1031 authentication audit rollout gate.
-- Read-only: run before the explicitly transactional migration file.
-- The supported operator is the single trusted non-application role that owns
-- both audit objects. Reapplication may repair ACL drift only while that
-- operator still owns every pre-existing audit object.

do $authentication_audit_preflight$
declare
    anon_id oid := (
        select oid from pg_catalog.pg_roles where rolname = 'anon'
    );
    authenticated_id oid := (
        select oid from pg_catalog.pg_roles where rolname = 'authenticated'
    );
    service_role_id oid := (
        select oid from pg_catalog.pg_roles where rolname = 'service_role'
    );
    users_table regclass := to_regclass('public.users');
    audit_table regclass := to_regclass('public.authentication_audit_events');
    record_function regprocedure := to_regprocedure(
        'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
    );
    occurred_at_index regclass := to_regclass(
        'public.idx_authentication_audit_events_occurred_at'
    );
    event_index regclass := to_regclass(
        'public.idx_authentication_audit_events_type_outcome_occurred_at'
    );
    user_index regclass := to_regclass(
        'public.idx_authentication_audit_events_user_occurred_at'
    );
    objects_present integer;
    current_owner_id oid := to_regrole(current_user);
begin
    if anon_id is null or authenticated_id is null or service_role_id is null then
        raise exception using
            errcode = 'P0001',
            message = 'authentication audit preflight failed: anon, authenticated, and service_role roles are required';
    end if;

    if users_table is null then
        raise exception using
            errcode = 'P0001',
            message = 'authentication audit preflight failed: public.users does not exist';
    end if;

    if current_user in ('anon', 'authenticated', 'service_role') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: migration must run as a trusted database owner';
    end if;

    if not has_schema_privilege(current_user, 'public', 'USAGE')
       or not has_schema_privilege(current_user, 'public', 'CREATE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: migration owner requires USAGE and CREATE on schema public';
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
            message = 'authentication audit preflight failed: migration owner must be authorized to SET ROLE service_role';
    end if;

    if not has_schema_privilege('anon', 'public', 'USAGE')
       or not has_schema_privilege('authenticated', 'public', 'USAGE')
       or not has_schema_privilege('service_role', 'public', 'USAGE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: application roles require schema USAGE';
    end if;

    if has_schema_privilege('anon', 'public', 'CREATE')
       or has_schema_privilege('authenticated', 'public', 'CREATE')
       or has_schema_privilege('service_role', 'public', 'CREATE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: application roles or PUBLIC have schema CREATE';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_namespace as namespace_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                namespace_definition.nspacl,
                pg_catalog.acldefault('n', namespace_definition.nspowner)
            )
        ) as privilege
        where namespace_definition.oid = 'public'::pg_catalog.regnamespace
          and privilege.grantee in (
              0,
              anon_id,
              authenticated_id,
              service_role_id
          )
          and (
              privilege.privilege_type = 'CREATE'
              or privilege.is_grantable
          )
    ) then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: unexpected schema grant option';
    end if;

    if audit_table is not null
       and (
           select table_definition.relowner
           from pg_catalog.pg_class as table_definition
           where table_definition.oid = audit_table
       ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: table is owned by an unrelated role';
    end if;

    if record_function is not null
       and (
           select function_definition.proowner
           from pg_catalog.pg_proc as function_definition
           where function_definition.oid = record_function
       ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: RPC is owned by an unrelated role';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::pg_catalog.regnamespace
          and function_definition.proname =
              'record_authentication_audit_event'
          and function_definition.oid is distinct from record_function
    ) then
        raise exception using
            errcode = '42501',
            message = 'authentication audit preflight failed: unexpected RPC overload exists';
    end if;

    select count(*)
    into objects_present
    from (
        values
            (audit_table is not null),
            (record_function is not null),
            (occurred_at_index is not null),
            (event_index is not null),
            (user_index is not null)
    ) as object_state(is_present)
    where is_present;

    if objects_present = 0 then
        raise notice 'authentication audit preflight passed: migration is not yet applied';
    elsif objects_present = 5 then
        -- Exact definitions and ACLs are validated after the migration has
        -- atomically repaired owner/grant drift. No partially present shape
        -- is accepted here.
        raise notice 'authentication audit preflight passed: core objects exist and transactional re-application is allowed';
    else
        raise exception using
            errcode = 'P0001',
            message = format(
                'authentication audit preflight failed: partial migration state (%s of 5 core objects present)',
                objects_present
            );
    end if;
end;
$authentication_audit_preflight$;
