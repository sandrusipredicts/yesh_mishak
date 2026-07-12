# Email verification (E01-02)

## Policy

- Password registrations are created with `email_verified=false`.
- Existing users are grandfathered as verified by the migration.
- Google identities are considered verified from the validated Google claim and do not receive another email.
- The register API keeps returning its existing token response for compatibility, but the frontend does not persist that session and instead shows the verification screen.
- Password login remains API-compatible. The response marks `email_verification_required=true`; the frontend stops at the verification screen until verification succeeds.

## Security and lifecycle

Only a SHA-256 hash of the random token is stored. Tokens expire after `EMAIL_VERIFICATION_TTL_MINUTES`, are invalidated on resend, and are consumed atomically by the `verify_email_token` database function. The raw token appears only in the email link and is never logged or returned by the API.

Resend uses both the existing IP rate limiter and a per-account database cooldown. Responses for unknown, verified, and Google-only accounts are deliberately generic to prevent account enumeration.

## Routes

- `POST /auth/verify-email` with `{ "token": "..." }`
- `POST /auth/resend-verification` with `{ "email": "..." }`
- Web/app route: `/verify-email?token=...`

## Required configuration

- `SUPABASE_SERVICE_ROLE_KEY`
- `PUBLIC_APP_URL` (for example `https://yesh-mishak.com`)
- `SMTP_HOST`
- `SMTP_PORT` (default `587`)
- `SMTP_USERNAME` (optional when the server does not authenticate)
- `SMTP_PASSWORD` (optional when the server does not authenticate)
- `SMTP_FROM_ADDRESS`
- `SMTP_USE_TLS` (default `true`)
- `EMAIL_VERIFICATION_TTL_MINUTES` (default `60`)
- `EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS` (default `60`)

Apply `backend/migrations/email_verification.sql` before enabling the feature in a deployed environment. Configure the canonical `/verify-email` URL in web hosting and native Associated Domains/App Links so the same HTTPS link works in browsers, Android, and iOS.
