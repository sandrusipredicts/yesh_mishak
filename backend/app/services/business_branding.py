from __future__ import annotations

from typing import Any

from postgrest.exceptions import APIError

from app.core.config import get_settings
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import raise_api_error

BUSINESS_SETTINGS_TABLE = "business_settings"
BUSINESS_SETTINGS_ID = "default"


def _normalize_business_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _is_missing_schema_error(error: APIError, name: str) -> bool:
    details = getattr(error, "args", [{}])[0]
    code = ""
    message = str(error)
    if isinstance(details, dict):
        code = str(details.get("code") or "")
        message = f"{message} {details.get('message') or ''}"
    return code in {"42P01", "42703"} and name in message


def _safe_default_business_name() -> str:
    settings = get_settings()
    configured = _normalize_business_name(settings.default_business_name)
    if configured:
        return configured
    fallback = _normalize_business_name(settings.fallback_business_name)
    if fallback:
        return fallback
    return "Business"


def get_business_branding(*, client: Any | None = None) -> dict[str, str]:
    supabase = client or get_supabase_client()
    try:
        response = (
            supabase.table(BUSINESS_SETTINGS_TABLE)
            .select("business_name")
            .eq("id", BUSINESS_SETTINGS_ID)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        if rows:
            business_name = _normalize_business_name(rows[0].get("business_name"))
            if business_name:
                return {"business_name": business_name, "source": "persisted"}
    except APIError as exc:
        if not (
            _is_missing_schema_error(exc, BUSINESS_SETTINGS_TABLE)
            or _is_missing_schema_error(exc, "business_name")
            or _is_missing_schema_error(exc, "id")
        ):
            raise

    return {"business_name": _safe_default_business_name(), "source": "default"}


def update_business_name(value: str, *, client: Any | None = None) -> dict[str, str]:
    business_name = _normalize_business_name(value)
    if not business_name:
        raise_api_error(
            status_code=400,
            code="VALIDATION_ERROR",
            message="business_name is required",
        )

    supabase = client or get_supabase_service_role_client()
    payload = {"id": BUSINESS_SETTINGS_ID, "business_name": business_name}

    try:
        existing = (
            supabase.table(BUSINESS_SETTINGS_TABLE)
            .select("id")
            .eq("id", BUSINESS_SETTINGS_ID)
            .limit(1)
            .execute()
            .data
            or []
        )
        if existing:
            supabase.table(BUSINESS_SETTINGS_TABLE).update(
                {"business_name": business_name}
            ).eq("id", BUSINESS_SETTINGS_ID).execute()
        else:
            supabase.table(BUSINESS_SETTINGS_TABLE).insert(payload).execute()
    except APIError as exc:
        if (
            _is_missing_schema_error(exc, BUSINESS_SETTINGS_TABLE)
            or _is_missing_schema_error(exc, "business_name")
            or _is_missing_schema_error(exc, "id")
        ):
            raise_api_error(
                status_code=503,
                code="BUSINESS_BRANDING_UNAVAILABLE",
                message="Business branding storage is not available",
            )
        raise

    return {"business_name": business_name, "source": "persisted"}
