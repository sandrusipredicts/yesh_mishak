from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.dependencies import require_active_user, require_admin
from app.db.supabase import get_supabase_client
from app.errors import raise_api_error
from app.routers.game_payloads import get_game_payloads_for_fields
from app.services.content_moderation import validate_field_submission

router = APIRouter(prefix="/fields", tags=["fields"])
FIELDS_PAGE_SIZE = 1000


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
    city: Optional[str] = None
    notes: Optional[str] = None


ALLOWED_FIELD_STATUSES = {"open", "closed", "renovation"}


class FieldStatusUpdate(BaseModel):
    status: str  # open / closed / renovation


def update_field_status_record(field_id: str, body: FieldStatusUpdate) -> dict[str, Any]:
    if body.status not in ALLOWED_FIELD_STATUSES:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invalid field status",
        )

    supabase = get_supabase_client()
    response = (
        supabase.table("fields")
        .update({"status": body.status})
        .eq("id", field_id)
        .execute()
    )
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )
    return {"message": "Status updated", "field": response.data[0]}


@router.get("/")
def get_fields(
    north: Optional[float] = Query(default=None),
    south: Optional[float] = Query(default=None),
    east: Optional[float] = Query(default=None),
    west: Optional[float] = Query(default=None),
):
    supabase = get_supabase_client()

    has_bounds = all(v is not None for v in (north, south, east, west))
    if has_bounds:
        query = (
            supabase.table("fields")
            .select("*")
            .eq("verified", True)
            .eq("approval_status", "approved")
            .eq("status", "open")
            .gte("lat", south)
            .lte("lat", north)
            .gte("lng", west)
            .lte("lng", east)
            .execute()
        )
        fields = query.data or []
    else:
        fields = []
        offset = 0
        while True:
            response = (
                supabase.table("fields")
                .select("*")
                .eq("verified", True)
                .eq("approval_status", "approved")
                .eq("status", "open")
                .range(offset, offset + FIELDS_PAGE_SIZE - 1)
                .execute()
            )
            page = response.data or []
            fields.extend(page)

            if len(page) < FIELDS_PAGE_SIZE:
                break

            offset += FIELDS_PAGE_SIZE

    field_ids = [str(field["id"]) for field in fields if field.get("id")]
    active_games_by_field_id, upcoming_games_by_field_id = get_game_payloads_for_fields(field_ids)

    for field in fields:
        field_id = str(field.get("id"))
        field["active_game"] = active_games_by_field_id.get(field_id)
        field["upcoming_games"] = upcoming_games_by_field_id.get(field_id, [])

    return fields


@router.get("/{field_id}")
def get_field(field_id: str):
    supabase = get_supabase_client()
    response = supabase.table("fields").select("*").eq("id", field_id).execute()
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )
    field = response.data[0]

    active_games_by_field_id, upcoming_games_by_field_id = get_game_payloads_for_fields([field_id])
    field["active_game"] = active_games_by_field_id.get(field_id)
    field["upcoming_games"] = upcoming_games_by_field_id.get(field_id, [])
    return field


@router.post("/")
def create_field(field: FieldCreate, current_user: dict[str, Any] = Depends(require_active_user)):
    moderation = validate_field_submission(
        name=field.name,
        notes=field.notes,
        opening_hours=field.opening_hours,
        city=field.city,
    )
    if not moderation.allowed:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CONTENT_REJECTED",
            message=moderation.message,
        )

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
        "city": field.city,
        "notes": field.notes,
        "verified": False,
        "approval_status": "pending",
        "status": "open",
        "added_by": current_user["id"],
    }
    try:
        response = supabase.table("fields").insert(data).execute()
    except Exception:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to create field",
        )

    return {"message": "Field submitted for VAR approval", "field": response.data[0]}


@router.patch("/{field_id}/status")
def update_field_status(
    field_id: str,
    body: FieldStatusUpdate,
    _: dict[str, Any] = Depends(require_admin),
):
    return update_field_status_record(field_id, body)

