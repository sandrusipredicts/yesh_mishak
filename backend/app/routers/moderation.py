from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.dependencies import require_active_user
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import raise_api_error, validate_uuid_id
from app.rate_limit import check_rate_limit_by_user

router = APIRouter(prefix="/moderation", tags=["moderation"])


class ContentReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_type: Literal["game", "user"]
    target_id: str
    reason: Literal[
        "abuse",
        "harassment",
        "hate",
        "spam",
        "impersonation",
        "inappropriate",
        "other",
    ]
    description: str | None = Field(default=None, max_length=500)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


def _ensure_target_exists(target_type: str, target_id: str) -> dict:
    table = "games" if target_type == "game" else "users"
    columns = "id,created_by" if target_type == "game" else "id"
    response = (
        get_supabase_client()
        .table(table)
        .select(columns)
        .eq("id", target_id)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="REPORT_TARGET_NOT_FOUND",
            message="The content or user is no longer available.",
        )
    return response.data[0]


@router.post("/reports", status_code=status.HTTP_201_CREATED)
def create_content_report(
    payload: ContentReportCreate,
    current_user: dict = Depends(require_active_user),
) -> dict:
    reporter_id = str(current_user["id"])
    rate_limit_hit = check_rate_limit_by_user(
        reporter_id, "content_reports_create", [(5, 60), (20, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    target_id = validate_uuid_id(payload.target_id, "target_id")
    target = _ensure_target_exists(payload.target_type, target_id)
    if payload.target_type == "user" and target_id == reporter_id:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="You cannot report your own account.",
        )
    if payload.target_type == "game" and str(target.get("created_by") or "") == reporter_id:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="You cannot report your own game.",
        )

    service = get_supabase_service_role_client()
    existing = (
        service.table("content_reports")
        .select("id")
        .eq("reporter_user_id", reporter_id)
        .eq("target_type", payload.target_type)
        .eq("target_id", target_id)
        .in_("status", ["open", "in_review"])
        .limit(1)
        .execute()
    )
    if existing.data:
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="REPORT_ALREADY_OPEN",
            message="You already have an open report for this item.",
        )

    response = service.table("content_reports").insert(
        {
            "reporter_user_id": reporter_id,
            "target_type": payload.target_type,
            "target_id": target_id,
            "reason": payload.reason,
            "description": payload.description,
            "status": "open",
        }
    ).execute()
    return {"message": "Report submitted", "report_id": str(response.data[0]["id"])}


@router.get("/blocks")
def get_user_blocks(current_user: dict = Depends(require_active_user)) -> dict:
    response = (
        get_supabase_service_role_client()
        .table("user_blocks")
        .select("blocked_user_id")
        .eq("blocker_user_id", str(current_user["id"]))
        .execute()
    )
    return {"blocked_user_ids": [str(row["blocked_user_id"]) for row in response.data]}


@router.post("/blocks/{blocked_user_id}", status_code=status.HTTP_201_CREATED)
def block_user(
    blocked_user_id: str,
    current_user: dict = Depends(require_active_user),
) -> dict:
    blocker_id = str(current_user["id"])
    blocked_user_id = validate_uuid_id(blocked_user_id, "blocked_user_id")
    if blocked_user_id == blocker_id:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="You cannot block your own account.",
        )
    _ensure_target_exists("user", blocked_user_id)
    service = get_supabase_service_role_client()
    existing = (
        service.table("user_blocks")
        .select("blocked_user_id")
        .eq("blocker_user_id", blocker_id)
        .eq("blocked_user_id", blocked_user_id)
        .limit(1)
        .execute()
    )
    if not existing.data:
        service.table("user_blocks").insert(
            {"blocker_user_id": blocker_id, "blocked_user_id": blocked_user_id}
        ).execute()
    return {"message": "User blocked", "blocked_user_id": blocked_user_id}


@router.delete("/blocks/{blocked_user_id}")
def unblock_user(
    blocked_user_id: str,
    current_user: dict = Depends(require_active_user),
) -> dict:
    blocked_user_id = validate_uuid_id(blocked_user_id, "blocked_user_id")
    (
        get_supabase_service_role_client()
        .table("user_blocks")
        .delete()
        .eq("blocker_user_id", str(current_user["id"]))
        .eq("blocked_user_id", blocked_user_id)
        .execute()
    )
    return {"message": "User unblocked", "blocked_user_id": blocked_user_id}
