-- ISSUE-1031 item 3, implementation PR 1: privacy-bounded security-request
-- attribution evidence, investigation-access evidence, bounded RPCs, and
-- retention cleanup.
--
-- This migration is additive and transactionally reapplicable. The trusted
-- migration role owns both tables and every SECURITY DEFINER function.
-- service_role can execute only the attribution-ingestion and cleanup RPCs;
-- it has no direct table access. The investigator query RPC remains
-- owner-only until an independently approved investigator role exists.

begin;

do $security_attribution_prerequisites$
declare
    current_owner_id oid := pg_catalog.to_regrole(current_user);
    object_name text;
    object_owner oid;
    expected_function pg_catalog.regprocedure;
begin
    if pg_catalog.to_regrole('anon') is null
       or pg_catalog.to_regrole('authenticated') is null
       or pg_catalog.to_regrole('service_role') is null then
        raise exception using
            errcode = 'P0001',
            message = 'security attribution migration requires anon, authenticated, and service_role roles';
    end if;

    if current_user in ('anon', 'authenticated', 'service_role') then
        raise exception using
            errcode = '42501',
            message = 'security attribution migration must run as a trusted database owner';
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
            message = 'security attribution migration owner requires schema USAGE and CREATE';
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
            message = 'security attribution migration found unsafe application-role schema privileges';
    end if;

    foreach object_name in array array[
        'security_request_attribution_events',
        'security_investigation_access_events'
    ]
    loop
        select table_definition.relowner
        into object_owner
        from pg_catalog.pg_class as table_definition
        where table_definition.oid = pg_catalog.to_regclass(
            pg_catalog.format('public.%I', object_name)
        );

        if object_owner is not null
           and object_owner <> current_owner_id then
            raise exception using
                errcode = '42501',
                message = 'security attribution migration cannot replace a table owned by another role';
        end if;
    end loop;

    foreach object_name in array array[
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
              and function_definition.proname = object_name
              and function_definition.proowner <> current_owner_id
        ) then
            raise exception using
                errcode = '42501',
                message = 'security attribution migration cannot replace a function owned by another role';
        end if;
    end loop;

    expected_function := pg_catalog.to_regprocedure(
        'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)'
    );
    if exists (
        select 1
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::pg_catalog.regnamespace
          and function_definition.proname =
              'record_security_request_attribution_event'
          and function_definition.oid is distinct from expected_function
    ) then
        raise exception using
            errcode = '42501',
            message = 'security attribution migration rejects unexpected ingestion RPC overloads';
    end if;

    expected_function := pg_catalog.to_regprocedure(
        'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'
    );
    if exists (
        select 1
        from pg_catalog.pg_proc as function_definition
        where function_definition.pronamespace =
              'public'::pg_catalog.regnamespace
          and function_definition.proname =
              'query_security_request_attribution_events'
          and function_definition.oid is distinct from expected_function
    ) then
        raise exception using
            errcode = '42501',
            message = 'security attribution migration rejects unexpected query RPC overloads';
    end if;

    foreach object_name in array array[
        'cleanup_security_request_attribution_events',
        'cleanup_security_investigation_access_events'
    ]
    loop
        expected_function := pg_catalog.to_regprocedure(
            pg_catalog.format(
                'public.%I(timestamptz,integer)',
                object_name
            )
        );
        if exists (
            select 1
            from pg_catalog.pg_proc as function_definition
            where function_definition.pronamespace =
                  'public'::pg_catalog.regnamespace
              and function_definition.proname = object_name
              and function_definition.oid is distinct from expected_function
        ) then
            raise exception using
                errcode = '42501',
                message = 'security attribution migration rejects unexpected cleanup RPC overloads';
        end if;
    end loop;
end;
$security_attribution_prerequisites$;

create table if not exists public.security_request_attribution_events (
    id uuid primary key default pg_catalog.gen_random_uuid(),
    request_event_id uuid not null unique,
    occurred_at timestamptz not null,
    account_pseudonym text not null,
    pseudonym_epoch text not null,
    pseudonym_key_version smallint not null,
    environment text not null,
    event_category text not null,
    route_key text not null,
    http_method text not null,
    outcome text not null,
    failure_category text,
    server_correlation_id uuid,
    created_at timestamptz not null default pg_catalog.now(),
    constraint security_attribution_request_event_nonzero check (
        request_event_id <>
        '00000000-0000-0000-0000-000000000000'::uuid
    ),
    constraint security_attribution_server_correlation_nonzero check (
        server_correlation_id is null
        or server_correlation_id <>
           '00000000-0000-0000-0000-000000000000'::uuid
    ),
    constraint security_attribution_timestamp_check check (
        pg_catalog.isfinite(occurred_at)
        and pg_catalog.isfinite(created_at)
        and occurred_at <= created_at
    ),
    constraint security_attribution_pseudonym_check check (
        pg_catalog.char_length(account_pseudonym) = 43
        and account_pseudonym ~ '^[A-Za-z0-9_-]{43}$'
    ),
    constraint security_attribution_epoch_check check (
        pseudonym_epoch ~
        '^[0-9]{4}-(0[1-9]|1[0-2])$'
        and pseudonym_epoch =
            pg_catalog.to_char(occurred_at at time zone 'UTC', 'YYYY-MM')
    ),
    constraint security_attribution_key_version_check check (
        pseudonym_key_version between 1 and 32767
    ),
    constraint security_attribution_environment_check check (
        environment in ('development', 'staging', 'production')
    ),
    constraint security_attribution_method_check check (
        http_method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
    ),
    constraint security_attribution_outcome_check check (
        outcome in ('succeeded', 'denied', 'failed', 'ambiguous')
    ),
    constraint security_attribution_failure_category_check check (
        failure_category is null
        or failure_category in (
            'authorization_denied',
            'reauthentication_failed',
            'validation_rejected',
            'conflict',
            'not_found',
            'rate_limited',
            'dependency_unavailable',
            'outcome_unknown',
            'internal_error'
        )
    ),
    constraint security_attribution_outcome_failure_check check (
        (outcome = 'succeeded' and failure_category is null)
        or (
            outcome = 'denied'
            and failure_category in (
                'authorization_denied',
                'reauthentication_failed'
            )
        )
        or (
            outcome = 'failed'
            and failure_category in (
                'validation_rejected',
                'conflict',
                'not_found',
                'rate_limited',
                'dependency_unavailable',
                'internal_error'
            )
        )
        or (
            outcome = 'ambiguous'
            and failure_category = 'outcome_unknown'
        )
    ),
    constraint security_attribution_route_registry_check check (
        (event_category, route_key, http_method) in (
            ('session_security_change', 'auth_logout', 'POST'),
            (
                'credential_configuration_read',
                'auth_account_methods_read',
                'GET'
            ),
            ('credential_method_change', 'auth_google_link', 'POST'),
            ('credential_method_change', 'auth_google_unlink', 'POST'),
            ('credential_method_change', 'auth_password_set', 'POST'),
            ('credential_method_change', 'auth_password_remove', 'POST'),
            (
                'credential_recovery',
                'auth_password_reset_confirm',
                'POST'
            ),
            ('account_assurance_change', 'auth_email_verify', 'POST'),
            ('account_lifecycle_change', 'auth_account_delete', 'DELETE'),
            (
                'private_security_record_read',
                'field_reports_mine_read',
                'GET'
            ),
            ('access_control_read', 'user_blocks_read', 'GET'),
            ('access_control_change', 'user_block_create', 'POST'),
            ('access_control_change', 'user_block_delete', 'DELETE'),
            (
                'private_notification_read',
                'notifications_private_read',
                'GET'
            ),
            (
                'private_security_setting_read',
                'notification_preferences_read',
                'GET'
            ),
            (
                'private_security_setting_change',
                'notification_preferences_update',
                'PUT'
            ),
            (
                'notification_delivery_binding_change',
                'push_token_bind',
                'POST'
            ),
            (
                'notification_delivery_binding_change',
                'push_token_unbind',
                'DELETE'
            ),
            ('admin_sensitive_read', 'admin_self_read', 'GET'),
            ('admin_sensitive_read', 'admin_users_read', 'GET'),
            ('admin_sensitive_read', 'admin_field_reports_read', 'GET'),
            ('admin_sensitive_read', 'admin_stats_read', 'GET'),
            ('admin_sensitive_read', 'admin_fields_read', 'GET'),
            ('admin_sensitive_read', 'admin_fields_pending_read', 'GET'),
            (
                'admin_sensitive_read',
                'admin_field_duplicates_read',
                'GET'
            ),
            ('admin_sensitive_read', 'admin_games_read', 'GET'),
            ('admin_sensitive_read', 'admin_engagement_read', 'GET'),
            ('admin_sensitive_read', 'admin_monitoring_read', 'GET'),
            (
                'admin_sensitive_read',
                'admin_content_reports_read',
                'GET'
            ),
            (
                'admin_sensitive_read',
                'admin_notification_candidates_read',
                'POST'
            ),
            ('admin_account_control', 'admin_user_ban', 'POST'),
            ('admin_account_control', 'admin_user_unban', 'POST'),
            ('admin_account_control', 'admin_user_suspend', 'POST'),
            ('admin_account_control', 'admin_user_unsuspend', 'POST'),
            (
                'admin_moderation_change',
                'admin_field_report_status',
                'PATCH'
            ),
            (
                'admin_moderation_change',
                'admin_field_report_resolve',
                'PATCH'
            ),
            ('admin_content_control', 'admin_field_approve', 'POST'),
            ('admin_content_control', 'admin_field_reject', 'POST'),
            ('admin_content_control', 'admin_field_status', 'PATCH'),
            ('admin_content_control', 'admin_field_update', 'PATCH'),
            ('admin_content_control', 'admin_field_delete', 'DELETE'),
            (
                'admin_content_control',
                'admin_field_status_external',
                'PATCH'
            ),
            (
                'admin_operational_action',
                'admin_reminders_run',
                'POST'
            ),
            (
                'admin_operational_action',
                'admin_notification_cleanup',
                'POST'
            ),
            ('admin_content_control', 'admin_game_close', 'POST'),
            ('admin_content_control', 'admin_game_extend', 'POST'),
            ('admin_content_control', 'admin_game_cancel', 'POST'),
            (
                'admin_moderation_change',
                'admin_content_report_update',
                'PATCH'
            )
        )
    )
);

create table if not exists public.security_investigation_access_events (
    id uuid primary key default pg_catalog.gen_random_uuid(),
    access_event_id uuid not null unique,
    occurred_at timestamptz not null,
    incident_id uuid not null,
    investigator_capability text not null,
    action_category text not null,
    query_window_start timestamptz not null,
    query_window_end timestamptz not null,
    requested_limit integer not null,
    result_count integer,
    environment text not null,
    outcome text not null,
    failure_category text,
    created_at timestamptz not null default pg_catalog.now(),
    constraint security_investigation_access_ids_nonzero check (
        access_event_id <>
        '00000000-0000-0000-0000-000000000000'::uuid
        and incident_id <>
            '00000000-0000-0000-0000-000000000000'::uuid
    ),
    constraint security_investigation_access_timestamp_check check (
        pg_catalog.isfinite(occurred_at)
        and pg_catalog.isfinite(created_at)
        and pg_catalog.isfinite(query_window_start)
        and pg_catalog.isfinite(query_window_end)
        and occurred_at <= created_at
    ),
    constraint security_investigation_access_window_check check (
        query_window_end > query_window_start
        and query_window_end - query_window_start <= interval '31 days'
    ),
    constraint security_investigation_access_limit_check check (
        requested_limit between 1 and 10000
    ),
    constraint security_investigation_access_result_count_check check (
        result_count is null
        or result_count between 0 and requested_limit
    ),
    constraint security_investigation_access_capability_check check (
        investigator_capability in (
            'owner_activation_gate',
            'security_evidence_reader'
        )
    ),
    constraint security_investigation_access_action_check check (
        action_category = 'query'
    ),
    constraint security_investigation_access_environment_check check (
        environment in ('development', 'staging', 'production')
    ),
    constraint security_investigation_access_outcome_check check (
        outcome in ('succeeded', 'rejected', 'failed')
    ),
    constraint security_investigation_access_failure_check check (
        failure_category is null
        or failure_category in (
            'invalid_window',
            'limit_out_of_range',
            'query_failed'
        )
    ),
    constraint security_investigation_access_outcome_failure_check check (
        (
            outcome = 'succeeded'
            and failure_category is null
            and result_count is not null
        )
        or (
            outcome = 'rejected'
            and failure_category in (
                'invalid_window',
                'limit_out_of_range'
            )
            and result_count is null
        )
        or (
            outcome = 'failed'
            and failure_category = 'query_failed'
            and result_count is null
        )
    )
);

alter table public.security_request_attribution_events owner to current_user;
alter table public.security_investigation_access_events owner to current_user;
alter table public.security_request_attribution_events
    enable row level security;
alter table public.security_request_attribution_events
    no force row level security;
alter table public.security_investigation_access_events
    enable row level security;
alter table public.security_investigation_access_events
    no force row level security;

do $security_attribution_table_acl$
declare
    table_name text;
    table_oid pg_catalog.regclass;
    grantee_name text;
    column_list text;
begin
    foreach table_name in array array[
        'security_request_attribution_events',
        'security_investigation_access_events'
    ]
    loop
        table_oid := pg_catalog.to_regclass(
            pg_catalog.format('public.%I', table_name)
        );

        execute pg_catalog.format(
            'revoke all privileges on table public.%I from public cascade',
            table_name
        );

        for grantee_name in
            select distinct role_definition.rolname
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
            join pg_catalog.pg_roles as role_definition
              on role_definition.oid = privilege.grantee
            where table_definition.oid = table_oid
        loop
            execute pg_catalog.format(
                'revoke all privileges on table public.%I from %I cascade',
                table_name,
                grantee_name
            );
        end loop;

        select pg_catalog.string_agg(
            pg_catalog.format('%I', attribute_definition.attname),
            ','
            order by attribute_definition.attnum
        )
        into column_list
        from pg_catalog.pg_attribute as attribute_definition
        where attribute_definition.attrelid = table_oid
          and attribute_definition.attnum > 0
          and not attribute_definition.attisdropped;

        execute pg_catalog.format(
            'revoke all privileges (%s) on table public.%I from public cascade',
            column_list,
            table_name
        );

        for grantee_name in
            select distinct role_definition.rolname
            from pg_catalog.pg_attribute as attribute_definition
            cross join lateral pg_catalog.aclexplode(
                attribute_definition.attacl
            ) as privilege
            join pg_catalog.pg_roles as role_definition
              on role_definition.oid = privilege.grantee
            where attribute_definition.attrelid = table_oid
              and attribute_definition.attnum > 0
              and not attribute_definition.attisdropped
        loop
            execute pg_catalog.format(
                'revoke all privileges (%s) on table public.%I from %I cascade',
                column_list,
                table_name,
                grantee_name
            );
        end loop;

        execute pg_catalog.format(
            'grant select, insert, delete on table public.%I to current_user',
            table_name
        );
        execute pg_catalog.format(
            'grant update (id) on table public.%I to current_user',
            table_name
        );
    end loop;
end;
$security_attribution_table_acl$;

create index if not exists idx_security_attribution_cleanup
    on public.security_request_attribution_events(occurred_at, id);
create index if not exists idx_security_attribution_environment_window
    on public.security_request_attribution_events(
        environment,
        occurred_at,
        id
    );
create index if not exists idx_security_attribution_pseudonym_epoch
    on public.security_request_attribution_events(
        account_pseudonym,
        pseudonym_epoch,
        occurred_at desc
    );
create index if not exists idx_security_investigation_access_cleanup
    on public.security_investigation_access_events(occurred_at, id);
create index if not exists idx_security_investigation_access_incident
    on public.security_investigation_access_events(
        incident_id,
        occurred_at desc,
        id desc
    );

create or replace function public.record_security_request_attribution_event(
    p_request_event_id uuid,
    p_occurred_at timestamptz,
    p_account_pseudonym text,
    p_pseudonym_epoch text,
    p_pseudonym_key_version smallint,
    p_environment text,
    p_event_category text,
    p_route_key text,
    p_http_method text,
    p_outcome text,
    p_failure_category text,
    p_server_correlation_id uuid
)
returns text
language plpgsql
volatile
parallel unsafe
security definer
set search_path = pg_catalog
as $$
declare
    inserted_count integer;
begin
    if p_request_event_id is null
       or p_request_event_id =
          '00000000-0000-0000-0000-000000000000'::uuid then
        raise exception using
            errcode = '22023',
            message = 'p_request_event_id must be a nonzero UUID';
    end if;
    if p_occurred_at is null
       or not pg_catalog.isfinite(p_occurred_at)
       or p_occurred_at > pg_catalog.now() then
        raise exception using
            errcode = '22023',
            message = 'p_occurred_at must be a finite non-future timestamp';
    end if;
    if p_account_pseudonym is null
       or pg_catalog.char_length(p_account_pseudonym) <> 43
       or p_account_pseudonym !~ '^[A-Za-z0-9_-]{43}$' then
        raise exception using
            errcode = '22023',
            message = 'p_account_pseudonym must be 43 unpadded Base64url characters';
    end if;
    if p_pseudonym_epoch is null
       or p_pseudonym_epoch !~
          '^[0-9]{4}-(0[1-9]|1[0-2])$'
       or p_pseudonym_epoch <>
          pg_catalog.to_char(
              p_occurred_at at time zone 'UTC',
              'YYYY-MM'
          ) then
        raise exception using
            errcode = '22023',
            message = 'p_pseudonym_epoch must match the UTC event month';
    end if;
    if p_pseudonym_key_version is null
       or p_pseudonym_key_version < 1 then
        raise exception using
            errcode = '22023',
            message = 'p_pseudonym_key_version must be positive';
    end if;
    if p_environment is null
       or p_environment not in (
           'development',
           'staging',
           'production'
       ) then
        raise exception using
            errcode = '22023',
            message = 'p_environment is not approved';
    end if;
    if p_http_method is null
       or p_http_method not in (
           'GET',
           'POST',
           'PUT',
           'PATCH',
           'DELETE'
       ) then
        raise exception using
            errcode = '22023',
            message = 'p_http_method is not approved';
    end if;
    if p_outcome is null
       or p_outcome not in (
           'succeeded',
           'denied',
           'failed',
           'ambiguous'
       ) then
        raise exception using
            errcode = '22023',
            message = 'p_outcome is not approved';
    end if;
    if p_failure_category is not null
       and p_failure_category not in (
           'authorization_denied',
           'reauthentication_failed',
           'validation_rejected',
           'conflict',
           'not_found',
           'rate_limited',
           'dependency_unavailable',
           'outcome_unknown',
           'internal_error'
       ) then
        raise exception using
            errcode = '22023',
            message = 'p_failure_category is not approved';
    end if;
    if not (
        (p_outcome = 'succeeded' and p_failure_category is null)
        or (
            p_outcome = 'denied'
            and p_failure_category in (
                'authorization_denied',
                'reauthentication_failed'
            )
        )
        or (
            p_outcome = 'failed'
            and p_failure_category in (
                'validation_rejected',
                'conflict',
                'not_found',
                'rate_limited',
                'dependency_unavailable',
                'internal_error'
            )
        )
        or (
            p_outcome = 'ambiguous'
            and p_failure_category = 'outcome_unknown'
        )
    ) then
        raise exception using
            errcode = '22023',
            message = 'p_outcome and p_failure_category are incompatible';
    end if;
    if p_server_correlation_id =
       '00000000-0000-0000-0000-000000000000'::uuid then
        raise exception using
            errcode = '22023',
            message = 'p_server_correlation_id must be null or nonzero';
    end if;
    if (p_event_category, p_route_key, p_http_method) not in (
        ('session_security_change', 'auth_logout', 'POST'),
        (
            'credential_configuration_read',
            'auth_account_methods_read',
            'GET'
        ),
        ('credential_method_change', 'auth_google_link', 'POST'),
        ('credential_method_change', 'auth_google_unlink', 'POST'),
        ('credential_method_change', 'auth_password_set', 'POST'),
        ('credential_method_change', 'auth_password_remove', 'POST'),
        (
            'credential_recovery',
            'auth_password_reset_confirm',
            'POST'
        ),
        ('account_assurance_change', 'auth_email_verify', 'POST'),
        ('account_lifecycle_change', 'auth_account_delete', 'DELETE'),
        (
            'private_security_record_read',
            'field_reports_mine_read',
            'GET'
        ),
        ('access_control_read', 'user_blocks_read', 'GET'),
        ('access_control_change', 'user_block_create', 'POST'),
        ('access_control_change', 'user_block_delete', 'DELETE'),
        (
            'private_notification_read',
            'notifications_private_read',
            'GET'
        ),
        (
            'private_security_setting_read',
            'notification_preferences_read',
            'GET'
        ),
        (
            'private_security_setting_change',
            'notification_preferences_update',
            'PUT'
        ),
        (
            'notification_delivery_binding_change',
            'push_token_bind',
            'POST'
        ),
        (
            'notification_delivery_binding_change',
            'push_token_unbind',
            'DELETE'
        ),
        ('admin_sensitive_read', 'admin_self_read', 'GET'),
        ('admin_sensitive_read', 'admin_users_read', 'GET'),
        ('admin_sensitive_read', 'admin_field_reports_read', 'GET'),
        ('admin_sensitive_read', 'admin_stats_read', 'GET'),
        ('admin_sensitive_read', 'admin_fields_read', 'GET'),
        ('admin_sensitive_read', 'admin_fields_pending_read', 'GET'),
        (
            'admin_sensitive_read',
            'admin_field_duplicates_read',
            'GET'
        ),
        ('admin_sensitive_read', 'admin_games_read', 'GET'),
        ('admin_sensitive_read', 'admin_engagement_read', 'GET'),
        ('admin_sensitive_read', 'admin_monitoring_read', 'GET'),
        ('admin_sensitive_read', 'admin_content_reports_read', 'GET'),
        (
            'admin_sensitive_read',
            'admin_notification_candidates_read',
            'POST'
        ),
        ('admin_account_control', 'admin_user_ban', 'POST'),
        ('admin_account_control', 'admin_user_unban', 'POST'),
        ('admin_account_control', 'admin_user_suspend', 'POST'),
        ('admin_account_control', 'admin_user_unsuspend', 'POST'),
        (
            'admin_moderation_change',
            'admin_field_report_status',
            'PATCH'
        ),
        (
            'admin_moderation_change',
            'admin_field_report_resolve',
            'PATCH'
        ),
        ('admin_content_control', 'admin_field_approve', 'POST'),
        ('admin_content_control', 'admin_field_reject', 'POST'),
        ('admin_content_control', 'admin_field_status', 'PATCH'),
        ('admin_content_control', 'admin_field_update', 'PATCH'),
        ('admin_content_control', 'admin_field_delete', 'DELETE'),
        (
            'admin_content_control',
            'admin_field_status_external',
            'PATCH'
        ),
        ('admin_operational_action', 'admin_reminders_run', 'POST'),
        (
            'admin_operational_action',
            'admin_notification_cleanup',
            'POST'
        ),
        ('admin_content_control', 'admin_game_close', 'POST'),
        ('admin_content_control', 'admin_game_extend', 'POST'),
        ('admin_content_control', 'admin_game_cancel', 'POST'),
        (
            'admin_moderation_change',
            'admin_content_report_update',
            'PATCH'
        )
    ) then
        raise exception using
            errcode = '22023',
            message = 'event category, route key, and method are not an approved tuple';
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(p_request_event_id::text, 1031)
    );

    begin
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
            failure_category,
            server_correlation_id
        )
        values (
            p_request_event_id,
            p_occurred_at,
            p_account_pseudonym,
            p_pseudonym_epoch,
            p_pseudonym_key_version,
            p_environment,
            p_event_category,
            p_route_key,
            p_http_method,
            p_outcome,
            p_failure_category,
            p_server_correlation_id
        )
        on conflict (request_event_id) do nothing;
    exception
        when others then
            raise exception using
                errcode = 'P0001',
                message = 'security attribution persistence failed';
    end;

    get diagnostics inserted_count = row_count;
    if inserted_count = 1 then
        return 'inserted';
    end if;

    if exists (
        select 1
        from public.security_request_attribution_events as existing_event
        where existing_event.request_event_id = p_request_event_id
          and existing_event.occurred_at is not distinct from p_occurred_at
          and existing_event.account_pseudonym is not distinct from
              p_account_pseudonym
          and existing_event.pseudonym_epoch is not distinct from
              p_pseudonym_epoch
          and existing_event.pseudonym_key_version is not distinct from
              p_pseudonym_key_version
          and existing_event.environment is not distinct from p_environment
          and existing_event.event_category is not distinct from
              p_event_category
          and existing_event.route_key is not distinct from p_route_key
          and existing_event.http_method is not distinct from p_http_method
          and existing_event.outcome is not distinct from p_outcome
          and existing_event.failure_category is not distinct from
              p_failure_category
          and existing_event.server_correlation_id is not distinct from
              p_server_correlation_id
    ) then
        return 'already_recorded';
    end if;

    raise exception using
        errcode = '23505',
        message = 'request event ID conflicts with an immutable payload';
end;
$$;

create or replace function public.query_security_request_attribution_events(
    p_incident_id uuid,
    p_environment text,
    p_window_start timestamptz,
    p_window_end timestamptz,
    p_result_limit integer
)
returns table (
    query_status text,
    request_event_id uuid,
    occurred_at timestamptz,
    account_pseudonym text,
    pseudonym_epoch text,
    pseudonym_key_version smallint,
    environment text,
    event_category text,
    route_key text,
    http_method text,
    outcome text,
    failure_category text,
    server_correlation_id uuid
)
language plpgsql
volatile
parallel unsafe
security definer
set search_path = pg_catalog
as $$
declare
    attempt_at timestamptz := pg_catalog.now();
    audit_window_start timestamptz;
    audit_window_end timestamptz;
    audit_limit integer;
    audit_failure text;
    returned_count integer;
    capability text;
begin
    if p_incident_id is null
       or p_incident_id =
          '00000000-0000-0000-0000-000000000000'::uuid then
        raise exception using
            errcode = '22023',
            message = 'p_incident_id must be a nonzero UUID';
    end if;
    if p_environment is null
       or p_environment not in (
           'development',
           'staging',
           'production'
       ) then
        raise exception using
            errcode = '22023',
            message = 'p_environment is not approved';
    end if;

    capability := case
        when session_user = current_user
            then 'owner_activation_gate'
        else 'security_evidence_reader'
    end;

    if p_window_start is null
       or p_window_end is null
       or not pg_catalog.isfinite(p_window_start)
       or not pg_catalog.isfinite(p_window_end)
       or p_window_end <= p_window_start
       or p_window_end - p_window_start > interval '31 days' then
        audit_window_start := attempt_at;
        audit_window_end := attempt_at + interval '1 microsecond';
        audit_limit := 1;
        audit_failure := 'invalid_window';
    elsif p_result_limit is null
          or p_result_limit < 1
          or p_result_limit > 10000 then
        audit_window_start := p_window_start;
        audit_window_end := p_window_end;
        audit_limit := 1;
        audit_failure := 'limit_out_of_range';
    end if;

    if audit_failure is not null then
        begin
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
            values (
                pg_catalog.gen_random_uuid(),
                attempt_at,
                p_incident_id,
                capability,
                'query',
                audit_window_start,
                audit_window_end,
                audit_limit,
                null,
                p_environment,
                'rejected',
                audit_failure
            );
        exception
            when others then
                raise exception using
                    errcode = 'P0001',
                    message = 'investigation access audit persistence failed';
        end;

        return query
        select
            'rejected'::text,
            null::uuid,
            null::timestamptz,
            null::text,
            null::text,
            null::smallint,
            null::text,
            null::text,
            null::text,
            null::text,
            null::text,
            null::text,
            null::uuid;
        return;
    end if;

    begin
        return query
        select
            'succeeded'::text,
            evidence.request_event_id,
            evidence.occurred_at,
            evidence.account_pseudonym,
            evidence.pseudonym_epoch,
            evidence.pseudonym_key_version,
            evidence.environment,
            evidence.event_category,
            evidence.route_key,
            evidence.http_method,
            evidence.outcome,
            evidence.failure_category,
            evidence.server_correlation_id
        from public.security_request_attribution_events as evidence
        where evidence.environment = p_environment
          and evidence.occurred_at >= p_window_start
          and evidence.occurred_at < p_window_end
        order by evidence.occurred_at asc, evidence.id asc
        limit p_result_limit;

        get diagnostics returned_count = row_count;

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
        values (
            pg_catalog.gen_random_uuid(),
            attempt_at,
            p_incident_id,
            capability,
            'query',
            p_window_start,
            p_window_end,
            p_result_limit,
            returned_count,
            p_environment,
            'succeeded',
            null
        );
    exception
        when others then
            begin
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
                values (
                    pg_catalog.gen_random_uuid(),
                    attempt_at,
                    p_incident_id,
                    capability,
                    'query',
                    p_window_start,
                    p_window_end,
                    p_result_limit,
                    null,
                    p_environment,
                    'failed',
                    'query_failed'
                );
            exception
                when others then
                    raise exception using
                        errcode = 'P0001',
                        message = 'investigation access audit persistence failed';
            end;

            return query
            select
                'failed'::text,
                null::uuid,
                null::timestamptz,
                null::text,
                null::text,
                null::smallint,
                null::text,
                null::text,
                null::text,
                null::text,
                null::text,
                null::text,
                null::uuid;
            return;
    end;

    if returned_count = 0 then
        return query
        select
            'succeeded'::text,
            null::uuid,
            null::timestamptz,
            null::text,
            null::text,
            null::smallint,
            null::text,
            null::text,
            null::text,
            null::text,
            null::text,
            null::text,
            null::uuid;
    end if;
end;
$$;

create or replace function public.cleanup_security_request_attribution_events(
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
    if p_cutoff is null
       or not pg_catalog.isfinite(p_cutoff)
       or p_cutoff > pg_catalog.now() then
        raise exception using
            errcode = '22023',
            message = 'p_cutoff must be finite and not in the future';
    end if;
    if p_batch_limit is null
       or p_batch_limit < 1
       or p_batch_limit > 1000 then
        raise exception using
            errcode = '22023',
            message = 'p_batch_limit must be between 1 and 1000';
    end if;

    with candidates as materialized (
        select evidence.id
        from public.security_request_attribution_events as evidence
        where evidence.occurred_at < p_cutoff
        order by evidence.occurred_at asc, evidence.id asc
        limit p_batch_limit
        for update of evidence skip locked
    ),
    deleted_rows as (
        delete from public.security_request_attribution_events as evidence
        using candidates
        where evidence.id = candidates.id
          and evidence.occurred_at < p_cutoff
        returning evidence.id
    )
    select pg_catalog.count(*)::integer
    into deleted_count
    from deleted_rows;

    return deleted_count;
end;
$$;

create or replace function public.cleanup_security_investigation_access_events(
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
    if p_cutoff is null
       or not pg_catalog.isfinite(p_cutoff)
       or p_cutoff > pg_catalog.now() then
        raise exception using
            errcode = '22023',
            message = 'p_cutoff must be finite and not in the future';
    end if;
    if p_batch_limit is null
       or p_batch_limit < 1
       or p_batch_limit > 1000 then
        raise exception using
            errcode = '22023',
            message = 'p_batch_limit must be between 1 and 1000';
    end if;

    with candidates as materialized (
        select access_event.id
        from public.security_investigation_access_events as access_event
        where access_event.occurred_at < p_cutoff
        order by access_event.occurred_at asc, access_event.id asc
        limit p_batch_limit
        for update of access_event skip locked
    ),
    deleted_rows as (
        delete from public.security_investigation_access_events
            as access_event
        using candidates
        where access_event.id = candidates.id
          and access_event.occurred_at < p_cutoff
        returning access_event.id
    )
    select pg_catalog.count(*)::integer
    into deleted_count
    from deleted_rows;

    return deleted_count;
end;
$$;

alter function public.record_security_request_attribution_event(
    uuid,
    timestamptz,
    text,
    text,
    smallint,
    text,
    text,
    text,
    text,
    text,
    text,
    uuid
) owner to current_user;
alter function public.query_security_request_attribution_events(
    uuid,
    text,
    timestamptz,
    timestamptz,
    integer
) owner to current_user;
alter function public.cleanup_security_request_attribution_events(
    timestamptz,
    integer
) owner to current_user;
alter function public.cleanup_security_investigation_access_events(
    timestamptz,
    integer
) owner to current_user;

do $security_attribution_function_acl$
declare
    function_definition record;
    grantee_name text;
begin
    for function_definition in
        select
            procedure_definition.oid,
            procedure_definition.oid::pg_catalog.regprocedure::text
                as identity
        from pg_catalog.pg_proc as procedure_definition
        where procedure_definition.oid in (
            'public.record_security_request_attribution_event(uuid,timestamptz,text,text,smallint,text,text,text,text,text,text,uuid)'::pg_catalog.regprocedure,
            'public.query_security_request_attribution_events(uuid,text,timestamptz,timestamptz,integer)'::pg_catalog.regprocedure,
            'public.cleanup_security_request_attribution_events(timestamptz,integer)'::pg_catalog.regprocedure,
            'public.cleanup_security_investigation_access_events(timestamptz,integer)'::pg_catalog.regprocedure
        )
    loop
        execute pg_catalog.format(
            'revoke all privileges on function %s from public cascade',
            function_definition.identity
        );

        for grantee_name in
            select distinct role_definition.rolname
            from pg_catalog.pg_proc as procedure_definition
            cross join lateral pg_catalog.aclexplode(
                coalesce(
                    procedure_definition.proacl,
                    pg_catalog.acldefault(
                        'f',
                        procedure_definition.proowner
                    )
                )
            ) as privilege
            join pg_catalog.pg_roles as role_definition
              on role_definition.oid = privilege.grantee
            where procedure_definition.oid = function_definition.oid
        loop
            execute pg_catalog.format(
                'revoke all privileges on function %s from %I cascade',
                function_definition.identity,
                grantee_name
            );
        end loop;
    end loop;
end;
$security_attribution_function_acl$;

grant execute on function public.record_security_request_attribution_event(
    uuid,
    timestamptz,
    text,
    text,
    smallint,
    text,
    text,
    text,
    text,
    text,
    text,
    uuid
) to current_user;
grant execute on function public.record_security_request_attribution_event(
    uuid,
    timestamptz,
    text,
    text,
    smallint,
    text,
    text,
    text,
    text,
    text,
    text,
    uuid
) to service_role;
grant execute on function public.query_security_request_attribution_events(
    uuid,
    text,
    timestamptz,
    timestamptz,
    integer
) to current_user;
grant execute on function public.cleanup_security_request_attribution_events(
    timestamptz,
    integer
) to current_user;
grant execute on function public.cleanup_security_request_attribution_events(
    timestamptz,
    integer
) to service_role;
grant execute on function public.cleanup_security_investigation_access_events(
    timestamptz,
    integer
) to current_user;
grant execute on function public.cleanup_security_investigation_access_events(
    timestamptz,
    integer
) to service_role;

commit;
