from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt import decode_access_token
from app.db.supabase import get_supabase_client
from app.errors import raise_api_error

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_REQUIRED",
            message="Missing bearer token",
        )

    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")

    if not user_id:
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="Invalid token",
        )

    response = (
        get_supabase_client()
        .table("users")
        .select("id,email,name,role,status")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="User not found",
        )

    return response.data[0]


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


def require_admin(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if current_user.get("role") != "admin":
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message="Admin access required",
        )

    return current_user

