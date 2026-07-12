-- E01-01: Password reset backend foundation.
-- Reset tokens are opaque to clients. The raw token is never stored; token_hash
-- contains HMAC-SHA256(PASSWORD_RESET_TOKEN_SECRET, raw_token).

create table if not exists password_reset_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    token_hash text not null unique,
    status text not null check (status in (
        'pending_delivery',
        'active',
        'consumed',
        'invalidated',
        'delivery_failed'
    )),
    delivery_status text not null check (delivery_status in (
        'pending',
        'sent',
        'failed'
    )),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    consumed_at timestamptz,
    invalidated_at timestamptz
);

alter table password_reset_tokens enable row level security;
revoke all on table password_reset_tokens from anon, authenticated;
grant select, insert, update, delete on table password_reset_tokens to service_role;

create index if not exists idx_password_reset_tokens_hash
    on password_reset_tokens(token_hash);
create index if not exists idx_password_reset_tokens_user_id
    on password_reset_tokens(user_id);
create index if not exists idx_password_reset_tokens_active_user
    on password_reset_tokens(user_id, expires_at)
    where status in ('pending_delivery', 'active')
      and consumed_at is null
      and invalidated_at is null;
create index if not exists idx_password_reset_tokens_expires_at
    on password_reset_tokens(expires_at);

create table if not exists password_reset_rate_limits (
    scope text not null,
    key_hash text not null,
    window_start timestamptz not null,
    window_seconds integer not null,
    count integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (scope, key_hash, window_start)
);

alter table password_reset_rate_limits enable row level security;
revoke all on table password_reset_rate_limits from anon, authenticated;
grant select, insert, update, delete on table password_reset_rate_limits to service_role;

create index if not exists idx_password_reset_rate_limits_cleanup
    on password_reset_rate_limits(updated_at);

create or replace function create_password_reset_token(
    p_user_id uuid,
    p_token_hash text,
    p_expires_at timestamptz
) returns table (id uuid)
language plpgsql
security definer
set search_path = public
as $$
begin
    perform pg_advisory_xact_lock(hashtextextended(p_user_id::text, 0));

    update password_reset_tokens
    set status = 'invalidated',
        invalidated_at = now()
    where user_id = p_user_id
      and status in ('pending_delivery', 'active')
      and consumed_at is null
      and invalidated_at is null;

    return query
    insert into password_reset_tokens (
        user_id,
        token_hash,
        status,
        delivery_status,
        expires_at
    )
    values (
        p_user_id,
        p_token_hash,
        'pending_delivery',
        'pending',
        p_expires_at
    )
    returning password_reset_tokens.id;
end;
$$;

create or replace function consume_password_reset_token(
    p_token_hash text,
    p_password_hash text,
    p_tokens_valid_after timestamptz
) returns table (result text, user_id uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_token password_reset_tokens%rowtype;
begin
    select *
    into v_token
    from password_reset_tokens
    where token_hash = p_token_hash
    for update;

    if not found then
        return query select 'invalid'::text, null::uuid;
        return;
    end if;

    if v_token.status = 'consumed' or v_token.consumed_at is not null then
        return query select 'consumed'::text, v_token.user_id;
        return;
    end if;

    if v_token.status in ('invalidated', 'delivery_failed')
       or v_token.invalidated_at is not null then
        return query select 'invalid'::text, v_token.user_id;
        return;
    end if;

    if v_token.status <> 'active' then
        return query select 'invalid'::text, v_token.user_id;
        return;
    end if;

    if v_token.expires_at <= now() then
        return query select 'expired'::text, v_token.user_id;
        return;
    end if;

    update users
    set password_hash = p_password_hash,
        tokens_valid_after = p_tokens_valid_after
    where users.id = v_token.user_id;

    update password_reset_tokens
    set status = 'consumed',
        consumed_at = p_tokens_valid_after
    where password_reset_tokens.id = v_token.id;

    update password_reset_tokens
    set status = 'invalidated',
        invalidated_at = p_tokens_valid_after
    where password_reset_tokens.user_id = v_token.user_id
      and password_reset_tokens.id <> v_token.id
      and password_reset_tokens.status in ('pending_delivery', 'active')
      and password_reset_tokens.consumed_at is null
      and password_reset_tokens.invalidated_at is null;

    return query select 'success'::text, v_token.user_id;
end;
$$;

create or replace function check_password_reset_rate_limit(
    p_email_key text,
    p_ip_key text,
    p_now timestamptz default now()
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_scope text;
    v_key text;
    v_window_seconds integer;
    v_limit integer;
    v_window_start timestamptz;
    v_count integer;
begin
    for v_scope, v_key, v_window_seconds, v_limit in
        select *
        from (values
            ('ip_short', p_ip_key, 600, 10),
            ('email_cooldown', p_email_key, 300, 1),
            ('email_hour', p_email_key, 3600, 5),
            ('email_day', p_email_key, 86400, 10)
        ) as limits(scope, key_hash, window_seconds, request_limit)
    loop
        v_window_start := to_timestamp(
            floor(extract(epoch from p_now) / v_window_seconds) * v_window_seconds
        );

        insert into password_reset_rate_limits (
            scope,
            key_hash,
            window_start,
            window_seconds,
            count,
            updated_at
        )
        values (
            v_scope,
            v_key,
            v_window_start,
            v_window_seconds,
            1,
            p_now
        )
        on conflict (scope, key_hash, window_start)
        do update set
            count = password_reset_rate_limits.count + 1,
            updated_at = p_now
        returning count into v_count;

        if v_count > v_limit then
            return jsonb_build_object(
                'allowed', false,
                'scope', v_scope,
                'retry_after_seconds',
                greatest(
                    1,
                    ceil(extract(epoch from (v_window_start + make_interval(secs => v_window_seconds) - p_now)))::integer
                )
            );
        end if;
    end loop;

    return jsonb_build_object('allowed', true);
end;
$$;

revoke all on function create_password_reset_token(uuid, text, timestamptz) from public, anon, authenticated;
revoke all on function consume_password_reset_token(text, text, timestamptz) from public, anon, authenticated;
revoke all on function check_password_reset_rate_limit(text, text, timestamptz) from public, anon, authenticated;
grant execute on function create_password_reset_token(uuid, text, timestamptz) to service_role;
grant execute on function consume_password_reset_token(text, text, timestamptz) to service_role;
grant execute on function check_password_reset_rate_limit(text, text, timestamptz) to service_role;
