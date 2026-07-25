-- Password registration is a trusted backend operation. Keep RLS enabled and
-- grant only the missing table privilege to the backend service role.
-- This forward-only GRANT is idempotent; historical user_moderation.sql may
-- already be applied and is intentionally left unchanged.
grant insert on table public.users to service_role;
