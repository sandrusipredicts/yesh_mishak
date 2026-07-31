from fastapi import HTTPException, status
from supabase import Client, ClientOptions, create_client

from app.core.config import get_settings


def get_supabase_client() -> Client:
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_key)


def get_supabase_service_role_client(
    *,
    postgrest_timeout_seconds: float | None = None,
) -> Client:
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_SERVICE_ROLE_KEY is not configured",
        )

    options = None
    if postgrest_timeout_seconds is not None:
        if postgrest_timeout_seconds <= 0:
            raise ValueError("PostgREST timeout must be positive")
        options = ClientOptions(postgrest_client_timeout=postgrest_timeout_seconds)

    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=options,
    )
