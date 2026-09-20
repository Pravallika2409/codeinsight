"""
Application configuration.

All configuration is sourced from environment variables (see .env.example
at the repository root). No secrets or credentials are hardcoded here.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "CodeInsight AI"
    ENV: str = "development"
    DEBUG: bool = True

    # --- API ---
    API_PREFIX: str = "/api"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # --- Security ---
    SECRET_KEY: str = "change-me-in-env"  # overridden by env var in real deployments
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # --- Database (used from Phase 3 onward) ---
    DATABASE_URL: str = "postgresql+psycopg2://codeinsight:codeinsight@localhost:5432/codeinsight"

    # --- Redis (used from Phase 5 onward) ---
    REDIS_URL: str = "redis://localhost:6379/0"
    ANALYSIS_CACHE_TTL_SECONDS: int = 3600
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_ANALYZE_PER_MINUTE: int = 20
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10

    # --- AI service (used from Phase 4 onward) ---
    AI_PROVIDER: str = "anthropic"
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-sonnet-4-6"
    AI_TIMEOUT_SECONDS: int = 20
    AI_MAX_OUTPUT_TOKENS: int = 1500

    # --- Analysis engine ---
    MAX_CODE_SIZE_BYTES: int = 200_000  # request-size guard for /api/analyze
    ANALYSIS_TIMEOUT_SECONDS: int = 15
    SUPPORTED_LANGUAGES: List[str] = ["cpp", "python", "javascript", "java"]

    # --- GitHub repository integration (Phase 6) ---
    GITHUB_TOKEN: str = ""  # optional; raises the unauthenticated rate limit and allows private repos
    GITHUB_API_TIMEOUT_SECONDS: int = 15
    GITHUB_MAX_FILES: int = 15  # caps cost/time for a single repo analysis
    GITHUB_MAX_FILE_SIZE_BYTES: int = 200_000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so we parse the environment only once."""
    return Settings()
