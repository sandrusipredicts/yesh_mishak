import logging
from typing import Any, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.dependencies import require_active_user
from app.db.supabase import get_supabase_client
from app.errors import raise_api_error, validate_uuid_id
from app.rate_limit import check_rate_limit_by_user
from app.services.content_moderation import validate_field_report

router = APIRouter(prefix="/field-reports", tags=["field-reports"])
logger = logging.getLogger(__name__)

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
    description: Optional[str] = Field(default=None, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("category")
    @classmethod
    def validate_category_value(cls, value: str) -> str:
        if value not in ALLOWED_FIELD_REPORT_CATEGORIES:
            from app.errors import raise_api_error
            raise_api_error(
                status_code=400,
                code="VALIDATION_ERROR",
                message="Invalid field report category",
            )
        return value


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
    validate_uuid_id(payload.field_id, "field_id")
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "field_reports_create", [(5, 60), (20, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

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
    except Exception as exc:
        logger.exception(
            "field report creation failed",
            extra={
                "event": "field_reports.create.failure",
                "endpoint": "/field-reports",
                "method": "POST",
                "user_id": current_user.get("id"),
                "field_id": payload.field_id,
                "error_code": "DATABASE_ERROR",
                "exception_type": exc.__class__.__name__,
                "result": "failure",
            },
        )
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

    report = response.data[0]
    logger.info(
        "field report created",
        extra={
            "event": "field_reports.create.success",
            "endpoint": "/field-reports",
            "method": "POST",
            "user_id": current_user.get("id"),
            "field_id": report.get("field_id"),
            "report_id": report.get("id"),
            "result": "success",
        },
    )
    return {"message": "Field report created", "report": report}

