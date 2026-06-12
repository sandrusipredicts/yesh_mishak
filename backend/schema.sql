create extension if not exists pgcrypto;

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    google_sub text unique,
    email text unique,
    name text not null,
    picture text,
    phone_number text,
    created_at timestamptz not null default now(),
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
    status text not null default 'pending' check (status in ('pending', 'approved', 'rejected', 'renovation')),
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
    started_at timestamptz not null default now(),
    expires_at timestamptz,
    check (min_age is null or max_age is null or min_age <= max_age)
);

create table if not exists game_players (
    id uuid primary key default gen_random_uuid(),
    game_id uuid not null references games(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    joined_at timestamptz not null default now(),
    unique (game_id, user_id)
);

create table if not exists notification_preferences (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    notification_type text not null check (notification_type in ('radius', 'city', 'specific_field')),
    radius_km numeric(6, 2),
    city text,
    field_id uuid references fields(id) on delete cascade,
    created_at timestamptz not null default now()
);

create index if not exists idx_fields_added_by on fields(added_by);
create index if not exists idx_games_field_id on games(field_id);
create index if not exists idx_games_created_by on games(created_by);
create index if not exists idx_game_players_game_id on game_players(game_id);
create index if not exists idx_game_players_user_id on game_players(user_id);
create index if not exists idx_notification_preferences_user_id on notification_preferences(user_id);
create index if not exists idx_notification_preferences_field_id on notification_preferences(field_id);
