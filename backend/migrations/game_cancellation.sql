alter table games
    add column if not exists cancelled_at timestamptz,
    add column if not exists cancelled_by uuid references users(id) on delete set null,
    add column if not exists cancelled_by_role text,
    add column if not exists cancel_reason text;
