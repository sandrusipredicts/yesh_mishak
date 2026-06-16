from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.auth.google import find_or_create_google_user, verify_google_token
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, verify_password
from app.db.supabase import get_supabase_client
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_user_response(user: dict[str, Any]) -> UserResponse:
    user_id = user.get("id")
    email = user.get("email")
    name = user.get("name")

    if not user_id or not email or not name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User record is missing required fields",
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
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def _update_last_login(user_id: str) -> None:
    try:
        get_supabase_client().table("users").update({"last_login": _now_iso()}).eq("id", user_id).execute()
    except Exception as exc:
        print(f"Failed to update users.last_login for {user_id}: {exc!r}")


@router.post("/google", response_model=TokenResponse)
def google_login(payload: GoogleAuthRequest) -> TokenResponse:
    google_user = verify_google_token(payload.token)
    user = find_or_create_google_user(google_user)

    _update_last_login(str(user["id"]))
    return _create_token_response(user)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> TokenResponse:
    if payload.password != payload.password_confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Passwords do not match",
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User registration failed",
        )

    return _create_token_response(response.data[0])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = _get_user_by_column("username", payload.username)
    if not user or not verify_password(payload.password, user.get("password_hash")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    _update_last_login(str(user["id"]))
    return _create_token_response(user)


@router.post("/check-username", response_model=AvailabilityResponse)
def check_username(payload: UsernameCheckRequest) -> AvailabilityResponse:
    return AvailabilityResponse(available=_get_user_by_column("username", payload.username) is None)


@router.post("/check-email", response_model=AvailabilityResponse)
def check_email(payload: EmailCheckRequest) -> AvailabilityResponse:
    return AvailabilityResponse(available=_get_user_by_column("email", payload.email) is None)
