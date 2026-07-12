-- E01-01: Password reset backend foundation.
-- SECURITY DEFINER functions in this migration are owned by the migration role.
-- Production migrations must run as the role that owns public.users. Runtime
-- execution is restricted to service_role; anon/authenticated receive no access.

-- Remove signatures from the pre-review draft if it was applied to a sandbox.
drop function if exists public.consume_password_reset_token(text, text, timestamptz);
drop function if exists public.check_password_reset_rate_limit(text, text, timestamptz);

create table if not exists public.password_reset_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.users(id) on delete cascade,
    token_hash text not null unique,
    status text not null check (status in (
        'pending_delivery', 'active', 'consumed', 'invalidated', 'delivery_failed'
    )),
    delivery_status text not null check (delivery_status in ('pending', 'sent', 'failed')),
    created_at timestamptz not null default pg_catalog.now(),
    expires_at timestamptz not null,
    consumed_at timestamptz,
    invalidated_at timestamptz
);

alter table public.password_reset_tokens enable row level security;
revoke all on table public.password_reset_tokens from public, anon, authenticated;
grant select, insert, update, delete on table public.password_reset_tokens to service_role;

create index if not exists idx_password_reset_tokens_hash on public.password_reset_tokens(token_hash);
create index if not exists idx_password_reset_tokens_user_id on public.password_reset_tokens(user_id);
create index if not exists idx_password_reset_tokens_active_user
    on public.password_reset_tokens(user_id, expires_at)
    where status in ('pending_delivery', 'active') and consumed_at is null and invalidated_at is null;
create index if not exists idx_password_reset_tokens_expires_at on public.password_reset_tokens(expires_at);

create table if not exists public.password_reset_rate_limits (
    scope text not null,
    key_hash text not null,
    window_start timestamptz not null,
    window_seconds integer not null,
    count integer not null default 0,
    created_at timestamptz not null default pg_catalog.now(),
    updated_at timestamptz not null default pg_catalog.now(),
    primary key (scope, key_hash, window_start)
);

create table if not exists public.password_reset_email_cooldowns (
    key_hash text primary key,
    last_attempt_at timestamptz not null,
    next_allowed_at timestamptz not null
);

alter table public.password_reset_rate_limits enable row level security;
alter table public.password_reset_email_cooldowns enable row level security;
revoke all on table public.password_reset_rate_limits from public, anon, authenticated;
revoke all on table public.password_reset_email_cooldowns from public, anon, authenticated;
grant select, insert, update, delete on table public.password_reset_rate_limits to service_role;
grant select, insert, update, delete on table public.password_reset_email_cooldowns to service_role;
grant usage on schema public to service_role;
create index if not exists idx_password_reset_rate_limits_cleanup on public.password_reset_rate_limits(updated_at);
create index if not exists idx_password_reset_email_cooldowns_cleanup on public.password_reset_email_cooldowns(next_allowed_at);

create or replace function public.create_password_reset_token(
    p_user_id uuid, p_token_hash text, p_ttl_minutes integer
) returns table (id uuid)
language plpgsql security definer set search_path = pg_catalog
as $$
begin
    if p_ttl_minutes < 1 or p_ttl_minutes > 1440 then
        raise exception 'invalid password reset token lifetime';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_user_id::text, 0));
    update public.password_reset_tokens
       set status = 'invalidated', invalidated_at = pg_catalog.now()
     where user_id = p_user_id and status in ('pending_delivery', 'active')
       and consumed_at is null and invalidated_at is null;
    return query
    insert into public.password_reset_tokens (user_id, token_hash, status, delivery_status, expires_at)
    values (p_user_id, p_token_hash, 'pending_delivery', 'pending',
            pg_catalog.now() + pg_catalog.make_interval(mins => p_ttl_minutes))
    returning password_reset_tokens.id;
end;
$$;

create or replace function public.finalize_password_reset_delivery(
    p_token_hash text, p_accepted boolean
) returns table (result text, activated boolean)
language plpgsql security definer set search_path = pg_catalog
as $$
declare v_id uuid;
begin
    select id into v_id from public.password_reset_tokens
     where token_hash = p_token_hash for update;
    if not found then return query select 'missing'::text, false; return; end if;

    if p_accepted then
        update public.password_reset_tokens
           set status = 'active', delivery_status = 'sent'
         where id = v_id and status = 'pending_delivery' and delivery_status = 'pending'
           and invalidated_at is null and consumed_at is null and expires_at > pg_catalog.now();
        if found then return query select 'active'::text, true; return; end if;
    else
        update public.password_reset_tokens
           set status = 'delivery_failed', delivery_status = 'failed', invalidated_at = pg_catalog.now()
         where id = v_id and status = 'pending_delivery' and delivery_status = 'pending'
           and invalidated_at is null and consumed_at is null;
        if found then return query select 'delivery_failed'::text, false; return; end if;
    end if;
    return query select 'unchanged'::text, false;
end;
$$;

create or replace function public.precheck_password_reset_token(p_token_hash text)
returns table (result text)
language plpgsql security definer stable set search_path = pg_catalog
as $$
declare v_token public.password_reset_tokens%rowtype;
begin
    select * into v_token from public.password_reset_tokens where token_hash = p_token_hash;
    if not found then return query select 'invalid'::text; return; end if;
    if v_token.status = 'consumed' or v_token.consumed_at is not null then return query select 'consumed'::text; return; end if;
    if v_token.status in ('invalidated', 'delivery_failed') or v_token.invalidated_at is not null then return query select 'invalid'::text; return; end if;
    if v_token.expires_at <= pg_catalog.now() then return query select 'expired'::text; return; end if;
    if v_token.status <> 'active' then return query select 'invalid'::text; return; end if;
    return query select 'usable'::text;
end;
$$;

create or replace function public.consume_password_reset_token(p_token_hash text, p_password_hash text)
returns table (result text, user_id uuid)
language plpgsql security definer set search_path = pg_catalog
as $$
declare v_token public.password_reset_tokens%rowtype; v_now timestamptz := pg_catalog.now();
begin
    select * into v_token from public.password_reset_tokens where token_hash = p_token_hash for update;
    if not found then return query select 'invalid'::text, null::uuid; return; end if;
    if v_token.status = 'consumed' or v_token.consumed_at is not null then return query select 'consumed'::text, v_token.user_id; return; end if;
    if v_token.status in ('invalidated', 'delivery_failed') or v_token.invalidated_at is not null then return query select 'invalid'::text, v_token.user_id; return; end if;
    if v_token.expires_at <= v_now then return query select 'expired'::text, v_token.user_id; return; end if;
    if v_token.status <> 'active' then return query select 'invalid'::text, v_token.user_id; return; end if;

    update public.users set password_hash = p_password_hash, tokens_valid_after = v_now where id = v_token.user_id;
    if not found then raise exception 'password reset user missing'; end if;
    update public.password_reset_tokens set status = 'consumed', consumed_at = v_now where id = v_token.id;
    update public.password_reset_tokens as reset_token set status = 'invalidated', invalidated_at = v_now
     where reset_token.user_id = v_token.user_id and reset_token.id <> v_token.id
       and reset_token.status in ('pending_delivery', 'active')
       and reset_token.consumed_at is null and reset_token.invalidated_at is null;
    return query select 'success'::text, v_token.user_id;
end;
$$;

create or replace function public.check_password_reset_request_rate_limit(p_email_key text, p_ip_key text)
returns jsonb language plpgsql security definer set search_path = pg_catalog
as $$
declare v_now timestamptz := pg_catalog.now(); v_next timestamptz; v_item record; v_start timestamptz; v_count integer;
begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('reset-email:' || p_email_key, 0));
    select next_allowed_at into v_next from public.password_reset_email_cooldowns where key_hash = p_email_key for update;
    if found and v_next > v_now then
        return pg_catalog.jsonb_build_object('allowed', false, 'scope', 'email_cooldown',
            'retry_after_seconds', greatest(1, pg_catalog.ceil(extract(epoch from (v_next - v_now)))::integer));
    end if;
    insert into public.password_reset_email_cooldowns(key_hash, last_attempt_at, next_allowed_at)
    values (p_email_key, v_now, v_now + interval '5 minutes')
    on conflict (key_hash) do update set last_attempt_at = excluded.last_attempt_at, next_allowed_at = excluded.next_allowed_at;

    for v_item in select * from (values ('ip_short', p_ip_key, 600, 10), ('email_hour', p_email_key, 3600, 5), ('email_day', p_email_key, 86400, 10)) v(scope,key_hash,seconds,request_limit)
    loop
        v_start := pg_catalog.to_timestamp(pg_catalog.floor(extract(epoch from v_now) / v_item.seconds) * v_item.seconds);
        insert into public.password_reset_rate_limits(scope,key_hash,window_start,window_seconds,count,updated_at)
        values(v_item.scope,v_item.key_hash,v_start,v_item.seconds,1,v_now)
        on conflict(scope,key_hash,window_start) do update set count=password_reset_rate_limits.count+1,updated_at=v_now
        returning count into v_count;
        if v_count > v_item.request_limit then
            return pg_catalog.jsonb_build_object('allowed',false,'scope',v_item.scope,'retry_after_seconds',
                greatest(1,pg_catalog.ceil(extract(epoch from (v_start+pg_catalog.make_interval(secs=>v_item.seconds)-v_now)))::integer));
        end if;
    end loop;
    return pg_catalog.jsonb_build_object('allowed',true);
end;
$$;

create or replace function public.check_password_reset_confirm_rate_limit(p_token_key text, p_ip_key text)
returns jsonb language plpgsql security definer set search_path = pg_catalog
as $$
declare v_now timestamptz := pg_catalog.now(); v_item record; v_start timestamptz; v_count integer;
begin
    for v_item in select * from (values ('confirm_ip',p_ip_key,600,20),('confirm_token',p_token_key,600,5)) v(scope,key_hash,seconds,request_limit)
    loop
        v_start := pg_catalog.to_timestamp(pg_catalog.floor(extract(epoch from v_now)/v_item.seconds)*v_item.seconds);
        insert into public.password_reset_rate_limits(scope,key_hash,window_start,window_seconds,count,updated_at)
        values(v_item.scope,v_item.key_hash,v_start,v_item.seconds,1,v_now)
        on conflict(scope,key_hash,window_start) do update set count=password_reset_rate_limits.count+1,updated_at=v_now
        returning count into v_count;
        if v_count > v_item.request_limit then
            return pg_catalog.jsonb_build_object('allowed',false,'scope',v_item.scope,'retry_after_seconds',
                greatest(1,pg_catalog.ceil(extract(epoch from(v_start+pg_catalog.make_interval(secs=>v_item.seconds)-v_now)))::integer));
        end if;
    end loop;
    return pg_catalog.jsonb_build_object('allowed',true);
end;
$$;

revoke all on function public.create_password_reset_token(uuid,text,integer) from public,anon,authenticated;
revoke all on function public.finalize_password_reset_delivery(text,boolean) from public,anon,authenticated;
revoke all on function public.precheck_password_reset_token(text) from public,anon,authenticated;
revoke all on function public.consume_password_reset_token(text,text) from public,anon,authenticated;
revoke all on function public.check_password_reset_request_rate_limit(text,text) from public,anon,authenticated;
revoke all on function public.check_password_reset_confirm_rate_limit(text,text) from public,anon,authenticated;
grant execute on function public.create_password_reset_token(uuid,text,integer) to service_role;
grant execute on function public.finalize_password_reset_delivery(text,boolean) to service_role;
grant execute on function public.precheck_password_reset_token(text) to service_role;
grant execute on function public.consume_password_reset_token(text,text) to service_role;
grant execute on function public.check_password_reset_request_rate_limit(text,text) to service_role;
grant execute on function public.check_password_reset_confirm_rate_limit(text,text) to service_role;
