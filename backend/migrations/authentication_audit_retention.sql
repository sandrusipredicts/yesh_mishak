-- ISSUE-1031 item 4: bounded authentication-audit retention cleanup.
--
-- Apply after authentication_audit_events.sql and
-- authentication_audit_revocation_phase_2.sql. The table remains restricted:
-- service_role receives EXECUTE on this dedicated RPC, never direct DELETE.
-- Reapplication is safe and repairs function ACL drift transactionally.

begin;

do $authentication_audit_retention_prerequisites$
declare
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
    if to_regrole('anon') is null
       or to_regrole('authenticated') is null
       or to_regrole('service_role') is null then
        raise exception using
            errcode = 'P0001',
            message = 'authentication audit retention migration requires anon, authenticated, and service_role roles';
    end if;

    if audit_table is null or record_function is null then
        raise exception using
            errcode = '42P01',
            message = 'authentication audit retention migration requires the authentication audit table and record RPC';
    end if;

    if to_regclass(
        'public.idx_authentication_audit_events_occurred_at'
    ) is null then
        raise exception using
            errcode = '42P01',
            message = 'authentication audit retention migration requires the occurred_at index';
    end if;

    if current_user in ('anon', 'authenticated', 'service_role') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention migration must run as the trusted audit owner';
    end if;

    if not has_schema_privilege(current_user, 'public', 'USAGE')
       or not has_schema_privilege(current_user, 'public', 'CREATE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention migration owner requires USAGE and CREATE on schema public';
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
            message = 'authentication audit retention migration owner must be authorized to SET ROLE service_role';
    end if;

    if (
        select table_definition.relowner
        from pg_catalog.pg_class as table_definition
        where table_definition.oid = audit_table
    ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention migration must run as the audit table owner';
    end if;

    if (
        select function_definition.proowner
        from pg_catalog.pg_proc as function_definition
        where function_definition.oid = record_function
    ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention migration requires the same trusted record-RPC owner';
    end if;

    if cleanup_function is not null
       and (
           select function_definition.proowner
           from pg_catalog.pg_proc as function_definition
           where function_definition.oid = cleanup_function
       ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit retention migration cannot replace a cleanup RPC owned by another role';
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
            message = 'authentication audit retention migration rejects unexpected cleanup RPC overloads';
    end if;
end;
$authentication_audit_retention_prerequisites$;

create or replace function public.cleanup_authentication_audit_events(
    p_cutoff timestamptz,
    p_batch_limit integer
)
returns integer
language plpgsql
volatile
parallel unsafe
security definer
set search_path = pg_catalog
as $$
declare
    deleted_count integer;
begin
    if p_cutoff is null or not pg_catalog.isfinite(p_cutoff) then
        raise exception using
            errcode = '22023',
            message = 'p_cutoff must be a finite timestamp';
    end if;

    if p_cutoff > pg_catalog.now() then
        raise exception using
            errcode = '22023',
            message = 'p_cutoff must not be in the future';
    end if;

    if p_batch_limit is null
       or p_batch_limit < 1
       or p_batch_limit > 1000 then
        raise exception using
            errcode = '22023',
            message = 'p_batch_limit must be between 1 and 1000';
    end if;

    with candidates as materialized (
        select audit_event.id
        from public.authentication_audit_events as audit_event
        where audit_event.occurred_at < p_cutoff
        order by audit_event.occurred_at asc, audit_event.id asc
        limit p_batch_limit
        for update of audit_event skip locked
    ),
    deleted_rows as (
        delete from public.authentication_audit_events as audit_event
        using candidates
        where audit_event.id = candidates.id
          and audit_event.occurred_at < p_cutoff
        returning audit_event.id
    )
    select pg_catalog.count(*)::integer
    into deleted_count
    from deleted_rows;

    return deleted_count;
end;
$$;

alter function public.cleanup_authentication_audit_events(
    timestamptz, integer
) owner to current_user;

do $authentication_audit_retention_function_acl$
declare
    grantee_name text;
begin
    revoke all privileges on function public.cleanup_authentication_audit_events(
        timestamptz, integer
    ) from public cascade;

    for grantee_name in
        select distinct role_definition.rolname
        from pg_catalog.pg_proc as function_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                function_definition.proacl,
                pg_catalog.acldefault('f', function_definition.proowner)
            )
        ) as privilege
        join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where function_definition.oid =
              'public.cleanup_authentication_audit_events(timestamptz,integer)'::pg_catalog.regprocedure
    loop
        execute pg_catalog.format(
            'revoke all privileges on function public.cleanup_authentication_audit_events(timestamptz,integer) from %I cascade',
            grantee_name
        );
    end loop;
end;
$authentication_audit_retention_function_acl$;

grant execute on function public.cleanup_authentication_audit_events(
    timestamptz, integer
) to current_user;
grant execute on function public.cleanup_authentication_audit_events(
    timestamptz, integer
) to service_role;

commit;
