from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from app.db.supabase import get_supabase_client

ACTIVE_GAME_STATUSES = ["open", "full"]
FINISHED_GAME_STATUS = "finished"


def get_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_game_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def is_game_expired(game: dict[str, Any], now: datetime | None = None) -> bool:
    expires_at = parse_game_datetime(game.get("expires_at"))
    if expires_at is None:
        return False

    current_time = now or get_now()
    return expires_at <= current_time.astimezone(timezone.utc)


def is_game_started(game: dict[str, Any], now: datetime | None = None) -> bool:
    scheduled_at = parse_game_datetime(game.get("scheduled_at"))
    if scheduled_at is None:
        return True

    current_time = now or get_now()
    return scheduled_at <= current_time.astimezone(timezone.utc)


def is_game_upcoming(game: dict[str, Any], now: datetime | None = None) -> bool:
    scheduled_at = parse_game_datetime(game.get("scheduled_at"))
    if scheduled_at is None:
        return False

    current_time = now or get_now()
    return scheduled_at > current_time.astimezone(timezone.utc)


def finish_game(game_id: str, supabase: Any | None = None) -> dict[str, Any] | None:
    client = supabase or get_supabase_client()
    response = (
        client.table("games")
        .update({"status": FINISHED_GAME_STATUS})
        .eq("id", game_id)
        .execute()
    )
    return response.data[0] if response.data else None


def finish_expired_games(
    games: list[dict[str, Any]],
    *,
    supabase: Any | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not games:
        return []

    client = supabase or get_supabase_client()
    current_time = now or get_now()
    active_games: list[dict[str, Any]] = []

    for game in games:
        if is_game_expired(game, current_time):
            game_id = game.get("id")
            if game_id:
                finish_game(str(game_id), client)
            game["status"] = FINISHED_GAME_STATUS
        else:
            active_games.append(game)

    return active_games


def ensure_game_is_actionable(game: dict[str, Any], *, supabase: Any | None = None) -> None:
    if game.get("status") not in ACTIVE_GAME_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Game already closed")

    if is_game_expired(game):
        game_id = game.get("id")
        if game_id:
            finish_game(str(game_id), supabase)
        game["status"] = FINISHED_GAME_STATUS
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Game already closed")
