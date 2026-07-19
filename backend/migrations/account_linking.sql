create table if not exists user_identities (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users(id) on delete cascade,
    provider text not null,
    provider_subject text not null,
    email_at_link text,
    email_verified_at_link boolean not null default false,
    created_at timestamptz not null default now(),
    last_used_at timestamptz not null default now(),
    unique (provider, provider_subject),
    unique (user_id, provider)
);

alter table user_identities enable row level security;

grant select, insert, update, delete on public.user_identities to service_role;

create index if not exists idx_user_identities_user_id on user_identities(user_id);
create index if not exists idx_user_identities_lookup on user_identities(provider, provider_subject);

-- Refuse ambiguous legacy data instead of silently dropping one side of a
-- conflict. An operator must repair these rows before retrying the migration.
do $$
begin
    if exists (
        select 1
        from public.users u
        join public.user_identities ui
          on ui.provider = 'google'
         and ui.provider_subject = u.google_sub
         and ui.user_id <> u.id
        where u.google_sub is not null
    ) then
        raise exception 'Google identity backfill conflict: a users.google_sub value belongs to another user_identities row';
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
        raise exception 'Google identity backfill conflict: a user has different legacy and identity subjects';
    end if;
end;
$$;

-- Backfill existing users only after the conflict audit succeeds.
insert into user_identities (user_id, provider, provider_subject, email_at_link, email_verified_at_link)
select id, 'google', google_sub, email, true
from users
where google_sub is not null
  and not exists (
      select 1 from user_identities ui
      where ui.user_id = users.id and ui.provider = 'google'
  );
