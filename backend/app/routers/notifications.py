from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.supabase import get_supabase_client

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationPreference(BaseModel):
    user_id: str
    notification_type: str  # radius / city / specific_field
    radius_km: Optional[int] = None
    city: Optional[str] = None
    field_id: Optional[str] = None


@router.get("/preferences")
def get_preferences(user_id: str):
    supabase = get_supabase_client()
    response = (
        supabase.table("notification_preferences")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    return response.data


@router.put("/preferences")
def save_preferences(pref: NotificationPreference):
    supabase = get_supabase_client()

    existing = (
        supabase.table("notification_preferences")
        .select("*")
        .eq("user_id", pref.user_id)
        .eq("notification_type", pref.notification_type)
        .execute()
    )

    data = {
        "user_id": pref.user_id,
        "notification_type": pref.notification_type,
        "radius_km": pref.radius_km,
        "city": pref.city,
        "field_id": pref.field_id,
    }

    if existing.data:
        response = (
            supabase.table("notification_preferences")
            .update(data)
            .eq("user_id", pref.user_id)
            .eq("notification_type", pref.notification_type)
            .execute()
        )
    else:
        response = (
            supabase.table("notification_preferences")
            .insert(data)
            .execute()
        )

    return {"message": "Preference saved", "preference": response.data[0]}