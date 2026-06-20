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
    # Path to the built frontend (vite `dist/`). When set, the backend serves
    # the SPA + its static assets itself — used by the single-image Docker
    # deploy. Empty in local dev (the separate vite dev server is used).
    FRONTEND_DIST: str = ""

    # CORS
    CORS_ALLOW_ORIGINS: str = "*"

    # Log
    LOG_DIR: str = "pylogs"
    DEBUG: bool = False

    # Admin account — auto-registered/ensured on startup (password reset each
    # start). Leave empty to skip admin bootstrap.
    ADMIN_ACCOUNT: str = ""
    ADMIN_PASSWORD: str = ""

    # Image upload — files stored under UPLOAD_DIR/<user_id>/<snowflake>.<ext>,
    # served publicly at UPLOAD_BASE_URL (mounted as StaticFiles in main.py).
    UPLOAD_DIR: str = "uploads"
    UPLOAD_BASE_URL: str = "/uploads"
    UPLOAD_MAX_SIZE_MB: int = 10
    # Comma-separated lowercase extension whitelist (no leading dot).
    # SVG excluded by default: served as image/svg+xml it runs <script> when the
    # public URL is opened directly (stored XSS via direct navigation).
    UPLOAD_ALLOWED_EXT: str = "png,jpg,jpeg,gif,webp"

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

    @property
    def UPLOAD_ALLOWED_EXT_LIST(self) -> set[str]:
        return {ext.strip().lower().lstrip(".") for ext in self.UPLOAD_ALLOWED_EXT.split(",") if ext.strip()}


settings = Settings()
