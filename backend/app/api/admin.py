from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import require_admin
from app.db.supabase import get_supabase_client
from app.routers.fields import FieldStatusUpdate, update_field_status_record
from app.routers.game_lifecycle import (
    ACTIVE_GAME_STATUSES,
    ensure_game_is_actionable,
    finish_expired_games,
)
from app.routers.game_payloads import attach_participants_to_games

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_FIELD_COLUMNS = ",".join(
    [
        "id",
        "name",
        "city",
        "lat",
        "lng",
        "sport_type",
        "surface_type",
        "status",
        "approval_status",
        "verified",
        "notes",
        "created_at",
    ]
)
FINISHED_GAME_STATUSES = ["finished", "cancelled"]
FINISHED_GAMES_LIMIT = 50

ADMIN_USER_COLUMNS = ",".join(
    [
        "id",
        "name",
        "email",
        "phone_number",
        "created_at",
        "last_active",
        "role",
    ]
)


def _count_rows(table_name: str, filters: list[tuple[str, Any]] | None = None) -> int:
    query = get_supabase_client().table(table_name).select("id", count="exact")

    for column, value in filters or []:
        query = query.eq(column, value)

    response = query.execute()
    count = getattr(response, "count", None)
    if count is not None:
        return count

    return len(response.data or [])


def _count_rows_in(table_name: str, column: str, values: list[str]) -> int:
    if table_name == "games" and column == "status" and values == ACTIVE_GAME_STATUSES:
        supabase = get_supabase_client()
        games = (
            supabase
            .table("games")
            .select("*")
            .in_(column, values)
            .execute()
            .data
        )
        return len(finish_expired_games(games, supabase=supabase))

    response = (
        get_supabase_client()
        .table(table_name)
        .select("id", count="exact")
        .in_(column, values)
        .execute()
    )
    count = getattr(response, "count", None)
    if count is not None:
        return count

    return len(response.data or [])


@router.get("/me")
def get_admin_me(current_user: dict[str, Any] = Depends(require_admin)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "name": current_user["name"],
        "role": current_user["role"],
    }


@router.get("/users")
def get_admin_users(_: dict[str, Any] = Depends(require_admin)):
    response = (
        get_supabase_client()
        .table("users")
        .select(ADMIN_USER_COLUMNS)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


@router.get("/stats")
def get_admin_stats(_: dict[str, Any] = Depends(require_admin)):
    return {
        "verified_fields": _count_rows(
            "fields",
            [("verified", True), ("approval_status", "approved")],
        ),
        "pending_fields": _count_rows("fields", [("approval_status", "pending")]),
        "active_games": _count_rows_in("games", "status", ACTIVE_GAME_STATUSES),
        "total_users": _count_rows("users"),
        "rejected_fields": _count_rows("fields", [("approval_status", "rejected")]),
        "finished_games": _count_rows_in("games", "status", FINISHED_GAME_STATUSES),
    }


@router.get("/fields")
def get_admin_fields(_: dict[str, Any] = Depends(require_admin)):
    response = (
        get_supabase_client()
        .table("fields")
        .select(ADMIN_FIELD_COLUMNS)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


@router.get("/fields/pending")
def get_pending_fields(_: dict[str, Any] = Depends(require_admin)):
    response = (
        get_supabase_client()
        .table("fields")
        .select("*")
        .eq("approval_status", "pending")
        .order("created_at", desc=False)
        .execute()
    )
    return response.data


@router.post("/fields/{field_id}/approve")
def approve_field(field_id: str, _: dict[str, Any] = Depends(require_admin)):
    return _update_field_approval(
        field_id=field_id,
        updates={"verified": True, "approval_status": "approved"},
    )


@router.post("/fields/{field_id}/reject")
def reject_field(field_id: str, _: dict[str, Any] = Depends(require_admin)):
    return _update_field_approval(
        field_id=field_id,
        updates={"verified": False, "approval_status": "rejected"},
    )


@router.patch("/fields/{field_id}/status")
def update_admin_field_status(
    field_id: str,
    body: FieldStatusUpdate,
    _: dict[str, Any] = Depends(require_admin),
):
    return update_field_status_record(field_id, body)


def _attach_field_names(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not games:
        return []

    field_ids = sorted({str(game["field_id"]) for game in games if game.get("field_id")})
    fields_by_id: dict[str, str] = {}
    if field_ids:
        field_rows = (
            get_supabase_client()
            .table("fields")
            .select("id,name")
            .in_("id", field_ids)
            .execute()
            .data
        )
        fields_by_id = {
            str(field["id"]): field.get("name") or "Unknown field"
            for field in field_rows
            if field.get("id")
        }

    return [
        dict(game, field_name=fields_by_id.get(str(game.get("field_id")), "Unknown field"))
        for game in games
    ]


def _format_admin_games(games: list[dict[str, Any]]) -> list[dict[str, Any]]:
    games_with_field_names = _attach_field_names(games)
    return attach_participants_to_games(games_with_field_names)


def _get_games_by_statuses(
    statuses: list[str],
    *,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    supabase = get_supabase_client()
    query = (
        supabase
        .table("games")
        .select("*")
        .in_("status", statuses)
        .order("started_at", desc=True)
    )

    if limit is not None:
        query = query.limit(limit)

    games = query.execute().data
    if statuses == ACTIVE_GAME_STATUSES:
        games = finish_expired_games(games, supabase=supabase)

    return _format_admin_games(games)


def _get_game(game_id: str) -> dict[str, Any]:
    response = (
        get_supabase_client()
        .table("games")
        .select("*")
        .eq("id", game_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")

    return response.data[0]


def _ensure_admin_active_game(game: dict[str, Any]) -> None:
    try:
        ensure_game_is_actionable(game, supabase=get_supabase_client())
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Game is not active",
        ) from exc


@router.get("/games")
def get_admin_games(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    _: dict[str, Any] = Depends(require_admin),
):
    if status_filter and status_filter not in ("active", "finished"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be active or finished",
        )

    if status_filter == "active":
        return {"active": _get_games_by_statuses(ACTIVE_GAME_STATUSES)}

    if status_filter == "finished":
        return {"finished": _get_games_by_statuses(FINISHED_GAME_STATUSES, limit=FINISHED_GAMES_LIMIT)}

    return {
        "active": _get_games_by_statuses(ACTIVE_GAME_STATUSES),
        "finished": _get_games_by_statuses(FINISHED_GAME_STATUSES, limit=FINISHED_GAMES_LIMIT),
    }


@router.post("/games/{game_id}/close")
def close_admin_game(game_id: str, _: dict[str, Any] = Depends(require_admin)):
    game = _get_game(game_id)
    _ensure_admin_active_game(game)

    response = (
        get_supabase_client()
        .table("games")
        .update({"status": "finished"})
        .eq("id", game_id)
        .execute()
    )
    return {"message": "Game closed", "game": response.data[0]}


@router.post("/games/{game_id}/extend")
def extend_admin_game(game_id: str, _: dict[str, Any] = Depends(require_admin)):
    game = _get_game(game_id)
    _ensure_admin_active_game(game)

    expires_at = game.get("expires_at")
    if not expires_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Game expires_at is missing",
        )

    current_expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    new_expires = current_expires + timedelta(hours=1)
    response = (
        get_supabase_client()
        .table("games")
        .update({"expires_at": new_expires.isoformat()})
        .eq("id", game_id)
        .execute()
    )

    return {
        "message": "Game extended by 1 hour",
        "new_expires_at": new_expires.isoformat(),
        "game": response.data[0],
    }


def _update_field_approval(field_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    response = (
        get_supabase_client()
        .table("fields")
        .update(updates)
        .eq("id", field_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found",
        )

    return response.data[0]
