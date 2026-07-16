-- Resolve Google login and Settings linking through atomic, service-role-only
-- functions. users.google_sub remains a compatibility mirror; the canonical
-- identity key is user_identities(provider, provider_subject).

lock table public.users, public.user_identities in share row exclusive mode;

-- Production-data preflight. Never discard or rewrite conflicting identities.
do $$
begin
    if exists (
        select 1
        from public.user_identities
        group by provider, provider_subject
        having count(*) > 1
    ) then
        raise exception 'Duplicate (provider, provider_subject) rows require manual repair';
    end if;

    if exists (
        select 1
        from public.user_identities
        group by user_id, provider
        having count(*) > 1
    ) then
        raise exception 'Multiple identities for one user/provider require manual repair';
    end if;

    if exists (
        select 1
        from public.users
        where email is not null
        group by pg_catalog.lower(pg_catalog.btrim(email))
        having count(*) > 1
    ) then
        raise exception 'Case-insensitive duplicate user emails require manual repair';
    end if;

    if exists (
        select 1
        from public.user_identities
        where pg_catalog.btrim(provider) = '' or pg_catalog.btrim(provider_subject) = ''
    ) then
        raise exception 'Blank provider identity values require manual repair';
    end if;

    if exists (
        select 1
        from public.users u
        join public.user_identities ui
          on ui.provider = 'google'
         and ui.provider_subject = u.google_sub
         and ui.user_id <> u.id
        where u.google_sub is not null
    ) then
        raise exception 'A legacy Google subject is mapped to another application user';
    end if;

    if exists (
        select 1
        from public.users u
        join public.user_identities ui
          on ui.provider = 'google'
         and ui.user_id = u.id
         and ui.provider_subject <> u.google_sub
        where u.google_sub is not null
    ) then
        raise exception 'A user has conflicting legacy and canonical Google subjects';
    end if;
end;
$$;

-- Repair only unambiguous legacy rows. The preflight above makes a conflict an
-- explicit migration failure instead of allowing ON CONFLICT DO NOTHING to
-- hide production data.
insert into public.user_identities (
    user_id, provider, provider_subject, email_at_link, email_verified_at_link
)
select u.id, 'google', u.google_sub, u.email, true
from public.users u
where u.google_sub is not null
  and not exists (
      select 1
      from public.user_identities ui
      where ui.user_id = u.id and ui.provider = 'google'
  );

create or replace function public.resolve_google_login(
    p_provider_subject text,
    p_email text,
    p_name text,
    p_picture text default null
)
returns table (result text, user_id uuid)
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
    v_subject text := pg_catalog.btrim(p_provider_subject);
    v_email text := pg_catalog.lower(pg_catalog.btrim(p_email));
    v_name text := coalesce(
        nullif(pg_catalog.btrim(p_name), ''),
        pg_catalog.split_part(pg_catalog.lower(pg_catalog.btrim(p_email)), '@', 1)
    );
    v_user_id uuid;
    v_existing_identity_subject text;
begin
    if v_subject = '' or v_email = '' then
        return query select 'invalid_claims'::text, null::uuid;
        return;
    end if;

    -- Serializes all login/create attempts for the same stable subject and
    -- provider email. The unique constraints remain the final safety net.
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('google-sub:' || v_subject, 7)
    );
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('google-email:' || v_email, 7)
    );

    -- Canonical lookup: email is intentionally not involved.
    select ui.user_id into v_user_id
    from public.user_identities ui
    where ui.provider = 'google' and ui.provider_subject = v_subject
    for update;

    if found then
        update public.user_identities
        set last_used_at = pg_catalog.now(),
            email_at_link = v_email,
            email_verified_at_link = true
        where provider = 'google' and provider_subject = v_subject;
        return query select 'existing'::text, v_user_id;
        return;
    end if;

    -- Backward-compatible recovery for a pre-migration Google user. This is a
    -- stable-subject match, not an email-based auto-link.
    select u.id into v_user_id
    from public.users u
    where u.google_sub = v_subject
    for update;

    if found then
        select ui.provider_subject into v_existing_identity_subject
        from public.user_identities ui
        where ui.user_id = v_user_id and ui.provider = 'google'
        for update;

        if found and v_existing_identity_subject <> v_subject then
            return query select 'identity_data_conflict'::text, null::uuid;
            return;
        end if;

        if v_existing_identity_subject is null then
            insert into public.user_identities (
                user_id, provider, provider_subject, email_at_link, email_verified_at_link
            ) values (
                v_user_id, 'google', v_subject, v_email, true
            );
        end if;

        return query select 'existing'::text, v_user_id;
        return;
    end if;

    -- A matching email is only a discovery signal. It never proves ownership
    -- of an existing application user and therefore never auto-links.
    select u.id into v_user_id
    from public.users u
    where pg_catalog.lower(pg_catalog.btrim(u.email)) = v_email
    for update;

    if found then
        return query select 'account_link_required'::text, v_user_id;
        return;
    end if;

    -- User + identity are one subtransaction. If either unique constraint is
    -- hit, the new user is rolled back before the winning row is re-resolved.
    begin
        insert into public.users (
            google_sub, email, name, picture, email_verified, email_verified_at
        ) values (
            v_subject, v_email, v_name, p_picture, true, pg_catalog.now()
        ) returning id into v_user_id;

        insert into public.user_identities (
            user_id, provider, provider_subject, email_at_link, email_verified_at_link
        ) values (
            v_user_id, 'google', v_subject, v_email, true
        );
    exception when unique_violation then
        select ui.user_id into v_user_id
        from public.user_identities ui
        where ui.provider = 'google' and ui.provider_subject = v_subject;

        if found then
            return query select 'existing'::text, v_user_id;
            return;
        end if;

        select u.id into v_user_id
        from public.users u
        where u.google_sub = v_subject;

        if found then
            insert into public.user_identities (
                user_id, provider, provider_subject, email_at_link, email_verified_at_link
            ) values (
                v_user_id, 'google', v_subject, v_email, true
            );
            return query select 'existing'::text, v_user_id;
            return;
        end if;

        select u.id into v_user_id
        from public.users u
        where pg_catalog.lower(pg_catalog.btrim(u.email)) = v_email;

        if found then
            return query select 'account_link_required'::text, v_user_id;
            return;
        end if;

        raise;
    end;

    return query select 'created'::text, v_user_id;
end;
$$;

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
declare
    v_user public.users%rowtype;
    v_subject text := pg_catalog.btrim(p_provider_subject);
    v_email text := pg_catalog.lower(pg_catalog.btrim(p_email_at_link));
    v_identity_user_id uuid;
    v_current_subject text;
begin
    if v_subject = '' or v_email = '' then
        return query select 'invalid_claims'::text;
        return;
    end if;

    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('user:' || p_user_id::text, 3)
    );
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('google-sub:' || v_subject, 7)
    );
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('google-email:' || v_email, 7)
    );

    select * into v_user
    from public.users
    where id = p_user_id
    for update;

    if not found then
        return query select 'user_not_found'::text;
        return;
    end if;

    select ui.user_id into v_identity_user_id
    from public.user_identities ui
    where ui.provider = 'google' and ui.provider_subject = v_subject
    for update;

    if found then
        if v_identity_user_id <> p_user_id then
            return query select 'conflict_other_user'::text;
            return;
        end if;

        if v_user.google_sub is not null and v_user.google_sub <> v_subject then
            return query select 'identity_data_conflict'::text;
            return;
        end if;

        if exists (
            select 1 from public.users
            where google_sub = v_subject and id <> p_user_id
        ) then
            return query select 'identity_data_conflict'::text;
            return;
        end if;

        update public.users
        set google_sub = v_subject
        where id = p_user_id and google_sub is null;

        update public.user_identities
        set last_used_at = pg_catalog.now(),
            email_at_link = v_email,
            email_verified_at_link = true
        where provider = 'google' and provider_subject = v_subject;

        return query select 'already_linked_same'::text;
        return;
    end if;

    select ui.provider_subject into v_current_subject
    from public.user_identities ui
    where ui.user_id = p_user_id and ui.provider = 'google'
    for update;

    if found then
        return query select 'already_linked'::text;
        return;
    end if;

    if v_user.google_sub is not null and v_user.google_sub <> v_subject then
        return query select 'already_linked'::text;
        return;
    end if;

    if exists (
        select 1 from public.users
        where google_sub = v_subject and id <> p_user_id
    ) then
        return query select 'conflict_other_user'::text;
        return;
    end if;

    if exists (
        select 1 from public.users
        where pg_catalog.lower(pg_catalog.btrim(email)) = v_email
          and id <> p_user_id
    ) then
        return query select 'email_conflict_other_user'::text;
        return;
    end if;

    insert into public.user_identities (
        user_id, provider, provider_subject, email_at_link, email_verified_at_link
    ) values (
        p_user_id, 'google', v_subject, v_email, true
    );

    -- Compatibility mirror only. Linking does not revoke or replace the
    -- caller's current application session.
    update public.users
    set google_sub = v_subject
    where id = p_user_id;

    return query select 'linked'::text;
end;
$$;

revoke all on function public.resolve_google_login(text, text, text, text) from public, anon, authenticated;
revoke all on function public.link_google_identity(uuid, text, text) from public, anon, authenticated;
grant execute on function public.resolve_google_login(text, text, text, text) to service_role;
grant execute on function public.link_google_identity(uuid, text, text) to service_role;
