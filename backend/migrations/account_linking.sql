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

-- Backfill existing users
insert into user_identities (user_id, provider, provider_subject, email_at_link, email_verified_at_link)
select id, 'google', google_sub, email, true
from users
where google_sub is not null
on conflict (provider, provider_subject) do nothing;
