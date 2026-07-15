import logging
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any, Optional, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, status
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, ValidationError

from app.auth.dependencies import require_active_user, require_admin
from app.errors import raise_api_error, validate_uuid_id
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.rate_limit import check_rate_limit_by_user
from app.routers.game_lifecycle import ACTIVE_GAME_STATUSES, parse_game_datetime
from app.services.firebase_push import FirebaseConfigError, send_fcm_notification
from app.services.notification_templates import render_notification_template
from app.services.push_delivery import (
    cas_update_attempt,
    handle_attempt_result,
    invalidate_sibling_attempts,
    record_and_claim_initial_delivery,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])
SCHEDULED_GAME_REMINDER_TYPE = "scheduled_game_reminder"
NOTIFICATION_RETENTION_DAYS = 90


class NotificationPreference(BaseModel):
    enabled: bool = True
    sport_type: Literal["football", "basketball", "both"] = "both"
    notification_type: Literal["radius", "city", "specific_field"] = "radius"
    radius_km: Optional[float] = Field(default=None, gt=0)
    lat: Optional[float] = None
    lng: Optional[float] = None
    city: Optional[str] = Field(default=None, max_length=100)
    field_id: Optional[str] = None


class NotificationCandidateRequest(BaseModel):
    field_id: str
    sport_type: Literal["football", "basketball"]


class NotificationSettings(BaseModel):
    distance_enabled: bool = True
    distance_radius_km: float = Field(default=5, ge=1, le=20)
    distance_lat: Optional[float] = None
    distance_lng: Optional[float] = None
    city_enabled: bool = False
    city_name: str = "ירוחם"
    specific_fields_enabled: bool = False
    selected_field_ids: list[str] = Field(default_factory=list)


class PushTokenRequest(BaseModel):
    token: str = Field(min_length=1)


class PushTokenDeleteRequest(BaseModel):
    token: str | None = None


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
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invalid sport_type",
        )

    if pref.notification_type not in ("radius", "city", "specific_field"):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invalid notification_type",
        )

    if pref.notification_type == "radius" and (
        pref.radius_km is None or pref.lat is None or pref.lng is None
    ):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Radius preferences require radius_km, lat, and lng",
        )

    if pref.notification_type == "specific_field" and not pref.field_id:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="specific_field preferences require field_id",
        )


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    earth_radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * earth_radius_km * asin(sqrt(a))


def _normalize_city(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _is_notification_unread(notification: dict[str, Any]) -> bool:
    """Return True when a notification has not been read.

    Supports both the ``read_at`` timestamp column and the legacy ``is_read``
    boolean column so the endpoint stays resilient regardless of which schema
    the live database currently has, and never crashes on missing metadata.
    """
    if notification.get("read_at"):
        return False
    if notification.get("is_read"):
        return False
    return True


def _uses_read_at_column(sample: dict[str, Any]) -> bool:
    """Decide which read-state column the live table exposes.

    Prefers the canonical ``read_at`` column, falls back to the legacy
    ``is_read`` boolean, and defaults to ``read_at`` when the row carries
    neither marker so behaviour stays correct once the migration is applied.
    """
    if "read_at" in sample:
        return True
    if "is_read" in sample:
        return False
    return True


def _mark_read_payload(sample: dict[str, Any], now: str) -> dict[str, Any]:
    if _uses_read_at_column(sample):
        return {"read_at": now}
    return {"is_read": True}


def _is_missing_column_error(error: APIError, column_name: str) -> bool:
    details = getattr(error, "args", [{}])[0]
    message = str(error)
    code = ""

    if isinstance(details, dict):
        message = f"{message} {details.get('message') or ''}"
        code = str(details.get("code") or "")

    return (code == "42703" or "42703" in message) and column_name in message


def _with_notification_target_aliases(notification: dict[str, Any]) -> dict[str, Any]:
    normalized_notification = dict(notification)
    data = normalized_notification.get("data")
    if not isinstance(data, dict):
        data = {}

    if not normalized_notification.get("game_id") and "related_game_id" in normalized_notification:
        normalized_notification["game_id"] = normalized_notification.get("related_game_id")
    if not normalized_notification.get("game_id") and data.get("game_id"):
        normalized_notification["game_id"] = data.get("game_id")

    if not normalized_notification.get("field_id") and "related_field_id" in normalized_notification:
        normalized_notification["field_id"] = normalized_notification.get("related_field_id")
    if not normalized_notification.get("field_id") and data.get("field_id"):
        normalized_notification["field_id"] = data.get("field_id")

    return normalized_notification


def _push_data(notification: dict[str, Any]) -> dict[str, Any]:
    normalized_notification = _with_notification_target_aliases(notification)
    data = normalized_notification.get("data")
    push_payload = dict(data) if isinstance(data, dict) else {}
    push_payload.update({
        "notification_id": normalized_notification.get("id"),
        "type": normalized_notification.get("type"),
        "game_id": normalized_notification.get("game_id"),
        "field_id": normalized_notification.get("field_id"),
    })
    return push_payload


def _delete_push_token(client: Any, token: str) -> None:
    client.table("push_tokens").delete().eq("token", token).execute()


def _send_push_to_tokens(
    client: Any,
    tokens: list[dict[str, Any]],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    suppress_config_error: bool = True,
) -> dict[str, int]:
    sent = 0
    invalid_tokens = 0
    notification_type = str((data or {}).get("type") or "unknown")
    notification_id = (data or {}).get("notification_id") if data else None
    track_delivery = notification_id is not None

    for token_row in tokens:
        token = token_row.get("token")
        if not token:
            continue

        attempt_row = None
        if track_delivery:
            attempt_row = record_and_claim_initial_delivery(
                client,
                notification_id=str(notification_id),
                push_token_id=str(token_row["id"]),
                token=token,
                title=title,
                body=body,
                data=data,
            )
            if attempt_row is None:
                continue

        try:
            result = send_fcm_notification(token, title, body, data)
        except FirebaseConfigError as exc:
            if attempt_row:
                handle_attempt_result(
                    client, attempt_row["id"], attempt_row["lease_id"],
                    token_row.get("id"), token,
                    None, exc,
                    attempt_row["attempt_count"], attempt_row["max_attempts"],
                )
            if not suppress_config_error:
                raise
            logger.error(
                "push notification configuration failure",
                extra={
                    "event": "notifications.push.failure",
                    "notification_type": notification_type,
                    "external_service": "firebase_fcm",
                    "recipient_count": len(tokens),
                    "sent_count": sent,
                    "invalid_token_count": invalid_tokens,
                    "error_code": "FIREBASE_CONFIG_ERROR",
                    "exception_type": exc.__class__.__name__,
                    "result": "failure",
                },
            )
            return {"sent": sent, "invalid_tokens": invalid_tokens}
        except Exception as exc:
            if attempt_row:
                handle_attempt_result(
                    client, attempt_row["id"], attempt_row["lease_id"],
                    token_row.get("id"), token,
                    None, exc,
                    attempt_row["attempt_count"], attempt_row["max_attempts"],
                    delete_token_fn=_delete_push_token,
                )
            logger.warning(
                "push notification send failed",
                extra={
                    "event": "notifications.push.failure",
                    "notification_type": notification_type,
                    "external_service": "firebase_fcm",
                    "recipient_count": len(tokens),
                    "sent_count": sent,
                    "invalid_token_count": invalid_tokens,
                    "error_code": "PUSH_SEND_FAILED",
                    "exception_type": exc.__class__.__name__,
                    "result": "partial_failure",
                },
                exc_info=True,
            )
            continue

        if result.get("invalid_token"):
            invalid_tokens += 1
            if attempt_row:
                handle_attempt_result(
                    client, attempt_row["id"], attempt_row["lease_id"],
                    token_row.get("id"), token,
                    result, None,
                    attempt_row["attempt_count"], attempt_row["max_attempts"],
                    delete_token_fn=_delete_push_token,
                )
            else:
                _delete_push_token(client, token)
            logger.warning(
                "invalid push token removed",
                extra={
                    "event": "notifications.push.failure",
                    "notification_type": notification_type,
                    "external_service": "firebase_fcm",
                    "status_code": result.get("status_code"),
                    "recipient_count": len(tokens),
                    "sent_count": sent,
                    "invalid_token_count": invalid_tokens,
                    "error_code": "INVALID_PUSH_TOKEN",
                    "result": "partial_failure",
                },
            )
        elif result.get("ok"):
            sent += 1
            if attempt_row:
                handle_attempt_result(
                    client, attempt_row["id"], attempt_row["lease_id"],
                    token_row.get("id"), token,
                    result, None,
                    attempt_row["attempt_count"], attempt_row["max_attempts"],
                )

    return {"sent": sent, "invalid_tokens": invalid_tokens}


def _send_push_for_notifications(
    client: Any,
    notifications: list[dict[str, Any]],
) -> dict[str, int]:
    if not notifications:
        return {"sent": 0, "invalid_tokens": 0}

    user_ids = list(
        dict.fromkeys(
            str(notification["user_id"])
            for notification in notifications
            if notification.get("user_id")
        )
    )
    if not user_ids:
        return {"sent": 0, "invalid_tokens": 0}

    tokens = (
        client.table("push_tokens")
        .select("*")
        .in_("user_id", user_ids)
        .execute()
        .data
        or []
    )
    tokens_by_user_id: dict[str, list[dict[str, Any]]] = {}
    for token in tokens:
        tokens_by_user_id.setdefault(str(token.get("user_id")), []).append(token)

    totals = {"sent": 0, "invalid_tokens": 0}
    for notification in notifications:
        user_tokens = tokens_by_user_id.get(str(notification.get("user_id")), [])
        result = _send_push_to_tokens(
            client,
            user_tokens,
            str(notification.get("title") or ""),
            str(notification.get("body") or ""),
            _push_data(notification),
        )
        totals["sent"] += result["sent"]
        totals["invalid_tokens"] += result["invalid_tokens"]

    return totals


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
        if (
            pref.get("notification_type") == "specific_field"
            and _field_key(pref.get("field_id"))
            and _field_key(pref.get("field_id")) == _field_key(field.get("id"))
        ):
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
    try:
        candidates = _find_notification_candidates(supabase, field, str(game["sport_type"]))
        recipient_ids = [
            candidate["user_id"]
            for candidate in candidates
            if candidate.get("user_id") and candidate["user_id"] != organizer_id
        ]

        if not recipient_ids:
            return []

        service_supabase = get_supabase_service_role_client()
        game_id_column = "game_id"
        field_id_column = "field_id"

        try:
            existing_response = (
                service_supabase.table("notifications")
                .select("user_id")
                .eq("type", "game_created")
                .eq(game_id_column, game["id"])
                .in_("user_id", recipient_ids)
                .execute()
            )
        except APIError as error:
            if not _is_missing_column_error(error, "notifications.game_id"):
                raise

            game_id_column = "related_game_id"
            field_id_column = "related_field_id"
            existing_response = (
                service_supabase.table("notifications")
                .select("user_id")
                .eq("type", "game_created")
                .eq(game_id_column, game["id"])
                .in_("user_id", recipient_ids)
                .execute()
            )

        existing_user_ids = {row["user_id"] for row in existing_response.data or [] if row.get("user_id")}
        field_name = field.get("name") or "Unknown field"
        rendered = render_notification_template(
            "game_created", "he",
            {"sport_type": game["sport_type"], "field_name": field_name},
        )
        rows = [
            {
                "user_id": user_id,
                "type": "game_created",
                "title": rendered["title"],
                "body": rendered["body"],
                game_id_column: game["id"],
                field_id_column: field.get("id"),
            }
            for user_id in recipient_ids
            if user_id not in existing_user_ids
        ]

        if not rows:
            return []

        notifications = service_supabase.table("notifications").insert(rows).execute().data or []
        _send_push_for_notifications(service_supabase, notifications)
        return notifications
    except Exception as exc:
        logger.warning(
            "Failed to create game_created notifications",
            extra={
                "event": "notifications.generate.failure",
                "notification_type": "game_created",
                "game_id": game.get("id"),
                "field_id": field.get("id"),
                "user_id": organizer_id,
                "error_code": "NOTIFICATION_GENERATION_FAILED",
                "exception_type": exc.__class__.__name__,
                "result": "partial_failure",
            },
            exc_info=True,
        )
        return []


def create_player_joined_game_notification(
    game: dict[str, Any],
    field: dict[str, Any],
    joined_user: dict[str, Any],
) -> list[dict[str, Any]]:
    organizer_id = game.get("created_by")
    joined_user_id = joined_user.get("id")

    if not organizer_id or not joined_user_id or str(organizer_id) == str(joined_user_id):
        return []

    service_supabase = get_supabase_service_role_client()
    field_name = field.get("name") or "Unknown field"
    player_name = str(joined_user.get("name") or "").strip()
    rendered = render_notification_template(
        "player_joined_game", "he",
        {"player_name": player_name, "field_name": field_name},
    )
    payload = {
        "game_id": game.get("id"),
        "field_id": field.get("id") or game.get("field_id"),
        "type": "player_joined_game",
        "joined_user_id": joined_user_id,
    }
    row = {
        "user_id": organizer_id,
        "type": "player_joined_game",
        "title": rendered["title"],
        "body": rendered["body"],
        "game_id": game.get("id"),
        "field_id": field.get("id") or game.get("field_id"),
        "data": payload,
    }

    try:
        notifications = service_supabase.table("notifications").insert(row).execute().data or []
    except APIError as error:
        if not _is_missing_column_error(error, "notifications.data"):
            raise

        game_id_column = "game_id"
        field_id_column = "field_id"
        legacy_row = {
            key: value
            for key, value in row.items()
            if key != "data"
        }

        try:
            notifications = service_supabase.table("notifications").insert(legacy_row).execute().data or []
        except APIError as legacy_error:
            if not _is_missing_column_error(legacy_error, "notifications.game_id"):
                raise

            legacy_row.pop(game_id_column, None)
            legacy_row.pop(field_id_column, None)
            legacy_row["related_game_id"] = game.get("id")
            legacy_row["related_field_id"] = field.get("id") or game.get("field_id")
            notifications = service_supabase.table("notifications").insert(legacy_row).execute().data or []

    _send_push_for_notifications(service_supabase, notifications)
    return notifications


def create_game_closed_notifications(
    supabase: Any,
    game: dict[str, Any],
    closed_by_user_id: str,
) -> list[dict[str, Any]]:
    game_id = game.get("id")
    if not game_id:
        return []

    participant_rows = (
        supabase.table("game_players")
        .select("user_id")
        .eq("game_id", game_id)
        .execute()
        .data
        or []
    )
    recipient_ids = [
        user_id
        for user_id in dict.fromkeys(
            str(row.get("user_id"))
            for row in participant_rows
            if row.get("user_id")
        )
        if user_id != str(closed_by_user_id)
    ]

    if not recipient_ids:
        return []

    field_id = game.get("field_id")
    field_name = "Unknown field"
    if field_id:
        field_rows = (
            supabase.table("fields")
            .select("id,name")
            .eq("id", field_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if field_rows:
            field_name = field_rows[0].get("name") or field_name

    service_supabase = get_supabase_service_role_client()
    existing_response = (
        service_supabase.table("notifications")
        .select("user_id")
        .eq("type", "game_closed")
        .eq("game_id", game_id)
        .in_("user_id", recipient_ids)
        .execute()
    )
    existing_user_ids = {
        str(row["user_id"])
        for row in existing_response.data or []
        if row.get("user_id")
    }
    rendered = render_notification_template(
        "game_closed", "he", {"field_name": field_name},
    )
    rows = [
        {
            "user_id": user_id,
            "type": "game_closed",
            "title": rendered["title"],
            "body": rendered["body"],
            "game_id": game_id,
            "field_id": field_id,
            "data": {
                "game_id": game_id,
                "field_id": field_id,
                "type": "game_closed",
                "closed_by_user_id": closed_by_user_id,
            },
        }
        for user_id in recipient_ids
        if user_id not in existing_user_ids
    ]

    if not rows:
        return []

    notifications = service_supabase.table("notifications").insert(rows).execute().data or []
    _send_push_for_notifications(service_supabase, notifications)
    return notifications


def create_scheduled_game_cancelled_notifications(
    supabase: Any,
    game: dict[str, Any],
    cancelled_by_user_id: str,
    cancelled_by_role: str,
) -> list[dict[str, Any]]:
    game_id = game.get("id")
    if not game_id:
        return []

    participant_rows = (
        supabase.table("game_players")
        .select("user_id")
        .eq("game_id", game_id)
        .execute()
        .data
        or []
    )

    all_participant_ids = list(
        dict.fromkeys(
            str(row.get("user_id"))
            for row in participant_rows
            if row.get("user_id")
        )
    )

    creator_id = str(game.get("created_by") or "")

    if cancelled_by_role == "admin":
        recipient_ids = all_participant_ids
        if creator_id and creator_id not in recipient_ids:
            recipient_ids.append(creator_id)
    else:
        recipient_ids = [
            uid for uid in all_participant_ids
            if uid != str(cancelled_by_user_id)
        ]

    if not recipient_ids:
        return []

    field_id = game.get("field_id")
    field_name = "Unknown field"
    if field_id:
        field_rows = (
            supabase.table("fields")
            .select("id,name")
            .eq("id", field_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if field_rows:
            field_name = field_rows[0].get("name") or field_name

    rendered = render_notification_template(
        "scheduled_game_cancelled", "he",
        {"field_name": field_name, "cancelled_by_role": cancelled_by_role},
    )

    service_supabase = get_supabase_service_role_client()
    rows = [
        {
            "user_id": user_id,
            "type": "scheduled_game_cancelled",
            "title": rendered["title"],
            "body": rendered["body"],
            "game_id": game_id,
            "field_id": field_id,
            "data": {
                "game_id": game_id,
                "field_id": field_id,
                "type": "scheduled_game_cancelled",
                "scheduled_at": game.get("scheduled_at"),
                "cancelled_by": cancelled_by_user_id,
                "cancelled_by_role": cancelled_by_role,
            },
        }
        for user_id in recipient_ids
    ]

    if not rows:
        return []

    notifications = service_supabase.table("notifications").insert(rows).execute().data or []
    _send_push_for_notifications(service_supabase, notifications)
    return notifications


def create_game_extended_notifications(
    supabase: Any,
    game: dict[str, Any],
    new_end_time: datetime,
    extended_by_user_id: str,
) -> list[dict[str, Any]]:
    game_id = game.get("id")
    organizer_id = game.get("created_by")
    if not game_id or not organizer_id:
        return []

    participant_rows = (
        supabase.table("game_players")
        .select("user_id")
        .eq("game_id", game_id)
        .execute()
        .data
        or []
    )
    excluded_user_ids = {str(organizer_id), str(extended_by_user_id)}
    recipient_ids = [
        user_id
        for user_id in dict.fromkeys(
            str(row.get("user_id"))
            for row in participant_rows
            if row.get("user_id")
        )
        if user_id not in excluded_user_ids
    ]

    if not recipient_ids:
        return []

    service_supabase = get_supabase_service_role_client()
    new_end_time_iso = new_end_time.isoformat()
    new_end_time_label = new_end_time.strftime("%H:%M")
    existing_response = (
        service_supabase.table("notifications")
        .select("user_id,data")
        .eq("type", "game_extended")
        .eq("game_id", game_id)
        .in_("user_id", recipient_ids)
        .execute()
    )
    existing_user_ids = {
        str(row["user_id"])
        for row in existing_response.data or []
        if row.get("user_id")
        and isinstance(row.get("data"), dict)
        and row["data"].get("new_end_time") == new_end_time_iso
    }
    field_id = game.get("field_id")
    rendered = render_notification_template(
        "game_extended", "he", {"time": new_end_time_label},
    )
    rows = [
        {
            "user_id": user_id,
            "type": "game_extended",
            "title": rendered["title"],
            "body": rendered["body"],
            "game_id": game_id,
            "field_id": field_id,
            "data": {
                "game_id": game_id,
                "field_id": field_id,
                "type": "game_extended",
                "new_end_time": new_end_time_iso,
                "extended_by_user_id": extended_by_user_id,
            },
        }
        for user_id in recipient_ids
        if user_id not in existing_user_ids
    ]

    if not rows:
        return []

    notifications = service_supabase.table("notifications").insert(rows).execute().data or []
    _send_push_for_notifications(service_supabase, notifications)
    return notifications


def _mark_scheduled_game_reminder_processed(
    supabase: Any,
    game_id: str,
    processed_at: datetime,
) -> None:
    (
        supabase.table("games")
        .update({"scheduled_reminder_processed_at": processed_at.isoformat()})
        .eq("id", game_id)
        .execute()
    )


def _get_current_game_participant_ids(supabase: Any, game_id: str) -> list[str]:
    participant_rows = (
        supabase.table("game_players")
        .select("user_id")
        .eq("game_id", game_id)
        .execute()
        .data
        or []
    )
    return [
        user_id
        for user_id in dict.fromkeys(
            str(row.get("user_id"))
            for row in participant_rows
            if row.get("user_id")
        )
    ]


def generate_scheduled_game_reminders(
    supabase: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    service_supabase = supabase or get_supabase_service_role_client()
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    games = (
        service_supabase.table("games")
        .select("*")
        .in_("status", ACTIVE_GAME_STATUSES)
        .execute()
        .data
        or []
    )

    processed_game_ids: list[str] = []
    skipped_game_ids: list[str] = []
    failed_game_ids: list[str] = []
    errors: list[dict[str, str]] = []
    notifications: list[dict[str, Any]] = []

    for game in games:
        game_id = str(game.get("id") or "")
        scheduled_at = parse_game_datetime(game.get("scheduled_at"))
        if not game_id or scheduled_at is None:
            continue

        if game.get("scheduled_reminder_processed_at"):
            skipped_game_ids.append(game_id)
            continue

        if scheduled_at <= current_time:
            continue

        reminder_time = scheduled_at - timedelta(hours=1)
        if current_time < reminder_time:
            continue

        try:
            existing_game_reminders = (
                service_supabase.table("notifications")
                .select("user_id")
                .eq("type", SCHEDULED_GAME_REMINDER_TYPE)
                .eq("game_id", game_id)
                .execute()
                .data
                or []
            )
            if existing_game_reminders:
                _mark_scheduled_game_reminder_processed(service_supabase, game_id, current_time)
                skipped_game_ids.append(game_id)
                continue

            recipient_ids = _get_current_game_participant_ids(service_supabase, game_id)
            if not recipient_ids:
                _mark_scheduled_game_reminder_processed(service_supabase, game_id, current_time)
                processed_game_ids.append(game_id)
                continue

            scheduled_at_iso = scheduled_at.isoformat()
            rendered = render_notification_template("scheduled_game_reminder", "he")
            rows = [
                {
                    "user_id": user_id,
                    "type": SCHEDULED_GAME_REMINDER_TYPE,
                    "title": rendered["title"],
                    "body": rendered["body"],
                    "game_id": game_id,
                    "field_id": game.get("field_id"),
                    "data": {
                        "type": SCHEDULED_GAME_REMINDER_TYPE,
                        "game_id": game_id,
                        "field_id": game.get("field_id"),
                        "scheduled_at": scheduled_at_iso,
                    },
                }
                for user_id in recipient_ids
            ]
            created_notifications = (
                service_supabase.table("notifications").insert(rows).execute().data or []
            )
            _mark_scheduled_game_reminder_processed(service_supabase, game_id, current_time)
            _send_push_for_notifications(service_supabase, created_notifications)
            notifications.extend(created_notifications)
            processed_game_ids.append(game_id)
        except Exception as exc:
            logger.warning(
                "Failed to process scheduled game reminder",
                extra={
                    "event": "jobs.scheduled_game_reminders.item_failure",
                    "job_name": "scheduled_game_reminders",
                    "notification_type": SCHEDULED_GAME_REMINDER_TYPE,
                    "game_id": game_id,
                    "field_id": game.get("field_id"),
                    "error_code": "NOTIFICATION_GENERATION_FAILED",
                    "exception_type": exc.__class__.__name__,
                    "result": "partial_failure",
                },
                exc_info=True,
            )
            failed_game_ids.append(game_id)
            errors.append({"game_id": game_id, "error": "reminder processing failed"})

    return {
        "processed_game_ids": processed_game_ids,
        "skipped_game_ids": skipped_game_ids,
        "failed_game_ids": failed_game_ids,
        "errors": errors,
        "notifications_created": len(notifications),
        "notifications": notifications,
    }


def create_field_report_status_notification(
    report: dict[str, Any],
    new_status: str,
) -> list[dict[str, Any]]:
    reporter_id = report.get("user_id")
    field_report_id = report.get("id")
    field_id = report.get("field_id")

    if not reporter_id or not field_report_id:
        return []

    service_supabase = get_supabase_service_role_client()

    field_name = "Unknown field"
    if field_id:
        field_rows = (
            service_supabase.table("fields")
            .select("id,name")
            .eq("id", field_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if field_rows:
            field_name = field_rows[0].get("name") or field_name

    existing = (
        service_supabase.table("notifications")
        .select("id,data")
        .eq("type", "field_report_status_changed")
        .eq("user_id", reporter_id)
        .execute()
        .data
        or []
    )
    for row in existing:
        data = row.get("data")
        if (
            isinstance(data, dict)
            and data.get("field_report_id") == field_report_id
            and data.get("new_status") == new_status
        ):
            return []

    rendered = render_notification_template(
        "field_report_status_changed",
        "he",
        {"new_status": new_status, "field_name": field_name},
    )

    notification_row = {
        "user_id": reporter_id,
        "type": "field_report_status_changed",
        "title": rendered["title"],
        "body": rendered["body"],
        "field_id": field_id,
        "data": {
            "type": "field_report_status_changed",
            "field_report_id": field_report_id,
            "field_id": field_id,
            "new_status": new_status,
        },
    }

    notifications = (
        service_supabase.table("notifications")
        .insert(notification_row)
        .execute()
        .data
        or []
    )

    _send_push_for_notifications(service_supabase, notifications)
    return notifications


@router.get("")
def get_notifications(current_user: dict[str, Any] = Depends(require_active_user)):
    authenticated_user_id = str(current_user["id"])
    response = (
        get_supabase_service_role_client()
        .table("notifications")
        .select("*")
        .eq("user_id", authenticated_user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [_with_notification_target_aliases(row) for row in response.data]


@router.get("/unread-count")
def get_unread_notification_count(current_user: dict[str, Any] = Depends(require_active_user)):
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "notifications_unread_count", [(30, 60)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    authenticated_user_id = str(current_user["id"])
    client = get_supabase_service_role_client()

    try:
        response = (
            client.table("notifications")
            .select("*", count="exact", head=True)
            .eq("user_id", authenticated_user_id)
            .is_("read_at", "null")
            .execute()
        )
    except APIError as error:
        if not _is_missing_column_error(error, "notifications.read_at"):
            raise

        response = (
            client.table("notifications")
            .select("*", count="exact", head=True)
            .eq("user_id", authenticated_user_id)
            .eq("is_read", False)
            .execute()
        )

    return {"unread_count": response.count or 0}


@router.post("/push-token")
def save_push_token(
    payload: PushTokenRequest,
    current_user: dict[str, Any] = Depends(require_active_user),
):
    client = get_supabase_service_role_client()
    token = payload.token.strip()
    user_id = str(current_user["id"])

    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Push token is required")

    existing = (
        client.table("push_tokens")
        .select("*")
        .eq("token", token)
        .limit(1)
        .execute()
        .data
        or []
    )
    row = {
        "user_id": user_id,
        "token": token,
    }

    if existing:
        response = (
            client.table("push_tokens")
            .update(row)
            .eq("id", existing[0]["id"])
            .execute()
        )
    else:
        response = client.table("push_tokens").insert(row).execute()

    return {"message": "Push token saved", "push_token": response.data[0]}


@router.delete("/push-token")
def delete_push_token(
    payload: PushTokenDeleteRequest | None = Body(default=None),
    current_user: dict[str, Any] = Depends(require_active_user),
):
    token = payload.token.strip() if payload and payload.token else ""
    if not token:
        # Without a token we cannot tell which device to remove. Refuse rather
        # than deleting every token the user has registered on other browsers.
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Push token is required",
        )

    client = get_supabase_service_role_client()
    (
        client.table("push_tokens")
        .delete()
        .eq("user_id", str(current_user["id"]))
        .eq("token", token)
        .execute()
    )
    return {"message": "Push token deleted"}


@router.post("/test-push")
def send_test_push(current_user: dict[str, Any] = Depends(require_active_user)):
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "notifications_test_push", [(3, 60), (10, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    client = get_supabase_service_role_client()
    tokens = (
        client.table("push_tokens")
        .select("*")
        .eq("user_id", str(current_user["id"]))
        .execute()
        .data
        or []
    )

    if not tokens:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message="No push token registered",
        )

    rendered = render_notification_template("test_push", "en")
    try:
        result = _send_push_to_tokens(
            client,
            tokens,
            rendered["title"],
            rendered["body"],
            {"type": "test_push"},
            suppress_config_error=False,
        )
    except FirebaseConfigError:
        logger.error(
            "test push failed because Firebase is not configured",
            extra={
                "event": "notifications.push.failure",
                "notification_type": "test_push",
                "external_service": "firebase_fcm",
                "user_id": current_user.get("id"),
                "recipient_count": len(tokens),
                "error_code": "FIREBASE_CONFIG_ERROR",
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="EXTERNAL_SERVICE_ERROR",
            message="Firebase push service configuration error",
        )

    if result["sent"] == 0 and result["invalid_tokens"] == 0:
        logger.error(
            "test push could not be sent",
            extra={
                "event": "notifications.push.failure",
                "notification_type": "test_push",
                "external_service": "firebase_fcm",
                "user_id": current_user.get("id"),
                "recipient_count": len(tokens),
                "sent_count": result["sent"],
                "invalid_token_count": result["invalid_tokens"],
                "error_code": "PUSH_SEND_FAILED",
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="EXTERNAL_SERVICE_ERROR",
            message="Push notification could not be sent",
        )

    return result


@router.patch("/read-all")
def mark_all_notifications_read(current_user: dict[str, Any] = Depends(require_active_user)):
    authenticated_user_id = str(current_user["id"])
    client = get_supabase_service_role_client()

    rows = (
        client.table("notifications")
        .select("*")
        .eq("user_id", authenticated_user_id)
        .execute()
        .data
        or []
    )

    if not rows:
        return {"message": "Notifications marked as read"}

    if _uses_read_at_column(rows[0]):
        now = datetime.now(timezone.utc).isoformat()
        (
            client.table("notifications")
            .update({"read_at": now})
            .eq("user_id", authenticated_user_id)
            .is_("read_at", "null")
            .execute()
        )
    else:
        (
            client.table("notifications")
            .update({"is_read": True})
            .eq("user_id", authenticated_user_id)
            .eq("is_read", False)
            .execute()
        )

    return {"message": "Notifications marked as read"}


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: dict[str, Any] = Depends(require_active_user),
):
    notification_id = validate_uuid_id(notification_id, "notification_id")
    authenticated_user_id = str(current_user["id"])
    client = get_supabase_service_role_client()

    existing = (
        client.table("notifications")
        .select("*")
        .eq("id", notification_id)
        .eq("user_id", authenticated_user_id)
        .limit(1)
        .execute()
    )

    if not existing.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message="Notification not found",
        )

    now = datetime.now(timezone.utc).isoformat()
    response = (
        client.table("notifications")
        .update(_mark_read_payload(existing.data[0], now))
        .eq("id", notification_id)
        .eq("user_id", authenticated_user_id)
        .execute()
    )

    return response.data[0]


@router.get("/preferences")
def get_preferences(current_user: dict[str, Any] = Depends(require_active_user)):
    response = (
        get_supabase_service_role_client()
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
    for fid in settings.selected_field_ids:
        validate_uuid_id(fid, "field_id")
    supabase = get_supabase_service_role_client()
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

    selected_field_ids = [
        field_id
        for field_id in dict.fromkeys(settings.selected_field_ids)
        if _field_key(field_id)
    ]
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
        if settings.specific_fields_enabled
    ]

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
    current_user: dict[str, Any] = Depends(require_active_user),
):
    if not isinstance(body, dict):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invalid request body",
        )

    is_settings_payload = _is_settings_payload(body)

    try:
        if is_settings_payload:
            return _save_settings(body, current_user)

        pref = NotificationPreference(**body)
        if pref.field_id:
            validate_uuid_id(pref.field_id, "field_id")
    except ValidationError as error:
        details = {}
        for err in error.errors():
            loc = err.get("loc", [])
            field = ".".join(str(x) for x in loc) if loc else "non_field_error"
            details[field] = err.get("msg", "Invalid value")
        raise_api_error(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            message="Validation failed",
            details=details,
        )

    _validate_preference(pref)
    supabase = get_supabase_service_role_client()

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
    validate_uuid_id(body.field_id, "field_id")
    if body.sport_type not in ("football", "basketball"):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invalid sport_type",
        )

    supabase = get_supabase_client()
    field_response = (
        supabase.table("fields")
        .select("*")
        .eq("id", body.field_id)
        .limit(1)
        .execute()
    )
    if not field_response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )

    field = field_response.data[0]
    return _find_notification_candidates(supabase, field, body.sport_type)


def cleanup_old_notifications(
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(days=NOTIFICATION_RETENTION_DAYS)
    cutoff_iso = cutoff.isoformat()

    service_supabase = get_supabase_service_role_client()
    old_rows = (
        service_supabase.table("notifications")
        .select("id")
        .lt("created_at", cutoff_iso)
        .execute()
        .data
        or []
    )

    if not old_rows:
        return {
            "deleted_count": 0,
            "retention_days": NOTIFICATION_RETENTION_DAYS,
            "cutoff": cutoff_iso,
        }

    old_ids = [row["id"] for row in old_rows if row.get("id")]
    if old_ids:
        service_supabase.table("notifications").delete().in_("id", old_ids).execute()

    return {
        "deleted_count": len(old_ids),
        "retention_days": NOTIFICATION_RETENTION_DAYS,
        "cutoff": cutoff_iso,
    }
