import logging
import sys
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import decode_access_token
from app.core.config import get_settings
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import raise_api_error

# Fields that gate authentication/authorization decisions. These are never
# served from a stale cached copy: every request re-reads them from the
# database (see _refresh_cached_revocation_fields and the cache-miss branch
# below), so a revocation or role change written by any worker/instance is
# visible to every other worker/instance on its very next request.
_SECURITY_FIELDS = "id,status,tokens_valid_after,role"

bearer_scheme = HTTPBearer(auto_error=False)
timing_logger = logging.getLogger("uvicorn.error")

# In-process TTL cache for user lookups: user_id -> (expires_at_monotonic, user_dict)
_user_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_enable_cache_in_tests = False


def _get_cached_user(user_id: str) -> dict[str, Any] | None:
    if "pytest" in sys.modules and not _enable_cache_in_tests:
        return None
    if user_id not in _user_cache:
        return None
    expires_at, user = _user_cache[user_id]
    if time.monotonic() > expires_at:
        del _user_cache[user_id]
        return None
    return dict(user)


def _set_cached_user(user_id: str, user: dict[str, Any]) -> None:
    ttl = float(get_settings().auth_user_cache_ttl_seconds)
    if ttl <= 0:
        return
    expires_at = time.monotonic() + ttl
    _user_cache[user_id] = (expires_at, dict(user))


def invalidate_cached_user(user_id: str) -> None:
    _user_cache.pop(user_id, None)


def _parse_iso_timestamp(value: str) -> float:
    from datetime import datetime, timezone

    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _check_token_revoked(user: dict[str, Any], token_iat: float | int | None) -> None:
    tokens_valid_after = user.get("tokens_valid_after")
    if tokens_valid_after is None or token_iat is None:
        return
    try:
        if isinstance(tokens_valid_after, str):
            threshold = _parse_iso_timestamp(tokens_valid_after)
        else:
            threshold = float(tokens_valid_after)
    except (ValueError, TypeError) as exc:
        # A malformed tokens_valid_after means revocation state cannot be
        # verified reliably - fail closed rather than let it crash into an
        # unhandled 500 or, worse, silently skip the revocation check.
        timing_logger.warning(
            "auth.tokens_valid_after_malformed exception_type=%s", exc.__class__.__name__
        )
        raise_api_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_SERVICE_UNAVAILABLE",
            message="Authentication service is temporarily unavailable",
        )
        return
    if int(token_iat) < int(threshold):
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="TOKEN_REVOKED",
            message="Token has been revoked",
        )


def _fetch_user_row(user_id: str, columns: str) -> dict[str, Any] | None:
    """Fetch a users row from the database, failing closed on any DB error.

    Auth must never treat a token as valid just because the database could
    not be reached: an unreachable/erroring database is mapped to a stable
    503 AUTH_SERVICE_UNAVAILABLE rather than silently falling back to a
    cached value or leaking the underlying exception to the client.
    """
    try:
        response = (
            get_supabase_service_role_client()
            .table("users")
            .select(columns)
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        timing_logger.warning(
            "auth.user_lookup_failed exception_type=%s", exc.__class__.__name__
        )
        raise_api_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="AUTH_SERVICE_UNAVAILABLE",
            message="Authentication service is temporarily unavailable",
        )
    return response.data[0] if response.data else None


def _refresh_cached_revocation_fields(user_id: str, cached_user: dict[str, Any]) -> dict[str, Any]:
    fresh = _fetch_user_row(user_id, _SECURITY_FIELDS)
    if fresh is None:
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="User not found",
        )
    cached_user["status"] = fresh.get("status", cached_user.get("status"))
    cached_user["tokens_valid_after"] = fresh.get("tokens_valid_after")
    cached_user["role"] = fresh.get("role", cached_user.get("role"))
    _set_cached_user(user_id, cached_user)
    return cached_user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    t_start = time.perf_counter()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Missing bearer token",
        )

    t_jwt_start = time.perf_counter()
    payload = decode_access_token(credentials.credentials)
    t_jwt_end = time.perf_counter()
    duration_jwt = t_jwt_end - t_jwt_start

    user_id = payload.get("sub")

    if not user_id:
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="Invalid token",
        )

    token_iat = payload.get("iat")

    # Cache lookup
    cached_user = _get_cached_user(user_id)
    if cached_user is not None:
        cached_user = _refresh_cached_revocation_fields(user_id, cached_user)
        _check_token_revoked(cached_user, token_iat)
        duration_db = 0.0
        t_total_end = time.perf_counter()
        duration_total = t_total_end - t_start
        timing_logger.debug(
            "auth.timing total=%.3f jwt_decode=%.3f user_lookup=%.3f cache=hit user_id=%s",
            duration_total,
            duration_jwt,
            duration_db,
            user_id,
        )
        return cached_user

    # Cache miss - lookup in Supabase
    t_db_start = time.perf_counter()
    user = _fetch_user_row(user_id, "id,email,name,role,status,tokens_valid_after")
    t_db_end = time.perf_counter()
    duration_db = t_db_end - t_db_start

    if user is None:
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="User not found",
        )

    _check_token_revoked(user, token_iat)
    _set_cached_user(user_id, user)

    t_total_end = time.perf_counter()
    duration_total = t_total_end - t_start

    timing_logger.debug(
        "auth.timing total=%.3f jwt_decode=%.3f user_lookup=%.3f cache=miss user_id=%s",
        duration_total,
        duration_jwt,
        duration_db,
        user_id,
    )

    return user


def require_active_user(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user_status = current_user.get("status", "active")
    if user_status == "banned":
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ACCOUNT_RESTRICTED",
            message="Account is banned",
        )
    if user_status == "suspended":
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="ACCOUNT_RESTRICTED",
            message="Account is suspended",
        )
    return current_user


def require_admin(current_user: dict[str, Any] = Depends(require_active_user)) -> dict[str, Any]:
    if current_user.get("role") != "admin":
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Admin access required",
        )

    return current_user

