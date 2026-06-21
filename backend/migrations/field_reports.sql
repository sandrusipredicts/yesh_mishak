create table if not exists field_reports (
    id uuid primary key default gen_random_uuid(),
    field_id uuid not null references fields(id) on delete cascade,
    user_id uuid not null references users(id) on delete cascade,
    category text not null check (
        category in (
            'wrong_location',
            'field_does_not_exist',
            'field_closed',
            'under_renovation',
            'private_field',
            'duplicate_field',
            'wrong_information',
            'other'
        )
    ),
    description text,
    status text not null default 'open' check (
        status in ('open', 'in_review', 'resolved', 'rejected')
    ),
    created_at timestamptz not null default now(),
    reviewed_at timestamptz,
    reviewed_by uuid references users(id) on delete set null
);

create index if not exists idx_field_reports_field_id on field_reports(field_id);
create index if not exists idx_field_reports_user_id on field_reports(user_id);
create index if not exists idx_field_reports_status on field_reports(status);
create index if not exists idx_field_reports_created_at on field_reports(created_at);
create index if not exists idx_field_reports_field_id_status on field_reports(field_id, status);
