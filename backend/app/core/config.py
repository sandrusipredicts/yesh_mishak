from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_key: str = Field(alias="SUPABASE_KEY")
    supabase_service_role_key: str | None = Field(default=None, alias="SUPABASE_SERVICE_ROLE_KEY")
    google_client_id: str = Field(alias="GOOGLE_CLIENT_ID")
    jwt_secret: str = Field(alias="JWT_SECRET")
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
        alias="CORS_ORIGINS",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=10080, alias="JWT_EXPIRE_MINUTES")
    firebase_project_id: str | None = Field(default=None, alias="FIREBASE_PROJECT_ID")
    firebase_service_account_json: str | None = Field(
        default=None,
        alias="FIREBASE_SERVICE_ACCOUNT_JSON",
    )
    firebase_service_account_file: str | None = Field(
        default=None,
        alias="FIREBASE_SERVICE_ACCOUNT_FILE",
    )
    disable_game_created_notifications: bool = Field(
        default=False,
        alias="DISABLE_GAME_CREATED_NOTIFICATIONS",
    )
    auth_user_cache_ttl_seconds: int = Field(
        default=300,
        alias="AUTH_USER_CACHE_TTL_SECONDS",
    )
    public_app_url: str = Field(default="http://localhost:5173", alias="PUBLIC_APP_URL")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from_address: str | None = Field(default=None, alias="SMTP_FROM_ADDRESS")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    email_verification_ttl_minutes: int = Field(default=60, alias="EMAIL_VERIFICATION_TTL_MINUTES")
    email_verification_resend_cooldown_seconds: int = Field(
        default=60,
        alias="EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS",
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
