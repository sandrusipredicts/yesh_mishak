import logging
import time
from functools import lru_cache

from fastapi import HTTPException, status
from supabase import Client, create_client

from app.core.config import get_settings

logger = logging.getLogger("app.db.supabase")


# --- TEMPORARY DIAGNOSTICS (WinError 10035 investigation) -------------------
# These httpx event hooks log when a PostgREST request is *sent* and when a
# response is *received*, including the negotiated HTTP version. If we see a
# "request SENT" line with no matching "response RECEIVED" before an
# httpx.ReadError, the failure is at the transport layer (before PostgREST
# answers) rather than an application/PostgREST error. Remove once the root
# cause is confirmed and the fix is in place.
def _instrument_session(client: Client, label: str) -> Client:
    try:
        session = client.postgrest.session  # httpx.Client used for PostgREST
    except Exception as exc:  # pragma: no cover - diagnostics must never break the app
        logger.warning("supabase[%s]: could not instrument session: %r", label, exc)
        return client

    def _log_request(request) -> None:
        request.extensions["diag_start"] = time.perf_counter()
        logger.warning(
            "supabase[%s] -> request SENT method=%s url=%s",
            label,
            request.method,
            request.url,
        )

    def _log_response(response) -> None:
        start = response.request.extensions.get("diag_start")
        elapsed_ms = (time.perf_counter() - start) * 1000 if start else -1.0
        logger.warning(
            "supabase[%s] <- response RECEIVED status=%s http_version=%s elapsed_ms=%.1f url=%s",
            label,
            response.status_code,
            response.http_version,
            elapsed_ms,
            response.request.url,
        )

    session.event_hooks["request"].append(_log_request)
    session.event_hooks["response"].append(_log_response)
    logger.warning("supabase[%s]: diagnostics attached (http2=%s)", label, getattr(session, "_transport", None) is not None)
    return client
# --- END TEMPORARY DIAGNOSTICS ---------------------------------------------


@lru_cache
def get_supabase_client() -> Client:
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_key)
    return _instrument_session(client, "anon")


@lru_cache
def get_supabase_service_role_client() -> Client:
    settings = get_settings()
    if not settings.supabase_service_role_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_SERVICE_ROLE_KEY is not configured",
        )

    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _instrument_session(client, "service_role")
