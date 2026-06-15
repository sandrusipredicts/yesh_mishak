from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_admin
from app.db.supabase import get_supabase_client
from app.routers.fields import FieldStatusUpdate, update_field_status_record

router = APIRouter(prefix="/admin", tags=["admin"])

ADMIN_FIELD_COLUMNS = ",".join(
    [
        "id",
        "name",
        "city",
        "lat",
        "lng",
        "sport_type",
        "surface_type",
        "status",
        "approval_status",
        "verified",
        "notes",
        "created_at",
    ]
)


@router.get("/me")
def get_admin_me(current_user: dict[str, Any] = Depends(require_admin)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "name": current_user["name"],
        "role": current_user["role"],
    }


@router.get("/fields")
def get_admin_fields(_: dict[str, Any] = Depends(require_admin)):
    response = (
        get_supabase_client()
        .table("fields")
        .select(ADMIN_FIELD_COLUMNS)
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
        .order("created_at", desc=False)
        .execute()
    )
    return response.data


@router.post("/fields/{field_id}/approve")
def approve_field(field_id: str, _: dict[str, Any] = Depends(require_admin)):
    return _update_field_approval(
        field_id=field_id,
        updates={"verified": True, "approval_status": "approved"},
    )


@router.post("/fields/{field_id}/reject")
def reject_field(field_id: str, _: dict[str, Any] = Depends(require_admin)):
    return _update_field_approval(
        field_id=field_id,
        updates={"verified": False, "approval_status": "rejected"},
    )


@router.patch("/fields/{field_id}/status")
def update_admin_field_status(
    field_id: str,
    body: FieldStatusUpdate,
    _: dict[str, Any] = Depends(require_admin),
):
    return update_field_status_record(field_id, body)


def _update_field_approval(field_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    response = (
        get_supabase_client()
        .table("fields")
        .update(updates)
        .eq("id", field_id)
        .execute()
    )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Field not found",
        )

    return response.data[0]
