from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import require_active_user
from app.db.supabase import get_supabase_client
from app.errors import raise_api_error
from app.services.content_moderation import validate_field_report

router = APIRouter(prefix="/field-reports", tags=["field-reports"])

ALLOWED_FIELD_REPORT_CATEGORIES = {
    "wrong_location",
    "field_does_not_exist",
    "field_closed",
    "under_renovation",
    "private_field",
    "duplicate_field",
    "wrong_information",
    "other",
}


class FieldReportCreate(BaseModel):
    field_id: str
    category: str
    description: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


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


def _ensure_field_exists(field_id: str) -> None:
    response = (
        get_supabase_client()
        .table("fields")
        .select("id")
        .eq("id", field_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="FIELD_NOT_FOUND",
            message="Field not found",
        )


@router.post("")
def create_field_report(
    payload: FieldReportCreate,
    current_user: dict[str, Any] = Depends(require_active_user),
):
    if payload.category not in ALLOWED_FIELD_REPORT_CATEGORIES:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Invalid field report category",
        )

    moderation = validate_field_report(payload.description)
    if not moderation.allowed:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="CONTENT_REJECTED",
            message=moderation.message,
        )

    _ensure_field_exists(payload.field_id)

    data = {
        "field_id": payload.field_id,
        "user_id": current_user["id"],
        "category": payload.category,
        "description": payload.description,
    }

    try:
        response = get_supabase_client().table("field_reports").insert(data).execute()
    except Exception:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="DATABASE_ERROR",
            message="Failed to create field report",
        )

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Failed to create field report",
        )

    return {"message": "Field report created", "report": response.data[0]}

