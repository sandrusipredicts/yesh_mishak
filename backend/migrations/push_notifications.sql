create table if not exists push_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    token text not null unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_push_tokens_user_id on push_tokens(user_id);
create index if not exists idx_push_tokens_token on push_tokens(token);
create index if not exists idx_push_tokens_user_id_token on push_tokens(user_id, token);

-- Multi-device support: a push token must be unique per device, never per user.
-- Legacy databases created before this migration may carry a single-column
-- UNIQUE constraint on user_id, which blocks a user from registering more than
-- one browser/device. Drop any such constraint and ensure token is unique.
-- (Idempotent: safe to re-run; only touches single-column UNIQUE constraints,
-- never the primary key or composite constraints.)
do $$
declare
    con record;
begin
    for con in
        select c.conname
        from pg_constraint c
        where c.conrelid = 'push_tokens'::regclass
            and c.contype = 'u'
            and (
                select array_agg(a.attname)
                from unnest(c.conkey) as cols(attnum)
                join pg_attribute a
                    on a.attrelid = c.conrelid and a.attnum = cols.attnum
            ) = array['user_id']
    loop
        execute format('alter table push_tokens drop constraint %I', con.conname);
    end loop;

    if not exists (
        select 1
        from pg_constraint c
        where c.conrelid = 'push_tokens'::regclass
            and c.contype = 'u'
            and (
                select array_agg(a.attname)
                from unnest(c.conkey) as cols(attnum)
                join pg_attribute a
                    on a.attrelid = c.conrelid and a.attnum = cols.attnum
            ) = array['token']
    ) then
        alter table push_tokens add constraint push_tokens_token_key unique (token);
    end if;
end $$;

alter table push_tokens enable row level security;

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
