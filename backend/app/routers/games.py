from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase_client

router = APIRouter(prefix="/games", tags=["games"])


class GameCreate(BaseModel):
    field_id: str
    sport_type: str
    players_present: int
    max_players: int
    age_note: Optional[str] = None


class GameJoin(BaseModel):
    user_id: str


class GameLeave(BaseModel):
    user_id: str


@router.post("/")
def create_game(game: GameCreate):
    supabase = get_supabase_client()

    existing = (
        supabase.table("games")
        .select("*")
        .eq("field_id", game.field_id)
        .eq("sport_type", game.sport_type)
        .in_("status", ["open", "full"])
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=400,
            detail="Active game already exists for this field and sport"
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=2)

    data = {
        "field_id": game.field_id,
        "sport_type": game.sport_type,
        "players_present": game.players_present,
        "max_players": game.max_players,
        "status": "open",
        "age_note": game.age_note,
        "started_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    response = supabase.table("games").insert(data).execute()
    return {"message": "Game created", "game": response.data[0]}


@router.get("/active")
def get_active_games():
    supabase = get_supabase_client()
    response = (
        supabase.table("games")
        .select("*")
        .eq("status", "open")
        .execute()
    )
    return response.data


@router.post("/{game_id}/join")
def join_game(game_id: str, body: GameJoin):
    supabase = get_supabase_client()

    game = supabase.table("games").select("*").eq("id", game_id).execute()
    if not game.data:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.data[0]["status"] != "open":
        raise HTTPException(status_code=400, detail="Game is not active")

    already_joined = (
        supabase.table("game_players")
        .select("*")
        .eq("game_id", game_id)
        .eq("user_id", body.user_id)
        .execute()
    )
    if already_joined.data:
        raise HTTPException(status_code=400, detail="User already joined this game")

    supabase.table("game_players").insert({
        "game_id": game_id,
        "user_id": body.user_id,
    }).execute()

    supabase.table("games").update({
        "players_present": game.data[0]["players_present"] + 1
    }).eq("id", game_id).execute()

    return {"message": "Joined successfully"}


@router.post("/{game_id}/leave")
def leave_game(game_id: str, body: GameLeave):
    supabase = get_supabase_client()

    game = supabase.table("games").select("*").eq("id", game_id).execute()
    if not game.data:
        raise HTTPException(status_code=404, detail="Game not found")

    supabase.table("game_players").delete().eq("game_id", game_id).eq("user_id", body.user_id).execute()

    new_count = max(0, game.data[0]["players_present"] - 1)
    supabase.table("games").update({
        "players_present": new_count
    }).eq("id", game_id).execute()

    return {"message": "Left successfully"}


@router.post("/{game_id}/close")
def close_game(game_id: str):
    supabase = get_supabase_client()

    game = supabase.table("games").select("*").eq("id", game_id).execute()
    if not game.data:
        raise HTTPException(status_code=404, detail="Game not found")

    supabase.table("games").update({"status": "finished"}).eq("id", game_id).execute()
    return {"message": "Game closed"}


@router.post("/{game_id}/extend")
def extend_game(game_id: str):
    supabase = get_supabase_client()

    game = supabase.table("games").select("*").eq("id", game_id).execute()
    if not game.data:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.data[0]["status"] != "open":
        raise HTTPException(status_code=400, detail="Game is not active")

    current_expires = datetime.fromisoformat(game.data[0]["expires_at"])
    new_expires = current_expires + timedelta(hours=1)

    supabase.table("games").update({
        "expires_at": new_expires.isoformat()
    }).eq("id", game_id).execute()

    return {"message": "Game extended by 1 hour", "new_expires_at": new_expires.isoformat()}