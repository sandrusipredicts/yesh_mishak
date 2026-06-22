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
    last_active timestamptz
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
    image_url text
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
    check (min_age is null or max_age is null or min_age <= max_age)
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

create index if not exists idx_users_status on users(status);
alter table user_moderation_audit enable row level security;

grant select, insert on public.user_moderation_audit to service_role;
grant select, update on public.users to service_role;

create index if not exists idx_user_moderation_audit_target_user_id on user_moderation_audit(target_user_id);
create index if not exists idx_user_moderation_audit_created_at on user_moderation_audit(created_at desc);
create index if not exists idx_fields_added_by on fields(added_by);
create index if not exists idx_games_field_id on games(field_id);
create index if not exists idx_games_created_by on games(created_by);
create index if not exists idx_games_scheduled_at on games(scheduled_at);
create index if not exists idx_games_scheduled_reminder_processed_at on games(scheduled_reminder_processed_at);
create unique index if not exists idx_games_unique_scheduled_slot
    on games(field_id, sport_type, scheduled_at)
    where scheduled_at is not null and status in ('open', 'full');
create index if not exists idx_game_players_game_id on game_players(game_id);
create index if not exists idx_game_players_user_id on game_players(user_id);
create index if not exists idx_field_reports_field_id on field_reports(field_id);
create index if not exists idx_field_reports_user_id on field_reports(user_id);
create index if not exists idx_field_reports_status on field_reports(status);
create index if not exists idx_field_reports_created_at on field_reports(created_at);
create index if not exists idx_field_reports_field_id_status on field_reports(field_id, status);
create index if not exists idx_notification_preferences_user_id on notification_preferences(user_id);
create index if not exists idx_notification_preferences_field_id on notification_preferences(field_id);
create index if not exists idx_notification_preferences_enabled on notification_preferences(enabled);
grant usage on schema public to service_role;
grant select, insert, update, delete on table public.notification_preferences to service_role;
create index if not exists idx_notifications_user_id on notifications(user_id);
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
