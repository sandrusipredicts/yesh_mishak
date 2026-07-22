import re

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.auth.passwords import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, validate_password


class GoogleAuthRequest(BaseModel):
    token: str


PHONE_REGEX = re.compile(r"^\+?[0-9]+$")


def normalize_email_value(value: str) -> str:
    email = value.strip().lower()
    if not email:
        raise ValueError("Email is required")
    if "@" not in email or "." not in email.rsplit("@", maxsplit=1)[-1]:
        raise ValueError("A valid email is required")
    return email


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=3, max_length=40)
    email: str = Field(min_length=3, max_length=254)
    phone_number: str = Field(min_length=6, max_length=30)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirm: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("full_name", "username", "email", "phone_number")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field is required")
        return stripped

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip().lower()
        if not username.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username can contain only letters, numbers, hyphens and underscores")
        return username

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)

    @field_validator("phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        val = value.strip()
        normalized = val.replace(" ", "").replace("-", "")
        if not PHONE_REGEX.match(normalized):
            raise ValueError("Phone number must contain only digits and optional leading +")
        if not (7 <= len(normalized) <= 20):
            raise ValueError("Phone number must be between 7 and 20 characters long")
        return normalized


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        identifier = value.strip().lower()
        if not identifier:
            raise ValueError("Username or email is required")
        return identifier


class UsernameCheckRequest(BaseModel):
    username: str = Field(min_length=3, max_length=40)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip().lower()
        if not username:
            raise ValueError("Username is required")
        if not username.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username can contain only letters, numbers, hyphens and underscores")
        return username


class EmailCheckRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class ResendVerificationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirm: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class MessageResponse(BaseModel):
    message: str

class AvailabilityResponse(BaseModel):
    available: bool


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    username: str | None = None
    phone_number: str | None = None
    terms_accepted: bool = False


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
    email_verification_required: bool = False
    email_verification_sent: bool | None = None


class RegistrationResponse(BaseModel):
    user: UserResponse
    email_verification_required: bool = True
    email_verification_sent: bool


class EmailVerificationResponse(BaseModel):
    status: str
    message: str


class LinkGoogleRequest(BaseModel):
    token: str = Field(min_length=1)


class UnlinkGoogleRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class SetPasswordRequest(BaseModel):
    google_token: str = Field(min_length=1)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirm: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class RemovePasswordRequest(BaseModel):
    google_token: str = Field(min_length=1)


class DeleteAccountRequest(BaseModel):
    confirmation: Literal["DELETE"]
    current_password: str | None = Field(default=None, min_length=1, max_length=128)
    google_token: str | None = Field(default=None, min_length=1)


class EmailAccountMethod(BaseModel):
    address: str | None = None
    linked: bool
    verified: bool
    can_unlink: bool


class GoogleAccountMethod(BaseModel):
    linked: bool
    email: str | None = None
    can_unlink: bool


class AccountMethodsResponse(BaseModel):
    email: EmailAccountMethod
    google: GoogleAccountMethod
    available_login_methods: int


class AccountMethodsMutationResponse(BaseModel):
    account_methods: AccountMethodsResponse
    access_token: str
