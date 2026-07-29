from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError
from supabase import Client

from app.auth.dependencies import invalidate_cached_user, require_active_user
from app.auth.google import find_or_create_google_user, verify_google_token
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password, validate_password, verify_password
from app.brute_force import record_failed_login_and_delay, reset_failed_login_state
from app.core.config import get_settings
from app.db.supabase import get_supabase_client, get_supabase_service_role_client
from app.errors import error_response, raise_api_error
from app.monitoring import resolve_environment
from app.rate_limit import check_rate_limit_by_ip, check_rate_limit_by_user
from app.schemas.auth import (
    AccountMethodsMutationResponse,
    AccountMethodsResponse,
    AvailabilityResponse,
    DeleteAccountRequest,
    EmailCheckRequest,
    GoogleAuthRequest,
    LinkGoogleRequest,
    LoginRequest,
    EmailVerificationResponse,
    MessageResponse,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RemovePasswordRequest,
    ResendVerificationRequest,
    RegistrationResponse,
    RegisterRequest,
    SetPasswordRequest,
    TokenResponse,
    UnlinkGoogleRequest,
    UsernameCheckRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.services import account_linking
from app.services.account_deletion import delete_account
from app.services.authentication_audit_events import (
    FailureCategory,
    new_audit_event_id,
    new_auth_correlation_id,
    record_authentication_event,
)
from app.services.authentication_observability import safe_auth_log, safe_auth_monitor
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
        terms_accepted=user.get("terms_accepted_at") is not None,
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


def _get_user_by_column(
    client: Client,
    column: str,
    value: str,
    columns: str,
) -> dict[str, Any] | None:
    response = (
        client.table("users")
        .select(columns)
        .eq(column, value)
        .limit(1)
        .execute()
    )
    return response.data[0] if response.data else None


def _ensure_unique(client: Client, column: str, value: str, message: str) -> None:
    if _get_user_by_column(client, column, value, "id"):
        raise_api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            message=message,
        )


class _LastLoginUpdateNotPersisted(RuntimeError):
    pass


class _SanitizedAuthenticationFailure(RuntimeError):
    """Constant-text boundary for unexpected auth errors sent to global monitoring."""


def _parse_aware_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _last_login_error_category(exc: Exception) -> str:
    if isinstance(exc, _LastLoginUpdateNotPersisted):
        return "no_rows_updated"
    if isinstance(exc, HTTPException):
        return "configuration_error"
    if isinstance(exc, APIError):
        return "postgrest_api_error"
    return "database_error"


def _update_last_login(
    user_id: str,
    *,
    auth_flow: str,
    attempt_id: str | None = None,
) -> None:
    endpoint = "/auth/login" if auth_flow == "password" else "/auth/google"
    environment = "unknown"
    try:
        environment = resolve_environment(get_settings().sentry_environment)
        response = (
            get_supabase_service_role_client()
            .table("users")
            .update({"last_login": _now_iso()})
            .eq("id", user_id)
            .execute()
        )
        updated_rows = response.data if isinstance(response.data, list) else []
        updated_user = next(
            (
                row
                for row in updated_rows
                if isinstance(row, dict) and str(row.get("id")) == user_id
            ),
            None,
        )
        if updated_user is None or _parse_aware_timestamp(updated_user.get("last_login")) is None:
            raise _LastLoginUpdateNotPersisted

        success_context = {
            "event": "auth.last_login.success",
            "auth_flow": auth_flow,
            "auth_method": auth_flow,
            "environment": environment,
            "user_id": user_id,
            "endpoint": endpoint,
            "method": "POST",
            "result": "success",
        }
        if attempt_id:
            success_context["attempt_id"] = attempt_id
        safe_auth_log(
            logger,
            "info",
            "auth last_login update succeeded",
            extra=success_context,
        )
    except Exception as exc:
        error_category = _last_login_error_category(exc)
        failure_context = {
            "event": "auth.last_login.failure",
            "auth_flow": auth_flow,
            "auth_method": auth_flow,
            "environment": environment,
            "user_id": user_id,
            "endpoint": endpoint,
            "method": "POST",
            "result": "partial_failure",
            "error_code": "DATABASE_ERROR",
            "error_category": error_category,
            "exception_type": exc.__class__.__name__,
        }
        if attempt_id:
            failure_context["attempt_id"] = attempt_id
        safe_auth_log(
            logger,
            "warning",
            "auth last_login update failed but login will continue",
            extra=failure_context,
        )
        safe_auth_monitor(
            "Authentication last_login update failed",
            level="warning",
            event="auth.last_login.failure",
            auth_flow=auth_flow,
            auth_method=auth_flow,
            environment=environment,
            user_id_present=True,
            endpoint=endpoint,
            error_code="DATABASE_ERROR",
            error_category=error_category,
            exception_type=exc.__class__.__name__,
        )


def _client_ip(request: Request) -> str:
    # Trust only ASGI's resolved peer. Production may enable Uvicorn proxy-header
    # handling only for explicitly trusted Railway proxy addresses; application
    # code never accepts a client-supplied forwarding header directly.
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _http_error_code(exc: HTTPException) -> str | None:
    if isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        return str(code) if code else None
    return None


def _login_failure_category(
    exc: HTTPException,
    *,
    auth_method: str,
) -> FailureCategory:
    code = _http_error_code(exc)
    if code == "EMAIL_NOT_VERIFIED" or (
        auth_method == "google"
        and exc.status_code == status.HTTP_403_FORBIDDEN
    ):
        return "email_not_verified"
    if code == "ACCOUNT_LINK_REQUIRED":
        return "account_link_required"
    if code == "IDENTITY_DATA_CONFLICT":
        return "identity_conflict"
    if code == "RATE_LIMITED" or exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return "rate_limited"
    if exc.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return "service_unavailable"
    if auth_method == "google":
        return "invalid_provider_credential"
    return "invalid_credentials"


@router.post("/google", response_model=TokenResponse)
def google_login(request: Request, payload: GoogleAuthRequest) -> TokenResponse:
    attempt_id = new_auth_correlation_id()
    audit_event_id = new_audit_event_id()
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_google", [(10, 60), (50, 3600)]
    )
    if rate_limit_hit:
        record_authentication_event(
            event_id=audit_event_id,
            event_type="login",
            outcome="failed",
            auth_method="google",
            correlation_id=attempt_id,
            failure_category="rate_limited",
        )
        return rate_limit_hit

    safe_auth_log(
        logger,
        "info",
        "google login request started",
        extra={
            "event": "auth.login.start",
            "auth_method": "google",
            "endpoint": "/auth/google",
            "method": "POST",
            "attempt_id": attempt_id,
        },
    )
    user: dict[str, Any] | None = None
    token_response: TokenResponse | None = None
    unexpected_error_type: str | None = None
    try:
        google_user = verify_google_token(payload.token, attempt_id=attempt_id)
        user = find_or_create_google_user(google_user, attempt_id=attempt_id)
        token_response = _create_token_response(user)
        _update_last_login(
            str(user["id"]),
            auth_flow="google",
            attempt_id=attempt_id,
        )
    except HTTPException as exc:
        audit_user_id = getattr(exc, "audit_user_id", None)
        if audit_user_id is None and user is not None:
            audit_user_id = str(user.get("id")) if user.get("id") else None
        record_authentication_event(
            event_id=audit_event_id,
            event_type="login",
            outcome="failed",
            auth_method="google",
            correlation_id=attempt_id,
            user_id=audit_user_id,
            failure_category=_login_failure_category(exc, auth_method="google"),
        )
        safe_auth_log(
            logger,
            "warning",
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
    except Exception as exc:
        record_authentication_event(
            event_id=audit_event_id,
            event_type="login",
            outcome="failed",
            auth_method="google",
            correlation_id=attempt_id,
            user_id=str(user.get("id")) if user and user.get("id") else None,
            failure_category="internal_error",
        )
        unexpected_error_type = exc.__class__.__name__

    if unexpected_error_type is not None:
        safe_auth_log(
            logger,
            "warning",
            "google login failed unexpectedly",
            extra={
                "event": "auth.login.failure",
                "auth_method": "google",
                "endpoint": "/auth/google",
                "method": "POST",
                "error_code": "INTERNAL_SERVER_ERROR",
                "exception_type": unexpected_error_type,
                "result": "failure",
            },
        )
        raise _SanitizedAuthenticationFailure(
            "Google authentication failed unexpectedly"
        ) from None

    if token_response is None:
        raise _SanitizedAuthenticationFailure(
            "Google authentication did not produce a token response"
        ) from None

    record_authentication_event(
        event_id=audit_event_id,
        event_type="login",
        outcome="succeeded",
        auth_method="google",
        correlation_id=attempt_id,
        user_id=token_response.user.id,
    )
    safe_auth_log(
        logger,
        "info",
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

    service_role_client = get_supabase_service_role_client()
    _ensure_unique(
        service_role_client,
        "username",
        payload.username,
        "Username is already taken",
    )
    _ensure_unique(
        service_role_client,
        "email",
        payload.email,
        "Email is already registered",
    )
    _ensure_unique(
        service_role_client,
        "phone_number",
        payload.phone_number,
        "Phone number is already registered",
    )

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
        response = service_role_client.table("users").insert(user_data).execute()
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
    attempt_id = new_auth_correlation_id()
    audit_event_id = new_audit_event_id()
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_login", [(10, 60), (50, 3600)]
    )
    if rate_limit_hit:
        record_authentication_event(
            event_id=audit_event_id,
            event_type="login",
            outcome="failed",
            auth_method="password",
            correlation_id=attempt_id,
            failure_category="rate_limited",
        )
        return rate_limit_hit

    user: dict[str, Any] | None = None
    token_response: TokenResponse | None = None
    unexpected_error_type: str | None = None
    unexpected_failure_category: FailureCategory = "service_unavailable"
    try:
        service_role_client = get_supabase_service_role_client()
        login_columns = (
            "id,email,name,username,phone_number,password_hash,email_verified,"
            "email_verified_at,terms_accepted_at"
        )
        user = _get_user_by_column(
            service_role_client,
            "username",
            payload.username,
            login_columns,
        )
        if not user and "@" in payload.username:
            user = _get_user_by_column(
                service_role_client,
                "email",
                payload.username,
                login_columns,
            )
        unexpected_failure_category = "internal_error"
        if not user or not verify_password(payload.password, user.get("password_hash")):
            delay_seconds = record_failed_login_and_delay(request, payload.username)
            if delay_seconds > 0:
                safe_auth_log(
                    logger,
                    "warning",
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
            safe_auth_log(
                logger,
                "warning",
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
        token_response = _create_token_response(user)
        _update_last_login(
            str(user["id"]),
            auth_flow="password",
            attempt_id=attempt_id,
        )
    except HTTPException as exc:
        record_authentication_event(
            event_id=audit_event_id,
            event_type="login",
            outcome="failed",
            auth_method="password",
            correlation_id=attempt_id,
            user_id=str(user.get("id")) if user and user.get("id") else None,
            failure_category=_login_failure_category(exc, auth_method="password"),
        )
        raise
    except Exception as exc:
        record_authentication_event(
            event_id=audit_event_id,
            event_type="login",
            outcome="failed",
            auth_method="password",
            correlation_id=attempt_id,
            user_id=str(user.get("id")) if user and user.get("id") else None,
            failure_category=unexpected_failure_category,
        )
        unexpected_error_type = exc.__class__.__name__

    if unexpected_error_type is not None:
        safe_auth_log(
            logger,
            "warning",
            "password login failed unexpectedly",
            extra={
                "event": "auth.login.failure",
                "auth_method": "password",
                "endpoint": "/auth/login",
                "method": "POST",
                "error_code": "INTERNAL_SERVER_ERROR",
                "exception_type": unexpected_error_type,
                "result": "failure",
            },
        )
        raise _SanitizedAuthenticationFailure(
            "Password authentication failed unexpectedly"
        ) from None

    if token_response is None:
        raise _SanitizedAuthenticationFailure(
            "Password authentication did not produce a token response"
        ) from None

    record_authentication_event(
        event_id=audit_event_id,
        event_type="login",
        outcome="succeeded",
        auth_method="password",
        correlation_id=attempt_id,
        user_id=token_response.user.id,
    )
    safe_auth_log(
        logger,
        "info",
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
    correlation_id = new_auth_correlation_id()
    logout_event_id = new_audit_event_id()
    revocation_event_id = new_audit_event_id()
    failure_category: FailureCategory = "service_unavailable"
    audit_user_id: str | None = str(user_id)
    revocation_failed = False
    revocation_exception_type: str | None = None
    try:
        # revoke_user_tokens bumps tokens_valid_after atomically to
        # GREATEST(current value, now()) under a per-user advisory lock, so a
        # logout can never regress a later revocation (e.g. a concurrent
        # password reset or account-linking mutation on another device) even
        # if this request's DB round trip commits after that one's.
        response = (
            get_supabase_service_role_client()
            .rpc("revoke_user_tokens", {"p_user_id": user_id})
            .execute()
        )
        result = response.data[0].get("result") if response.data else None
        if result not in ("revoked", "user_not_found"):
            failure_category = "invalid_state"
            raise RuntimeError("unexpected revoke_user_tokens result")
        if result == "user_not_found":
            audit_user_id = None
    except Exception as exc:
        revocation_failed = True
        revocation_exception_type = exc.__class__.__name__

    if revocation_failed:
        record_authentication_event(
            event_id=revocation_event_id,
            event_type="token_revocation",
            outcome="failed",
            auth_method="bearer",
            correlation_id=correlation_id,
            user_id=audit_user_id,
            failure_category=failure_category,
            revocation_reason="logout",
        )
        record_authentication_event(
            event_id=logout_event_id,
            event_type="logout",
            outcome="failed",
            auth_method="bearer",
            correlation_id=correlation_id,
            user_id=audit_user_id,
            failure_category=failure_category,
        )
        safe_auth_log(
            logger,
            "warning",
            "logout tokens_valid_after update failed",
            extra={
                "event": "auth.logout.failure",
                "user_id": user_id,
                "exception_type": revocation_exception_type,
            },
        )
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Logout failed",
        )

    cache_invalidation_exception_type: str | None = None
    try:
        # Authentication dependencies re-read tokens_valid_after from the
        # database on every request, including cache hits. This local cache
        # cleanup is therefore an optimization after authoritative revocation,
        # not part of the revocation security boundary.
        invalidate_cached_user(user_id)
    except Exception as exc:  # noqa: BLE001 - revocation already succeeded
        cache_invalidation_exception_type = exc.__class__.__name__

    if cache_invalidation_exception_type is not None:
        safe_auth_log(
            logger,
            "warning",
            "logout cache invalidation failed after token revocation",
            extra={
                "event": "auth.logout.cache_invalidation.failure",
                "auth_method": "bearer",
                "exception_type": cache_invalidation_exception_type,
                "user_id_present": True,
                "result": "partial_failure",
            },
        )
        safe_auth_monitor(
            "Authentication logout cache invalidation failed",
            level="warning",
            event="auth.logout.cache_invalidation.failure",
            auth_method="bearer",
            exception_type=cache_invalidation_exception_type,
            user_id_present=True,
            result="partial_failure",
        )

    record_authentication_event(
        event_id=revocation_event_id,
        event_type="token_revocation",
        outcome="succeeded",
        auth_method="bearer",
        correlation_id=correlation_id,
        user_id=audit_user_id,
        revocation_reason="logout",
    )
    record_authentication_event(
        event_id=logout_event_id,
        event_type="logout",
        outcome="succeeded",
        auth_method="bearer",
        correlation_id=correlation_id,
        user_id=audit_user_id,
    )
    safe_auth_log(
        logger,
        "info",
        "user logged out",
        extra={
            "event": "auth.logout.success",
            "user_id": user_id,
        },
    )
    return {"message": "Logged out successfully"}



@router.post("/accept-terms", response_model=MessageResponse)
def accept_terms(current_user: dict = Depends(require_active_user)) -> MessageResponse:
    user_id = str(current_user["id"])
    response = (
        get_supabase_service_role_client()
        .table("users")
        .update({"terms_accepted_at": _now_iso()})
        .eq("id", user_id)
        .execute()
    )
    if not response.data:
        raise_api_error(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_SERVER_ERROR",
            message="Terms acceptance could not be saved",
        )
    invalidate_cached_user(user_id)
    return MessageResponse(message="Terms accepted")


@router.post("/check-username", response_model=AvailabilityResponse)
def check_username(request: Request, payload: UsernameCheckRequest) -> AvailabilityResponse:
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_check_availability", [(20, 60), (100, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit
    # Availability checks intentionally disclose one registration-oriented
    # boolean and no user record. Login and recovery failures remain generic.
    service_role_client = get_supabase_service_role_client()
    user = _get_user_by_column(
        service_role_client,
        "username",
        payload.username,
        "id",
    )
    return AvailabilityResponse(available=user is None)


@router.post("/check-email", response_model=AvailabilityResponse)
def check_email(request: Request, payload: EmailCheckRequest) -> AvailabilityResponse:
    rate_limit_hit = check_rate_limit_by_ip(
        request, "auth_check_availability", [(20, 60), (100, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit
    service_role_client = get_supabase_service_role_client()
    user = _get_user_by_column(
        service_role_client,
        "email",
        payload.email,
        "id",
    )
    return AvailabilityResponse(available=user is None)


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
    service_role_client = get_supabase_service_role_client()
    user = _get_user_by_column(
        service_role_client,
        "email",
        payload.email,
        "id,email_verified,password_hash",
    )
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


# --- Account linking (E01-04) -----------------------------------------------
# Every mutating endpoint below returns a fresh access token. Linking Google is
# additive and does not revoke existing sessions; unlinking or changing the
# password still advances tokens_valid_after and revokes other sessions.


@router.get("/account-methods", response_model=AccountMethodsResponse)
def get_account_methods(current_user: dict = Depends(require_active_user)) -> AccountMethodsResponse:
    methods = account_linking.get_account_methods(str(current_user["id"]))
    return AccountMethodsResponse(**methods)


@router.post("/link/google", response_model=AccountMethodsMutationResponse)
def link_google_account(
    request: Request,
    payload: LinkGoogleRequest,
    current_user: dict = Depends(require_active_user),
) -> AccountMethodsMutationResponse:
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "account_linking_link_google", [(10, 60), (30, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    result = account_linking.link_google(str(current_user["id"]), payload.token)
    logger.info(
        "google account linked",
        extra={"event": "auth.account_linking.link_google.success", "user_id": current_user["id"]},
    )
    return AccountMethodsMutationResponse(**result)


@router.post("/unlink/google", response_model=AccountMethodsMutationResponse)
def unlink_google_account(
    request: Request,
    payload: UnlinkGoogleRequest,
    current_user: dict = Depends(require_active_user),
) -> AccountMethodsMutationResponse:
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "account_linking_unlink_google", [(10, 60), (30, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    result = account_linking.unlink_google(str(current_user["id"]), payload.current_password, request)
    logger.info(
        "google account unlinked",
        extra={"event": "auth.account_linking.unlink_google.success", "user_id": current_user["id"]},
    )
    return AccountMethodsMutationResponse(**result)


@router.post("/set-password", response_model=AccountMethodsMutationResponse)
def set_account_password(
    request: Request,
    payload: SetPasswordRequest,
    current_user: dict = Depends(require_active_user),
) -> AccountMethodsMutationResponse:
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "account_linking_set_password", [(10, 60), (30, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    result = account_linking.set_password_for_user(
        str(current_user["id"]), payload.google_token, payload.password, payload.password_confirm
    )
    logger.info(
        "account password set",
        extra={"event": "auth.account_linking.set_password.success", "user_id": current_user["id"]},
    )
    return AccountMethodsMutationResponse(**result)


@router.post("/remove-password", response_model=AccountMethodsMutationResponse)
def remove_account_password(
    request: Request,
    payload: RemovePasswordRequest,
    current_user: dict = Depends(require_active_user),
) -> AccountMethodsMutationResponse:
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "account_linking_remove_password", [(10, 60), (30, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    result = account_linking.remove_password_for_user(str(current_user["id"]), payload.google_token)
    logger.info(
        "account password removed",
        extra={"event": "auth.account_linking.remove_password.success", "user_id": current_user["id"]},
    )
    return AccountMethodsMutationResponse(**result)


@router.delete("/account", response_model=MessageResponse)
def delete_user_account(
    request: Request,
    payload: DeleteAccountRequest,
    current_user: dict = Depends(require_active_user),
) -> MessageResponse:
    rate_limit_hit = check_rate_limit_by_user(
        str(current_user["id"]), "account_deletion", [(3, 60), (5, 3600)]
    )
    if rate_limit_hit:
        return rate_limit_hit

    delete_account(
        user_id=str(current_user["id"]),
        password=payload.password,
        current_password=payload.current_password,
        google_token=payload.google_token,
        request=request,
    )
    return MessageResponse(message="Account deleted")

