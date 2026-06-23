from datetime import datetime, timezone
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from app.auth.google import find_or_create_google_user, verify_google_token
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.db.supabase import get_supabase_client
from app.errors import raise_api_error
from app.schemas.auth import (
    AvailabilityResponse,
    EmailCheckRequest,
    GoogleAuthRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UsernameCheckRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_user_response(user: dict[str, Any]) -> UserResponse:
    user_id = user.get("id")
    email = user.get("email")
    name = user.get("name")

    if not user_id or not email or not name:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="User record is missing required fields",
        )

    return UserResponse(
        id=str(user_id),
        email=email,
        name=name,
        username=user.get("username"),
        phone_number=user.get("phone_number"),
    )


def _create_token_response(user: dict[str, Any]) -> TokenResponse:
    user_response = _format_user_response(user)
    access_token = create_access_token(subject=user_response.id, email=user_response.email)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_response,
    )


def _get_user_by_column(column: str, value: str) -> dict[str, Any] | None:
    response = (
        get_supabase_client()
        .table("users")
        .select("id,email,name,username,phone_number,password_hash")
        .eq(column, value)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def _ensure_unique(column: str, value: str, message: str) -> None:
    if _get_user_by_column(column, value):
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            message=message,
        )


def _update_last_login(user_id: str, attempt_id: str = "unknown") -> None:
    try:
        get_supabase_client().table("users").update({"last_login": _now_iso()}).eq("id", user_id).execute()
        logger.info("google_login[%s] users.last_login updated user_id=%s", attempt_id, user_id)
    except Exception as exc:
        logger.warning(
            "google_login[%s] users.last_login update failed but login will continue user_id=%s error=%r",
            attempt_id,
            user_id,
            exc,
        )


@router.post("/google", response_model=TokenResponse)
def google_login(payload: GoogleAuthRequest) -> TokenResponse:
    attempt_id = uuid4().hex[:10]
    logger.info("google_login[%s] request started", attempt_id)
    google_user = verify_google_token(payload.token, attempt_id=attempt_id)
    user = find_or_create_google_user(google_user, attempt_id=attempt_id)

    _update_last_login(str(user["id"]), attempt_id=attempt_id)
    token_response = _create_token_response(user)
    logger.info(
        "google_login[%s] login succeeded user_id=%s email=%s username_is_null=%s phone_is_null=%s",
        attempt_id,
        token_response.user.id,
        token_response.user.email,
        token_response.user.username is None,
        token_response.user.phone_number is None,
    )
    return token_response


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> TokenResponse:
    if payload.password != payload.password_confirm:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Passwords do not match",
        )

    _ensure_unique("username", payload.username, "Username is already taken")
    _ensure_unique("email", payload.email, "Email is already registered")
    _ensure_unique("phone_number", payload.phone_number, "Phone number is already registered")

    user_data = {
        "name": payload.full_name,
        "username": payload.username,
        "email": payload.email,
        "phone_number": payload.phone_number,
        "password_hash": hash_password(payload.password),
        "last_login": _now_iso(),
    }

    response = get_supabase_client().table("users").insert(user_data).execute()
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="User registration failed",
        )

    return _create_token_response(response.data[0])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = _get_user_by_column("username", payload.username)
    if not user or not verify_password(payload.password, user.get("password_hash")):
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="Invalid username or password",
        )

    _update_last_login(str(user["id"]), attempt_id="password")
    return _create_token_response(user)


@router.post("/check-username", response_model=AvailabilityResponse)
def check_username(payload: UsernameCheckRequest) -> AvailabilityResponse:
    return AvailabilityResponse(available=_get_user_by_column("username", payload.username) is None)


@router.post("/check-email", response_model=AvailabilityResponse)
def check_email(payload: EmailCheckRequest) -> AvailabilityResponse:
    return AvailabilityResponse(available=_get_user_by_column("email", payload.email) is None)

