alter table public.fields
    add column if not exists has_nets boolean not null default false;
