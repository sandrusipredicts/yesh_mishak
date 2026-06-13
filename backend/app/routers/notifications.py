from math import asin, cos, radians, sin, sqrt
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

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


@router.put("/preferences")
def save_preferences(
    pref: NotificationPreference,
    current_user: dict[str, Any] = Depends(get_current_user),
):
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
