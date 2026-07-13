import math
from datetime import datetime, timezone
from typing import Any, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.dependencies import require_active_user, require_admin
from app.db.supabase import get_supabase_client
from app.errors import raise_api_error, validate_uuid_id
from app.rate_limit import check_rate_limit_by_user
from app.routers.game_payloads import get_game_payloads_for_fields
from app.services.content_moderation import (
    MAX_LENGTH_DEFAULT,
    MAX_LENGTH_SHORT,
    MIN_LENGTH_NAME,
    validate_field_submission,
    validate_text,
)
from app.services.duplicate_detection import RISK_CONFIRMED, score_pair

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
    name: str = Field(min_length=2, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    sport_type: Literal["football", "basketball", "both"]
    surface_type: str = Field(max_length=100)
    has_nets: bool
    has_water: bool
    opening_hours: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field name cannot be empty")
        return stripped


ALLOWED_FIELD_STATUSES = {"open", "closed", "renovation"}


class FieldStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status_value(cls, value: str) -> str:
        if value not in ALLOWED_FIELD_STATUSES:
            from app.errors import raise_api_error
            raise_api_error(
                status_code=400,
                code="VALIDATION_ERROR",
                message="Invalid field status",
            )
        return value


# Controlled removal reasons for moderated field deletion. Kept distinct
# from field_reports' category enum (a user-facing report reason) since
# this drives an admin-only, irreversible-from-the-public-map action and
# needs a couple of values reports don't (school_property, safety_issue,
# invalid_field).
FIELD_REMOVAL_REASONS = {
    "field_does_not_exist",
    "duplicate_field",
    "private_field",
    "school_property",
    "wrong_location",
    "invalid_field",
    "safety_issue",
    "other",
}


class FieldRemoveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if value not in FIELD_REMOVAL_REASONS:
            raise ValueError("Invalid removal reason")
        return value

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        stripped = value.strip()
        return stripped or None


def remove_field_record(
    field_id: str, body: FieldRemoveBody, actor_user_id: str
) -> dict[str, Any]:
    field_id = validate_uuid_id(field_id, "field_id")
    supabase = get_supabase_client()

    existing_response = (
        supabase.table("fields").select("*").eq("id", field_id).execute()
    )
    if not existing_response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )

    if existing_response.data[0].get("removed_at") is not None:
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="FIELD_ALREADY_REMOVED",
            message="Field has already been removed",
        )

    update_payload = {
        "removed_at": datetime.now(timezone.utc).isoformat(),
        "removed_by": actor_user_id,
        "removal_reason": body.reason,
    }

    try:
        # The removed_at IS NULL guard makes this a single atomic
        # check-and-set at the database level: if another request removed
        # the field between our read above and this write, zero rows match
        # and we fall through to the 409 below instead of double-applying
        # the removal or clobbering the first actor's reason.
        response = (
            supabase.table("fields")
            .update(update_payload)
            .eq("id", field_id)
            .is_("removed_at", "null")
            .execute()
        )
    except Exception:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to remove field",
        )

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="FIELD_ALREADY_REMOVED",
            message="Field has already been removed",
        )

    return {"message": "Field removed", "field": response.data[0]}


def update_field_status_record(field_id: str, body: FieldStatusUpdate) -> dict[str, Any]:
    field_id = validate_uuid_id(field_id, "field_id")
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


# Fields an authorized editor may change. Anything else (id, added_by,
# approval_status, verified, status, created_at, ...) is admin-managed
# through its own dedicated endpoint (approve/reject/status) or is
# immutable, and is silently out of scope here — never mass-assigned.
FIELD_UPDATE_ALLOWED_FIELDS = {
    "name",
    "lat",
    "lng",
    "sport_type",
    "surface_type",
    "has_nets",
    "has_water",
    "opening_hours",
    "city",
    "notes",
}
# These may never be nulled out once the field exists — they may be
# omitted from a PATCH body (left unchanged), but not set to null.
FIELD_UPDATE_REQUIRED_WHEN_PRESENT = {
    "name",
    "lat",
    "lng",
    "sport_type",
    "surface_type",
    "has_nets",
    "has_water",
}
# Coordinate/name/city changes are the only edits that can produce a new
# duplicate relative to another field, so duplicate detection only needs
# to re-run when one of these actually changes.
FIELD_UPDATE_DUPLICATE_TRIGGER_FIELDS = {"name", "lat", "lng", "city"}


class FieldUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, max_length=200)
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lng: Optional[float] = Field(default=None, ge=-180, le=180)
    sport_type: Optional[Literal["football", "basketball", "both"]] = None
    surface_type: Optional[str] = Field(default=None, max_length=100)
    has_nets: Optional[bool] = None
    has_water: Optional[bool] = None
    opening_hours: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=1000)

    @field_validator("name", "surface_type", "opening_hours", "city", "notes")
    @classmethod
    def strip_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return value.strip()

    @field_validator("lat", "lng")
    @classmethod
    def reject_non_finite(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and not math.isfinite(value):
            raise ValueError("must be a finite number")
        return value


def _validate_field_update_content(provided: dict[str, Any]) -> None:
    """Re-runs content moderation only on the fields actually being changed.

    Unchanged fields on a legacy record are never re-validated here, so an
    edit to `city` alone cannot be blocked by a pre-existing `name` that
    would no longer pass today's moderation rules.
    """
    checks: list[tuple[str, Any, dict[str, Any]]] = []

    if "name" in provided:
        checks.append((
            "name",
            provided["name"],
            {
                "required": True,
                "min_length": MIN_LENGTH_NAME,
                "max_length": MAX_LENGTH_SHORT,
                "check_fake_names": True,
                "check_personal_data": True,
            },
        ))
    if provided.get("notes") is not None:
        checks.append((
            "notes",
            provided["notes"],
            {"max_length": MAX_LENGTH_DEFAULT, "check_urls": True, "check_personal_data": True},
        ))
    if provided.get("opening_hours") is not None:
        checks.append((
            "opening_hours",
            provided["opening_hours"],
            {"max_length": MAX_LENGTH_SHORT},
        ))
    if provided.get("city") is not None:
        checks.append((
            "city",
            provided["city"],
            {"max_length": MAX_LENGTH_SHORT, "check_fake_names": True},
        ))

    for field_name, value, kwargs in checks:
        result = validate_text(value, field_name=field_name, **kwargs)
        if not result.allowed:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="CONTENT_REJECTED",
                message=result.message,
            )


def _check_no_confirmed_duplicate(
    field_id: str, candidate: dict[str, Any], supabase: Any
) -> None:
    other_fields = (
        supabase.table("fields").select("*").is_("removed_at", "null").execute().data or []
    )
    for other in other_fields:
        if str(other.get("id")) == str(field_id):
            continue
        result = score_pair(candidate, other)
        if result is not None and result["risk_level"] == RISK_CONFIRMED:
            raise_api_error(
                status_code=status.HTTP_409_CONFLICT,
                code="FIELD_DUPLICATE",
                message="This change would make the field a duplicate of an existing field",
                details={"duplicate_field_id": other.get("id")},
            )


def update_field_record(field_id: str, body: FieldUpdate) -> dict[str, Any]:
    field_id = validate_uuid_id(field_id, "field_id")
    provided = body.model_dump(exclude_unset=True)

    if not provided:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="FIELD_EDIT_EMPTY",
            message="No fields provided to update",
        )

    for key in FIELD_UPDATE_REQUIRED_WHEN_PRESENT:
        if key in provided and provided[key] is None:
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message=f"{key} cannot be empty",
            )

    if provided.get("name") == "":
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Field name cannot be empty",
        )
    if provided.get("surface_type") == "":
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Surface type cannot be empty",
        )

    _validate_field_update_content(provided)

    supabase = get_supabase_client()
    existing_response = (
        supabase.table("fields").select("*").eq("id", field_id).execute()
    )
    if not existing_response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )
    existing_field = existing_response.data[0]

    if FIELD_UPDATE_DUPLICATE_TRIGGER_FIELDS & provided.keys():
        candidate = {**existing_field, **provided}
        _check_no_confirmed_duplicate(field_id, candidate, supabase)

    update_payload = dict(provided)
    update_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        response = (
            supabase.table("fields")
            .update(update_payload)
            .eq("id", field_id)
            .execute()
        )
    except Exception:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to update field",
        )

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )

    return {"message": "Field updated", "field": response.data[0]}


@router.get("/")
def get_fields(
    north: Optional[float] = Query(default=None),
    south: Optional[float] = Query(default=None),
    east: Optional[float] = Query(default=None),
    west: Optional[float] = Query(default=None),
):
    for coord_name, coord_val, min_val, max_val in [
        ("north", north, -90.0, 90.0),
        ("south", south, -90.0, 90.0),
        ("east", east, -180.0, 180.0),
        ("west", west, -180.0, 180.0),
    ]:
        if coord_val is not None:
            if not (min_val <= coord_val <= max_val):
                raise_api_error(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="VALIDATION_ERROR",
                    message=f"{coord_name} must be between {min_val} and {max_val}",
                )
    if north is not None and south is not None and north < south:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="north must be greater than or equal to south",
        )
    if east is not None and west is not None and east < west:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="east must be greater than or equal to west (antimeridian crossing not supported)",
        )
    supabase = get_supabase_client()

    has_bounds = all(v is not None for v in (north, south, east, west))
    if has_bounds:
        query = (
            supabase.table("fields")
            .select("*")
            .eq("verified", True)
            .eq("approval_status", "approved")
            .eq("status", "open")
            .is_("removed_at", "null")
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
                .is_("removed_at", "null")
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
    field_id = validate_uuid_id(field_id, "field_id")
    supabase = get_supabase_client()
    response = supabase.table("fields").select("*").eq("id", field_id).execute()
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )
    field = response.data[0]
    if field.get("removed_at") is not None:
        # Same code/message as a genuinely missing field — a removed field's
        # existence and moderation reason are not public information.
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )

    active_games_by_field_id, upcoming_games_by_field_id = get_game_payloads_for_fields([field_id])
    field["active_game"] = active_games_by_field_id.get(field_id)
    field["upcoming_games"] = upcoming_games_by_field_id.get(field_id, [])
    return field


@router.post("/")
def create_field(field: FieldCreate, current_user: dict[str, Any] = Depends(require_active_user)):
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "fields_create", [(3, 60), (10, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

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

