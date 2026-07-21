# yesh_mishak backend

FastAPI backend for `yesh_mishak`, using PostgreSQL on Supabase.

## Project structure

```text
backend/
  app/
    main.py
    core/
      config.py
    db/
      supabase.py
  requirements.txt
  README.md
  .env.example
  schema.sql
```

## Setup

Create a virtual environment, install dependencies, and copy `.env.example` to `.env`.

Required environment variables:

```text
SUPABASE_URL=
SUPABASE_KEY=
GOOGLE_CLIENT_ID=
JWT_SECRET=
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
JWT_ISSUER=yesh-mishak-api
JWT_AUDIENCE=yesh-mishak-app
FIREBASE_PROJECT_ID=
FIREBASE_SERVICE_ACCOUNT_JSON=
FIREBASE_SERVICE_ACCOUNT_FILE=
```

Application JWTs are backend-issued HS256 bearer tokens. Newly issued tokens
include `sub` (internal `users.id`), `email`, `iat`, `exp`, `iss`, and `aud`.
The backend validates signature, expiration, `JWT_ISSUER`, and `JWT_AUDIENCE`
on protected endpoints. Deployments that change issuer/audience values will
invalidate existing stored sessions and users may need to sign in again.

For Firebase Cloud Messaging, set `FIREBASE_PROJECT_ID`. The current Firebase
project is:

```text
FIREBASE_PROJECT_ID=yesh-mishak
```

The backend supports these credential sources, in order:

- `FIREBASE_SERVICE_ACCOUNT_JSON`: the full Firebase service account JSON as an environment variable.
- `FIREBASE_SERVICE_ACCOUNT_FILE`: an absolute or backend-relative path to a service account JSON file.
- Application Default Credentials (ADC), used when neither service account variable is configured.

For local ADC without a service account JSON key:

```bash
gcloud auth application-default login
gcloud config set project yesh-mishak
```

The signed-in Google account must have permission to send Firebase Cloud
Messaging messages for the `yesh-mishak` project. Keep
`FIREBASE_SERVICE_ACCOUNT_JSON` and `FIREBASE_SERVICE_ACCOUNT_FILE` empty when
using ADC locally.

Do not expose Firebase service account JSON or private keys to the frontend.

Run the API locally:

```bash
python -m uvicorn app.main:app --reload
```

Health check:

```http
GET /
```

Response:

```json
{
  "status": "ok"
}
```

## Database schema

The approved Task A tables are:

- `users`
- `fields`
- `games`
- `game_players`
- `notification_preferences`

The SQL schema is in `schema.sql` and includes foreign keys between users, fields, games, game players, and notification preferences.

## Scheduled game expiry reconciliation

Expired games are reconciled by a scheduler-compatible CLI job:

```bash
python -m app.jobs.reconcile_game_expiry --batch-size 100 --max-batches 50
```

Apply `migrations/game_expiry_reconciliation.sql` before enabling the job. In production, run it from a Railway cron service every 5 minutes with the required backend env vars configured. See `../docs/game-expiry-reconciliation.md` for full deployment, verification, and rollback steps.

## Event analytics ingestion (E09-02)

First-party product analytics are ingested through `POST /analytics/events`
(authenticated, batched, max 20 events per request) and stored in the
`analytics_events` table. Aggregated counts are exposed to admins via the
`analytics_events` section of `GET /admin/monitoring`.

Events are strictly anonymous: no user IDs (raw or hashed), resource IDs,
URLs, coordinates, or free text are ever accepted or stored — only event
names and closed-enum properties. The event/property contract is owned by
the registry in `app/analytics/registry.py` (mirrored by
`frontend/src/analytics/registry.js` and the CHECK constraints in the
migration); extend all three together when new events are approved.

Apply `migrations/analytics_events.sql` in Supabase (staging, then production),
after `api_request_metrics.sql`. Use the required preflight, atomic apply,
rollback-only live verification, exact Supabase/Railway commands, and rollback
behavior in [`../docs/analytics-events-rollout.md`](../docs/analytics-events-rollout.md).
Until the migration is applied, the pipeline degrades gracefully by design:
`POST /analytics/events` returns `503 ANALYTICS_UNAVAILABLE` (clients drop
events silently) and the `analytics_events` monitoring section reports
`source_available: false`.

Old events are deleted by a scheduler-compatible CLI job:

```bash
python -m app.jobs.cleanup_analytics_events --retention-days 90
```

In production, run it from a Railway cron service daily with the required
backend env vars configured. Runs are recorded in `job_runs` under the
`analytics_events_cleanup` job name; `--retention-days` accepts 1-365.

## Google login

`POST /auth/google` verifies a Google ID token and resolves the stable Google
`sub` through `user_identities(provider, provider_subject)`. A matching email
without a linked identity returns `409 ACCOUNT_LINK_REQUIRED`; it is never
silently attached. A genuinely new Google identity creates its application user
and identity row atomically, then returns the normal internal app JWT.

Apply `migrations/google_identity_resolution.sql` after the existing account
linking migrations. The migration stops with an explicit error if legacy
identity or case-insensitive email conflicts require manual repair.

The Google ID token comes from the Google Identity Services `response.credential` value.

For local manual testing, run this from the repository root:

```bash
python docs/google_identity_test_server.py
```

Open:

```text
http://127.0.0.1:5500/test-google-login
```

The test server reads `GOOGLE_CLIENT_ID` from your environment or `backend/.env`. After Google Sign-In, it prints `response.credential` to the browser console and shows it in a textarea. The token is not stored.

Test it in Postman:

1. Set the method to `POST`.
2. Use `http://localhost:8000/auth/google`.
3. Set `Content-Type: application/json`.
4. Send this JSON body:

```json
{
  "token": "google_id_token"
}
```

Expected response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user": {
    "id": "...",
    "email": "user@example.com",
    "name": "Example User"
  }
}
```

Invalid Google tokens return `401`, unverified Google email claims return `403`,
and an existing unlinked email returns `409 ACCOUNT_LINK_REQUIRED`.

Swagger admin test:

1. Copy the `response.credential` value from the textarea.
2. Send `POST /auth/google` with:

```json
{
  "token": "paste_response_credential_here"
}
```

3. Copy the returned `access_token`.
4. In Swagger, click `Authorize` and enter:

```text
Bearer <access_token>
```

5. Call `GET /admin/fields/pending`.

## Admin field approval

Admin endpoints require the internal JWT from `POST /auth/google`:

```http
Authorization: Bearer <access_token>
```

Only users with `role = "admin"` in the `users` table can access:

- `GET /admin/fields/pending`
- `POST /admin/fields/{field_id}/approve`
- `POST /admin/fields/{field_id}/reject`

Manual test flow:

1. Create one regular user and one admin user in Supabase. Set the admin user's `role` to `admin`.
2. Create a field with `approval_status = "pending"` and `verified = false`.
3. Log in as the regular user and call any `/admin` endpoint. Expected: `403`.
4. Log in as the admin user and call `GET /admin/fields/pending`. Expected: the pending field is returned.
5. Call `POST /admin/fields/{field_id}/approve`. Expected: the field returns with `verified = true` and `approval_status = "approved"`.
6. Call `GET /fields`. Expected: the approved field appears because public fields are filtered by `verified = true`.
7. Create or reset another pending field, then call `POST /admin/fields/{field_id}/reject`. Expected: `verified = false` and `approval_status = "rejected"`.

## Task G end-to-end Postman flow

See `../docs/task_g_postman_flow.md` for the full manual MVP backend test sequence, including request bodies, expected responses, DB verification queries, and known schema alignment SQL.
