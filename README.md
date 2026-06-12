# yesh_mishak

כל הסכמות שצריך להטמיע  ב DB כל טבלה והקטגוריות שבה מצורפות מתחת

users

id, google_sub, email, name, picture, phone_number, created_at, last_active

fields

id, name, lat, lng, sport_type (football/basketball/both), surface_type, has_nets, has_water, opening_hours, status (pending/approved/rejected/renovation), verified, added_by, created_at, notes, image_url

games

id, field_id, created_by, sport_type (football/basketball), players_present, max_players, status (open/full/finished/cancelled), age_note, min_age, max_age, started_at, expires_at

game_players

id, game_id, user_id, joined_at

notification_preferences

id, user_id, notification_type (radius/city/specific_field), radius_km, city, field_id, created_at

## Task B - Auth + Users

Install backend dependencies from the `backend` folder:

```bash
pip install -r requirements.txt
```

Create `backend/.env` from `backend/.env.example` with these variables:

```text
SUPABASE_URL=
SUPABASE_KEY=
GOOGLE_CLIENT_ID=
JWT_SECRET=
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080
```

Run the backend from the `backend` folder:

```bash
python -m uvicorn app.main:app --reload
```

Test Google login with Postman:

```http
POST http://localhost:8000/auth/google
Content-Type: application/json
```

```json
{
  "token": "google_id_token"
}
```

The Google ID token comes from Google Identity Services as `response.credential`. For manual testing, see `docs/test_google_login.html`.

Expected response shape:

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
