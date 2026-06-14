from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.db.supabase import get_supabase_client
from app.routers.game_payloads import ACTIVE_GAME_STATUSES, attach_participants_to_games

router = APIRouter(prefix="/games", tags=["games"])


class GameCreate(BaseModel):
    field_id: str
    sport_type: str
    players_present: int = Field(ge=1)
    max_players: int = Field(gt=0)
    age_note: Optional[str] = None
    min_age: Optional[int] = Field(default=None, ge=0)
    max_age: Optional[int] = Field(default=None, ge=0)


def _get_single(table: str, item_id: str, not_found_detail: str) -> dict[str, Any]:
    response = get_supabase_client().table(table).select("*").eq("id", item_id).limit(1).execute()
    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    return response.data[0]


def _ensure_active_game(game: dict[str, Any]) -> None:
    if game.get("status") not in ACTIVE_GAME_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Game already closed")


@router.post("/")
def create_game(game: GameCreate, current_user: dict[str, Any] = Depends(get_current_user)):
    if game.players_present > game.max_players:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="players_present must be less than or equal to max_players",
        )

    if game.min_age is not None and game.max_age is not None and game.min_age > game.max_age:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid age range")

    supabase = get_supabase_client()
    field = _get_single("fields", game.field_id, "Field not found")

    if not field.get("verified") or field.get("approval_status") != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Field not approved")

    field_sport = field.get("sport_type")
    if field_sport not in (game.sport_type, "both"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Field does not support this sport")

    existing = (
        supabase.table("games")
        .select("id")
        .eq("field_id", game.field_id)
        .eq("sport_type", game.sport_type)
        .in_("status", ACTIVE_GAME_STATUSES)
        .limit(1)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Active game already exists for this field",
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=2)
    data = {
        "field_id": game.field_id,
        "created_by": current_user["id"],
        "sport_type": game.sport_type,
        "players_present": game.players_present,
        "max_players": game.max_players,
        "status": "open",
        "age_note": game.age_note,
        "min_age": game.min_age,
        "max_age": game.max_age,
        "started_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    response = supabase.table("games").insert(data).execute()
    created_game = response.data[0]

    supabase.table("game_players").insert(
        {"game_id": created_game["id"], "user_id": current_user["id"]}
    ).execute()

    return {"message": "Game created", "game": created_game}


@router.get("/active")
def get_active_games():
    response = (
        get_supabase_client()
        .table("games")
        .select("*")
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
    )
    return attach_participants_to_games(response.data)


@router.post("/{game_id}/join")
def join_game(game_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    supabase = get_supabase_client()
    game = _get_single("games", game_id, "Game not found")
    _ensure_active_game(game)

    if game["players_present"] >= game["max_players"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Game is full")

    already_joined = (
        supabase.table("game_players")
        .select("id")
        .eq("game_id", game_id)
        .eq("user_id", current_user["id"])
        .limit(1)
        .execute()
    )
    if already_joined.data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already joined")

    supabase.table("game_players").insert(
        {"game_id": game_id, "user_id": current_user["id"]}
    ).execute()

    players_present = game["players_present"] + 1
    new_status = "full" if players_present >= game["max_players"] else "open"
    response = (
        supabase.table("games")
        .update({"players_present": players_present, "status": new_status})
        .eq("id", game_id)
        .execute()
    )

    return {"message": "Joined successfully", "game": response.data[0]}


@router.post("/{game_id}/leave")
def leave_game(game_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not in game")

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
def close_game(game_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    game = _get_single("games", game_id, "Game not found")
    _ensure_active_game(game)

    if game.get("created_by") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organizer can close game",
        )

    response = (
        get_supabase_client()
        .table("games")
        .update({"status": "finished"})
        .eq("id", game_id)
        .execute()
    )
    return {"message": "Game closed", "game": response.data[0]}


@router.post("/{game_id}/extend")
def extend_game(game_id: str, current_user: dict[str, Any] = Depends(get_current_user)):
    game = _get_single("games", game_id, "Game not found")
    _ensure_active_game(game)

    if game.get("created_by") != current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the organizer can extend game",
        )

    current_expires = datetime.fromisoformat(game["expires_at"])
    new_expires = current_expires + timedelta(hours=1)

    get_supabase_client().table("games").update(
        {"expires_at": new_expires.isoformat()}
    ).eq("id", game_id).execute()

    return {"message": "Game extended by 1 hour", "new_expires_at": new_expires.isoformat()}
