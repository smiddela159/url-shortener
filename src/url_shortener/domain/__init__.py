"""Domain layer package exports."""

from src.url_shortener.domain.exceptions import (
    DomainError,
    InvalidUrlError,
    ShortCodeNotFoundError,
    SlugCollisionError,
    UrlExpiredError,
    SSRFSecurityViolationError,
    RateLimitExceededError,
    DomainPolicyViolationError,
)
from src.url_shortener.domain.models import (
    ShortenedUrl,
    ClickEvent,
    AnalyticsSummary,
)
from src.url_shortener.domain.value_objects import (
    ShortCode,
    OriginalUrl,
    SlugType,
    ClickMetadata,
)
from src.url_shortener.domain.repositories import (
    UrlRepository,
    AnalyticsRepository,
    CacheService,
    RateLimiterService,
)

__all__ = [
    "DomainError",
    "InvalidUrlError",
    "ShortCodeNotFoundError",
    "SlugCollisionError",
    "UrlExpiredError",
    "SSRFSecurityViolationError",
    "RateLimitExceededError",
    "DomainPolicyViolationError",
    "ShortenedUrl",
    "ClickEvent",
    "AnalyticsSummary",
    "ShortCode",
    "OriginalUrl",
    "SlugType",
    "ClickMetadata",
    "UrlRepository",
    "AnalyticsRepository",
    "CacheService",
    "RateLimiterService",
]
