from typing import Any

from app.db.supabase import get_supabase_client
from app.routers.game_lifecycle import (
    ACTIVE_GAME_STATUSES,
    finish_expired_games,
    is_game_started,
    is_game_upcoming,
    parse_game_datetime,
)


def attach_participants_to_games(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not games:
        return []

    game_ids = [str(game["id"]) for game in games if game.get("id")]
    if not game_ids:
        return [dict(game, participants=[]) for game in games]

    supabase = get_supabase_client()
    player_rows = (
        supabase.table("game_players")
        .select("game_id,user_id")
        .in_("game_id", game_ids)
        .execute()
        .data
    )

    user_ids = sorted({str(row["user_id"]) for row in player_rows if row.get("user_id")})
    users_by_id: dict[str, dict[str, str | None]] = {}
    if user_ids:
        user_rows = (
            supabase.table("users")
            .select("id,username,name")
            .in_("id", user_ids)
            .execute()
            .data
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
    games = (
        supabase
        .table("games")
        .select("*")
        .in_("field_id", field_ids)
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
        .data
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
    games = (
        supabase
        .table("games")
        .select("*")
        .in_("field_id", field_ids)
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
        .data
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
