from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.db.supabase import get_supabase_client

router = APIRouter(prefix="/fields", tags=["fields"])


def _format_supabase_error(exc: Exception) -> dict[str, Any]:
    error: dict[str, Any] = {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "repr": repr(exc),
    }

    for attr in ("code", "message", "details", "hint"):
        value = getattr(exc, attr, None)
        if value:
            error[attr] = value

    if exc.args and isinstance(exc.args[0], dict):
        error.update(exc.args[0])

    return error


class FieldCreate(BaseModel):
    name: str
    lat: float
    lng: float
    sport_type: str  # football / basketball / both
    surface_type: str
    has_nets: bool
    has_water: bool
    opening_hours: Optional[str] = None
    notes: Optional[str] = None


class FieldStatusUpdate(BaseModel):
    status: str  # open / closed / renovation


@router.get("/")
def get_fields():
    supabase = get_supabase_client()
    response = (
        supabase.table("fields")
        .select("*")
        .eq("verified", True)
        .eq("approval_status", "approved")
        .execute()
    )
    return response.data


@router.get("/{field_id}")
def get_field(field_id: str):
    supabase = get_supabase_client()
    response = supabase.table("fields").select("*").eq("id", field_id).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Field not found")
    field = response.data[0]

    games_response = (
        supabase.table("games")
        .select("*")
        .eq("field_id", field_id)
        .eq("status", "open")
        .execute()
    )
    field["active_game"] = games_response.data[0] if games_response.data else None
    return field


@router.post("/")
def create_field(field: FieldCreate, current_user: dict[str, Any] = Depends(get_current_user)):
    supabase = get_supabase_client()
    data = {
        "name": field.name,
        "lat": field.lat,
        "lng": field.lng,
        "sport_type": field.sport_type,
        "surface_type": field.surface_type,
        "has_nets": field.has_nets,
        "has_water": field.has_water,
        "opening_hours": field.opening_hours,
        "notes": field.notes,
        "verified": False,
        "approval_status": "pending",
        "status": "open",
        "added_by": current_user["id"],
    }
    try:
        response = supabase.table("fields").insert(data).execute()
    except Exception as exc:
        error = _format_supabase_error(exc)
        print(f"Supabase fields insert failed: {error}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "Failed to create field",
                "supabase_error": error,
                "insert_data": data,
            },
        ) from exc

    return {"message": "Field submitted for VAR approval", "field": response.data[0]}


@router.patch("/{field_id}/status")
def update_field_status(field_id: str, body: FieldStatusUpdate):
    supabase = get_supabase_client()
    response = (
        supabase.table("fields")
        .update({"status": body.status})
        .eq("id", field_id)
        .execute()
    )
    if not response.data:
        raise HTTPException(status_code=404, detail="Field not found")
    return {"message": "Status updated", "field": response.data[0]}
