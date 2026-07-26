# Auth users hardening follow-up

This follow-up is intentionally separate from the password-login read-boundary
fix.

## Remaining work

- `_update_last_login` in `backend/app/api/auth.py` uses the anon Supabase
  client. With RLS enabled and no `public.users` policies, the trusted backend
  write does not persist, while its best-effort error handling allows login to
  continue.
- Audit and remove unnecessary anon and authenticated table privileges on
  `public.users`. The current anon grants are excessively broad; `TRUNCATE`
  requires particular attention because row-level security does not govern it.

## Constraints

- Keep RLS enabled.
- Do not add an anon SELECT policy.
- Use explicit service-role selection for the trusted `last_login` write.
- Harden grants in a separate migration after auditing direct dependencies.
- Validate both changes in dev before production rollout.
