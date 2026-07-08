from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field("development", alias="PENTECOSTAL_LIVE_ENV")
    database_url: str = Field(
        "sqlite:///./pentecostal_live.db",
        alias="PENTECOSTAL_LIVE_DB_URL",
    )
    jwt_secret: str = Field("change_me_before_real_use", alias="PENTECOSTAL_LIVE_JWT_SECRET")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(30, alias="PENTECOSTAL_LIVE_ACCESS_TOKEN_MINUTES")
    refresh_token_days: int = Field(30, alias="PENTECOSTAL_LIVE_REFRESH_TOKEN_DAYS")
    rate_limit_enabled: bool = Field(True, alias="PENTECOSTAL_LIVE_RATE_LIMIT_ENABLED")
    auth_rate_limit: str = Field("5/minute", alias="PENTECOSTAL_LIVE_AUTH_RATE_LIMIT")
    fernet_key: str = Field(
        "t3wLwiGjnd21N2hPHC8Gk0cVLquXgVD+ZO3BkWvNlao=",
        alias="PENTECOSTAL_LIVE_FERNET_KEY",
    )
    cors_origins: str = Field(
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        alias="PENTECOSTAL_LIVE_API_CORS_ORIGINS",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
