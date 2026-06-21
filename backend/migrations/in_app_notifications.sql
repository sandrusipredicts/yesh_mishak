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

do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_name = 'notifications'
            and column_name = 'related_game_id'
    ) and not exists (
        select 1
        from information_schema.columns
        where table_name = 'notifications'
            and column_name = 'game_id'
    ) then
        alter table notifications rename column related_game_id to game_id;
    end if;

    if exists (
        select 1
        from information_schema.columns
        where table_name = 'notifications'
            and column_name = 'related_field_id'
    ) and not exists (
        select 1
        from information_schema.columns
        where table_name = 'notifications'
            and column_name = 'field_id'
    ) then
        alter table notifications rename column related_field_id to field_id;
    end if;
end $$;

alter table notifications add column if not exists game_id uuid references games(id) on delete set null;
alter table notifications add column if not exists field_id uuid references fields(id) on delete set null;
alter table notifications add column if not exists data jsonb;
alter table notifications add column if not exists read_at timestamptz;

do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_name = 'notifications'
            and column_name = 'is_read'
    ) then
        execute 'update notifications set read_at = created_at where read_at is null and is_read = true';
    end if;
end $$;

create index if not exists idx_notifications_user_id on notifications(user_id);
create index if not exists idx_notifications_read_at on notifications(read_at);
create index if not exists idx_notifications_created_at on notifications(created_at);
create index if not exists idx_notifications_game_id on notifications(game_id);
create index if not exists idx_notifications_field_id on notifications(field_id);
create index if not exists idx_notifications_data_type on notifications((data ->> 'type'));
drop index if exists idx_notifications_user_type_game_unique;
create unique index if not exists idx_notifications_user_type_game_unique
    on notifications(user_id, type, game_id)
    where game_id is not null and type in ('game_created', 'game_closed');
create unique index if not exists idx_notifications_user_game_extended_end_time_unique
    on notifications(user_id, type, game_id, (data ->> 'new_end_time'))
    where game_id is not null and type = 'game_extended' and data ? 'new_end_time';
