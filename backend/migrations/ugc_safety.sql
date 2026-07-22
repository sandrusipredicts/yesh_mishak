-- E10-08: user-facing UGC report/block controls and moderation queue.

create table if not exists public.content_reports (
    id uuid primary key default gen_random_uuid(),
    reporter_user_id uuid references public.users(id) on delete set null,
    target_type text not null check (target_type in ('game', 'user')),
    target_id uuid not null,
    reason text not null check (reason in ('abuse', 'harassment', 'hate', 'spam', 'impersonation', 'inappropriate', 'other')),
    description text check (description is null or char_length(description) <= 500),
    status text not null default 'open' check (status in ('open', 'in_review', 'resolved', 'rejected')),
    admin_note text check (admin_note is null or char_length(admin_note) <= 1000),
    reviewed_at timestamptz,
    reviewed_by uuid references public.users(id) on delete set null,
    created_at timestamptz not null default now()
);

create table if not exists public.user_blocks (
    blocker_user_id uuid not null references public.users(id) on delete cascade,
    blocked_user_id uuid not null references public.users(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (blocker_user_id, blocked_user_id),
    check (blocker_user_id <> blocked_user_id)
);

alter table public.content_reports enable row level security;
alter table public.user_blocks enable row level security;

grant select, insert, update on public.content_reports to service_role;
grant select, insert, delete on public.user_blocks to service_role;

create index if not exists idx_content_reports_status_created
    on public.content_reports(status, created_at desc);
create index if not exists idx_content_reports_target
    on public.content_reports(target_type, target_id);
create index if not exists idx_user_blocks_blocker
    on public.user_blocks(blocker_user_id);
