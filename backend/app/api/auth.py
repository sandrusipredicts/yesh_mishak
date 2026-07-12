from datetime import datetime, timezone
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from app.auth.dependencies import invalidate_cached_user, require_active_user
from app.auth.google import find_or_create_google_user, verify_google_token
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, validate_password, verify_password
from app.brute_force import record_failed_login_and_delay, reset_failed_login_state
from app.db.supabase import get_supabase_client
from app.errors import error_response, raise_api_error
from app.rate_limit import check_rate_limit_by_ip
from app.schemas.auth import (
    AvailabilityResponse,
    EmailCheckRequest,
    GoogleAuthRequest,
    LoginRequest,
    EmailVerificationResponse,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    ResendVerificationRequest,
    RegistrationResponse,
    RegisterRequest,
    TokenResponse,
    UsernameCheckRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services.email_verification import (
    GENERIC_RESEND_MESSAGE,
    VerificationDeliveryError,
    issue_verification_email,
    verify_email_token,
)
from app.services.password_reset import (
    PasswordResetRateLimited,
    PasswordResetService,
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
    email_verified = user.get("email_verified") is not False

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=user_response,
        email_verification_required=not email_verified,
    )


def _get_user_by_column(column: str, value: str) -> dict[str, Any] | None:
    response = (
        get_supabase_client()
        .table("users")
        .select("id,email,name,username,phone_number,password_hash,email_verified,email_verified_at")
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
        logger.info(
            "auth last_login update succeeded",
            extra={
                "event": "auth.last_login.success",
                "auth_method": attempt_id,
                "user_id": user_id,
                "endpoint": "/auth/login" if attempt_id == "password" else "/auth/google",
                "method": "POST",
                "result": "success",
            },
        )
    except Exception as exc:
        logger.warning(
            "auth last_login update failed but login will continue",
            extra={
                "event": "auth.last_login.failure",
                "auth_method": attempt_id,
                "user_id": user_id,
                "endpoint": "/auth/login" if attempt_id == "password" else "/auth/google",
                "method": "POST",
                "result": "partial_failure",
                "error_code": "DATABASE_ERROR",
                "exception_type": exc.__class__.__name__,
            },
        )


def _client_ip(request: Request) -> str:
    # Trust only ASGI's resolved peer. Production may enable Uvicorn proxy-header
    # handling only for explicitly trusted Railway proxy addresses; application
    # code never accepts a client-supplied forwarding header directly.
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.post("/google", response_model=TokenResponse)
def google_login(request: Request, payload: GoogleAuthRequest) -> TokenResponse:
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_google", [(10, 60), (50, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    attempt_id = uuid4().hex[:10]
    logger.info(
        "google login request started",
        extra={
            "event": "auth.login.start",
            "auth_method": "google",
            "endpoint": "/auth/google",
            "method": "POST",
            "attempt_id": attempt_id,
        },
    )
    try:
        google_user = verify_google_token(payload.token, attempt_id=attempt_id)
        user = find_or_create_google_user(google_user, attempt_id=attempt_id)
    except HTTPException as exc:
        logger.warning(
            "google login failed",
            extra={
                "event": "auth.login.failure",
                "auth_method": "google",
                "endpoint": "/auth/google",
                "method": "POST",
                "status_code": exc.status_code,
                "error_code": "AUTH_INVALID" if exc.status_code == status.HTTP_401_UNAUTHORIZED else "AUTH_FAILURE",
                "attempt_id": attempt_id,
                "result": "failure",
            },
        )
        raise

    _update_last_login(str(user["id"]), attempt_id=attempt_id)
    token_response = _create_token_response(user)
    logger.info(
        "google login succeeded",
        extra={
            "event": "auth.login.success",
            "auth_method": "google",
            "endpoint": "/auth/google",
            "method": "POST",
            "user_id": token_response.user.id,
            "attempt_id": attempt_id,
            "result": "success",
            "username_is_null": token_response.user.username is None,
            "phone_is_null": token_response.user.phone_number is None,
        },
    )
    return token_response


@router.post("/register", response_model=RegistrationResponse, status_code=status.HTTP_201_CREATED)
def register(request: Request, payload: RegisterRequest) -> RegistrationResponse:
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_register", [(5, 60), (20, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    if payload.password != payload.password_confirm:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message="Passwords do not match",
        )

    password_errors = validate_password(payload.password)
    if password_errors:
        raise_api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message=password_errors[0],
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
        "email_verified": False,
        "email_verified_at": None,
    }

    try:
        response = get_supabase_client().table("users").insert(user_data).execute()
    except APIError as exc:
        error_details = getattr(exc, "args", [{}])[0]
        msg = error_details.get("message", "") if isinstance(error_details, dict) else str(exc)
        code = error_details.get("code", "") if isinstance(error_details, dict) else ""
        if code == "23505" or "23505" in msg or "duplicate key" in msg.lower():
            if "username" in msg.lower():
                raise_api_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code="USERNAME_TAKEN",
                    message="Username is already taken",
                )
            elif "email" in msg.lower():
                raise_api_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code="EMAIL_TAKEN",
                    message="Email is already registered",
                )
            elif "phone_number" in msg.lower():
                raise_api_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code="PHONE_TAKEN",
                    message="Phone number is already registered",
                )
            else:
                raise_api_error(
                    status_code=status.HTTP_409_CONFLICT,
                    code="CONFLICT",
                    message="Uniqueness constraint violation",
                )
        raise

    if not response.data:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="User registration failed",
        )

    email_sent = True
    try:
        issue_verification_email(str(response.data[0]["id"]), payload.email)
    except Exception:
        email_sent = False
        logger.warning(
            "verification email was not delivered",
            extra={"event": "auth.email_verification.delivery_failure", "user_id": str(response.data[0]["id"])},
        )
    return RegistrationResponse(
        user=_format_user_response(response.data[0]),
        email_verification_sent=email_sent,
    )


@router.post("/login", response_model=TokenResponse)
def login(request: Request, payload: LoginRequest) -> TokenResponse:
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_login", [(10, 60), (50, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    user = _get_user_by_column("username", payload.username)
    if not user and "@" in payload.username:
        user = _get_user_by_column("email", payload.username)
    if not user or not verify_password(payload.password, user.get("password_hash")):
        delay_seconds = record_failed_login_and_delay(request, payload.username)
        if delay_seconds > 0:
            logger.warning(
                "password login progressive delay applied",
                extra={
                    "event": "auth.login.progressive_delay",
                    "auth_method": "password",
                    "endpoint": "/auth/login",
                    "method": "POST",
                    "delay_seconds": delay_seconds,
                    "result": "delayed",
                },
            )
        logger.warning(
            "password login failed",
            extra={
                "event": "auth.login.failure",
                "auth_method": "password",
                "endpoint": "/auth/login",
                "method": "POST",
                "status_code": status.HTTP_401_UNAUTHORIZED,
                "error_code": "AUTH_INVALID",
                "result": "failure",
            },
        )
        raise_api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID",
            message="Invalid username or password",
        )

    if user.get("email_verified") is False:
        raise_api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="EMAIL_NOT_VERIFIED",
            message="Email verification is required before signing in.",
        )

    reset_failed_login_state(request, payload.username)
    _update_last_login(str(user["id"]), attempt_id="password")
    token_response = _create_token_response(user)
    logger.info(
        "password login succeeded",
        extra={
            "event": "auth.login.success",
            "auth_method": "password",
            "endpoint": "/auth/login",
            "method": "POST",
            "user_id": token_response.user.id,
            "result": "success",
        },
    )
    return token_response


@router.post("/password-reset/request", response_model=MessageResponse)
def request_password_reset(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: PasswordResetRequest,
) -> MessageResponse | JSONResponse:
    try:
        service = PasswordResetService()
        result = service.request_password_reset(
            email=payload.email,
            client_ip=_client_ip(request),
        )
    except PasswordResetRateLimited as exc:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(exc.retry_after_seconds)},
            content=error_response(
                code="RATE_LIMITED",
                message="Too many requests. Please try again later.",
            ),
        )
    if result.delivery_job is not None:
        background_tasks.add_task(service.deliver_password_reset, result.delivery_job)
    return MessageResponse(message=result.message)


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(request: Request, payload: PasswordResetConfirmRequest) -> MessageResponse | JSONResponse:
    try:
        result = PasswordResetService().confirm_password_reset(
            token=payload.token,
            password=payload.password,
            password_confirm=payload.password_confirm,
            client_ip=_client_ip(request),
        )
    except PasswordResetRateLimited as exc:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(exc.retry_after_seconds)},
            content=error_response(code="RATE_LIMITED", message="Too many requests. Please try again later."),
        )
    return MessageResponse(message=result["message"])


@router.post("/logout")
def logout(current_user: dict = Depends(require_active_user)) -> dict:
    user_id = current_user["id"]
    try:
        get_supabase_client().table("users").update(
            {"tokens_valid_after": _now_iso()}
        ).eq("id", user_id).execute()
    except Exception:
        logger.warning(
            "logout tokens_valid_after update failed",
            extra={
                "event": "auth.logout.failure",
                "user_id": user_id,
            },
        )
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Logout failed",
        )
    invalidate_cached_user(user_id)
    logger.info(
        "user logged out",
        extra={
            "event": "auth.logout.success",
            "user_id": user_id,
        },
    )
    return {"message": "Logged out successfully"}


@router.post("/check-username", response_model=AvailabilityResponse)
def check_username(request: Request, payload: UsernameCheckRequest) -> AvailabilityResponse:
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_check_availability", [(20, 60), (100, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit
    return AvailabilityResponse(available=_get_user_by_column("username", payload.username) is None)


@router.post("/check-email", response_model=AvailabilityResponse)
def check_email(request: Request, payload: EmailCheckRequest) -> AvailabilityResponse:
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_check_availability", [(20, 60), (100, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit
    return AvailabilityResponse(available=_get_user_by_column("email", payload.email) is None)


@router.post("/verify-email", response_model=EmailVerificationResponse)
def verify_email(request: Request, payload: VerifyEmailRequest) -> EmailVerificationResponse:
    rate_limit_hit = check_rate_limit_by_ip(request, "auth_verify_email", [(20, 60), (100, 3600)])
    if rate_limit_hit:
        return rate_limit_hit
    result = verify_email_token(payload.token)
    messages = {
        "verified": "Email verified successfully.",
        "already_used": "This verification link has already been used.",
        "expired": "This verification link has expired.",
        "invalid": "This verification link is invalid.",
    }
    return EmailVerificationResponse(status=result, message=messages.get(result, messages["invalid"]))


@router.post("/resend-verification", response_model=EmailVerificationResponse)
def resend_verification(request: Request, payload: ResendVerificationRequest) -> EmailVerificationResponse:
    rate_limit_hit = check_rate_limit_by_ip(request, "auth_resend_verification", [(5, 60), (20, 3600)])
    if rate_limit_hit:
        return rate_limit_hit
    user = _get_user_by_column("email", payload.email)
    if user and user.get("email_verified") is False and user.get("password_hash"):
        try:
            issue_verification_email(str(user["id"]), payload.email)
        except ValueError as exc:
            if str(exc) == "VERIFICATION_COOLDOWN":
                raise_api_error(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    code="VERIFICATION_COOLDOWN",
                    message="Please wait before requesting another verification email.",
                )
        except Exception:
            logger.warning(
                "verification resend delivery failed",
                extra={"event": "auth.email_verification.resend_failure", "user_id": str(user["id"])},
            )
    return EmailVerificationResponse(status="accepted", message=GENERIC_RESEND_MESSAGE)

