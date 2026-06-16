from datetime import datetime, timezone
import logging
from math import asin, cos, radians, sin, sqrt
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ValidationError

from app.auth.dependencies import get_current_user, require_admin
from app.core.config import get_settings
from app.db.supabase import get_supabase_client, get_supabase_service_role_client

router = APIRouter(prefix="/notifications", tags=["notifications"])
logger = logging.getLogger(__name__)

NOTIFICATION_DEBUG_EXPECTED_USER_ID = "5b03fef8-20c1-49bc-a4fb-7879edf449e1"


def _supabase_project_ref(supabase_url: str) -> str:
    hostname = urlparse(supabase_url).hostname or ""
    return hostname.split(".")[0] if hostname.endswith(".supabase.co") else hostname


def _response_debug(response: Any) -> dict[str, Any]:
    return {
        "data": getattr(response, "data", None),
        "error": getattr(response, "error", None),
        "count": getattr(response, "count", None),
    }


def _query_notifications_for_debug(supabase: Any, user_id: str) -> dict[str, Any]:
    try:
        response = (
            supabase.table("notifications")
            .select("*", count="exact")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return _response_debug(response)
    except Exception as error:
        logger.exception("Notification debug query failed")
        return {"data": None, "error": str(error), "count": None}


def _query_rls_catalog_for_debug(supabase: Any) -> dict[str, Any]:
    try:
        response = (
            supabase.schema("pg_catalog")
            .table("pg_class")
            .select("relname,relrowsecurity,relforcerowsecurity")
            .eq("relname", "notifications")
            .limit(1)
            .execute()
        )
        return _response_debug(response)
    except Exception as error:
        logger.info("Notification RLS catalog debug query unavailable: %s", error)
        return {"data": None, "error": str(error), "count": None}


def _query_rls_policies_for_debug(supabase: Any) -> dict[str, Any]:
    try:
        response = (
            supabase.schema("pg_catalog")
            .table("pg_policies")
            .select("schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check")
            .eq("tablename", "notifications")
            .execute()
        )
        return _response_debug(response)
    except Exception as error:
        logger.info("Notification RLS policy debug query unavailable: %s", error)
        return {"data": None, "error": str(error), "count": None}


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
    distance_lat: Optional[float] = None
    distance_lng: Optional[float] = None
    city_enabled: bool = False
    city_name: str = "ירוחם"
    specific_fields_enabled: bool = False
    selected_field_ids: list[str] = Field(default_factory=list)


SETTINGS_PAYLOAD_KEYS = {
    "distance_enabled",
    "distance_radius_km",
    "distance_lat",
    "distance_lng",
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


def _normalize_city(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _find_notification_candidates(
    supabase: Any,
    field: dict[str, Any],
    sport_type: str,
) -> list[dict[str, str]]:
    preferences = (
        supabase.table("notification_preferences")
        .select("*")
        .eq("enabled", True)
        .execute()
    )

    candidates: list[dict[str, str]] = []
    seen_user_ids: set[str] = set()

    for pref in preferences.data:
        if pref.get("sport_type") not in (sport_type, "both"):
            continue

        reason = None
        if pref.get("notification_type") == "specific_field" and pref.get("field_id") == field.get("id"):
            reason = "specific_field_and_sport_match"
        elif pref.get("notification_type") == "city":
            if _normalize_city(pref.get("city")) and _normalize_city(pref.get("city")) == _normalize_city(field.get("city")):
                reason = "city_and_sport_match"
        elif pref.get("notification_type") == "radius":
            if (
                pref.get("lat") is None
                or pref.get("lng") is None
                or pref.get("radius_km") is None
                or field.get("lat") is None
                or field.get("lng") is None
            ):
                continue

            try:
                distance = _distance_km(
                    float(pref["lat"]),
                    float(pref["lng"]),
                    float(field["lat"]),
                    float(field["lng"]),
                )
            except (TypeError, ValueError):
                continue

            if distance <= float(pref["radius_km"]):
                reason = "within_radius_and_sport_match"

        user_id = pref.get("user_id")
        if reason and user_id and user_id not in seen_user_ids:
            seen_user_ids.add(user_id)
            candidates.append({"user_id": user_id, "reason": reason})

    return candidates


def create_game_created_notifications(
    supabase: Any,
    game: dict[str, Any],
    field: dict[str, Any],
    organizer_id: str,
) -> list[dict[str, Any]]:
    candidates = _find_notification_candidates(supabase, field, str(game["sport_type"]))
    recipient_ids = [
        candidate["user_id"]
        for candidate in candidates
        if candidate.get("user_id") and candidate["user_id"] != organizer_id
    ]

    if not recipient_ids:
        return []

    service_supabase = get_supabase_service_role_client()
    existing_response = (
        service_supabase.table("notifications")
        .select("user_id")
        .eq("type", "game_created")
        .eq("game_id", game["id"])
        .in_("user_id", recipient_ids)
        .execute()
    )
    existing_user_ids = {row["user_id"] for row in existing_response.data or [] if row.get("user_id")}
    field_name = field.get("name") or "Unknown field"
    rows = [
        {
            "user_id": user_id,
            "type": "game_created",
            "title": "נפתח משחק חדש",
            "body": f"נפתח משחק {game['sport_type']} במגרש {field_name}",
            "game_id": game["id"],
            "field_id": field.get("id"),
            "read_at": None,
        }
        for user_id in recipient_ids
        if user_id not in existing_user_ids
    ]

    if not rows:
        return []

    return service_supabase.table("notifications").insert(rows).execute().data or []


@router.get("")
def get_notifications(
    debug: bool = Query(default=False),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    authenticated_user_id = str(current_user["id"])
    settings = get_settings()
    supabase_project_ref = _supabase_project_ref(settings.supabase_url)
    query_description = {
        "table": "notifications",
        "select": "*",
        "filters": [{"column": "user_id", "operator": "eq", "value": authenticated_user_id}],
        "order": {"column": "created_at", "desc": True},
    }
    logger.info(
        "GET /notifications authenticated_user_id=%s expected_user_id=%s matches_expected=%s query=%s",
        authenticated_user_id,
        NOTIFICATION_DEBUG_EXPECTED_USER_ID,
        authenticated_user_id == NOTIFICATION_DEBUG_EXPECTED_USER_ID,
        query_description,
    )
    anon_supabase = get_supabase_client()
    response = (
        anon_supabase.table("notifications")
        .select("*")
        .eq("user_id", authenticated_user_id)
        .order("created_at", desc=True)
        .execute()
    )
    logger.info(
        "GET /notifications raw notifications query result data=%s error=%s",
        getattr(response, "data", None),
        getattr(response, "error", None),
    )

    if debug:
        anon_query_result = _query_notifications_for_debug(anon_supabase, authenticated_user_id)
        service_role_configured = bool(settings.supabase_service_role_key)
        service_role_query_result = None
        rls_catalog_query_result = None

        if service_role_configured:
            service_supabase = get_supabase_service_role_client()
            service_role_query_result = _query_notifications_for_debug(
                service_supabase,
                authenticated_user_id,
            )
            rls_catalog_query_result = _query_rls_catalog_for_debug(service_supabase)

        anon_count = len(anon_query_result.get("data") or [])
        service_count = (
            len(service_role_query_result.get("data") or [])
            if service_role_query_result is not None
            else None
        )
        likely_rls_blocking = service_count is not None and service_count > anon_count
        debug_payload = {
            "supabase": {
                "project_ref": supabase_project_ref,
                "url_host": urlparse(settings.supabase_url).hostname,
            },
            "client_used_by_endpoint": {
                "client": "get_supabase_client",
                "env_var": "SUPABASE_KEY",
                "type": "anon key / publishable key",
                "is_service_role": False,
            },
            "clients_checked": {
                "anon_key": True,
                "service_role_key": service_role_configured,
            },
            "authenticated_user": {
                "id": authenticated_user_id,
                "email": current_user.get("email"),
                "name": current_user.get("name"),
            },
            "expected_user_id": NOTIFICATION_DEBUG_EXPECTED_USER_ID,
            "matches_expected_user_id": authenticated_user_id == NOTIFICATION_DEBUG_EXPECTED_USER_ID,
            "query": query_description,
            "table_column_check": {
                "table": "notifications",
                "user_id_column": "user_id",
            },
            "raw_supabase_results": {
                "actual_endpoint_query": {
                    "response_data": getattr(response, "data", None),
                    "response_error": getattr(response, "error", None),
                    "response_count": getattr(response, "count", None),
                },
                "endpoint_anon_response": _response_debug(response),
                "anon_exact_count_response": anon_query_result,
                "service_role_exact_count_response": service_role_query_result,
            },
            "rls_check": {
                "catalog_query_result": rls_catalog_query_result,
                "likely_blocked_by_rls_or_policy": likely_rls_blocking,
                "reason": (
                    "Service role can read more rows than anon endpoint client for the same user_id filter."
                    if likely_rls_blocking
                    else "No anon/service-role row-count difference observed, or service role is unavailable."
                ),
            },
            "notifications": response.data,
        }
        logger.info("GET /notifications debug payload=%s", debug_payload)
        return {
            **debug_payload,
        }

    return response.data


@router.get("/unread-count")
def get_unread_notification_count(current_user: dict[str, Any] = Depends(get_current_user)):
    response = (
        get_supabase_client()
        .table("notifications")
        .select("id")
        .eq("user_id", current_user["id"])
        .is_("read_at", "null")
        .execute()
    )
    return {"unread_count": len(response.data or [])}


@router.patch("/read-all")
def mark_all_notifications_read(current_user: dict[str, Any] = Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    (
        get_supabase_client()
        .table("notifications")
        .update({"read_at": now})
        .eq("user_id", current_user["id"])
        .is_("read_at", "null")
        .execute()
    )
    return {"message": "Notifications marked as read"}


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    now = datetime.now(timezone.utc).isoformat()
    response = (
        get_supabase_client()
        .table("notifications")
        .update({"read_at": now})
        .eq("id", notification_id)
        .eq("user_id", current_user["id"])
        .execute()
    )

    if not response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    return response.data[0]


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
                "lat": settings.distance_lat,
                "lng": settings.distance_lng,
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
    body: Any = Body(...),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    if not isinstance(body, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request body")

    is_settings_payload = _is_settings_payload(body)
    print(
        "PUT /notifications/preferences",
        {
            "body_keys": list(body.keys()),
            "is_settings_payload": is_settings_payload,
        },
    )

    try:
        if is_settings_payload:
            print("PUT /notifications/preferences routing to settings handler")
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
    _: dict[str, Any] = Depends(require_admin),
):
    if body.sport_type not in ("football", "basketball"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid sport_type")

    supabase = get_supabase_client()
    field_response = (
        supabase.table("fields")
        .select("*")
        .eq("id", body.field_id)
        .limit(1)
        .execute()
    )
    if not field_response.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")

    field = field_response.data[0]
    return _find_notification_candidates(supabase, field, body.sport_type)
