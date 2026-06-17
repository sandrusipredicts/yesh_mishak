create table if not exists push_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    token text not null unique,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_push_tokens_user_id on push_tokens(user_id);
create index if not exists idx_push_tokens_token on push_tokens(token);

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
