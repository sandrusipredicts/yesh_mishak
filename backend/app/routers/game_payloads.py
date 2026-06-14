from typing import Any

from app.db.supabase import get_supabase_client

ACTIVE_GAME_STATUSES = ["open", "full"]


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
    users_by_id: dict[str, str] = {}
    if user_ids:
        user_rows = (
            supabase.table("users")
            .select("id,name")
            .in_("id", user_ids)
            .execute()
            .data
        )
        users_by_id = {
            str(user["id"]): user.get("name") or "Unknown player"
            for user in user_rows
            if user.get("id")
        }

    participants_by_game_id = {game_id: [] for game_id in game_ids}
    for row in player_rows:
        game_id = str(row.get("game_id") or "")
        user_id = str(row.get("user_id") or "")
        if not game_id or not user_id:
            continue

        participants_by_game_id.setdefault(game_id, []).append(
            {
                "user_id": user_id,
                "name": users_by_id.get(user_id, "Unknown player"),
            }
        )

    return [
        dict(game, participants=participants_by_game_id.get(str(game.get("id")), []))
        for game in games
    ]


def get_active_games_for_fields(field_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not field_ids:
        return {}

    games = (
        get_supabase_client()
        .table("games")
        .select("*")
        .in_("field_id", field_ids)
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
        .data
    )

    games_with_participants = attach_participants_to_games(games)
    return {
        str(game["field_id"]): game
        for game in games_with_participants
        if game.get("field_id")
    }
