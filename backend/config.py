"""Application configuration via environment variables."""

import json
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://hr_app:password@localhost:5432/hr_intelligence"
    DATABASE_URL_SYNC: str = "postgresql://hr_app:password@localhost:5432/hr_intelligence"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "https://hr.cfai.in/auth/callback"

    # Auth — JWT_SECRET MUST be set via environment / .env (no default)
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24
    ALLOWED_DOMAIN: str = "creativefuel.io"

    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "debug"
    CORS_ORIGINS: str = '["http://localhost:3000"]'

    # File Storage
    UPLOAD_DIR: str = "/data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # Keka (for migration/sync)
    KEKA_BASE_URL: str = "https://creativefuel.keka.com/api/v1"
    KEKA_CLIENT_ID: str = ""
    KEKA_CLIENT_SECRET: str = ""
    KEKA_API_KEY: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS JSON string into a list."""
        try:
            return json.loads(self.CORS_ORIGINS)
        except (json.JSONDecodeError, TypeError):
            return ["http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
