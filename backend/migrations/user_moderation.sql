alter table users
    add column if not exists status text not null default 'active'
        check (status in ('active', 'banned', 'suspended')),
    add column if not exists restriction_reason text,
    add column if not exists restricted_at timestamptz,
    add column if not exists restricted_by uuid references users(id) on delete set null;

create table if not exists user_moderation_audit (
    id uuid primary key default gen_random_uuid(),
    target_user_id uuid not null references users(id) on delete cascade,
    actor_user_id uuid references users(id) on delete set null,
    action_type text not null check (action_type in ('ban', 'unban', 'suspend', 'unsuspend')),
    reason text,
    previous_status text not null,
    new_status text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_users_status on users(status);
create index if not exists idx_user_moderation_audit_target_user_id on user_moderation_audit(target_user_id);
create index if not exists idx_user_moderation_audit_created_at on user_moderation_audit(created_at desc);
