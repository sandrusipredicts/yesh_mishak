-- E04-05: Android FCM device-token registration lifecycle
-- Adds device-identity metadata to the existing push_tokens table so that:
--   * tokens can be filtered/targeted by platform later (push_delivery_metrics, admin monitoring)
--   * a rotated FCM token can be reconciled against the same physical install
--     instead of leaving the old token as an orphaned row until a delivery
--     attempt against it eventually fails.
-- Additive only: existing rows get NULL platform/installation_id and keep working
-- exactly as before (platform-agnostic, installation-agnostic token rows).
-- Safe to re-run.

alter table push_tokens add column if not exists platform text;
alter table push_tokens add column if not exists installation_id text;

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'push_tokens'::regclass
            and conname = 'push_tokens_platform_check'
    ) then
        alter table push_tokens
            add constraint push_tokens_platform_check
            check (platform is null or platform in ('android', 'ios', 'web'));
    end if;
end $$;

create index if not exists idx_push_tokens_user_id_installation_id
    on push_tokens(user_id, installation_id);
