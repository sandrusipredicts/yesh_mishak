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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
