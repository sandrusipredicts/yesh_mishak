-- ISSUE-1031 post-migration verification.
-- Run as the same trusted owner that applied the migration.
-- All reference objects and synthetic data are rolled back.

begin transaction isolation level repeatable read;
set local statement_timeout = '30s';
set local lock_timeout = '5s';

-- Build a transaction-local canonical schema and compare PostgreSQL's own
-- normalized catalog representation with the deployed relation.
create table public.authentication_audit_events_expected (
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
    check (
        (outcome = 'succeeded' and failure_category is null)
        or (outcome = 'failed' and failure_category is not null)
    ),
    check (
        (event_type = 'token_revocation' and revocation_reason is not null)
        or (event_type <> 'token_revocation' and revocation_reason is null)
    ),
    check (
        (event_type = 'login' and auth_method in ('password', 'google'))
        or (event_type = 'logout' and auth_method = 'bearer')
        or event_type = 'token_revocation'
    ),
    check (
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
    check (
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

create index authentication_audit_events_expected_occurred_at
    on authentication_audit_events_expected(occurred_at desc);
create index authentication_audit_events_expected_type_outcome_occurred_at
    on authentication_audit_events_expected(event_type, outcome, occurred_at desc);
create index authentication_audit_events_expected_user_occurred_at
    on authentication_audit_events_expected(user_id, occurred_at desc)
    where user_id is not null;

do $schema_verification$
declare
    audit_table regclass := to_regclass('public.authentication_audit_events');
    expected_table regclass := to_regclass(
        'public.authentication_audit_events_expected'
    );
    record_function regprocedure := to_regprocedure(
        'public.record_authentication_audit_event(uuid,text,text,text,uuid,text,text,text,text)'
    );
    service_role_id oid := to_regrole('service_role');
    anon_id oid := to_regrole('anon');
    authenticated_id oid := to_regrole('authenticated');
    current_owner_id oid := to_regrole(current_user);
    table_owner_id oid;
    function_owner_id oid;
    rls_enabled boolean;
    service_table_select_count integer;
    service_function_execute_count integer;
    expected_function_body text := $expected_body$
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
$expected_body$;
begin
    if anon_id is null or authenticated_id is null or service_role_id is null then
        raise exception 'authentication audit verification failed: required roles are missing';
    end if;

    if audit_table is null or expected_table is null or record_function is null then
        raise exception 'authentication audit verification failed: table or RPC is missing';
    end if;

    if (
        select count(*)
        from pg_catalog.pg_proc as function_definition
        join pg_catalog.pg_namespace as namespace_definition
          on namespace_definition.oid = function_definition.pronamespace
        where namespace_definition.nspname = 'public'
          and function_definition.proname =
              'record_authentication_audit_event'
    ) <> 1 then
        raise exception 'authentication audit verification failed: exact RPC signature is not the only deployed overload';
    end if;

    select table_definition.relrowsecurity, table_definition.relowner
    into rls_enabled, table_owner_id
    from pg_catalog.pg_class as table_definition
    where table_definition.oid = audit_table;

    if not rls_enabled then
        raise exception 'authentication audit verification failed: RLS is not enabled';
    end if;

    if table_owner_id <> current_owner_id then
        raise exception 'authentication audit verification failed: table owner is not the trusted migration owner';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_policies
        where schemaname = 'public'
          and tablename = 'authentication_audit_events'
    ) then
        raise exception 'authentication audit verification failed: direct-access RLS policies are not allowed';
    end if;

    if exists (
        select 1
        from (
            (
                select
                    attribute.attnum,
                    attribute.attname,
                    attribute.atttypid,
                    attribute.atttypmod,
                    attribute.attnotnull,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            default_definition.adbin,
                            default_definition.adrelid
                        ),
                        ''
                    ) as default_expression
                from pg_catalog.pg_attribute as attribute
                left join pg_catalog.pg_attrdef as default_definition
                  on default_definition.adrelid = attribute.attrelid
                 and default_definition.adnum = attribute.attnum
                where attribute.attrelid = audit_table
                  and attribute.attnum > 0
                  and not attribute.attisdropped
            )
            except all
            (
                select
                    attribute.attnum,
                    attribute.attname,
                    attribute.atttypid,
                    attribute.atttypmod,
                    attribute.attnotnull,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            default_definition.adbin,
                            default_definition.adrelid
                        ),
                        ''
                    ) as default_expression
                from pg_catalog.pg_attribute as attribute
                left join pg_catalog.pg_attrdef as default_definition
                  on default_definition.adrelid = attribute.attrelid
                 and default_definition.adnum = attribute.attnum
                where attribute.attrelid = expected_table
                  and attribute.attnum > 0
                  and not attribute.attisdropped
            )
            union all
            (
                select
                    attribute.attnum,
                    attribute.attname,
                    attribute.atttypid,
                    attribute.atttypmod,
                    attribute.attnotnull,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            default_definition.adbin,
                            default_definition.adrelid
                        ),
                        ''
                    ) as default_expression
                from pg_catalog.pg_attribute as attribute
                left join pg_catalog.pg_attrdef as default_definition
                  on default_definition.adrelid = attribute.attrelid
                 and default_definition.adnum = attribute.attnum
                where attribute.attrelid = expected_table
                  and attribute.attnum > 0
                  and not attribute.attisdropped
            )
            except all
            (
                select
                    attribute.attnum,
                    attribute.attname,
                    attribute.atttypid,
                    attribute.atttypmod,
                    attribute.attnotnull,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            default_definition.adbin,
                            default_definition.adrelid
                        ),
                        ''
                    ) as default_expression
                from pg_catalog.pg_attribute as attribute
                left join pg_catalog.pg_attrdef as default_definition
                  on default_definition.adrelid = attribute.attrelid
                 and default_definition.adnum = attribute.attnum
                where attribute.attrelid = audit_table
                  and attribute.attnum > 0
                  and not attribute.attisdropped
            )
        ) as column_drift
    ) then
        raise exception 'authentication audit verification failed: exact columns, types, nullability, or defaults do not match';
    end if;

    if exists (
        select 1
        from (
            (
                select
                    constraint_definition.contype,
                    pg_catalog.pg_get_constraintdef(
                        constraint_definition.oid,
                        true
                    ) as definition
                from pg_catalog.pg_constraint as constraint_definition
                where constraint_definition.conrelid = audit_table
                  and constraint_definition.contype in ('p', 'u', 'f', 'c', 'x')
            )
            except all
            (
                select
                    constraint_definition.contype,
                    pg_catalog.pg_get_constraintdef(
                        constraint_definition.oid,
                        true
                    ) as definition
                from pg_catalog.pg_constraint as constraint_definition
                where constraint_definition.conrelid = expected_table
                  and constraint_definition.contype in ('p', 'u', 'f', 'c', 'x')
            )
            union all
            (
                select
                    constraint_definition.contype,
                    pg_catalog.pg_get_constraintdef(
                        constraint_definition.oid,
                        true
                    ) as definition
                from pg_catalog.pg_constraint as constraint_definition
                where constraint_definition.conrelid = expected_table
                  and constraint_definition.contype in ('p', 'u', 'f', 'c', 'x')
            )
            except all
            (
                select
                    constraint_definition.contype,
                    pg_catalog.pg_get_constraintdef(
                        constraint_definition.oid,
                        true
                    ) as definition
                from pg_catalog.pg_constraint as constraint_definition
                where constraint_definition.conrelid = audit_table
                  and constraint_definition.contype in ('p', 'u', 'f', 'c', 'x')
            )
        ) as constraint_drift
    ) then
        raise exception 'authentication audit verification failed: exact PK, FK, or CHECK semantics do not match';
    end if;

    if exists (
        select 1
        from (
            (
                select
                    index_definition.relname as index_name,
                    index_catalog.indisunique,
                    index_catalog.indisprimary,
                    index_catalog.indisvalid,
                    index_catalog.indisready,
                    index_catalog.indislive,
                    index_catalog.indnkeyatts,
                    index_catalog.indnatts,
                    access_method.amname as access_method,
                    array(
                        select pg_catalog.pg_get_indexdef(
                            index_catalog.indexrelid,
                            key_position,
                            true
                        )
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_keys,
                    array(
                        select
                            case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 1
                                ) = 1 then 'desc'
                                else 'asc'
                            end
                            || ':'
                            || case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 2
                                ) = 2 then 'nulls_first'
                                else 'nulls_last'
                            end
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_sort_and_nulls,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            index_catalog.indpred,
                            index_catalog.indrelid,
                            true
                        ),
                        ''
                    ) as predicate
                from pg_catalog.pg_index as index_catalog
                join pg_catalog.pg_class as index_definition
                  on index_definition.oid = index_catalog.indexrelid
                join pg_catalog.pg_am as access_method
                  on access_method.oid = index_definition.relam
                where index_catalog.indrelid = audit_table
            )
            except all
            (
                select
                    case index_definition.relname
                        when 'authentication_audit_events_expected_pkey'
                            then 'authentication_audit_events_pkey'
                        when 'authentication_audit_events_expected_occurred_at'
                            then 'idx_authentication_audit_events_occurred_at'
                        when 'authentication_audit_events_expected_type_outcome_occurred_at'
                            then 'idx_authentication_audit_events_type_outcome_occurred_at'
                        when 'authentication_audit_events_expected_user_occurred_at'
                            then 'idx_authentication_audit_events_user_occurred_at'
                    end as index_name,
                    index_catalog.indisunique,
                    index_catalog.indisprimary,
                    index_catalog.indisvalid,
                    index_catalog.indisready,
                    index_catalog.indislive,
                    index_catalog.indnkeyatts,
                    index_catalog.indnatts,
                    access_method.amname as access_method,
                    array(
                        select pg_catalog.pg_get_indexdef(
                            index_catalog.indexrelid,
                            key_position,
                            true
                        )
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_keys,
                    array(
                        select
                            case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 1
                                ) = 1 then 'desc'
                                else 'asc'
                            end
                            || ':'
                            || case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 2
                                ) = 2 then 'nulls_first'
                                else 'nulls_last'
                            end
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_sort_and_nulls,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            index_catalog.indpred,
                            index_catalog.indrelid,
                            true
                        ),
                        ''
                    ) as predicate
                from pg_catalog.pg_index as index_catalog
                join pg_catalog.pg_class as index_definition
                  on index_definition.oid = index_catalog.indexrelid
                join pg_catalog.pg_am as access_method
                  on access_method.oid = index_definition.relam
                where index_catalog.indrelid = expected_table
            )
            union all
            (
                select
                    case index_definition.relname
                        when 'authentication_audit_events_expected_pkey'
                            then 'authentication_audit_events_pkey'
                        when 'authentication_audit_events_expected_occurred_at'
                            then 'idx_authentication_audit_events_occurred_at'
                        when 'authentication_audit_events_expected_type_outcome_occurred_at'
                            then 'idx_authentication_audit_events_type_outcome_occurred_at'
                        when 'authentication_audit_events_expected_user_occurred_at'
                            then 'idx_authentication_audit_events_user_occurred_at'
                    end as index_name,
                    index_catalog.indisunique,
                    index_catalog.indisprimary,
                    index_catalog.indisvalid,
                    index_catalog.indisready,
                    index_catalog.indislive,
                    index_catalog.indnkeyatts,
                    index_catalog.indnatts,
                    access_method.amname as access_method,
                    array(
                        select pg_catalog.pg_get_indexdef(
                            index_catalog.indexrelid,
                            key_position,
                            true
                        )
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_keys,
                    array(
                        select
                            case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 1
                                ) = 1 then 'desc'
                                else 'asc'
                            end
                            || ':'
                            || case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 2
                                ) = 2 then 'nulls_first'
                                else 'nulls_last'
                            end
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_sort_and_nulls,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            index_catalog.indpred,
                            index_catalog.indrelid,
                            true
                        ),
                        ''
                    ) as predicate
                from pg_catalog.pg_index as index_catalog
                join pg_catalog.pg_class as index_definition
                  on index_definition.oid = index_catalog.indexrelid
                join pg_catalog.pg_am as access_method
                  on access_method.oid = index_definition.relam
                where index_catalog.indrelid = expected_table
            )
            except all
            (
                select
                    index_definition.relname as index_name,
                    index_catalog.indisunique,
                    index_catalog.indisprimary,
                    index_catalog.indisvalid,
                    index_catalog.indisready,
                    index_catalog.indislive,
                    index_catalog.indnkeyatts,
                    index_catalog.indnatts,
                    access_method.amname as access_method,
                    array(
                        select pg_catalog.pg_get_indexdef(
                            index_catalog.indexrelid,
                            key_position,
                            true
                        )
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_keys,
                    array(
                        select
                            case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 1
                                ) = 1 then 'desc'
                                else 'asc'
                            end
                            || ':'
                            || case
                                when (
                                    index_catalog.indoption[key_position - 1]
                                    & 2
                                ) = 2 then 'nulls_first'
                                else 'nulls_last'
                            end
                        from pg_catalog.generate_series(
                            1,
                            index_catalog.indnkeyatts
                        ) as key_position
                        order by key_position
                    ) as ordered_sort_and_nulls,
                    coalesce(
                        pg_catalog.pg_get_expr(
                            index_catalog.indpred,
                            index_catalog.indrelid,
                            true
                        ),
                        ''
                    ) as predicate
                from pg_catalog.pg_index as index_catalog
                join pg_catalog.pg_class as index_definition
                  on index_definition.oid = index_catalog.indexrelid
                join pg_catalog.pg_am as access_method
                  on access_method.oid = index_definition.relam
                where index_catalog.indrelid = audit_table
            )
        ) as index_drift
    ) then
        raise exception 'authentication audit verification failed: exact named index definitions or health flags do not match';
    end if;

    select function_definition.proowner
    into function_owner_id
    from pg_catalog.pg_proc as function_definition
    where function_definition.oid = record_function;

    if function_owner_id <> current_owner_id
       or function_owner_id <> table_owner_id then
        raise exception 'authentication audit verification failed: function owner is not the trusted table owner';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_proc as function_definition
        join pg_catalog.pg_language as language_definition
          on language_definition.oid = function_definition.prolang
        where function_definition.oid = record_function
          and (
              function_definition.prorettype <> 'boolean'::pg_catalog.regtype
              or function_definition.proargnames is distinct from array[
                  'p_event_id',
                  'p_event_type',
                  'p_outcome',
                  'p_auth_method',
                  'p_user_id',
                  'p_failure_category',
                  'p_revocation_reason',
                  'p_correlation_id',
                  'p_source_environment'
              ]::text[]
              or function_definition.pronargs <> 9
              or function_definition.pronargdefaults <> 0
              or language_definition.lanname <> 'plpgsql'
              or function_definition.provolatile <> 'v'
              or function_definition.proparallel <> 'u'
              or function_definition.prosecdef is not true
              or function_definition.proleakproof is not false
              or function_definition.proisstrict is not false
              or function_definition.proconfig is distinct from
                 array['search_path=pg_catalog']::text[]
              or pg_catalog.regexp_replace(
                    function_definition.prosrc,
                    '\s+',
                    '',
                    'g'
                 ) <> pg_catalog.regexp_replace(
                    expected_function_body,
                    '\s+',
                    '',
                    'g'
                 )
          )
    ) then
        raise exception 'authentication audit verification failed: exact RPC contract or implementation does not match';
    end if;

    if not has_schema_privilege('anon', 'public', 'USAGE')
       or not has_schema_privilege('authenticated', 'public', 'USAGE')
       or not has_schema_privilege('service_role', 'public', 'USAGE')
       or has_schema_privilege('anon', 'public', 'CREATE')
       or has_schema_privilege('authenticated', 'public', 'CREATE')
       or has_schema_privilege('service_role', 'public', 'CREATE') then
        raise exception 'authentication audit verification failed: application-role schema privileges are outside the supported boundary';
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
        raise exception 'authentication audit verification failed: unexpected schema CREATE or grant option';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_class as table_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                table_definition.relacl,
                pg_catalog.acldefault('r', table_definition.relowner)
            )
        ) as privilege
        where table_definition.oid = audit_table
          and (
              privilege.grantee not in (table_owner_id, service_role_id)
              or (
                  privilege.grantee = service_role_id
                  and (
                      privilege.privilege_type <> 'SELECT'
                      or privilege.is_grantable
                  )
              )
          )
    ) then
        raise exception 'authentication audit verification failed: table ACL contains an unexpected grant';
    end if;

    select count(*)
    into service_table_select_count
    from pg_catalog.pg_class as table_definition
    cross join lateral pg_catalog.aclexplode(
        coalesce(
            table_definition.relacl,
            pg_catalog.acldefault('r', table_definition.relowner)
        )
    ) as privilege
    where table_definition.oid = audit_table
      and privilege.grantee = service_role_id
      and privilege.privilege_type = 'SELECT'
      and not privilege.is_grantable;

    if service_table_select_count <> 1
       or has_table_privilege('service_role', audit_table, 'INSERT')
       or has_table_privilege('service_role', audit_table, 'UPDATE')
       or has_table_privilege('service_role', audit_table, 'DELETE')
       or has_table_privilege('anon', audit_table, 'SELECT')
       or has_table_privilege('anon', audit_table, 'INSERT')
       or has_table_privilege('anon', audit_table, 'UPDATE')
       or has_table_privilege('anon', audit_table, 'DELETE')
       or has_table_privilege('authenticated', audit_table, 'SELECT')
       or has_table_privilege('authenticated', audit_table, 'INSERT')
       or has_table_privilege('authenticated', audit_table, 'UPDATE')
       or has_table_privilege('authenticated', audit_table, 'DELETE') then
        raise exception 'authentication audit verification failed: table privileges are not the exact allowlist';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_attribute as attribute_definition
        cross join lateral pg_catalog.aclexplode(attribute_definition.attacl) as privilege
        where attribute_definition.attrelid = audit_table
          and attribute_definition.attnum > 0
          and not attribute_definition.attisdropped
    )
       or has_any_column_privilege('service_role', audit_table, 'INSERT')
       or has_any_column_privilege('service_role', audit_table, 'UPDATE')
       or has_any_column_privilege('anon', audit_table, 'SELECT')
       or has_any_column_privilege('anon', audit_table, 'INSERT')
       or has_any_column_privilege('anon', audit_table, 'UPDATE')
       or has_any_column_privilege('authenticated', audit_table, 'SELECT')
       or has_any_column_privilege('authenticated', audit_table, 'INSERT')
       or has_any_column_privilege('authenticated', audit_table, 'UPDATE') then
        raise exception 'authentication audit verification failed: column ACL contains an unexpected grant';
    end if;

    if exists (
        select 1
        from pg_catalog.pg_proc as function_definition
        cross join lateral pg_catalog.aclexplode(
            coalesce(
                function_definition.proacl,
                pg_catalog.acldefault('f', function_definition.proowner)
            )
        ) as privilege
        where function_definition.oid = record_function
          and (
              privilege.grantee not in (function_owner_id, service_role_id)
              or (
                  privilege.grantee = service_role_id
                  and (
                      privilege.privilege_type <> 'EXECUTE'
                      or privilege.is_grantable
                  )
              )
          )
    ) then
        raise exception 'authentication audit verification failed: RPC ACL contains an unexpected grant';
    end if;

    select count(*)
    into service_function_execute_count
    from pg_catalog.pg_proc as function_definition
    cross join lateral pg_catalog.aclexplode(
        coalesce(
            function_definition.proacl,
            pg_catalog.acldefault('f', function_definition.proowner)
        )
    ) as privilege
    where function_definition.oid = record_function
      and privilege.grantee = service_role_id
      and privilege.privilege_type = 'EXECUTE'
      and not privilege.is_grantable;

    if service_function_execute_count <> 1
       or not has_function_privilege('service_role', record_function, 'EXECUTE')
       or has_function_privilege('anon', record_function, 'EXECUTE')
       or has_function_privilege('authenticated', record_function, 'EXECUTE') then
        raise exception 'authentication audit verification failed: RPC execution privileges are not the exact allowlist';
    end if;
end;
$schema_verification$;

insert into public.users (id, email, name)
values (
    '00000000-0000-4000-8000-000000001031',
    'audit-verification@example.invalid',
    'Audit Verification'
);

set local role service_role;

do $rpc_verification$
declare
    inserted boolean;
    duplicate_inserted boolean;
    same_correlation_inserted boolean;
begin
    select public.record_authentication_audit_event(
        '00000000-0000-4000-8000-000000001032',
        'login',
        'succeeded',
        'password',
        '00000000-0000-4000-8000-000000001031',
        null,
        null,
        'verification-correlation',
        'verification'
    ) into inserted;

    select public.record_authentication_audit_event(
        '00000000-0000-4000-8000-000000001032',
        'login',
        'succeeded',
        'password',
        '00000000-0000-4000-8000-000000001031',
        null,
        null,
        'verification-correlation',
        'verification'
    ) into duplicate_inserted;

    select public.record_authentication_audit_event(
        '00000000-0000-4000-8000-000000001033',
        'login',
        'succeeded',
        'password',
        '00000000-0000-4000-8000-000000001031',
        null,
        null,
        'verification-correlation',
        'verification'
    ) into same_correlation_inserted;

    if inserted is not true
       or duplicate_inserted is not false
       or same_correlation_inserted is not true then
        raise exception 'authentication audit verification failed: RPC idempotency behavior is incorrect';
    end if;

    begin
        perform public.record_authentication_audit_event(
            '00000000-0000-4000-8000-000000001032',
            'login',
            'failed',
            'password',
            '00000000-0000-4000-8000-000000001031',
            'internal_error',
            null,
            'verification-correlation',
            'verification'
        );
        raise exception 'authentication audit verification failed: conflicting retry was accepted';
    exception
        when unique_violation then
            null;
    end;
end;
$rpc_verification$;

reset role;

delete from public.users
where id = '00000000-0000-4000-8000-000000001031';

do $data_verification$
declare
    event_count integer;
    nulled_user_count integer;
begin
    select count(*)
    into event_count
    from public.authentication_audit_events
    where correlation_id = 'verification-correlation'
      and occurred_at >= transaction_timestamp()
      and occurred_at < clock_timestamp() + interval '1 second';

    select count(*)
    into nulled_user_count
    from public.authentication_audit_events
    where correlation_id = 'verification-correlation'
      and user_id is null;

    if event_count <> 2 or nulled_user_count <> 2 then
        raise exception 'authentication audit verification failed: time query or FK behavior is incorrect';
    end if;
end;
$data_verification$;

do $verification_complete$
begin
    raise notice 'authentication audit migration verification passed; synthetic changes are being rolled back';
end;
$verification_complete$;

rollback;
