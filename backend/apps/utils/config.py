"""Application configuration loaded from .env via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # PostgreSQL
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_USER: str = "cloudnote"
    DB_PASSWORD: str = ""
    DB_NAME: str = "amanuensis"
    DB_SCHEMA: str = "public"
    DB_SSLMODE: str = "require"

    # SQLite
    SQLITE_PATH: str = "./cache/sqlite.db"

    # JWT
    ACCESS_JWT_SECRET: str = ""
    REFRESH_JWT_SECRET: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 2 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Server
    BACKEND_SERVER_PORT: int = 6581
    FRONTEND_SERVER_PORT: int = 6580

    # CORS
    CORS_ALLOW_ORIGINS: str = "*"

    # Log
    LOG_DIR: str = "pylogs"
    DEBUG: bool = False

    # AI
    AI_TYPE: str = ""
    API_KEY: str = ""
    API_BASE: str = ""
    AI_MODEL: str = ""

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        if self.CORS_ALLOW_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ALLOW_ORIGINS.split(",")]


settings = Settings()
