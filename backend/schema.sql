create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    google_sub text unique,
    email text unique,
    username text unique,
    password_hash text,
    name text not null,
    role text not null default 'user' check (role in ('user', 'admin')),
    status text not null default 'active' check (status in ('active', 'banned', 'suspended')),
    restriction_reason text,
    restricted_at timestamptz,
    restricted_by uuid references users(id) on delete set null,
    picture text,
    phone_number text unique,
    created_at timestamptz not null default now(),
    last_login timestamptz,
    last_active timestamptz,
    tokens_valid_after timestamptz,
    email_verified boolean not null default true,
    email_verified_at timestamptz,
    terms_accepted_at timestamptz
);

create table if not exists email_verification_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    token_hash text not null unique,
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    used_at timestamptz
);

create table if not exists user_identities (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    provider text not null,
    provider_subject text not null,
    email_at_link text,
    email_verified_at_link boolean not null default false,
    created_at timestamptz not null default now(),
    last_used_at timestamptz not null default now(),
    unique (provider, provider_subject),
    unique (user_id, provider)
);

create table if not exists fields (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    lat numeric(10, 7) not null,
    lng numeric(10, 7) not null,
    sport_type text not null check (sport_type in ('football', 'basketball', 'both')),
    surface_type text,
    has_nets boolean not null default false,
    has_water boolean not null default false,
    opening_hours text,
    city text,
    status text not null default 'open' check (status in ('open', 'closed', 'renovation')),
    approval_status text not null default 'pending' check (approval_status in ('pending', 'approved', 'rejected')),
    verified boolean not null default false,
    added_by uuid references users(id) on delete set null,
    created_at timestamptz not null default now(),
    notes text,
    image_url text,
    updated_at timestamptz,
    removed_at timestamptz,
    removed_by uuid references users(id) on delete set null,
    removal_reason text
        check (removal_reason is null or removal_reason in (
            'field_does_not_exist',
            'duplicate_field',
            'private_field',
            'school_property',
            'wrong_location',
            'invalid_field',
            'safety_issue',
            'other'
        ))
);

create table if not exists games (
    id uuid primary key default gen_random_uuid(),
    field_id uuid not null references fields(id) on delete cascade,
    created_by uuid references users(id) on delete set null,
    sport_type text not null check (sport_type in ('football', 'basketball')),
    players_present integer not null default 0 check (players_present >= 0),
    max_players integer not null check (max_players > 0),
    status text not null default 'open' check (status in ('open', 'full', 'finished', 'cancelled')),
    age_note text,
    min_age integer check (min_age is null or min_age >= 0),
    max_age integer check (max_age is null or max_age >= 0),
    scheduled_at timestamptz,
    scheduled_reminder_processed_at timestamptz,
    started_at timestamptz not null default now(),
    expires_at timestamptz,
    cancelled_at timestamptz,
    cancelled_by uuid references users(id) on delete set null,
    cancelled_by_role text,
    cancel_reason text,
    check (min_age is null or max_age is null or min_age <= max_age),
    check (players_present <= max_players)
);

create table if not exists game_players (
    id uuid primary key default gen_random_uuid(),
    game_id uuid not null references games(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    joined_at timestamptz not null default now(),
    unique (game_id, user_id)
);

create table if not exists field_reports (
    id uuid primary key default gen_random_uuid(),
    field_id uuid not null references fields(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    category text not null check (
        category in (
            'wrong_location',
            'field_does_not_exist',
            'field_closed',
            'under_renovation',
            'private_field',
            'duplicate_field',
            'wrong_information',
            'other'
        )
    ),
    description text,
    status text not null default 'open' check (
        status in ('open', 'in_review', 'resolved', 'rejected')
    ),
    admin_note text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz,
    reviewed_by uuid references users(id) on delete set null
);

create table if not exists notification_preferences (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    enabled boolean not null default true,
    sport_type text not null default 'both' check (sport_type in ('football', 'basketball', 'both')),
    notification_type text not null check (notification_type in ('radius', 'city', 'specific_field')),
    radius_km numeric(6, 2),
    lat numeric(10, 7),
    lng numeric(10, 7),
    city text,
    field_id uuid references fields(id) on delete cascade,
    created_at timestamptz not null default now()
);

create table if not exists notifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    type text not null,
    title text not null,
    body text not null,
    game_id uuid references games(id) on delete set null,
    field_id uuid references fields(id) on delete set null,
    data jsonb,
    read_at timestamptz,
    created_at timestamptz not null default now()
);

-- Canonical fresh-bootstrap form of migrations/push_notifications.sql plus
-- migrations/push_token_device_metadata.sql. This table must precede
-- push_delivery_attempts, whose push_token_id foreign key references it.
create table if not exists push_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    token text not null unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    platform text,
    installation_id text,
    constraint push_tokens_platform_check
        check (platform is null or platform in ('android', 'ios', 'web'))
);

create table if not exists user_moderation_audit (
    id uuid primary key default gen_random_uuid(),
    target_user_id uuid not null references users(id) on delete cascade,
    actor_user_id uuid references users(id) on delete set null,
    action_type text not null check (action_type in ('ban', 'unban', 'suspend', 'unsuspend')),
    reason text,
    previous_status text not null,
    new_status text not null,
    created_at timestamptz not null default now()
);

create table if not exists authentication_audit_events (
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
    user_id uuid references users(id) on delete set null,
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
        (outcome = 'succeeded' and failure_category is null)
        or (outcome = 'failed' and failure_category is not null)
    ),
    constraint authentication_audit_events_revocation_presence_check check (
        (event_type = 'token_revocation' and revocation_reason is not null)
        or (event_type <> 'token_revocation' and revocation_reason is null)
    ),
    constraint authentication_audit_events_method_check check (
        (event_type = 'login' and auth_method in ('password', 'google'))
        or (event_type = 'logout' and auth_method = 'bearer')
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
            revocation_reason = 'logout'
            and auth_method = 'bearer'
        )
        or (
            revocation_reason = 'google_unlinked'
            and auth_method = 'password'
        )
        or (
            revocation_reason in ('password_set', 'password_removed')
            and auth_method = 'google'
        )
        or (
            revocation_reason = 'password_reset'
            and auth_method = 'recovery'
        )
        or (
            revocation_reason = 'account_deleted'
            and auth_method in ('password', 'google')
        )
    )
);
alter table public.authentication_audit_events owner to current_user;

create table if not exists job_runs (
    id uuid primary key default gen_random_uuid(),
    job_name text not null check (length(job_name) between 1 and 120),
    status text not null check (status in ('running', 'succeeded', 'failed')),
    started_at timestamptz not null,
    finished_at timestamptz,
    duration_ms integer check (duration_ms is null or duration_ms >= 0),
    processed_count integer check (processed_count is null or processed_count >= 0),
    scanned_count integer check (scanned_count is null or scanned_count >= 0),
    reconciled_count integer check (reconciled_count is null or reconciled_count >= 0),
    skipped_count integer check (skipped_count is null or skipped_count >= 0),
    failed_count integer check (failed_count is null or failed_count >= 0),
    batch_count integer check (batch_count is null or batch_count >= 0),
    reached_max_batches boolean,
    error_type text check (error_type is null or length(error_type) <= 120),
    error_message text check (error_message is null or length(error_message) <= 500),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (
        (status = 'running' and finished_at is null)
        or (status in ('succeeded', 'failed') and finished_at is not null)
    )
);

create table if not exists push_delivery_attempts (
    id uuid primary key default gen_random_uuid(),
    notification_id uuid not null references notifications(id) on delete cascade,
    push_token_id uuid references push_tokens(id) on delete set null,
    token_hash text not null,
    title text not null,
    body text not null,
    push_data jsonb,
    status text not null default 'processing'
        check (status in ('processing', 'delivered', 'failed_retryable', 'failed_permanent', 'abandoned')),
    attempt_count integer not null default 1 check (attempt_count >= 0 and attempt_count <= 20),
    max_attempts integer not null default 5 check (max_attempts >= 1 and max_attempts <= 20),
    lease_id uuid not null default gen_random_uuid(),
    lease_expires_at timestamptz not null default now() + interval '300 seconds',
    last_error_type text check (last_error_type is null or length(last_error_type) <= 120),
    last_error_message text check (last_error_message is null or length(last_error_message) <= 500),
    last_http_status integer,
    next_retry_at timestamptz,
    processing_started_at timestamptz not null default now(),
    last_attempted_at timestamptz,
    delivered_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check ((status = 'delivered' and delivered_at is not null) or (status != 'delivered'))
);

create table if not exists api_request_metrics (
    id uuid primary key default gen_random_uuid(),
    recorded_at timestamptz not null default now(),
    method text not null check (method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD')),
    normalized_path text not null check (length(normalized_path) between 1 and 240),
    status_code integer not null check (status_code between 100 and 599),
    duration_ms integer not null check (duration_ms >= 0),
    is_error boolean not null,
    created_at timestamptz not null default now()
);

create table if not exists content_reports (
    id uuid primary key default gen_random_uuid(),
    reporter_user_id uuid references users(id) on delete set null,
    target_type text not null check (target_type in ('game', 'user')),
    target_id uuid not null,
    reason text not null check (reason in ('abuse', 'harassment', 'hate', 'spam', 'impersonation', 'inappropriate', 'other')),
    description text check (description is null or char_length(description) <= 500),
    status text not null default 'open' check (status in ('open', 'in_review', 'resolved', 'rejected')),
    admin_note text check (admin_note is null or char_length(admin_note) <= 1000),
    reviewed_at timestamptz,
    reviewed_by uuid references users(id) on delete set null,
    created_at timestamptz not null default now()
);

create table if not exists user_blocks (
    blocker_user_id uuid not null references users(id) on delete cascade,
    blocked_user_id uuid not null references users(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (blocker_user_id, blocked_user_id),
    check (blocker_user_id <> blocked_user_id)
);

create table if not exists share_events (
    id uuid primary key default gen_random_uuid(),
    recorded_at timestamptz not null default now(),
    event_name text not null check (event_name in ('share_action', 'link_open')),
    entity_type text not null check (entity_type in ('game', 'field')),
    platform text not null check (platform in ('web', 'android', 'ios')),
    mechanism text check (mechanism is null or mechanism in ('native_share', 'copy_link')),
    outcome text not null check (
        outcome in (
            'shared',
            'copied',
            'cancelled',
            'unavailable',
            'failed',
            'valid',
            'invalid',
            'not_found',
            'deferred_for_auth'
        )
    ),
    error_category text check (
        error_category is null
        or error_category in (
            'invalid_resource',
            'unsupported_platform',
            'share_unavailable',
            'share_failed',
            'clipboard_failed',
            'malformed_link',
            'unsupported_link',
            'resource_not_found',
            'resolution_failed'
        )
    ),
    created_at timestamptz not null default now(),
    check (
        (
            event_name = 'share_action'
            and mechanism is not null
            and outcome in ('shared', 'copied', 'cancelled', 'unavailable', 'failed')
        )
        or (
            event_name = 'link_open'
            and mechanism is null
            and outcome in ('valid', 'invalid', 'not_found', 'deferred_for_auth')
        )
    )
);

create index if not exists idx_users_status on users(status);
create index if not exists idx_users_last_login on users(last_login);
alter table push_tokens enable row level security;
alter table user_moderation_audit enable row level security;
alter table authentication_audit_events enable row level security;
alter table job_runs enable row level security;
alter table push_delivery_attempts enable row level security;
alter table api_request_metrics enable row level security;
alter table share_events enable row level security;

drop policy if exists push_tokens_select_own on push_tokens;
create policy push_tokens_select_own
    on push_tokens for select
    using (auth.uid() = user_id);

drop policy if exists push_tokens_insert_own on push_tokens;
create policy push_tokens_insert_own
    on push_tokens for insert
    with check (auth.uid() = user_id);

drop policy if exists push_tokens_update_own on push_tokens;
create policy push_tokens_update_own
    on push_tokens for update
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

drop policy if exists push_tokens_delete_own on push_tokens;
create policy push_tokens_delete_own
    on push_tokens for delete
    using (auth.uid() = user_id);

grant select, insert on public.user_moderation_audit to service_role;
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
-- The schema installer is the trusted table/RPC owner. SELECT and INSERT are
-- needed by the append-only record RPC, DELETE by the bounded retention RPC,
-- and UPDATE(user_id) is limited to PostgreSQL's ON DELETE SET NULL
-- referential action and satisfies SELECT ... FOR UPDATE row locking.
grant select, insert, delete
    on table public.authentication_audit_events to current_user;
grant update (user_id)
    on table public.authentication_audit_events to current_user;
grant select on table public.authentication_audit_events to service_role;
grant select, insert, update on public.job_runs to service_role;
grant select, insert, update on public.push_delivery_attempts to service_role;
grant select, insert, delete on public.api_request_metrics to service_role;
grant select, insert, delete on public.share_events to service_role;
grant select, insert, update on public.users to service_role;
grant select, insert, update, delete on public.user_identities to service_role;
grant select, insert, update on public.content_reports to service_role;
grant select, insert, delete on public.user_blocks to service_role;

create or replace function public.delete_user_account(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_game record;
    v_new_count integer;
    v_new_status text;
    v_reconciled integer := 0;
begin
    -- 1. Revoke all sessions (set tokens_valid_after to now)
    update users
    set tokens_valid_after = now()
    where id = p_user_id;

    if not found then
        return jsonb_build_object('error', 'user_not_found');
    end if;

    -- 2. Reconcile game counters for active games
    for v_game in
        select g.id, g.players_present, g.max_players, g.status
        from games g
        join game_players gp on gp.game_id = g.id
        where gp.user_id = p_user_id
          and g.status in ('open', 'full')
    loop
        v_new_count := greatest(0, v_game.players_present - 1);
        v_new_status := case
            when v_new_count < v_game.max_players then 'open'
            else v_game.status
        end;

        update games
        set players_present = v_new_count,
            status = v_new_status
        where id = v_game.id;

        v_reconciled := v_reconciled + 1;
    end loop;

    -- 3. Delete the user row (CASCADE handles dependent rows)
    delete from users where id = p_user_id;

    return jsonb_build_object(
        'deleted', true,
        'games_reconciled', v_reconciled
    );
end;
$$;

revoke all on function public.delete_user_account(uuid)
from public, anon, authenticated;
grant execute on function public.delete_user_account(uuid) to service_role;

alter table user_identities enable row level security;
alter table content_reports enable row level security;
alter table user_blocks enable row level security;

create index if not exists idx_user_moderation_audit_target_user_id on user_moderation_audit(target_user_id);
create index if not exists idx_user_moderation_audit_created_at on user_moderation_audit(created_at desc);
create index if not exists idx_authentication_audit_events_occurred_at
    on authentication_audit_events(occurred_at desc);
create index if not exists idx_authentication_audit_events_type_outcome_occurred_at
    on authentication_audit_events(event_type, outcome, occurred_at desc);
create index if not exists idx_authentication_audit_events_user_occurred_at
    on authentication_audit_events(user_id, occurred_at desc)
    where user_id is not null;
create index if not exists idx_job_runs_job_name_started_at on job_runs(job_name, started_at desc);
create index if not exists idx_job_runs_status_started_at on job_runs(status, started_at desc);
create index if not exists idx_job_runs_started_at on job_runs(started_at desc);
create index if not exists idx_api_request_metrics_recorded_at on api_request_metrics(recorded_at desc);
create index if not exists idx_api_request_metrics_error_recorded_at on api_request_metrics(is_error, recorded_at desc);
create index if not exists idx_api_request_metrics_path_recorded_at on api_request_metrics(normalized_path, recorded_at desc);
create index if not exists idx_share_events_recorded_at on share_events(recorded_at desc);
create index if not exists idx_share_events_event_recorded_at on share_events(event_name, recorded_at desc);
create index if not exists idx_share_events_entity_recorded_at on share_events(entity_type, recorded_at desc);
create index if not exists idx_fields_added_by on fields(added_by);
create index if not exists idx_fields_public_listing_spatial on fields(verified, approval_status, status, lat, lng);
create index if not exists idx_fields_approval_status on fields(approval_status);
create index if not exists idx_fields_removed_at on fields(removed_at);
create index if not exists idx_fields_public_active_spatial
    on fields(lat, lng)
    where removed_at is null
      and verified = true
      and approval_status = 'approved'
      and status = 'open';
create index if not exists idx_games_field_id on games(field_id);
create index if not exists idx_games_field_id_status on games(field_id, status);
create index if not exists idx_games_status on games(status);
create index if not exists idx_games_expiry_reconciliation
    on games(expires_at, id)
    where status in ('open', 'full')
      and expires_at is not null;
create index if not exists idx_games_created_by on games(created_by);
create index if not exists idx_games_scheduled_at on games(scheduled_at);
create index if not exists idx_games_scheduled_reminder_processed_at on games(scheduled_reminder_processed_at);
create unique index if not exists idx_games_unique_scheduled_slot
    on games(field_id, sport_type, scheduled_at)
    where scheduled_at is not null and status in ('open', 'full');
create index if not exists idx_game_players_game_id on game_players(game_id);
create index if not exists idx_game_players_user_id on game_players(user_id);

-- GET /fields map payload: one request for games and participant identities,
-- with expired-game reconciliation in the same database transaction.
create or replace function public.get_field_game_payloads(p_field_ids uuid[])
returns table(payload jsonb)
language plpgsql
security invoker
set search_path = public
as $$
begin
    update public.games
       set status = 'finished'
     where field_id = any(p_field_ids)
       and status in ('open', 'full')
       and expires_at is not null
       and expires_at <= now();

    return query
    select to_jsonb(g) || jsonb_build_object(
        'participants',
        coalesce(
            (
                select jsonb_agg(
                    jsonb_build_object(
                        'user_id', gp.user_id,
                        'username', u.username,
                        'name', coalesce(u.username, u.name, 'Unknown player')
                    )
                    order by gp.joined_at, gp.id
                )
                  from public.game_players gp
                  left join public.users u on u.id = gp.user_id
                 where gp.game_id = g.id
            ),
            '[]'::jsonb
        )
    )
      from public.games g
     where g.field_id = any(p_field_ids)
       and g.status in ('open', 'full');
end;
$$;

revoke all on function public.get_field_game_payloads(uuid[]) from public;
revoke all on function public.get_field_game_payloads(uuid[]) from anon;
revoke all on function public.get_field_game_payloads(uuid[]) from authenticated;
grant execute on function public.get_field_game_payloads(uuid[]) to service_role;
create index if not exists idx_field_reports_field_id on field_reports(field_id);
create index if not exists idx_field_reports_user_id on field_reports(user_id);
create index if not exists idx_field_reports_status on field_reports(status);
create index if not exists idx_field_reports_created_at on field_reports(created_at);
create index if not exists idx_field_reports_field_id_status on field_reports(field_id, status);
create index if not exists idx_notification_preferences_user_id on notification_preferences(user_id);
create index if not exists idx_notification_preferences_field_id on notification_preferences(field_id);
create index if not exists idx_notification_preferences_user_id_type on notification_preferences(user_id, notification_type);
grant usage on schema public to service_role;
grant select, insert, update, delete on table public.notification_preferences to service_role;
create index if not exists idx_notifications_user_id on notifications(user_id);
create index if not exists idx_notifications_user_id_created_at on notifications(user_id, created_at desc);
create index if not exists idx_notifications_user_unread on notifications(user_id) where read_at is null;
create index if not exists idx_notifications_type_game_id on notifications(type, game_id);
create index if not exists idx_notifications_read_at on notifications(read_at);
create index if not exists idx_notifications_created_at on notifications(created_at);
create index if not exists idx_notifications_game_id on notifications(game_id);
create index if not exists idx_notifications_field_id on notifications(field_id);
create index if not exists idx_notifications_data_type on notifications((data ->> 'type'));
create unique index if not exists idx_notifications_user_type_game_unique
    on notifications(user_id, type, game_id)
    where game_id is not null and type in ('game_created', 'game_closed', 'scheduled_game_reminder');
create unique index if not exists idx_notifications_user_game_extended_end_time_unique
    on notifications(user_id, type, game_id, (data ->> 'new_end_time'))
    where game_id is not null and type = 'game_extended' and data ? 'new_end_time';
create index if not exists idx_push_tokens_user_id on push_tokens(user_id);
create index if not exists idx_push_tokens_token on push_tokens(token);
create index if not exists idx_push_tokens_user_id_token on push_tokens(user_id, token);
create index if not exists idx_push_tokens_user_id_installation_id
    on push_tokens(user_id, installation_id);

create index if not exists idx_user_identities_user_id on user_identities(user_id);
create index if not exists idx_user_identities_lookup on user_identities(provider, provider_subject);
create index if not exists idx_content_reports_status_created on content_reports(status, created_at desc);
create index if not exists idx_content_reports_target on content_reports(target_type, target_id);
create index if not exists idx_user_blocks_blocker on user_blocks(blocker_user_id);

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

-- Authentication audit retention is fixed at 180 days by the scheduled job.
-- service_role can delete expired rows only through this bounded RPC.
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

create or replace function public.cleanup_api_request_metrics(retention_days integer default 14)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    deleted_count integer;
begin
    if retention_days is null or retention_days < 1 or retention_days > 365 then
        raise exception 'retention_days must be between 1 and 365';
    end if;

    delete from public.api_request_metrics
    where recorded_at < now() - make_interval(days => retention_days);

    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$;

grant execute on function public.cleanup_api_request_metrics(integer) to service_role;

create or replace function public.get_api_response_time_metrics(
    window_start timestamptz,
    window_end timestamptz
)
returns table (
    sample_count bigint,
    average_ms numeric,
    p50_ms numeric,
    p95_ms numeric,
    max_ms numeric
)
language sql
stable
security definer
set search_path = public
as $$
    select
        count(*)::bigint as sample_count,
        coalesce(round(avg(duration_ms)::numeric, 2), 0.0)::numeric as average_ms,
        coalesce(
            round((percentile_cont(0.50) within group (order by duration_ms))::numeric, 2),
            0.0
        )::numeric as p50_ms,
        coalesce(
            round((percentile_cont(0.95) within group (order by duration_ms))::numeric, 2),
            0.0
        )::numeric as p95_ms,
        coalesce(max(duration_ms), 0)::numeric as max_ms
    from public.api_request_metrics
    where recorded_at >= window_start
      and recorded_at < window_end;
$$;

grant execute on function public.get_api_response_time_metrics(timestamptz, timestamptz) to service_role;

create index if not exists idx_pda_created_at on push_delivery_attempts(created_at);

create or replace function public.get_push_delivery_metrics(
    window_start timestamptz,
    window_end timestamptz
)
returns table (
    attempted_count bigint,
    accepted_count bigint,
    failed_count bigint,
    invalid_token_count bigint
)
language sql
stable
security definer
set search_path = public
as $$
    select
        count(*) filter (
            where status in ('delivered', 'failed_permanent', 'abandoned')
        )::bigint as attempted_count,
        count(*) filter (
            where status = 'delivered'
        )::bigint as accepted_count,
        count(*) filter (
            where (status = 'failed_permanent' and (last_error_type is null or last_error_type not in ('INVALID_TOKEN', 'TOKEN_INVALIDATED')))
               or status = 'abandoned'
        )::bigint as failed_count,
        count(*) filter (
            where status = 'failed_permanent' and last_error_type in ('INVALID_TOKEN', 'TOKEN_INVALIDATED')
        )::bigint as invalid_token_count
    from public.push_delivery_attempts
    where created_at >= window_start
      and created_at < window_end;
$$;

grant execute on function public.get_push_delivery_metrics(timestamptz, timestamptz) to service_role;

create or replace function public.get_share_event_metrics(
    window_start timestamptz,
    window_end timestamptz
)
returns table (
    event_name text,
    entity_type text,
    platform text,
    mechanism text,
    outcome text,
    error_category text,
    event_count bigint
)
language sql
stable
security definer
set search_path = public
as $$
    select
        share_events.event_name,
        share_events.entity_type,
        share_events.platform,
        share_events.mechanism,
        share_events.outcome,
        share_events.error_category,
        count(*)::bigint as event_count
    from public.share_events
    where recorded_at >= window_start
      and recorded_at < window_end
    group by
        share_events.event_name,
        share_events.entity_type,
        share_events.platform,
        share_events.mechanism,
        share_events.outcome,
        share_events.error_category
    order by
        share_events.event_name,
        share_events.entity_type,
        share_events.platform,
        share_events.mechanism,
        share_events.outcome,
        share_events.error_category;
$$;

grant execute on function public.get_share_event_metrics(timestamptz, timestamptz) to service_role;

create or replace function public.cleanup_share_events(retention_days integer default 90)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    deleted_count integer;
begin
    if retention_days is null or retention_days < 1 or retention_days > 365 then
        raise exception 'retention_days must be between 1 and 365';
    end if;

    delete from public.share_events
    where recorded_at < now() - make_interval(days => retention_days);

    get diagnostics deleted_count = row_count;
    return deleted_count;
end;
$$;

grant execute on function public.cleanup_share_events(integer) to service_role;

-- ISSUE-1031 item 3: security-request attribution database foundation.
-- Keep this block equivalent to migrations/security_request_attribution.sql.
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
