alter table user_identities
    add column if not exists phone_verified_at timestamptz;

create index if not exists idx_user_identities_phone_verified_at
    on user_identities(phone_verified_at)
    where provider = 'phone';
