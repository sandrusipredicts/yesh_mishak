-- E01-05: Fix multi-worker in-process user-cache lag on token revocation.
--
-- Problem this migration closes: every existing write path to
-- users.tokens_valid_after (logout, account linking/unlinking, set/remove
-- password, password reset) computes "now()" independently and then blindly
-- overwrites the column. None of those writes coordinate with each other, so
-- two revocations racing for the same user (e.g. a logout on one device and
-- a password reset on another, landing on different Railway
-- workers/instances) can commit out of order. Because the writes are blind
-- assignments rather than a monotonic max, a revocation that captured its
-- timestamp *later* in wall-clock time can still lose to one that captured
-- an *earlier* timestamp but committed after it, silently moving
-- tokens_valid_after backward and un-revoking a session that should have
-- stayed revoked.
--
-- Fix: every write to tokens_valid_after in this migration uses
-- GREATEST(existing_value, now()) inside a single atomic UPDATE, so the
-- column can never move backward regardless of commit order. This is a
-- redefinition-only migration (`create or replace function`): it does not
-- alter table structure or data, and is idempotent/safe to re-run. It does
-- not modify migrations/account_linking_actions.sql or
-- migrations/password_reset_tokens.sql — those files are left as the
-- original source of the function signatures; this migration must be
-- applied after both.
--
-- Rollback: re-apply the original `create or replace function` bodies from
-- migrations/account_linking_actions.sql and migrations/password_reset_tokens.sql
-- respectively, and `drop function if exists public.revoke_user_tokens(uuid);`.
--
-- This migration has NOT been run against any live database. Applying it
-- requires the same migration role used for the other files in this
-- directory (owner of public.users) and explicit sign-off before running
-- against staging/production.

create or replace function public.revoke_user_tokens(p_user_id uuid)
returns table (result text)
language plpgsql
security definer
set search_path = pg_catalog
as $$
begin
    -- Same advisory lock class (3) as link/unlink/set/remove in
    -- account_linking_actions.sql, so a logout and an account-security
    -- mutation for the same user can never interleave their
    -- tokens_valid_after writes.
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_user_id::text, 3));

    if not exists (select 1 from public.users where id = p_user_id) then
        return query select 'user_not_found'::text;
        return;
    end if;

    update public.users
    set tokens_valid_after = greatest(
        coalesce(tokens_valid_after, to_timestamp(0)),
        pg_catalog.now()
    )
    where id = p_user_id;

    return query select 'revoked'::text;
end;
$$;

revoke all on function public.revoke_user_tokens(uuid) from public, anon, authenticated;
grant execute on function public.revoke_user_tokens(uuid) to service_role;


-- Redefine the E01-04 account-linking mutations so their tokens_valid_after
-- write is monotonic too. Bodies are otherwise unchanged from
-- account_linking_actions.sql.

create or replace function public.link_google_identity(
    p_user_id uuid,
    p_provider_subject text,
    p_email_at_link text
)
returns table (result text)
language plpgsql
security definer
set search_path = pg_catalog
as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_user_id::text, 3));

    if not exists (select 1 from public.users where id = p_user_id) then
        return query select 'user_not_found'::text;
        return;
    end if;

    if exists (
        select 1 from public.user_identities
        where user_id = p_user_id and provider = 'google'
    ) then
        return query select 'already_linked'::text;
        return;
    end if;

    if exists (
        select 1 from public.user_identities
        where provider = 'google' and provider_subject = p_provider_subject
    ) then
        return query select 'conflict_other_user'::text;
        return;
    end if;

    if exists (
        select 1 from public.users
        where google_sub = p_provider_subject and id <> p_user_id
    ) then
        return query select 'conflict_other_user'::text;
        return;
    end if;

    insert into public.user_identities (
        user_id, provider, provider_subject, email_at_link, email_verified_at_link
    ) values (
        p_user_id, 'google', p_provider_subject, p_email_at_link, true
    );

    update public.users
    set google_sub = p_provider_subject,
        tokens_valid_after = greatest(coalesce(tokens_valid_after, to_timestamp(0)), pg_catalog.now())
    where id = p_user_id;

    return query select 'linked'::text;
end;
$$;

create or replace function public.unlink_google_identity(p_user_id uuid)
returns table (result text)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    v_user public.users%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_user_id::text, 3));

    select * into v_user from public.users where id = p_user_id for update;
    if not found then
        return query select 'user_not_found'::text;
        return;
    end if;

    if not exists (
        select 1 from public.user_identities
        where user_id = p_user_id and provider = 'google'
    ) then
        return query select 'not_linked'::text;
        return;
    end if;

    if v_user.password_hash is null or v_user.email_verified is not true then
        return query select 'last_method'::text;
        return;
    end if;

    delete from public.user_identities
    where user_id = p_user_id and provider = 'google';

    update public.users
    set google_sub = null,
        tokens_valid_after = greatest(coalesce(tokens_valid_after, to_timestamp(0)), pg_catalog.now())
    where id = p_user_id;

    return query select 'unlinked'::text;
end;
$$;

create or replace function public.set_account_password(
    p_user_id uuid,
    p_password_hash text
)
returns table (result text)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    v_user public.users%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_user_id::text, 3));

    select * into v_user from public.users where id = p_user_id for update;
    if not found then
        return query select 'user_not_found'::text;
        return;
    end if;

    if v_user.password_hash is not null then
        return query select 'already_set'::text;
        return;
    end if;

    update public.users
    set password_hash = p_password_hash,
        tokens_valid_after = greatest(coalesce(tokens_valid_after, to_timestamp(0)), pg_catalog.now())
    where id = p_user_id;

    return query select 'set'::text;
end;
$$;

create or replace function public.remove_account_password(p_user_id uuid)
returns table (result text)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    v_user public.users%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_user_id::text, 3));

    select * into v_user from public.users where id = p_user_id for update;
    if not found then
        return query select 'user_not_found'::text;
        return;
    end if;

    if v_user.password_hash is null then
        return query select 'not_set'::text;
        return;
    end if;

    if not exists (
        select 1 from public.user_identities
        where user_id = p_user_id and provider = 'google'
    ) then
        return query select 'last_method'::text;
        return;
    end if;

    update public.users
    set password_hash = null,
        tokens_valid_after = greatest(coalesce(tokens_valid_after, to_timestamp(0)), pg_catalog.now())
    where id = p_user_id;

    return query select 'removed'::text;
end;
$$;

revoke all on function public.link_google_identity(uuid, text, text) from public, anon, authenticated;
revoke all on function public.unlink_google_identity(uuid) from public, anon, authenticated;
revoke all on function public.set_account_password(uuid, text) from public, anon, authenticated;
revoke all on function public.remove_account_password(uuid) from public, anon, authenticated;

grant execute on function public.link_google_identity(uuid, text, text) to service_role;
grant execute on function public.unlink_google_identity(uuid) to service_role;
grant execute on function public.set_account_password(uuid, text) to service_role;
grant execute on function public.remove_account_password(uuid) to service_role;


-- Redefine the password-reset consume RPC so its tokens_valid_after write is
-- monotonic too. Body is otherwise unchanged from password_reset_tokens.sql.

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

    update public.users
    set password_hash = p_password_hash,
        tokens_valid_after = greatest(coalesce(tokens_valid_after, to_timestamp(0)), v_now)
    where id = v_token.user_id;
    if not found then raise exception 'password reset user missing'; end if;
    update public.password_reset_tokens set status = 'consumed', consumed_at = v_now where id = v_token.id;
    update public.password_reset_tokens as reset_token set status = 'invalidated', invalidated_at = v_now
     where reset_token.user_id = v_token.user_id and reset_token.id <> v_token.id
       and reset_token.status in ('pending_delivery', 'active')
       and reset_token.consumed_at is null and reset_token.invalidated_at is null;
    return query select 'success'::text, v_token.user_id;
end;
$$;
