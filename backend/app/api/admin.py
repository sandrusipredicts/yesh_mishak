import logging
from time import perf_counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from typing import Any, Optional, Literal
from app.errors import raise_api_error, validate_uuid_id

from app.auth.dependencies import require_admin
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import raise_api_error
from app.routers.fields import (
    FieldRemoveBody,
    FieldStatusUpdate,
    FieldUpdate,
    remove_field_record,
    update_field_record,
    update_field_status_record,
)
from app.routers.game_lifecycle import (
    ACTIVE_GAME_STATUSES,
    ensure_game_is_actionable,
    finish_expired_games,
    get_now,
    parse_game_datetime,
)
from app.routers.game_payloads import attach_participants_to_games
from app.routers.notifications import (
    cleanup_old_notifications,
    create_game_closed_notifications,
    create_game_extended_notifications,
    create_scheduled_game_cancelled_notifications,
    generate_scheduled_game_reminders,
)
from app.services.duplicate_detection import find_duplicates

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)

ADMIN_FIELD_COLUMNS = ",".join(
    [
        "id",
        "name",
        "city",
        "lat",
        "lng",
        "sport_type",
        "surface_type",
        "has_nets",
        "has_water",
        "opening_hours",
        "status",
        "approval_status",
        "verified",
        "notes",
        "created_at",
        "removed_at",
        "removed_by",
        "removal_reason",
    ]
)
FINISHED_GAME_STATUSES = ["finished", "cancelled"]
FINISHED_GAMES_LIMIT = 50

ADMIN_USER_COLUMNS = ",".join(
    [
        "id",
        "username",
        "name",
        "email",
        "phone_number",
        "created_at",
        "last_active",
        "role",
        "status",
        "restriction_reason",
        "restricted_at",
    ]
)
ADMIN_FIELD_REPORT_COLUMNS = ",".join(
    [
        "id",
        "field_id",
        "user_id",
        "category",
        "description",
        "status",
        "created_at",
        "reviewed_at",
        "reviewed_by",
    ]
)
FIELD_REPORT_STATUSES = {"open", "in_review", "resolved", "rejected"}
FIELD_REPORT_REVIEW_STATUSES = {"in_review", "resolved", "rejected"}


class FieldReportStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status_value(cls, value: str) -> str:
        if value not in FIELD_REPORT_REVIEW_STATUSES:
            from app.errors import raise_api_error
            raise_api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="VALIDATION_ERROR",
                message="status must be in_review, resolved, or rejected",
            )
        return value


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


ACTION_TO_NEW_STATUS = {
    "ban": "banned",
    "unban": "active",
    "suspend": "suspended",
    "unsuspend": "active",
}
ACTION_REQUIRED_CURRENT_STATUS = {
    "ban": "active",
    "unban": "banned",
    "suspend": "active",
    "unsuspend": "suspended",
}


class ModerationActionBody(BaseModel):
    reason: str = Field(default="", max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


def _perform_moderation_action(
    user_id: str,
    action_type: str,
    body: ModerationActionBody,
    admin_user: dict[str, Any],
) -> dict[str, Any]:
    user_id = validate_uuid_id(user_id, "user_id")
    supabase = get_supabase_service_role_client()

    target = (
        supabase
        .table("users")
        .select("id,role,status")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not target.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="USER_NOT_FOUND",
            message="User not found",
        )

    target_user = target.data[0]

    if target_user["role"] == "admin":
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="FORBIDDEN",
            message="Cannot moderate admin users",
        )

    required_status = ACTION_REQUIRED_CURRENT_STATUS[action_type]
    if target_user["status"] != required_status:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CONFLICT",
            message=f"User is not currently {required_status}",
        )

    if action_type in ("ban", "suspend") and not body.reason:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Reason is required",
        )

    new_status = ACTION_TO_NEW_STATUS[action_type]
    now = datetime.now(timezone.utc).isoformat()

    update_payload: dict[str, Any] = {"status": new_status}
    if action_type in ("ban", "suspend"):
        update_payload["restriction_reason"] = body.reason
        update_payload["restricted_at"] = now
        update_payload["restricted_by"] = admin_user["id"]
    else:
        update_payload["restriction_reason"] = None
        update_payload["restricted_at"] = None
        update_payload["restricted_by"] = None

    updated = (
        supabase
        .table("users")
        .update(update_payload)
        .eq("id", user_id)
        .execute()
    )

    supabase.table("user_moderation_audit").insert(
        {
            "target_user_id": user_id,
            "actor_user_id": admin_user["id"],
            "action_type": action_type,
            "reason": body.reason or None,
            "previous_status": target_user["status"],
            "new_status": new_status,
        }
    ).execute()

    return {"message": f"User {action_type} successful", "user": updated.data[0]}


@router.post("/users/{user_id}/ban")
def ban_user(
    user_id: str,
    body: ModerationActionBody,
    current_user: dict[str, Any] = Depends(require_admin),
):
    return _perform_moderation_action(user_id, "ban", body, current_user)


@router.post("/users/{user_id}/unban")
def unban_user(
    user_id: str,
    body: ModerationActionBody = ModerationActionBody(),
    current_user: dict[str, Any] = Depends(require_admin),
):
    return _perform_moderation_action(user_id, "unban", body, current_user)


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: str,
    body: ModerationActionBody,
    current_user: dict[str, Any] = Depends(require_admin),
):
    return _perform_moderation_action(user_id, "suspend", body, current_user)


@router.post("/users/{user_id}/unsuspend")
def unsuspend_user(
    user_id: str,
    body: ModerationActionBody = ModerationActionBody(),
    current_user: dict[str, Any] = Depends(require_admin),
):
    return _perform_moderation_action(user_id, "unsuspend", body, current_user)


def _attach_field_report_details(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not reports:
        return []

    supabase = get_supabase_client()
    field_ids = sorted({str(report["field_id"]) for report in reports if report.get("field_id")})
    user_ids = sorted({str(report["user_id"]) for report in reports if report.get("user_id")})

    fields_by_id: dict[str, dict[str, Any]] = {}
    if field_ids:
        field_rows = (
            supabase
            .table("fields")
            .select("id,name")
            .in_("id", field_ids)
            .execute()
            .data
        )
        fields_by_id = {
            str(field["id"]): field
            for field in field_rows
            if field.get("id")
        }

    users_by_id: dict[str, dict[str, Any]] = {}
    if user_ids:
        user_rows = (
            supabase
            .table("users")
            .select("id,name,email")
            .in_("id", user_ids)
            .execute()
            .data
        )
        users_by_id = {
            str(user["id"]): user
            for user in user_rows
            if user.get("id")
        }

    enriched_reports = []
    for report in reports:
        field = fields_by_id.get(str(report.get("field_id")), {})
        reporter = users_by_id.get(str(report.get("user_id")), {})
        enriched_reports.append(
            dict(
                report,
                field_name=field.get("name"),
                reporter_name=reporter.get("name"),
                reporter_email=reporter.get("email"),
            )
        )

    return enriched_reports


@router.get("/field-reports")
def get_admin_field_reports(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    _: dict[str, Any] = Depends(require_admin),
):
    if status_filter and status_filter not in FIELD_REPORT_STATUSES:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="status must be open, in_review, resolved, or rejected",
        )

    query = (
        get_supabase_client()
        .table("field_reports")
        .select(ADMIN_FIELD_REPORT_COLUMNS)
        .order("created_at", desc=True)
    )

    if status_filter:
        query = query.eq("status", status_filter)

    return _attach_field_report_details(query.execute().data or [])


@router.patch("/field-reports/{report_id}/status")
def update_admin_field_report_status(
    report_id: str,
    body: FieldReportStatusUpdate,
    current_user: dict[str, Any] = Depends(require_admin),
):
    report_id = validate_uuid_id(report_id, "report_id")
    if body.status not in FIELD_REPORT_REVIEW_STATUSES:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="status must be in_review, resolved, or rejected",
        )

    response = (
        get_supabase_client()
        .table("field_reports")
        .update(
            {
                "status": body.status,
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "reviewed_by": current_user["id"],
            }
        )
        .eq("id", report_id)
        .execute()
    )

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="REPORT_NOT_FOUND",
            message="Field report not found",
        )

    return {"message": "Field report status updated", "report": response.data[0]}


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
    # Removed fields stay in the database for history/audit, but the
    # default admin listing must not surface them — same rule as the
    # public listing. A future "show removed fields" view should be an
    # explicit, separate filter rather than changing this default.
    response = (
        get_supabase_client()
        .table("fields")
        .select(ADMIN_FIELD_COLUMNS)
        .is_("removed_at", "null")
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
        .is_("removed_at", "null")
        .order("created_at", desc=False)
        .execute()
    )
    return response.data


@router.post("/fields/{field_id}/approve")
def approve_field(field_id: str, current_user: dict[str, Any] = Depends(require_admin)):
    field_id = validate_uuid_id(field_id, "field_id")
    return _update_field_approval(
        field_id=field_id,
        updates={"verified": True, "approval_status": "approved"},
        actor_user_id=str(current_user["id"]),
        event="fields.moderation.approve",
    )


@router.post("/fields/{field_id}/reject")
def reject_field(field_id: str, current_user: dict[str, Any] = Depends(require_admin)):
    field_id = validate_uuid_id(field_id, "field_id")
    return _update_field_approval(
        field_id=field_id,
        updates={"verified": False, "approval_status": "rejected"},
        actor_user_id=str(current_user["id"]),
        event="fields.moderation.reject",
    )


@router.patch("/fields/{field_id}/status")
def update_admin_field_status(
    field_id: str,
    body: FieldStatusUpdate,
    _: dict[str, Any] = Depends(require_admin),
):
    field_id = validate_uuid_id(field_id, "field_id")
    return update_field_status_record(field_id, body)


@router.patch("/fields/{field_id}")
def update_admin_field(
    field_id: str,
    body: FieldUpdate,
    current_user: dict[str, Any] = Depends(require_admin),
):
    field_id = validate_uuid_id(field_id, "field_id")
    result = update_field_record(field_id, body)
    logger.info(
        "field edited by admin",
        extra={
            "event": "fields.edit.success",
            "endpoint": "/admin/fields/{field_id}",
            "method": "PATCH",
            "actor_user_id": current_user.get("id"),
            "field_id": field_id,
            "changed_fields": sorted(body.model_dump(exclude_unset=True).keys()),
            "result": "success",
        },
    )
    return result


@router.delete("/fields/{field_id}")
def delete_admin_field(
    field_id: str,
    body: FieldRemoveBody,
    current_user: dict[str, Any] = Depends(require_admin),
):
    field_id = validate_uuid_id(field_id, "field_id")
    result = remove_field_record(field_id, body, str(current_user["id"]))
    logger.info(
        "field removed by admin",
        extra={
            "event": "fields.moderation.remove",
            "endpoint": "/admin/fields/{field_id}",
            "method": "DELETE",
            "actor_user_id": current_user.get("id"),
            "field_id": field_id,
            "removal_reason": body.reason,
            "result": "success",
        },
    )
    return result


@router.get("/fields/duplicates")
def get_field_duplicates(_: dict[str, Any] = Depends(require_admin)):
    fields = (
        get_supabase_client()
        .table("fields")
        .select(ADMIN_FIELD_COLUMNS + ",added_by")
        .is_("removed_at", "null")
        .execute()
        .data
        or []
    )
    return find_duplicates(fields)


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
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="GAME_NOT_FOUND",
            message="Game not found",
        )

    return response.data[0]


def _ensure_admin_active_game(game: dict[str, Any]) -> None:
    try:
        ensure_game_is_actionable(game, supabase=get_supabase_client())
    except HTTPException:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="GAME_NOT_ACTIONABLE",
            message="Game is not active",
        )


@router.get("/games")
def get_admin_games(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    _: dict[str, Any] = Depends(require_admin),
):
    if status_filter and status_filter not in ("active", "finished"):
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="status must be active or finished",
        )

    if status_filter == "active":
        return {"active": _get_games_by_statuses(ACTIVE_GAME_STATUSES)}

    if status_filter == "finished":
        return {"finished": _get_games_by_statuses(FINISHED_GAME_STATUSES, limit=FINISHED_GAMES_LIMIT)}

    return {
        "active": _get_games_by_statuses(ACTIVE_GAME_STATUSES),
        "finished": _get_games_by_statuses(FINISHED_GAME_STATUSES, limit=FINISHED_GAMES_LIMIT),
    }


@router.post("/reminders/scheduled-games/run")
def run_scheduled_game_reminders(current_user: dict[str, Any] = Depends(require_admin)):
    start = perf_counter()
    logger.info(
        "scheduled game reminders job started",
        extra={
            "event": "jobs.scheduled_game_reminders.start",
            "job_name": "scheduled_game_reminders",
            "trigger": "admin",
            "actor_user_id": current_user.get("id"),
            "endpoint": "/admin/reminders/scheduled-games/run",
            "method": "POST",
        },
    )
    try:
        result = generate_scheduled_game_reminders()
    except Exception as exc:
        logger.exception(
            "scheduled game reminders job failed",
            extra={
                "event": "jobs.scheduled_game_reminders.failure",
                "job_name": "scheduled_game_reminders",
                "trigger": "admin",
                "actor_user_id": current_user.get("id"),
                "endpoint": "/admin/reminders/scheduled-games/run",
                "method": "POST",
                "result": "failure",
                "error_code": "SCHEDULED_JOB_FAILED",
                "exception_type": exc.__class__.__name__,
                "execution_time_ms": round((perf_counter() - start) * 1000, 2),
            },
        )
        raise

    logger.info(
        "scheduled game reminders job finished",
        extra={
            "event": "jobs.scheduled_game_reminders.finish",
            "job_name": "scheduled_game_reminders",
            "trigger": "admin",
            "actor_user_id": current_user.get("id"),
            "endpoint": "/admin/reminders/scheduled-games/run",
            "method": "POST",
            "result": "partial_failure" if result.get("failed_game_ids") else "success",
            "processed_count": len(result.get("processed_game_ids", [])),
            "skipped_count": len(result.get("skipped_game_ids", [])),
            "failed_count": len(result.get("failed_game_ids", [])),
            "notifications_created": result.get("notifications_created", 0),
            "execution_time_ms": round((perf_counter() - start) * 1000, 2),
        },
    )
    return result


@router.post("/notifications/cleanup")
def run_notification_cleanup(current_user: dict[str, Any] = Depends(require_admin)):
    start = perf_counter()
    logger.info(
        "notification cleanup job started",
        extra={
            "event": "jobs.notification_cleanup.start",
            "job_name": "notification_cleanup",
            "trigger": "admin",
            "actor_user_id": current_user.get("id"),
            "endpoint": "/admin/notifications/cleanup",
            "method": "POST",
        },
    )
    try:
        result = cleanup_old_notifications(now=get_now())
    except Exception as exc:
        logger.exception(
            "notification cleanup job failed",
            extra={
                "event": "jobs.notification_cleanup.failure",
                "job_name": "notification_cleanup",
                "trigger": "admin",
                "actor_user_id": current_user.get("id"),
                "endpoint": "/admin/notifications/cleanup",
                "method": "POST",
                "result": "failure",
                "error_code": "SCHEDULED_JOB_FAILED",
                "exception_type": exc.__class__.__name__,
                "execution_time_ms": round((perf_counter() - start) * 1000, 2),
            },
        )
        raise

    logger.info(
        "notification cleanup job finished",
        extra={
            "event": "jobs.notification_cleanup.finish",
            "job_name": "notification_cleanup",
            "trigger": "admin",
            "actor_user_id": current_user.get("id"),
            "endpoint": "/admin/notifications/cleanup",
            "method": "POST",
            "result": "success",
            "processed_count": result.get("deleted_count", 0),
            "skipped_count": 0,
            "failed_count": 0,
            "deleted_count": result.get("deleted_count", 0),
            "execution_time_ms": round((perf_counter() - start) * 1000, 2),
        },
    )
    return result


@router.post("/games/{game_id}/close")
def close_admin_game(game_id: str, current_user: dict[str, Any] = Depends(require_admin)):
    game_id = validate_uuid_id(game_id, "game_id")
    game = _get_game(game_id)
    _ensure_admin_active_game(game)

    supabase = get_supabase_client()
    response = (
        supabase
        .table("games")
        .update({"status": "finished"})
        .eq("id", game_id)
        .execute()
    )
    updated_game = response.data[0]

    logger.info(
        "game closed by admin",
        extra={
            "event": "games.close.success",
            "endpoint": "/admin/games/{game_id}/close",
            "method": "POST",
            "actor_user_id": current_user.get("id"),
            "game_id": game_id,
            "field_id": updated_game.get("field_id"),
            "closed_by_role": "admin",
            "result": "success",
        },
    )

    try:
        create_game_closed_notifications(
            supabase=supabase,
            game=updated_game,
            closed_by_user_id=current_user["id"],
        )
    except Exception as exc:
        logger.warning(
            "Failed to create game closed notifications after successful admin close",
            extra={
                "event": "notifications.generate.failure",
                "notification_type": "game_closed",
                "game_id": game_id,
                "actor_user_id": current_user.get("id"),
                "field_id": updated_game.get("field_id"),
                "error_code": "NOTIFICATION_GENERATION_FAILED",
                "exception_type": exc.__class__.__name__,
                "result": "partial_failure",
            },
            exc_info=True,
        )

    return {"message": "Game closed", "game": updated_game}


@router.post("/games/{game_id}/extend")
def extend_admin_game(game_id: str, current_user: dict[str, Any] = Depends(require_admin)):
    game_id = validate_uuid_id(game_id, "game_id")
    game = _get_game(game_id)
    _ensure_admin_active_game(game)

    expires_at = game.get("expires_at")
    if not expires_at:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Game expires_at is missing",
        )

    current_expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    new_expires = current_expires + timedelta(hours=1)
    supabase = get_supabase_client()
    response = (
        supabase
        .table("games")
        .update({"expires_at": new_expires.isoformat()})
        .eq("id", game_id)
        .execute()
    )
    updated_game = response.data[0]

    try:
        create_game_extended_notifications(
            supabase=supabase,
            game=updated_game,
            new_end_time=new_expires,
            extended_by_user_id=current_user["id"],
        )
    except Exception:
        logger.exception(
            "Failed to create game extended notifications after successful admin extend",
            extra={
                "game_id": game_id,
                "extended_by_user_id": current_user.get("id"),
                "field_id": updated_game.get("field_id"),
                "new_end_time": new_expires.isoformat(),
            },
        )

    return {
        "message": "Game extended by 1 hour",
        "new_expires_at": new_expires.isoformat(),
        "game": updated_game,
    }


class AdminGameCancelBody(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


@router.post("/games/{game_id}/cancel")
def cancel_admin_game(
    game_id: str,
    body: AdminGameCancelBody = AdminGameCancelBody(),
    current_user: dict[str, Any] = Depends(require_admin),
):
    game_id = validate_uuid_id(game_id, "game_id")
    game = _get_game(game_id)

    if game.get("status") not in ACTIVE_GAME_STATUSES:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="GAME_NOT_ACTIONABLE",
            message="Game is not active",
        )

    scheduled_at = parse_game_datetime(game.get("scheduled_at"))
    if scheduled_at is None:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="GAME_NOT_ACTIONABLE",
            message="Only scheduled games can be cancelled",
        )

    now = get_now()
    if scheduled_at <= now:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="GAME_NOT_ACTIONABLE",
            message="Cannot cancel a game after its scheduled start time",
        )

    service_supabase = get_supabase_service_role_client()
    update_payload = {
        "status": "cancelled",
        "cancelled_at": now.isoformat(),
        "cancelled_by": current_user["id"],
        "cancelled_by_role": "admin",
        "cancel_reason": (body.reason or "").strip() or None,
    }

    response = service_supabase.table("games").update(update_payload).eq("id", game_id).execute()
    updated_game = response.data[0] if response.data else game

    try:
        create_scheduled_game_cancelled_notifications(
            supabase=service_supabase,
            game=updated_game,
            cancelled_by_user_id=current_user["id"],
            cancelled_by_role="admin",
        )
    except Exception:
        logger.exception(
            "Failed to create game cancelled notifications after admin cancel",
            extra={"game_id": game_id, "cancelled_by_user_id": current_user.get("id")},
        )

    return {"message": "Game cancelled", "game": updated_game}


def _update_field_approval(
    field_id: str,
    updates: dict[str, Any],
    *,
    actor_user_id: str,
    event: str,
) -> dict[str, Any]:
    response = (
        get_supabase_client()
        .table("fields")
        .update(updates)
        .eq("id", field_id)
        .execute()
    )

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )

    field = response.data[0]
    logger.info(
        "field moderation decision applied",
        extra={
            "event": event,
            "endpoint": (
                "/admin/fields/{field_id}/approve"
                if updates.get("approval_status") == "approved"
                else "/admin/fields/{field_id}/reject"
            ),
            "method": "POST",
            "actor_user_id": actor_user_id,
            "field_id": field_id,
            "approval_status": updates.get("approval_status"),
            "verified": updates.get("verified"),
            "result": "success",
        },
    )
    return field


@router.get("/monitoring")
def get_monitoring(current_user: dict[str, Any] = Depends(require_admin)):
    now = get_now()
    generated_at = now.isoformat()
    supabase = get_supabase_client()

    # --- Active games (reuses existing logic) ---
    active_games_count = _count_rows_in("games", "status", ACTIVE_GAME_STATUSES)

    # --- Active users (last 24h and 7d via last_login) ---
    day_ago = (now - timedelta(days=1)).isoformat()
    week_ago = (now - timedelta(days=7)).isoformat()

    users_24h_rows = (
        supabase.table("users")
        .select("id")
        .gte("last_login", day_ago)
        .execute()
        .data or []
    )
    users_7d_rows = (
        supabase.table("users")
        .select("id")
        .gte("last_login", week_ago)
        .execute()
        .data or []
    )

    # --- Total users ---
    total_users = _count_rows("users")

    # --- Pending moderation ---
    pending_fields = _count_rows("fields", [("approval_status", "pending")])

    # --- Notification counts ---
    day_ago_iso = day_ago
    recent_notifications_rows = (
        supabase.table("notifications")
        .select("id")
        .gte("created_at", day_ago_iso)
        .execute()
        .data or []
    )
    unread_notifications_rows = (
        supabase.table("notifications")
        .select("id")
        .is_("read_at", "null")
        .execute()
        .data or []
    )

    # --- Database health (simple connectivity check) ---
    db_healthy = True
    db_error = None
    try:
        supabase.table("users").select("id").limit(1).execute()
    except Exception as exc:
        db_healthy = False
        db_error = exc.__class__.__name__

    return {
        "status": "ok" if db_healthy else "degraded",
        "generated_at": generated_at,
        "runtime": {},
        "active_games": {
            "count": active_games_count,
            "source": "database",
        },
        "active_users": {
            "last_24h": len(users_24h_rows),
            "last_7d": len(users_7d_rows),
            "total_registered": total_users,
            "source": "database",
            "note": "Based on last_login timestamp. Users without last_login are excluded from active counts.",
        },
        "notifications": {
            "created_last_24h": len(recent_notifications_rows),
            "unread_total": len(unread_notifications_rows),
            "source": "database",
        },
        "moderation": {
            "pending_fields": pending_fields,
            "source": "database",
        },
        "database": {
            "healthy": db_healthy,
            "error_type": db_error,
        },
        "api_errors": {
            "source_available": False,
            "reason": "No persistent metrics store yet. Requires Phase 2 metrics middleware per ISSUE-069.",
        },
        "response_time": {
            "source_available": False,
            "reason": "Response-time middleware not implemented yet. Requires Phase 2 per ISSUE-069.",
        },
        "scheduled_jobs": {
            "source_available": False,
            "reason": "Job execution history is not persisted. Review backend logs for job.*.start/finish/failure events. Requires Phase 2 per ISSUE-069.",
        },
        "push_notifications": {
            "source_available": False,
            "reason": "Push delivery metrics are in backend logs only. Requires Phase 2 log aggregation per ISSUE-069.",
        },
    }
