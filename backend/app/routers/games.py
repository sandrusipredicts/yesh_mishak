import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import require_active_user
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import raise_api_error
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


class GameCreate(BaseModel):
    field_id: str
    sport_type: str
    players_present: int = Field(ge=1)
    max_players: int = Field(gt=0)
    age_note: Optional[str] = None
    min_age: Optional[int] = Field(default=None, ge=0)
    max_age: Optional[int] = Field(default=None, ge=0)
    scheduled_at: Optional[datetime] = None


class GameCancelBody(BaseModel):
    reason: Optional[str] = None


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


@router.post("/")
def create_game(game: GameCreate, current_user: dict[str, Any] = Depends(require_active_user)):
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
    field = _get_single("fields", game.field_id, "Field not found")
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

    response = supabase.table("games").insert(data).execute()
    created_game = response.data[0]

    supabase.table("game_players").insert(
        {"game_id": created_game["id"], "user_id": current_user["id"]}
    ).execute()

    try:
        create_game_created_notifications(
            supabase=supabase,
            game=created_game,
            field=field,
            organizer_id=current_user["id"],
        )
    except Exception:
        logger.exception(
            "Failed to create game_created notifications",
            extra={
                "game_id": created_game.get("id"),
                "field_id": created_game.get("field_id"),
                "organizer_id": current_user.get("id"),
            },
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
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Game close update did not persist",
        )

    try:
        create_game_closed_notifications(
            supabase=supabase,
            game=updated_game,
            closed_by_user_id=current_user["id"],
        )
    except Exception:
        logger.exception(
            "Failed to create game closed notifications after successful close",
            extra={
                "game_id": game_id,
                "closed_by_user_id": current_user.get("id"),
                "field_id": updated_game.get("field_id"),
            },
        )

    return {"message": "Game closed", "game": updated_game}


@router.post("/{game_id}/extend")
def extend_game(game_id: str, current_user: dict[str, Any] = Depends(require_active_user)):
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
