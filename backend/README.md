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
```

Run the API locally:

```bash
uvicorn app.main:app --reload
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
