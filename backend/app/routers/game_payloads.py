import logging
import time
from typing import Any

from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.routers.game_lifecycle import (
    ACTIVE_GAME_STATUSES,
    finish_expired_games,
    is_game_started,
    is_game_upcoming,
    parse_game_datetime,
)

logger = logging.getLogger(__name__)

SUPABASE_IN_FILTER_BATCH_SIZE = 100
SUPABASE_SELECT_MAX_ATTEMPTS = 3
SUPABASE_SELECT_RETRY_DELAY_SECONDS = 0.2


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
    batches = _batched_unique_values(values)
    logger.info(
        "supabase batched select start table=%s filter_column=%s total_ids=%s batches=%s batch_size=%s extra_filters=%s",
        table_name,
        filter_column,
        len({value for value in values if value}),
        len(batches),
        SUPABASE_IN_FILTER_BATCH_SIZE,
        sorted((extra_in_filters or {}).keys()),
    )

    for batch_index, batch in enumerate(batches, start=1):
        for attempt in range(1, SUPABASE_SELECT_MAX_ATTEMPTS + 1):
            try:
                query = supabase.table(table_name).select(columns).in_(filter_column, batch)
                for column, filter_values in (extra_in_filters or {}).items():
                    query = query.in_(column, filter_values)
                response = query.execute()
                rows.extend(response.data)
                break
            except Exception as exc:
                logger.exception(
                    "supabase batched select failed table=%s filter_column=%s total_ids=%s batches=%s batch_index=%s batch_ids_count=%s batch_size=%s attempt=%s max_attempts=%s exception_type=%s exception_repr=%r",
                    table_name,
                    filter_column,
                    len({value for value in values if value}),
                    len(batches),
                    batch_index,
                    len(batch),
                    len(batch),
                    attempt,
                    SUPABASE_SELECT_MAX_ATTEMPTS,
                    exc.__class__.__qualname__,
                    exc,
                )
                if attempt >= SUPABASE_SELECT_MAX_ATTEMPTS:
                    raise
                time.sleep(SUPABASE_SELECT_RETRY_DELAY_SECONDS * attempt)

    return rows


def _get_active_status_games_for_fields(
    supabase: Any,
    field_ids: list[str],
) -> list[dict[str, Any]]:
    return _select_with_in_batches(
        supabase,
        "games",
        "*",
        "field_id",
        field_ids,
        {"status": ACTIVE_GAME_STATUSES},
    )


def _get_map_game_payload_rows(supabase: Any, field_ids: list[str]) -> list[dict[str, Any]]:
    for attempt in range(1, SUPABASE_SELECT_MAX_ATTEMPTS + 1):
        try:
            response = supabase.rpc(
                "get_field_game_payloads",
                {"p_field_ids": list(dict.fromkeys(field_ids))},
            ).execute()
            break
        except Exception:
            if attempt >= SUPABASE_SELECT_MAX_ATTEMPTS:
                raise
            time.sleep(SUPABASE_SELECT_RETRY_DELAY_SECONDS * attempt)
    rows = response.data or []
    return [row.get("payload", row) for row in rows]


def _split_games_by_field(
    games: list[dict[str, Any]],
    field_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    active_games: list[dict[str, Any]] = []
    upcoming_games: list[dict[str, Any]] = []

    for game in games:
        if is_game_started(game):
            active_games.append(game)
        elif is_game_upcoming(game):
            upcoming_games.append(game)

    upcoming_games.sort(key=lambda game: parse_game_datetime(game.get("scheduled_at")))
    visible_games = active_games + upcoming_games
    games_with_participants = (
        visible_games
        if all("participants" in game for game in visible_games)
        else attach_participants_to_games(visible_games)
    )

    active_games_by_field_id: dict[str, dict[str, Any]] = {}
    upcoming_games_by_field_id = {field_id: [] for field_id in field_ids}

    for game in games_with_participants:
        field_id = str(game.get("field_id") or "")
        if not field_id:
            continue

        if is_game_started(game):
            active_games_by_field_id[field_id] = game
        elif is_game_upcoming(game):
            upcoming_games_by_field_id.setdefault(field_id, []).append(game)

    return active_games_by_field_id, upcoming_games_by_field_id


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
    games = finish_expired_games(_get_active_status_games_for_fields(supabase, field_ids), supabase=supabase)
    active_games_by_field_id, _ = _split_games_by_field(games, field_ids)
    return active_games_by_field_id


def get_upcoming_games_for_fields(field_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not field_ids:
        return {}

    supabase = get_supabase_client()
    games = finish_expired_games(_get_active_status_games_for_fields(supabase, field_ids), supabase=supabase)
    _, upcoming_games_by_field_id = _split_games_by_field(games, field_ids)
    return upcoming_games_by_field_id


def get_game_payloads_for_fields(
    field_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    if not field_ids:
        return {}, {}

    supabase = get_supabase_client()
    games = finish_expired_games(_get_active_status_games_for_fields(supabase, field_ids), supabase=supabase)
    return _split_games_by_field(games, field_ids)


def get_map_game_payloads_for_fields(
    field_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Load the GET /fields game payload through one database RPC."""
    if not field_ids:
        return {}, {}

    supabase = get_supabase_service_role_client()
    games = _get_map_game_payload_rows(supabase, field_ids)
    return _split_games_by_field(games, field_ids)
