# Task G - Backend MVP Postman Flow

Run the backend from `backend/`:

```bash
python -m uvicorn app.main:app --reload
```

Use Swagger or Postman with this header for authenticated endpoints:

```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

Get `<access_token>` by signing in with Google Identity Services and sending:

```http
POST /auth/google
```

```json
{
  "token": "response.credential"
}
```

The returned `access_token` is the internal backend JWT.

## Required Schema Alignment

Task G expects these live Supabase columns:

```sql
alter table public.users
add column if not exists role text not null default 'user';

alter table public.fields
add column if not exists status text not null default 'open';

alter table public.fields
add column if not exists approval_status text not null default 'pending';

alter table public.fields
alter column verified set default false;

alter table public.notification_preferences
add column if not exists enabled boolean not null default true;

alter table public.notification_preferences
add column if not exists sport_type text not null default 'both';

alter table public.notification_preferences
add column if not exists lat numeric(10, 7);

alter table public.notification_preferences
add column if not exists lng numeric(10, 7);
```

If an old `fields.status` default is `pending`, fix it:

```sql
alter table public.fields
alter column status set default 'open';

update public.fields
set status = 'open'
where status = 'pending';
```

## 1. Login

Use Google Identity Services helper:

```bash
python docs/google_identity_test_server.py
```

Open `http://127.0.0.1:5500/test-google-login`, copy `response.credential`, then call:

```http
POST http://localhost:8000/auth/google
```

```json
{
  "token": "response.credential"
}
```

Expected response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user": {
    "id": "...",
    "email": "...",
    "name": "..."
  }
}
```

DB check:

```sql
select id, email, name, role from public.users order by created_at desc;
```

Set one test user as admin:

```sql
update public.users
set role = 'admin'
where email = 'ADMIN_EMAIL@example.com';
```

## 2. Create Field

Authenticated regular user:

```http
POST http://localhost:8000/fields/
Authorization: Bearer <USER_ACCESS_TOKEN>
```

```json
{
  "name": "Test Football Field",
  "lat": 32.0853,
  "lng": 34.7818,
  "sport_type": "football",
  "surface_type": "synthetic",
  "has_nets": true,
  "has_water": true,
  "opening_hours": "08:00-22:00",
  "notes": "Task G test field"
}
```

Expected: field is created with `approval_status = "pending"`, `verified = false`, `added_by = current user id`, `status = "open"`.

DB check:

```sql
select id, name, added_by, verified, approval_status, status
from public.fields
order by created_at desc;
```

Unauthenticated request expected error: `401`.

## 3. Admin List Pending Fields

```http
GET http://localhost:8000/admin/fields/pending
Authorization: Bearer <ADMIN_ACCESS_TOKEN>
```

Expected: pending field appears.

Regular user expected error: `403`.

## 4. Admin Approve Field

```http
POST http://localhost:8000/admin/fields/FIELD_ID/approve
Authorization: Bearer <ADMIN_ACCESS_TOKEN>
```

Expected:

```json
{
  "verified": true,
  "approval_status": "approved"
}
```

DB check:

```sql
select id, verified, approval_status
from public.fields
where id = 'FIELD_ID';
```

## 5. List Public Fields

```http
GET http://localhost:8000/fields/
```

Expected: approved field appears. Pending/rejected fields do not appear.

## 6. Open Game

Authenticated organizer:

```http
POST http://localhost:8000/games/
Authorization: Bearer <ORGANIZER_ACCESS_TOKEN>
```

```json
{
  "field_id": "FIELD_ID",
  "sport_type": "football",
  "max_players": 10,
  "age_note": "18+"
}
```

Expected: game is created with `status = "open"`, `players_present = 1`, `created_by = organizer user id`. The organizer is inserted into `game_players`.

DB checks:

```sql
select id, field_id, created_by, sport_type, players_present, max_players, status
from public.games
order by started_at desc;

select game_id, user_id
from public.game_players
where game_id = 'GAME_ID';
```

Expected error cases:

- unapproved field: `Field not approved`
- duplicate active game for same field and sport: `Active game already exists for this field`
- field not found: `Field not found`

## 7. List Active Games

```http
GET http://localhost:8000/games/active
```

Expected: open/full games appear.

## 8. Prevent Duplicate Game

Repeat the same `POST /games/` body for the same field and sport while the first game is open.

Expected:

```json
{
  "detail": "Active game already exists for this field"
}
```

## 9. Join Game

Authenticated second user:

```http
POST http://localhost:8000/games/GAME_ID/join
Authorization: Bearer <SECOND_USER_ACCESS_TOKEN>
```

No body.

Expected: `game_players` has the second user, and `games.players_present` increments by 1.

DB checks:

```sql
select players_present, status
from public.games
where id = 'GAME_ID';

select game_id, user_id
from public.game_players
where game_id = 'GAME_ID';
```

Expected error cases:

- same user joins twice: `User already joined`
- closed game: `Game already closed`
- full game: `Game is full`

## 10. Leave Game

Authenticated joined user:

```http
POST http://localhost:8000/games/GAME_ID/leave
Authorization: Bearer <SECOND_USER_ACCESS_TOKEN>
```

No body.

Expected: user's `game_players` row is removed, and `games.players_present` decrements by 1.

Expected error case:

- user not in game: `User not in game`

## 11. Close Game

Authenticated organizer:

```http
POST http://localhost:8000/games/GAME_ID/close
Authorization: Bearer <ORGANIZER_ACCESS_TOKEN>
```

Expected: game `status = "finished"` and no longer appears in `GET /games/active`.

Expected error cases:

- non-organizer: `Only the organizer can close game`
- already closed: `Game already closed`

DB check:

```sql
select id, status
from public.games
where id = 'GAME_ID';
```

## 12. Save Notification Preferences

Authenticated user:

```http
PUT http://localhost:8000/notifications/preferences
Authorization: Bearer <USER_ACCESS_TOKEN>
```

```json
{
  "enabled": true,
  "sport_type": "football",
  "notification_type": "radius",
  "radius_km": 5,
  "lat": 32.0853,
  "lng": 34.7818
}
```

Expected: preference is saved for the authenticated user, not a `user_id` from the body.

DB check:

```sql
select user_id, enabled, sport_type, notification_type, radius_km, lat, lng
from public.notification_preferences
where user_id = 'USER_ID';
```

Invalid preference examples:

- radius without `radius_km`, `lat`, or `lng`
- invalid `sport_type`
- invalid `notification_type`

## 13. Read Notification Preferences

```http
GET http://localhost:8000/notifications/preferences
Authorization: Bearer <USER_ACCESS_TOKEN>
```

Expected: only that authenticated user's preferences.

## 14. Notification Candidates

Authenticated request:

```http
POST http://localhost:8000/notifications/candidates
Authorization: Bearer <ACCESS_TOKEN>
```

```json
{
  "field_id": "FIELD_ID",
  "sport_type": "football"
}
```

Expected:

```json
[
  {
    "user_id": "USER_ID",
    "reason": "within_radius_and_sport_match"
  }
]
```

DB logic:

- `notification_preferences.enabled = true`
- `notification_preferences.sport_type` equals requested `sport_type` or `both`
- radius preference has `lat`, `lng`, and `radius_km`
- distance from preference lat/lng to field lat/lng is within radius

No real push notification is sent.
