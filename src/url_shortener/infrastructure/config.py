"""Enterprise configuration management using Pydantic Settings."""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings for the URL Shortener service."""
    model_config = SettingsConfigDict(
        env_prefix="URL_SHORTENER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Service & Networking
    ENVIRONMENT: str = "production"
    SERVICE_NAME: str = "enterprise-url-shortener"
    BASE_URL: str = "http://localhost:8000"
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database & Persistence
    DATABASE_URL: str = "sqlite:///./url_shortener.db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Caching
    REDIS_URL: Optional[str] = None
    CACHE_DEFAULT_TTL_SECONDS: int = 3600  # 1 hour default redirect cache

    # Shortcode Configuration
    DEFAULT_SLUG_LENGTH: int = 7
    MAX_COLLISION_RETRIES: int = 5
    DEFAULT_EXPIRATION_DAYS: Optional[int] = 365  # 1 year default, None for permanent

    # Security & Abuse Prevention
    ENABLE_SSRF_PROTECTION: bool = True
    BLOCKED_DOMAINS: List[str] = [
        "localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal",
        "169.254.169.254", "internal", "local"
    ]
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # Human-In-The-Loop & Governance
    REQUIRE_HITL_ON_BREAKING_CHANGES: bool = True
    AUDIT_LOG_PATH: str = "artifacts/audit_ledger.jsonl"


settings = Settings()
