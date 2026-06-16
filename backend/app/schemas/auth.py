from pydantic import BaseModel, Field, field_validator


class GoogleAuthRequest(BaseModel):
    token: str


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    username: str = Field(min_length=3, max_length=40)
    email: str = Field(min_length=3, max_length=254)
    phone_number: str = Field(min_length=6, max_length=30)
    password: str = Field(min_length=8, max_length=128)
    password_confirm: str = Field(min_length=8, max_length=128)

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
        email = value.strip().lower()
        if "@" not in email or "." not in email.rsplit("@", maxsplit=1)[-1]:
            raise ValueError("A valid email is required")
        return email


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip().lower()
        if not username:
            raise ValueError("Username is required")
        return username


class UsernameCheckRequest(BaseModel):
    username: str = Field(min_length=1, max_length=40)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip().lower()
        if not username:
            raise ValueError("Username is required")
        return username


class EmailCheckRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not email:
            raise ValueError("Email is required")
        return email


class AvailabilityResponse(BaseModel):
    available: bool


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    username: str | None = None
    phone_number: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
