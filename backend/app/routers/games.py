import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field

from app.auth.dependencies import require_active_user
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import raise_api_error, validate_uuid_id
from app.core.config import get_settings
from app.rate_limit import check_rate_limit_by_user
from app.services.content_moderation import validate_game_text
from app.routers.game_lifecycle import (
    ACTIVE_GAME_STATUSES,
    ensure_game_is_actionable,
    finish_expired_games,
    get_now,
    is_game_started,
    is_game_upcoming,
    parse_game_datetime,
)
from app.routers.game_payloads import attach_participants_to_games
from app.routers.notifications import (
    create_game_closed_notifications,
    create_game_created_notifications,
    create_game_extended_notifications,
    create_player_joined_game_notification,
    create_scheduled_game_cancelled_notifications,
)

router = APIRouter(prefix="/games", tags=["games"])
logger = logging.getLogger(__name__)
timing_logger = logging.getLogger("uvicorn.error")


class GameCreate(BaseModel):
    field_id: str
    sport_type: Literal["football", "basketball"]
    players_present: int = Field(ge=1, le=1000)
    max_players: int = Field(gt=0, le=1000)
    age_note: Optional[str] = None
    min_age: Optional[int] = Field(default=None, ge=0, le=120)
    max_age: Optional[int] = Field(default=None, ge=0, le=120)
    scheduled_at: Optional[datetime] = None


class GameCancelBody(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


def _get_single(table: str, item_id: str, not_found_detail: str) -> dict[str, Any]:
    return _get_single_with_client(
        get_supabase_client(),
        table,
        item_id,
        not_found_detail,
    )


def _get_single_with_client(
    supabase: Any,
    table: str,
    item_id: str,
    not_found_detail: str,
) -> dict[str, Any]:
    response = supabase.table(table).select("*").eq("id", item_id).limit(1).execute()
    if not response.data:
        code = "NOT_FOUND"
        if "Game" in not_found_detail:
            code = "GAME_NOT_FOUND"
        elif "Field" in not_found_detail:
            code = "FIELD_NOT_FOUND"
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code=code,
            message=not_found_detail,
        )
    return response.data[0]


def _ensure_active_game(game: dict[str, Any]) -> None:
    ensure_game_is_actionable(game, supabase=get_supabase_client())


def _normalize_scheduled_at(value: datetime | None) -> datetime | None:
    scheduled_at = parse_game_datetime(value)
    if scheduled_at is None:
        return None

    return scheduled_at


def _create_game_created_notifications_background(
    game: dict[str, Any],
    field: dict[str, Any],
    organizer_id: str,
) -> None:
    t_start = time.perf_counter()
    duration_notif = 0.0
    try:
        supabase = get_supabase_client()
        t_notif_start = time.perf_counter()
        create_game_created_notifications(
            supabase=supabase,
            game=game,
            field=field,
            organizer_id=organizer_id,
        )
        t_notif_end = time.perf_counter()
        duration_notif = t_notif_end - t_notif_start
    except Exception as exc:
        logger.warning(
            "Failed to create game_created notifications",
            extra={
                "event": "notifications.generate.failure",
                "notification_type": "game_created",
                "game_id": game.get("id"),
                "field_id": field.get("id"),
                "user_id": organizer_id,
                "error_code": "NOTIFICATION_GENERATION_FAILED",
                "exception_type": exc.__class__.__name__,
                "result": "partial_failure",
            },
            exc_info=True,
        )
    finally:
        t_end = time.perf_counter()
        duration_total = t_end - t_start
        timing_logger.debug(
            "games.create.background_timing "
            "total=%.3f notification_fanout=%.3f "
            "game_id=%s field_id=%s sport_type=%s",
            duration_total,
            duration_notif,
            game.get("id"),
            field.get("id"),
            game.get("sport_type"),
        )


@router.post("/")
def create_game(
    game: GameCreate,
    background_tasks: BackgroundTasks,
    current_user: dict[str, Any] = Depends(require_active_user),
):
    validate_uuid_id(game.field_id, "field_id")
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "games_create", [(5, 60), (20, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    t_start = time.perf_counter()

    moderation = validate_game_text(age_note=game.age_note)
    if not moderation.allowed:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CONTENT_REJECTED",
            message=moderation.message,
        )

    if game.sport_type not in ("football", "basketball"):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Game sport_type must be football or basketball",
        )

    if game.players_present > game.max_players:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="players_present must be less than or equal to max_players",
        )

    if game.min_age is not None and game.max_age is not None and game.min_age > game.max_age:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invalid age range",
        )

    supabase = get_supabase_client()

    t_field_start = time.perf_counter()
    field = _get_single_with_client(supabase, "fields", game.field_id, "Field not found")
    t_field_end = time.perf_counter()
    duration_field = t_field_end - t_field_start

    now = get_now()
    scheduled_at = _normalize_scheduled_at(game.scheduled_at)
    is_scheduled_game = scheduled_at is not None

    if scheduled_at is not None and scheduled_at <= now:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="scheduled_at must be in the future",
        )

    if not field.get("verified") or field.get("approval_status") != "approved":
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="FIELD_NOT_OPEN",
            message="Field not approved",
        )

    if field.get("removed_at") is not None:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="FIELD_NOT_OPEN",
            message="Field has been removed",
        )

    if field.get("status") != "open":
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="FIELD_NOT_OPEN",
            message="Field is not open",
        )

    field_sport = field.get("sport_type")
    if field_sport not in (game.sport_type, "both"):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Field does not support this sport",
        )

    t_dup_start = time.perf_counter()
    existing_games = (
        supabase.table("games")
        .select("*")
        .eq("field_id", game.field_id)
        .eq("sport_type", game.sport_type)
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
        .data
    )

    existing_active_games = finish_expired_games(existing_games, supabase=supabase, now=now)

    if is_scheduled_game:
        if any(
            parse_game_datetime(existing_game.get("scheduled_at")) == scheduled_at
            for existing_game in existing_active_games
        ):
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="CONFLICT",
                message="Scheduled game already exists for this field and sport at this time",
            )
    elif any(is_game_started(existing_game, now) for existing_game in existing_active_games):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CONFLICT",
            message="Active game already exists for this field",
        )
    t_dup_end = time.perf_counter()
    duration_dup = t_dup_end - t_dup_start

    started_at = scheduled_at or now
    expires_at = started_at + timedelta(hours=2)
    scheduled_reminder_processed_at = (
        now
        if scheduled_at is not None and now > scheduled_at - timedelta(hours=1)
        else None
    )
    data = {
        "field_id": game.field_id,
        "created_by": current_user["id"],
        "sport_type": game.sport_type,
        "players_present": game.players_present,
        "max_players": game.max_players,
        "status": "full" if game.players_present >= game.max_players else "open",
        "age_note": game.age_note,
        "min_age": game.min_age,
        "max_age": game.max_age,
        "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
        "scheduled_reminder_processed_at": (
            scheduled_reminder_processed_at.isoformat()
            if scheduled_reminder_processed_at
            else None
        ),
        "started_at": started_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    t_insert_game_start = time.perf_counter()
    try:
        response = supabase.table("games").insert(data).execute()
    except APIError as exc:
        error_details = getattr(exc, "args", [{}])[0]
        msg = error_details.get("message", "") if isinstance(error_details, dict) else str(exc)
        code = error_details.get("code", "") if isinstance(error_details, dict) else ""
        if code == "23505" or "23505" in msg or "duplicate key" in msg.lower():
            raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="CONFLICT",
                message="Scheduled game already exists for this field and sport at this time",
            )
        raise
    created_game = response.data[0]
    t_insert_game_end = time.perf_counter()
    duration_insert_game = t_insert_game_end - t_insert_game_start

    t_insert_player_start = time.perf_counter()
    supabase.table("game_players").insert(
        {"game_id": created_game["id"], "user_id": current_user["id"]}
    ).execute()
    t_insert_player_end = time.perf_counter()
    duration_insert_player = t_insert_player_end - t_insert_player_start

    logger.info(
        "game created",
        extra={
            "event": "games.create.success",
            "endpoint": "/games/",
            "method": "POST",
            "user_id": current_user.get("id"),
            "game_id": created_game.get("id"),
            "field_id": created_game.get("field_id"),
            "sport_type": created_game.get("sport_type"),
            "result": "success",
        },
    )

    settings = get_settings()
    if settings.disable_game_created_notifications:
        t_bg_start = time.perf_counter()
        t_bg_end = time.perf_counter()
        duration_bg = t_bg_end - t_bg_start
        timing_logger.debug(
            "games.create.background_skipped reason=disabled_by_config game_id=%s field_id=%s sport_type=%s",
            created_game.get("id"),
            game.field_id,
            game.sport_type,
        )
    else:
        t_bg_start = time.perf_counter()
        background_tasks.add_task(
            _create_game_created_notifications_background,
            created_game,
            field,
            current_user["id"],
        )
        t_bg_end = time.perf_counter()
        duration_bg = t_bg_end - t_bg_start

    t_total_end = time.perf_counter()
    duration_total = t_total_end - t_start

    timing_logger.debug(
        "games.create.timing "
        "total=%.3f field_lookup=%.3f duplicate_check=%.3f "
        "game_insert=%.3f player_insert=%.3f background_task=%.3f "
        "game_id=%s field_id=%s sport_type=%s",
        duration_total,
        duration_field,
        duration_dup,
        duration_insert_game,
        duration_insert_player,
        duration_bg,
        created_game.get("id"),
        game.field_id,
        game.sport_type,
    )

    return {"message": "Game created", "game": created_game}


@router.get("/active")
def get_active_games():
    supabase = get_supabase_client()
    response = (
        supabase
        .table("games")
        .select("*")
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
    )
    active_games = [
        game for game in finish_expired_games(response.data, supabase=supabase)
        if is_game_started(game)
    ]
    return attach_participants_to_games(active_games)


@router.get("/upcoming")
def get_upcoming_games():
    supabase = get_supabase_client()
    response = (
        supabase
        .table("games")
        .select("*")
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
    )
    active_games = finish_expired_games(response.data, supabase=supabase)
    upcoming_games = [game for game in active_games if is_game_upcoming(game)]
    latest_datetime = datetime.max.replace(tzinfo=timezone.utc)
    upcoming_games.sort(
        key=lambda game: parse_game_datetime(game.get("scheduled_at")) or latest_datetime,
    )
    return attach_participants_to_games(upcoming_games)


@router.get("/me")
def get_my_games(current_user: dict[str, Any] = Depends(require_active_user)):
    supabase = get_supabase_client()
    user_id = current_user["id"]

    player_rows = (
        supabase.table("game_players")
        .select("game_id")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    participant_game_ids = [str(row["game_id"]) for row in player_rows if row.get("game_id")]

    created_response = (
        supabase.table("games").select("*").eq("created_by", user_id).execute()
    )
    created_games = {str(g["id"]): g for g in created_response.data if g.get("id")}

    if participant_game_ids:
        joined_response = (
            supabase.table("games")
            .select("*")
            .in_("id", participant_game_ids)
            .execute()
        )
        for g in joined_response.data:
            if g.get("id"):
                created_games.setdefault(str(g["id"]), g)

    all_games = list(created_games.values())

    active_status_games = [g for g in all_games if g.get("status") in ACTIVE_GAME_STATUSES]
    active_status_games = finish_expired_games(active_status_games, supabase=supabase)

    active_games = [g for g in active_status_games if is_game_started(g)]
    active_games.sort(key=lambda g: parse_game_datetime(g.get("started_at")) or datetime.min.replace(tzinfo=timezone.utc))

    upcoming_games = [g for g in active_status_games if is_game_upcoming(g)]
    latest_dt = datetime.max.replace(tzinfo=timezone.utc)
    upcoming_games.sort(key=lambda g: parse_game_datetime(g.get("scheduled_at")) or latest_dt)

    past_games = [g for g in all_games if g.get("status") == "finished"]
    past_games.sort(key=lambda g: parse_game_datetime(g.get("expires_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    cancelled_games = [g for g in all_games if g.get("status") == "cancelled"]
    cancelled_games.sort(key=lambda g: parse_game_datetime(g.get("cancelled_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    def enrich(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        games = _attach_field_names(games, supabase)
        games = attach_participants_to_games(games)
        for g in games:
            g["is_creator"] = str(g.get("created_by", "")) == user_id
        return games

    return {
        "active_games": enrich(active_games),
        "upcoming_games": enrich(upcoming_games),
        "past_games": enrich(past_games),
        "cancelled_games": enrich(cancelled_games),
    }


@router.get("/{game_id}")
def get_game(game_id: str):
    game_id = validate_uuid_id(game_id, "game_id")
    supabase = get_supabase_client()
    game = _get_single_with_client(supabase, "games", game_id, "Game not found")
    if game.get("status") in ACTIVE_GAME_STATUSES:
        finish_expired_games([game], supabase=supabase)
    return attach_participants_to_games([game])[0]


def _attach_field_names(games: list[dict[str, Any]], supabase: Any) -> list[dict[str, Any]]:
    if not games:
        return []

    field_ids = sorted({str(g["field_id"]) for g in games if g.get("field_id")})
    fields_by_id: dict[str, str] = {}
    if field_ids:
        field_rows = (
            supabase.table("fields").select("id,name").in_("id", field_ids).execute().data
        )
        fields_by_id = {
            str(f["id"]): f.get("name") or "Unknown field"
            for f in field_rows
            if f.get("id")
        }

    return [
        dict(g, field_name=fields_by_id.get(str(g.get("field_id")), "Unknown field"))
        for g in games
    ]


@router.post("/{game_id}/join")
def join_game(game_id: str, current_user: dict[str, Any] = Depends(require_active_user)):
    game_id = validate_uuid_id(game_id, "game_id")
    supabase = get_supabase_client()
    game = _get_single("games", game_id, "Game not found")
    _ensure_active_game(game)

    rpc_result = supabase.rpc(
        "join_game_atomic",
        {"p_game_id": game_id, "p_user_id": current_user["id"]},
    ).execute()

    result_data = rpc_result.data
    if isinstance(result_data, list):
        result_data = result_data[0] if result_data else {}

    if "error" in result_data:
        err_msg = result_data["error"]
        if "full" in err_msg.lower():
            code = "GAME_FULL"
        elif "not open" in err_msg.lower():
            code = "FIELD_NOT_OPEN"
        else:
            code = "CONFLICT"
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=code,
            message=err_msg,
        )

    updated_game = result_data["game"]

    if game.get("field_id"):
        field_response = (
            supabase.table("fields")
            .select("*")
            .eq("id", game.get("field_id"))
            .limit(1)
            .execute()
        )
        field = (
            field_response.data[0]
            if field_response.data
            else {"id": game.get("field_id"), "name": "Unknown field"}
        )
        try:
            create_player_joined_game_notification(
                game=game,
                field=field,
                joined_user=current_user,
            )
        except Exception:
            logger.exception(
                "Failed to create player joined game notification after successful join",
                extra={
                    "game_id": game_id,
                    "organizer_id": game.get("created_by"),
                    "joined_user_id": current_user.get("id"),
                    "field_id": game.get("field_id"),
                },
            )

    return {"message": "Joined successfully", "game": updated_game}


@router.post("/{game_id}/leave")
def leave_game(game_id: str, current_user: dict[str, Any] = Depends(require_active_user)):
    game_id = validate_uuid_id(game_id, "game_id")
    supabase = get_supabase_client()
    game = _get_single("games", game_id, "Game not found")
    _ensure_active_game(game)

    membership = (
        supabase.table("game_players")
        .select("id")
        .eq("game_id", game_id)
        .eq("user_id", current_user["id"])
        .limit(1)
        .execute()
    )
    if not membership.data:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CONFLICT",
            message="User not in game",
        )

    supabase.table("game_players").delete().eq("id", membership.data[0]["id"]).execute()

    players_present = max(0, game["players_present"] - 1)
    response = (
        supabase.table("games")
        .update({"players_present": players_present, "status": "open"})
        .eq("id", game_id)
        .execute()
    )

    return {"message": "Left successfully", "game": response.data[0]}


@router.post("/{game_id}/close")
def close_game(game_id: str, current_user: dict[str, Any] = Depends(require_active_user)):
    game_id = validate_uuid_id(game_id, "game_id")
    supabase = get_supabase_client()
    game = _get_single_with_client(supabase, "games", game_id, "Game not found")
    _ensure_active_game(game)

    if game.get("created_by") != current_user["id"]:
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Only the organizer can close game",
        )

    response = (
        supabase.table("games")
        .update({"status": "finished"})
        .eq("id", game_id)
        .execute()
    )
    updated_game = response.data[0] if response.data else _get_single_with_client(
        supabase,
        "games",
        game_id,
        "Game not found",
    )
    if updated_game.get("status") != "finished":
        logger.error(
            "game close update did not persist",
            extra={
                "event": "games.close.failure",
                "endpoint": "/games/{game_id}/close",
                "method": "POST",
                "user_id": current_user.get("id"),
                "game_id": game_id,
                "field_id": updated_game.get("field_id"),
                "closed_by_role": "creator",
                "error_code": "INTERNAL_SERVER_ERROR",
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Game close update did not persist",
        )

    logger.info(
        "game closed",
        extra={
            "event": "games.close.success",
            "endpoint": "/games/{game_id}/close",
            "method": "POST",
            "user_id": current_user.get("id"),
            "game_id": game_id,
            "field_id": updated_game.get("field_id"),
            "closed_by_role": "creator",
            "result": "success",
        },
    )

    try:
        create_game_closed_notifications(
            supabase=supabase,
            game=updated_game,
            closed_by_user_id=current_user["id"],
        )
    except Exception as exc:
        logger.warning(
            "Failed to create game closed notifications after successful close",
            extra={
                "event": "notifications.generate.failure",
                "notification_type": "game_closed",
                "game_id": game_id,
                "user_id": current_user.get("id"),
                "field_id": updated_game.get("field_id"),
                "error_code": "NOTIFICATION_GENERATION_FAILED",
                "exception_type": exc.__class__.__name__,
                "result": "partial_failure",
            },
            exc_info=True,
        )

    return {"message": "Game closed", "game": updated_game}


@router.post("/{game_id}/extend")
def extend_game(game_id: str, current_user: dict[str, Any] = Depends(require_active_user)):
    game_id = validate_uuid_id(game_id, "game_id")
    supabase = get_supabase_client()
    game = _get_single_with_client(supabase, "games", game_id, "Game not found")
    _ensure_active_game(game)

    if game.get("created_by") != current_user["id"]:
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Only the organizer can extend game",
        )

    current_expires = datetime.fromisoformat(game["expires_at"].replace("Z", "+00:00"))
    new_expires = current_expires + timedelta(hours=1)

    response = supabase.table("games").update(
        {"expires_at": new_expires.isoformat()}
    ).eq("id", game_id).execute()
    updated_game = response.data[0] if response.data else dict(game, expires_at=new_expires.isoformat())

    try:
        create_game_extended_notifications(
            supabase=supabase,
            game=updated_game,
            new_end_time=new_expires,
            extended_by_user_id=current_user["id"],
        )
    except Exception:
        logger.exception(
            "Failed to create game extended notifications after successful extend",
            extra={
                "game_id": game_id,
                "extended_by_user_id": current_user.get("id"),
                "field_id": updated_game.get("field_id"),
                "new_end_time": new_expires.isoformat(),
            },
        )

    return {"message": "Game extended by 1 hour", "new_expires_at": new_expires.isoformat()}


@router.post("/{game_id}/cancel")
def cancel_game(
    game_id: str,
    body: GameCancelBody = GameCancelBody(),
    current_user: dict[str, Any] = Depends(require_active_user),
):
    game_id = validate_uuid_id(game_id, "game_id")
    moderation = validate_game_text(cancel_reason=body.reason)
    if not moderation.allowed:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CONTENT_REJECTED",
            message=moderation.message,
        )

    supabase = get_supabase_client()
    game = _get_single_with_client(supabase, "games", game_id, "Game not found")

    if game.get("status") not in ACTIVE_GAME_STATUSES:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="GAME_NOT_ACTIONABLE",
            message="Game is not active",
        )

    scheduled_at = parse_game_datetime(game.get("scheduled_at"))
    if scheduled_at is None:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="GAME_NOT_ACTIONABLE",
            message="Only scheduled games can be cancelled",
        )

    now = get_now()
    if scheduled_at <= now:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="GAME_NOT_ACTIONABLE",
            message="Cannot cancel a game after its scheduled start time",
        )

    if game.get("created_by") != current_user["id"]:
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Only the organizer can cancel game",
        )

    service_supabase = get_supabase_service_role_client()
    update_payload = {
        "status": "cancelled",
        "cancelled_at": now.isoformat(),
        "cancelled_by": current_user["id"],
        "cancelled_by_role": "creator",
        "cancel_reason": (body.reason or "").strip() or None,
    }

    response = service_supabase.table("games").update(update_payload).eq("id", game_id).execute()
    updated_game = response.data[0] if response.data else game

    try:
        create_scheduled_game_cancelled_notifications(
            supabase=service_supabase,
            game=updated_game,
            cancelled_by_user_id=current_user["id"],
            cancelled_by_role="creator",
        )
    except Exception:
        logger.exception(
            "Failed to create game cancelled notifications",
            extra={"game_id": game_id, "cancelled_by": current_user.get("id")},
        )

    return {"message": "Game cancelled", "game": updated_game}
