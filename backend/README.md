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
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
```

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

## Google login

`POST /auth/google` verifies a Google ID token, finds or creates a user in Supabase by email, and returns an internal app JWT.

The Google ID token comes from the Google Identity Services `response.credential` value. A minimal helper page is available at `../docs/test_google_login.html` for manually getting that token during local testing.

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

Invalid Google tokens return `401`. User insert failures return `500`.
