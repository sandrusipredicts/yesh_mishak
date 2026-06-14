from math import asin, cos, radians, sin, sqrt
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from app.auth.dependencies import get_current_user
from app.db.supabase import get_supabase_client

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationPreference(BaseModel):
    enabled: bool = True
    sport_type: str = "both"
    notification_type: str = "radius"
    radius_km: Optional[float] = Field(default=None, gt=0)
    lat: Optional[float] = None
    lng: Optional[float] = None
    city: Optional[str] = None
    field_id: Optional[str] = None


class NotificationCandidateRequest(BaseModel):
    field_id: str
    sport_type: str


class NotificationSettings(BaseModel):
    distance_enabled: bool = True
    distance_radius_km: float = Field(default=5, ge=1, le=20)
    city_enabled: bool = False
    city_name: str = "ירוחם"
    specific_fields_enabled: bool = False
    selected_field_ids: list[str] = Field(default_factory=list)


SETTINGS_PAYLOAD_KEYS = {
    "distance_enabled",
    "distance_radius_km",
    "city_enabled",
    "city_name",
    "specific_fields_enabled",
    "selected_field_ids",
}


def _validate_preference(pref: NotificationPreference) -> None:
    if pref.sport_type not in ("football", "basketball", "both"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sport_type")

    if pref.notification_type not in ("radius", "city", "specific_field"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notification_type")

    if pref.notification_type == "radius" and (
        pref.radius_km is None or pref.lat is None or pref.lng is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Radius preferences require radius_km, lat, and lng",
        )

    if pref.notification_type == "specific_field" and not pref.field_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="specific_field preferences require field_id",
        )


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


@router.get("/preferences")
def get_preferences(current_user: dict[str, Any] = Depends(get_current_user)):
    response = (
        get_supabase_client()
        .table("notification_preferences")
        .select("*")
        .eq("user_id", current_user["id"])
        .execute()
    )
    return response.data


def _is_settings_payload(body: dict[str, Any]) -> bool:
    if not isinstance(body, dict):
        return False

    body_keys = {str(key).strip() for key in body}
    return bool(SETTINGS_PAYLOAD_KEYS.intersection(body_keys))


def _save_preference_row(
    supabase: Any,
    row: dict[str, Any],
    existing_row: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if existing_row:
        response = (
            supabase.table("notification_preferences")
            .update(row)
            .eq("id", existing_row["id"])
            .execute()
        )
    else:
        response = supabase.table("notification_preferences").insert(row).execute()

    return response.data or []


def _field_key(field_id: Any) -> str:
    return str(field_id) if field_id else ""


def _save_settings(body: dict[str, Any], current_user: dict[str, Any]) -> dict[str, Any]:
    settings_data = dict(body)

    if settings_data.get("selected_field_ids") is None:
        settings_data["selected_field_ids"] = []

    settings = NotificationSettings(**settings_data)
    supabase = get_supabase_client()
    user_id = current_user["id"]

    existing_response = (
        supabase.table("notification_preferences")
        .select("*")
        .eq("user_id", user_id)
        .in_("notification_type", ["radius", "city", "specific_field"])
        .execute()
    )
    existing_rows = existing_response.data or []

    existing_by_type: dict[str, dict[str, Any]] = {}
    existing_specific_by_field: dict[str, dict[str, Any]] = {}

    for row in existing_rows:
        notification_type = row.get("notification_type")

        if notification_type == "specific_field":
            field_key = _field_key(row.get("field_id"))
            existing_specific_by_field.setdefault(field_key, row)
        elif notification_type in ("radius", "city"):
            existing_by_type.setdefault(notification_type, row)

    saved_preferences: list[dict[str, Any]] = []
    saved_preferences.extend(
        _save_preference_row(
            supabase,
            {
                "user_id": user_id,
                "enabled": settings.distance_enabled,
                "sport_type": "both",
                "notification_type": "radius",
                "radius_km": settings.distance_radius_km,
                "lat": None,
                "lng": None,
                "city": None,
                "field_id": None,
            },
            existing_by_type.get("radius"),
        )
    )
    saved_preferences.extend(
        _save_preference_row(
            supabase,
            {
                "user_id": user_id,
                "enabled": settings.city_enabled,
                "sport_type": "both",
                "notification_type": "city",
                "radius_km": None,
                "lat": None,
                "lng": None,
                "city": settings.city_name,
                "field_id": None,
            },
            existing_by_type.get("city"),
        )
    )

    selected_field_ids = list(dict.fromkeys(settings.selected_field_ids))
    desired_specific_rows = [
        {
            "user_id": user_id,
            "enabled": settings.specific_fields_enabled,
            "sport_type": "both",
            "notification_type": "specific_field",
            "radius_km": None,
            "lat": None,
            "lng": None,
            "city": None,
            "field_id": field_id,
        }
        for field_id in selected_field_ids
    ]

    if not desired_specific_rows:
        desired_specific_rows.append(
            {
                "user_id": user_id,
                "enabled": settings.specific_fields_enabled,
                "sport_type": "both",
                "notification_type": "specific_field",
                "radius_km": None,
                "lat": None,
                "lng": None,
                "city": None,
                "field_id": None,
            }
        )

    kept_specific_ids: set[str] = set()

    for row in desired_specific_rows:
        existing_row = existing_specific_by_field.get(_field_key(row.get("field_id")))
        saved_rows = _save_preference_row(supabase, row, existing_row)
        saved_preferences.extend(saved_rows)

        if existing_row:
            kept_specific_ids.add(str(existing_row["id"]))
        elif saved_rows:
            kept_specific_ids.add(str(saved_rows[0]["id"]))

    stale_specific_ids = [
        row["id"]
        for row in existing_rows
        if row.get("notification_type") == "specific_field" and str(row["id"]) not in kept_specific_ids
    ]

    if stale_specific_ids:
        (
            supabase.table("notification_preferences")
            .delete()
            .in_("id", stale_specific_ids)
            .execute()
        )

    return {"message": "Preferences saved", "preferences": saved_preferences}


@router.put("/preferences")
def save_preferences(
    body: dict[str, Any] = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    try:
        if _is_settings_payload(body):
            return _save_settings(body, current_user)

        pref = NotificationPreference(**body)
    except ValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=error.errors()) from error

    _validate_preference(pref)
    supabase = get_supabase_client()

    existing = (
        supabase.table("notification_preferences")
        .select("id")
        .eq("user_id", current_user["id"])
        .eq("notification_type", pref.notification_type)
        .eq("sport_type", pref.sport_type)
        .limit(1)
        .execute()
    )

    data = {
        "user_id": current_user["id"],
        "enabled": pref.enabled,
        "sport_type": pref.sport_type,
        "notification_type": pref.notification_type,
        "radius_km": pref.radius_km,
        "lat": pref.lat,
        "lng": pref.lng,
        "city": pref.city,
        "field_id": pref.field_id,
    }

    if existing.data:
        response = (
            supabase.table("notification_preferences")
            .update(data)
            .eq("id", existing.data[0]["id"])
            .execute()
        )
    else:
        response = supabase.table("notification_preferences").insert(data).execute()

    return {"message": "Preference saved", "preference": response.data[0]}


@router.post("/candidates")
def get_notification_candidates(
    body: NotificationCandidateRequest,
    _: dict[str, Any] = Depends(get_current_user),
):
    if body.sport_type not in ("football", "basketball"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sport_type")

    supabase = get_supabase_client()
    field_response = (
        supabase.table("fields")
        .select("id,lat,lng,sport_type")
        .eq("id", body.field_id)
        .limit(1)
        .execute()
    )
    if not field_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")

    field = field_response.data[0]
    preferences = (
        supabase.table("notification_preferences")
        .select("*")
        .eq("enabled", True)
        .execute()
    )

    candidates: list[dict[str, str]] = []
    seen_user_ids: set[str] = set()

    for pref in preferences.data:
        if pref.get("sport_type") not in (body.sport_type, "both"):
            continue

        reason = None
        if pref.get("notification_type") == "specific_field" and pref.get("field_id") == body.field_id:
            reason = "specific_field_and_sport_match"
        elif pref.get("notification_type") == "radius":
            if pref.get("lat") is None or pref.get("lng") is None or pref.get("radius_km") is None:
                continue

            distance = _distance_km(
                float(pref["lat"]),
                float(pref["lng"]),
                float(field["lat"]),
                float(field["lng"]),
            )
            if distance <= float(pref["radius_km"]):
                reason = "within_radius_and_sport_match"

        user_id = pref.get("user_id")
        if reason and user_id and user_id not in seen_user_ids:
            seen_user_ids.add(user_id)
            candidates.append({"user_id": user_id, "reason": reason})

    return candidates
