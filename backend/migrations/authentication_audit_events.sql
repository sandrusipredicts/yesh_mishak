-- ISSUE-1031 phase 1: durable, privacy-bounded authentication audit events.
--
-- Supported application procedure: run this entire file as one transaction.
-- The explicit BEGIN/COMMIT keeps object creation, ownership changes, and ACL
-- revocation atomic, including when the file is executed outside psql.
-- One trusted migration operator owns both the table and SECURITY DEFINER RPC.
-- Its only direct table DML is SELECT/INSERT, which is the minimum needed by
-- the RPC's insert and immutable-payload replay check.

begin;

do $authentication_audit_prerequisites$
declare
    audit_table regclass := to_regclass('public.authentication_audit_events');
    record_function regprocedure := to_regprocedure(
        'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
    );
    current_owner_id oid := to_regrole(current_user);
begin
    if to_regrole('anon') is null
       or to_regrole('authenticated') is null
       or to_regrole('service_role') is null then
        raise exception using
            errcode = 'P0001',
            message = 'authentication audit migration requires anon, authenticated, and service_role roles';
    end if;

    if to_regclass('public.users') is null then
        raise exception using
            errcode = 'P0001',
            message = 'authentication audit migration requires public.users';
    end if;

    if current_user in ('anon', 'authenticated', 'service_role') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit migration must run as a trusted database owner, not an application role';
    end if;

    if not has_schema_privilege(current_user, 'public', 'USAGE')
       or not has_schema_privilege(current_user, 'public', 'CREATE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit migration owner requires USAGE and CREATE on schema public';
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
            message = 'authentication audit migration owner must be authorized to SET ROLE service_role for verification';
    end if;

    if not has_schema_privilege('anon', 'public', 'USAGE')
       or not has_schema_privilege('authenticated', 'public', 'USAGE')
       or not has_schema_privilege('service_role', 'public', 'USAGE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit migration requires schema USAGE for anon, authenticated, and service_role';
    end if;

    if has_schema_privilege('anon', 'public', 'CREATE')
       or has_schema_privilege('authenticated', 'public', 'CREATE')
       or has_schema_privilege('service_role', 'public', 'CREATE') then
        raise exception using
            errcode = '42501',
            message = 'authentication audit migration rejects schema CREATE for application roles or PUBLIC';
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
              to_regrole('anon'),
              to_regrole('authenticated'),
              to_regrole('service_role')
          )
          and (
              privilege.privilege_type = 'CREATE'
              or privilege.is_grantable
          )
    ) then
        raise exception using
            errcode = '42501',
            message = 'authentication audit migration rejects application-role or PUBLIC schema grant options';
    end if;

    if audit_table is not null
       and (
           select table_definition.relowner
           from pg_catalog.pg_class as table_definition
           where table_definition.oid = audit_table
       ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit migration cannot alter a table owned by an unrelated role';
    end if;

    if record_function is not null
       and (
           select function_definition.proowner
           from pg_catalog.pg_proc as function_definition
           where function_definition.oid = record_function
       ) <> current_owner_id then
        raise exception using
            errcode = '42501',
            message = 'authentication audit migration cannot alter an RPC owned by an unrelated role';
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
            message = 'authentication audit migration rejects unexpected RPC overloads before DDL';
    end if;
end;
$authentication_audit_prerequisites$;

create table if not exists public.authentication_audit_events (
    id uuid primary key,
    occurred_at timestamptz not null default pg_catalog.now(),
    event_type text not null check (
        event_type in ('login', 'logout', 'token_revocation')
    ),
    outcome text not null check (
        outcome in ('succeeded', 'failed')
    ),
    auth_method text not null check (
        auth_method in ('password', 'google', 'bearer', 'recovery')
    ),
    user_id uuid references public.users(id) on delete set null,
    failure_category text check (
        failure_category is null
        or failure_category in (
            'invalid_credentials',
            'invalid_provider_credential',
            'email_not_verified',
            'account_link_required',
            'rate_limited',
            'identity_conflict',
            'service_unavailable',
            'invalid_state',
            'internal_error'
        )
    ),
    revocation_reason text check (
        revocation_reason is null
        or revocation_reason in (
            'logout',
            'google_unlinked',
            'password_set',
            'password_removed',
            'password_reset',
            'account_deleted'
        )
    ),
    correlation_id text not null check (
        char_length(correlation_id) between 8 and 64
        and correlation_id ~ '^[A-Za-z0-9_-]+$'
    ),
    source_environment text not null check (
        char_length(source_environment) between 1 and 32
        and source_environment ~ '^[A-Za-z0-9._-]+$'
    ),
    constraint authentication_audit_events_outcome_failure_check check (
        (
            outcome = 'succeeded'
            and failure_category is null
        )
        or (
            outcome = 'failed'
            and failure_category is not null
        )
    ),
    constraint authentication_audit_events_revocation_presence_check check (
        (
            event_type = 'token_revocation'
            and revocation_reason is not null
        )
        or (
            event_type <> 'token_revocation'
            and revocation_reason is null
        )
    ),
    constraint authentication_audit_events_method_check check (
        (
            event_type = 'login'
            and auth_method in ('password', 'google')
        )
        or (
            event_type = 'logout'
            and auth_method = 'bearer'
        )
        or event_type = 'token_revocation'
    ),
    constraint authentication_audit_events_failure_context_check check (
        failure_category is null
        or (
            event_type = 'login'
            and (
                (
                    auth_method = 'password'
                    and failure_category in (
                        'invalid_credentials',
                        'email_not_verified',
                        'rate_limited',
                        'service_unavailable',
                        'internal_error'
                    )
                )
                or (
                    auth_method = 'google'
                    and failure_category in (
                        'invalid_provider_credential',
                        'email_not_verified',
                        'account_link_required',
                        'rate_limited',
                        'identity_conflict',
                        'service_unavailable',
                        'invalid_state',
                        'internal_error'
                    )
                )
            )
        )
        or (
            event_type in ('logout', 'token_revocation')
            and failure_category in (
                'service_unavailable',
                'invalid_state',
                'internal_error'
            )
        )
    ),
    constraint authentication_audit_events_revocation_method_check check (
        event_type <> 'token_revocation'
        or (
            revocation_reason in (
                'logout',
                'google_unlinked',
                'password_set',
                'password_removed',
                'account_deleted'
            )
            and auth_method = 'bearer'
        )
        or (
            revocation_reason = 'password_reset'
            and auth_method = 'recovery'
        )
    )
);

-- The supported migration role is the trusted owner. Application roles never
-- own this table or function and receive only the explicit grants below.
alter table public.authentication_audit_events owner to current_user;
alter table public.authentication_audit_events enable row level security;

-- Remove legacy/direct grants from every named role before applying the exact
-- allowlist. Identifiers come from pg_roles and are quoted with format(%I).
do $authentication_audit_table_acl$
declare
    grantee_name text;
begin
    revoke all privileges on table public.authentication_audit_events from public cascade;

    for grantee_name in
        select distinct role_definition.rolname
        from pg_catalog.pg_class as table_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                table_definition.relacl,
                pg_catalog.acldefault('r', table_definition.relowner)
            )
        ) as privilege
        join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where table_definition.oid =
              'public.authentication_audit_events'::pg_catalog.regclass
    loop
        execute pg_catalog.format(
            'revoke all privileges on table public.authentication_audit_events from %I cascade',
            grantee_name
        );
    end loop;
end;
$authentication_audit_table_acl$;

do $authentication_audit_column_acl$
declare
    grantee_name text;
    column_list text;
begin
    select pg_catalog.string_agg(
        pg_catalog.format('%I', attribute_definition.attname),
        ','
        order by attribute_definition.attnum
    )
    into column_list
    from pg_catalog.pg_attribute as attribute_definition
    where attribute_definition.attrelid =
          'public.authentication_audit_events'::pg_catalog.regclass
      and attribute_definition.attnum > 0
      and not attribute_definition.attisdropped;

    execute pg_catalog.format(
        'revoke all privileges (%s) on table public.authentication_audit_events from public cascade',
        column_list
    );

    for grantee_name in
        select distinct role_definition.rolname
        from pg_catalog.pg_attribute as attribute_definition
        cross join lateral pg_catalog.aclexplode(attribute_definition.attacl) as privilege
        join pg_catalog.pg_roles as role_definition
          on role_definition.oid = privilege.grantee
        where attribute_definition.attrelid =
              'public.authentication_audit_events'::pg_catalog.regclass
          and attribute_definition.attnum > 0
          and not attribute_definition.attisdropped
    loop
        execute pg_catalog.format(
            'revoke all privileges (%s) on table public.authentication_audit_events from %I cascade',
            column_list,
            grantee_name
        );
    end loop;
end;
$authentication_audit_column_acl$;

grant select, insert on table public.authentication_audit_events to current_user;
grant select on table public.authentication_audit_events to service_role;

create index if not exists idx_authentication_audit_events_occurred_at
    on public.authentication_audit_events(occurred_at desc);

create index if not exists idx_authentication_audit_events_type_outcome_occurred_at
    on public.authentication_audit_events(event_type, outcome, occurred_at desc);

create index if not exists idx_authentication_audit_events_user_occurred_at
    on public.authentication_audit_events(user_id, occurred_at desc)
    where user_id is not null;

-- correlation_id intentionally is not unique. It groups the distinct events
-- produced by one operation (logout + token revocation in phase 1). The
-- application-generated primary-key UUID is the retry/idempotency key.
create or replace function public.record_authentication_audit_event(
    p_event_id uuid,
    p_event_type text,
    p_outcome text,
    p_auth_method text,
    p_user_id uuid,
    p_failure_category text,
    p_revocation_reason text,
    p_correlation_id text,
    p_source_environment text
)
returns boolean
language plpgsql
volatile
parallel unsafe
security definer
set search_path = pg_catalog
as $$
declare
    inserted_count integer;
begin
    -- Serialize intentional retries of one application-generated event ID.
    -- Different event IDs remain fully concurrent.
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(p_event_id::text, 1031)
    );

    insert into public.authentication_audit_events (
        id,
        event_type,
        outcome,
        auth_method,
        user_id,
        failure_category,
        revocation_reason,
        correlation_id,
        source_environment
    )
    values (
        p_event_id,
        p_event_type,
        p_outcome,
        p_auth_method,
        p_user_id,
        p_failure_category,
        p_revocation_reason,
        p_correlation_id,
        p_source_environment
    )
    on conflict (id) do nothing;

    get diagnostics inserted_count = row_count;
    if inserted_count = 1 then
        return true;
    end if;

    if exists (
        select 1
        from public.authentication_audit_events as existing_event
        where existing_event.id = p_event_id
          and existing_event.event_type is not distinct from p_event_type
          and existing_event.outcome is not distinct from p_outcome
          and existing_event.auth_method is not distinct from p_auth_method
          and existing_event.user_id is not distinct from p_user_id
          and existing_event.failure_category is not distinct from p_failure_category
          and existing_event.revocation_reason is not distinct from p_revocation_reason
          and existing_event.correlation_id is not distinct from p_correlation_id
          and existing_event.source_environment is not distinct from p_source_environment
    ) then
        return false;
    end if;

    raise exception using
        errcode = '23505',
        message = 'authentication audit event ID conflicts with existing immutable payload';
end;
$$;

alter function public.record_authentication_audit_event(
    uuid, text, text, text, uuid, text, text, text, text
) owner to current_user;

do $authentication_audit_function_acl$
declare
    grantee_name text;
begin
    revoke all privileges on function public.record_authentication_audit_event(
        uuid, text, text, text, uuid, text, text, text, text
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
              'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'::pg_catalog.regprocedure
    loop
        execute pg_catalog.format(
            'revoke all privileges on function public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text) from %I cascade',
            grantee_name
        );
    end loop;
end;
$authentication_audit_function_acl$;

grant execute on function public.record_authentication_audit_event(
    uuid, text, text, text, uuid, text, text, text, text
) to current_user;
grant execute on function public.record_authentication_audit_event(
    uuid, text, text, text, uuid, text, text, text, text
) to service_role;

commit;
