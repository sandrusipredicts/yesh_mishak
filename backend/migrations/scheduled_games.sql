alter table if exists public.games
    add column if not exists scheduled_at timestamptz;

create index if not exists idx_games_scheduled_at
    on public.games(scheduled_at);

create unique index if not exists idx_games_unique_scheduled_slot
    on public.games(field_id, sport_type, scheduled_at)
    where scheduled_at is not null and status in ('open', 'full');
