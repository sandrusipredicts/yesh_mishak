-- E01-02: Email verification for password-based accounts.
-- Existing accounts are grandfathered as verified; new manual registrations
-- explicitly write email_verified=false. Google accounts are written true.
alter table users
    add column if not exists email_verified boolean,
    add column if not exists email_verified_at timestamptz;

update users
set email_verified = true,
    email_verified_at = coalesce(email_verified_at, created_at, now())
where email_verified is null;

alter table users alter column email_verified set default true;
alter table users alter column email_verified set not null;

create table if not exists email_verification_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    token_hash text not null unique,
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    used_at timestamptz
);

alter table email_verification_tokens enable row level security;
revoke all on table email_verification_tokens from public, anon, authenticated;
grant select, insert, update, delete on public.email_verification_tokens to service_role;
create index if not exists idx_email_verification_tokens_user_id on email_verification_tokens(user_id);
create index if not exists idx_email_verification_tokens_expires_at on email_verification_tokens(expires_at);

create or replace function prepare_email_verification_token(
    p_user_id uuid,
    p_token_hash text,
    p_expires_at timestamptz,
    p_cooldown_seconds integer
)
returns text
language plpgsql
security definer
set search_path = public
as $$
begin
    -- Shared across workers/instances and held until the transaction ends.
    perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    if exists (
        select 1 from email_verification_tokens
        where user_id = p_user_id
          and used_at is null
          and created_at > now() - make_interval(secs => greatest(p_cooldown_seconds, 0))
    ) then
        return 'cooldown';
    end if;

    update email_verification_tokens
    set used_at = now()
    where user_id = p_user_id and used_at is null;

    insert into email_verification_tokens (user_id, token_hash, expires_at)
    values (p_user_id, p_token_hash, p_expires_at);
    return 'created';
end;
$$;

revoke all on function prepare_email_verification_token(uuid, text, timestamptz, integer)
from public, anon, authenticated;
grant execute on function prepare_email_verification_token(uuid, text, timestamptz, integer)
to service_role;

create or replace function verify_email_token(p_token_hash text)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
    token_row email_verification_tokens%rowtype;
begin
    select * into token_row
    from email_verification_tokens
    where token_hash = p_token_hash
    for update;

    if not found then return 'invalid'; end if;
    if token_row.used_at is not null then return 'already_used'; end if;
    if token_row.expires_at <= now() then return 'expired'; end if;
    if not exists (select 1 from users where id = token_row.user_id) then return 'invalid'; end if;

    update users
    set email_verified = true, email_verified_at = coalesce(email_verified_at, now())
    where id = token_row.user_id;
    update email_verification_tokens set used_at = now() where id = token_row.id;
    return 'verified';
end;
$$;

revoke all on function verify_email_token(text) from public, anon, authenticated;
grant execute on function verify_email_token(text) to service_role;
