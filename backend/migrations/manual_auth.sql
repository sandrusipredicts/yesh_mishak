alter table users
    add column if not exists username text,
    add column if not exists password_hash text,
    add column if not exists last_login timestamptz;

create unique index if not exists users_username_unique
    on users (username)
    where username is not null;

create unique index if not exists users_phone_number_unique
    on users (phone_number)
    where phone_number is not null;
