# Task K Manual Verification

## Open Game Player Count Contract

Purpose: verify that `POST /games` persists the player count sent by the frontend.

### Request

Use an authenticated user and an approved field id.

```http
POST /games
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "field_id": "<approved-field-id>",
  "sport_type": "football",
  "players_present": 4,
  "max_players": 10,
  "age_note": "18+"
}
```

### Expected Response

```json
{
  "message": "Game created",
  "game": {
    "players_present": 4,
    "max_players": 10
  }
}
```

### Follow-up Check

```http
GET /games/active
Authorization: Bearer <access_token>
```

Expected: the created game appears with:

```json
{
  "players_present": 4,
  "max_players": 10
}
```

### Validation Errors

- `players_present < 1` should fail.
- `players_present > max_players` should fail with `400`.
