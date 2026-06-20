from typing import Any

from app.db.supabase import get_supabase_client
from app.routers.game_lifecycle import (
    ACTIVE_GAME_STATUSES,
    finish_expired_games,
    is_game_started,
    is_game_upcoming,
    parse_game_datetime,
)

SUPABASE_IN_FILTER_BATCH_SIZE = 100


def _batched_unique_values(values: list[str], batch_size: int = SUPABASE_IN_FILTER_BATCH_SIZE) -> list[list[str]]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)

    return [
        unique_values[index : index + batch_size]
        for index in range(0, len(unique_values), batch_size)
    ]


def _select_with_in_batches(
    supabase: Any,
    table_name: str,
    columns: str,
    filter_column: str,
    values: list[str],
    extra_in_filters: dict[str, list[Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for batch in _batched_unique_values(values):
        query = supabase.table(table_name).select(columns).in_(filter_column, batch)
        for column, filter_values in (extra_in_filters or {}).items():
            query = query.in_(column, filter_values)
        rows.extend(query.execute().data)
    return rows


def attach_participants_to_games(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not games:
        return []

    game_ids = [str(game["id"]) for game in games if game.get("id")]
    if not game_ids:
        return [dict(game, participants=[]) for game in games]

    supabase = get_supabase_client()
    player_rows = _select_with_in_batches(
        supabase,
        "game_players",
        "game_id,user_id",
        "game_id",
        game_ids,
    )

    user_ids = sorted({str(row["user_id"]) for row in player_rows if row.get("user_id")})
    users_by_id: dict[str, dict[str, str | None]] = {}
    if user_ids:
        user_rows = _select_with_in_batches(
            supabase,
            "users",
            "id,username,name",
            "id",
            user_ids,
        )
        users_by_id = {
            str(user["id"]): {
                "username": user.get("username"),
                "name": user.get("name"),
            }
            for user in user_rows
            if user.get("id")
        }

    participants_by_game_id = {game_id: [] for game_id in game_ids}
    for row in player_rows:
        game_id = str(row.get("game_id") or "")
        user_id = str(row.get("user_id") or "")
        if not game_id or not user_id:
            continue

        user = users_by_id.get(user_id, {})
        username = user.get("username")
        name = user.get("name")
        participants_by_game_id.setdefault(game_id, []).append(
            {
                "user_id": user_id,
                "username": username,
                "name": username or name or "Unknown player",
            }
        )

    return [
        dict(game, participants=participants_by_game_id.get(str(game.get("id")), []))
        for game in games
    ]


def get_active_games_for_fields(field_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not field_ids:
        return {}

    supabase = get_supabase_client()
    games = _select_with_in_batches(
        supabase,
        "games",
        "*",
        "field_id",
        field_ids,
        {"status": ACTIVE_GAME_STATUSES},
    )
    games = [
        game for game in finish_expired_games(games, supabase=supabase)
        if is_game_started(game)
    ]

    games_with_participants = attach_participants_to_games(games)
    return {
        str(game["field_id"]): game
        for game in games_with_participants
        if game.get("field_id")
    }


def get_upcoming_games_for_fields(field_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not field_ids:
        return {}

    supabase = get_supabase_client()
    games = _select_with_in_batches(
        supabase,
        "games",
        "*",
        "field_id",
        field_ids,
        {"status": ACTIVE_GAME_STATUSES},
    )
    games = finish_expired_games(games, supabase=supabase)
    upcoming_games = [game for game in games if is_game_upcoming(game)]
    upcoming_games.sort(
        key=lambda game: parse_game_datetime(game.get("scheduled_at")),
    )

    games_with_participants = attach_participants_to_games(upcoming_games)
    upcoming_games_by_field_id = {field_id: [] for field_id in field_ids}
    for game in games_with_participants:
        field_id = str(game.get("field_id") or "")
        if field_id:
            upcoming_games_by_field_id.setdefault(field_id, []).append(game)

    return upcoming_games_by_field_id
