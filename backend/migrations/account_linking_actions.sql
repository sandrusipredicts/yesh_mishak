-- E01-04: Account linking settings screen — atomic mutation functions.
-- Builds on the user_identities table created by account_linking.sql.
-- These functions never delete the users row, never change users.id, and
-- never touch users.email / users.email_verified — linking Google to an
-- existing account must not silently change the account's primary email or
-- verification status. Each function takes a per-user advisory lock so
-- concurrent link/unlink/set-password/remove-password calls for the same
-- user serialize instead of racing past the "last remaining login method"
-- check (SECURITY DEFINER functions are owned by the migration role;
-- production migrations must run as the role that owns public.users).

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

    -- One Google identity per user (schema unique (user_id, provider)); any
    -- existing Google link — same subject or not — must be unlinked first.
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
        tokens_valid_after = pg_catalog.now()
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

    -- Google may only be unlinked if password login remains usable
    -- immediately afterward: a password hash must exist AND the email must
    -- already be verified (login() rejects unverified-email password sign-in
    -- outright, so an unverified email is not a real fallback).
    if v_user.password_hash is null or v_user.email_verified is not true then
        return query select 'last_method'::text;
        return;
    end if;

    delete from public.user_identities
    where user_id = p_user_id and provider = 'google';

    update public.users
    set google_sub = null,
        tokens_valid_after = pg_catalog.now()
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
        tokens_valid_after = pg_catalog.now()
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
        tokens_valid_after = pg_catalog.now()
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
