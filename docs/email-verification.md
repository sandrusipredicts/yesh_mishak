# Email verification (E01-02)

## Policy

- Password registrations are created with `email_verified=false`.
- Existing users are grandfathered as verified by the migration.
- Google identities are considered verified from the validated Google claim and do not receive another email.
- Registration returns account metadata and delivery status, but no access token or session.
- Password login with correct credentials returns `403 EMAIL_NOT_VERIFIED` until verification succeeds. Unknown accounts and wrong passwords continue to return the same generic authentication failure, preventing arbitrary account enumeration.

## Security and lifecycle

Only a SHA-256 hash of the random token is stored. Tokens expire after `EMAIL_VERIFICATION_TTL_MINUTES`, are invalidated on resend, and are consumed atomically by the `verify_email_token` database function. The raw token appears only in the email link and is never logged or returned by the API.

Resend uses both the existing IP rate limiter and an atomic per-account database cooldown. The IP limiter is process-local, resets on restart, and is not shared across instances. The database RPC uses a transaction-scoped advisory lock, so concurrent requests or multiple application instances cannot bypass the account cooldown. Responses for unknown, verified, and Google-only accounts are deliberately generic to prevent account enumeration.

If HTTPS email delivery fails after token creation, the undelivered token is invalidated immediately. The account remains unverified and intact, the registration response reports `email_verification_sent=false`, and resend can create a fresh token without waiting for the normal cooldown.

Email delivery uses the shared `email_delivery` abstraction over Resend's HTTPS `POST /emails` API and the existing `httpx` dependency. There is no automatic retry: the provider may accept a request even if the response is lost, so retrying inside the transport could send duplicates. Recovery is explicit through resend, which has database-backed idempotency and cooldown controls.

## Routes

- `POST /auth/verify-email` with `{ "token": "..." }`
- `POST /auth/resend-verification` with `{ "email": "..." }`
- Web/app route: `/verify-email?token=...`

## Required configuration

- `SUPABASE_SERVICE_ROLE_KEY`
- `PUBLIC_APP_URL` (`https://yesh-mishak.com` for production; both this custom domain and `https://yesh-mishak.vercel.app` returned HTTP 200 from Vercel on 2026-07-12)
- `SMTP_PASSWORD` (backward-compatible primary name used by existing tasks and deployments; despite its name, it currently contains the Resend API key)
- `RESEND_API_KEY` (optional forward-compatible alias, not required; takes precedence over `SMTP_PASSWORD` when both are configured)
- `RESEND_API_URL` (default `https://api.resend.com/emails`)
- `EMAIL_FROM_ADDRESS` (use the sender authorized for the configured Resend key/domain)
- `EMAIL_VERIFICATION_TTL_MINUTES` (default `60`)
- `EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS` (default `60`)

The branch preview URL checked on 2026-07-12 redirects unauthenticated visitors to Vercel SSO. Do not use that protected preview as `PUBLIC_APP_URL` for real recipients unless deployment protection is disabled or a public bypass is intentionally configured. Use the public production domain once deployed, or another public, unprotected environment URL. The Railway development service was reachable at `https://yeshmishak-dev.up.railway.app` on the same date, but that backend URL is not the frontend verification-link origin.

Apply `backend/migrations/email_verification.sql` before enabling the feature in a deployed environment. Configure the canonical `/verify-email` URL in web hosting and native Associated Domains/App Links so the same HTTPS link works in browsers, Android, and iOS.

## Migration safety and rollback

The migration is idempotent: columns, table and indexes use `if not exists`, while RPC functions use `create or replace`. Existing rows are grandfathered only when `email_verified is null`; rerunning the migration does not turn a newer explicitly-unverified account into a verified account. Deleted users cascade-delete their tokens. Google users are grandfathered and new Google users are explicitly written as verified.

The token table has RLS enabled. Table operations and both security-definer RPCs are revoked from `public`, `anon`, and `authenticated`; only `service_role` is granted access. Verification locks the token row with `for update`, so two concurrent verify requests cannot both consume it.

No production migration is run automatically. Before applying it, take a Supabase backup or snapshot. If deployment must be rolled back, first deploy the previous backend/frontend, then optionally remove the two RPC functions and token table. Keep the two user columns during rollback because older application code ignores them; dropping them is unnecessary and makes a later re-enable harder. Exact optional cleanup:

```sql
drop function if exists verify_email_token(text);
drop function if exists prepare_email_verification_token(uuid, text, timestamptz, integer);
drop table if exists email_verification_tokens;
```

## Production URL verification

On 2026-07-12, read-only `curl -I -L` checks returned `HTTP/1.1 200 OK` and `Server: Vercel` for both `https://yesh-mishak.vercel.app/` and `https://yesh-mishak.com/`. The custom domain is therefore active rather than merely assumed, and production should use `PUBLIC_APP_URL=https://yesh-mishak.com`. The Vercel URL remains a working fallback. Recheck reachability before changing this value in Railway.

## Backend full-suite collection investigation

The exact command `python -m pytest -q`, run from `backend/`, fails during collection on both this branch and a clean archive of the current `main` commit. With the required settings supplied to the clean archive, both produce the same 13 pre-existing `ModuleNotFoundError` failures:

- `test_admin_user_moderation.py`
- `test_content_moderation_endpoints.py`
- `test_game_cancel.py`
- `test_game_creator_ownership.py`
- `test_game_deep_link.py`
- `test_game_participant_limits.py`
- `test_game_transitions.py`
- `test_game_visibility.py`
- `test_inactive_field_lifecycle.py`
- `test_my_games.py`
- `test_notification_cleanup.py`
- `test_notification_stress.py`
- `test_organizer_history.py`

The missing imports are `tests.test_admin_me`, `tests.test_game_close`, and `tests.test_notifications`. `--import-mode=importlib` is not a valid workaround because three other modules then fail on the repository's top-level `test_manual_auth` imports. Focused suites invoked by explicit file path are the established working path and were used for this feature.

## Shared email infrastructure

The merged application contains both email verification and password reset. They use one Resend HTTPS transport in `email_delivery.py`: email verification calls the provider-neutral function directly, while password reset keeps its existing `ResendEmailDelivery` adapter and result contract. This avoids duplicate provider clients while preserving both public service interfaces.

`SMTP_PASSWORD` remains supported for backward compatibility with existing tasks and Railway configuration. Despite its historical name, it is currently also used as the Resend HTTPS API key. `RESEND_API_KEY` is an optional alias rather than a deployment requirement; when both names exist, `RESEND_API_KEY` wins. Other legacy `SMTP_*` variables are not used by this HTTPS delivery path. Do not remove external values until the HTTPS flow has been verified live.

## Live verification checklist

1. Register a new manual account and confirm the response contains no JWT/session.
2. Confirm Resend Logs shows one accepted email from the configured `EMAIL_FROM_ADDRESS` with subject `Verify your yesh_mishak email`.
3. Confirm the email arrives and the link begins with the environment's exact `PUBLIC_APP_URL`.
4. Confirm password login is rejected with `EMAIL_NOT_VERIFIED` before opening the link.
5. Open the link once; verify `users.email_verified=true`, `email_verified_at` is populated, and the token has `used_at`.
6. Confirm password login succeeds after verification.
7. Open the same link twice quickly; only the first request may return `verified` and the second must be `already_used`.
8. Request resend; confirm the prior token is unusable and the new token succeeds.
9. Request resend again inside the cooldown; confirm HTTP 429 and no extra Resend email.
10. Test an expired token and an invalid token; neither may authenticate the user.
11. Confirm Google login and a grandfathered legacy password user still work.
12. Verify English/LTR and Hebrew/RTL in desktop and mobile browsers.
13. Verify the Preview URL, production URL, Android App Link, and iOS Universal Link all preserve `/verify-email?token=...`.
14. Review Railway logs for only safe event/status metadata and Resend logs for the expected provider request; no API key or verification token may appear in Railway logs.
15. Confirm Supabase contains only `token_hash`, never the raw token.
