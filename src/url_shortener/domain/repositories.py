"""Domain port interfaces for repositories, caching, and rate limiting."""

from abc import ABC, abstractmethod
from typing import Optional

from src.url_shortener.domain.models import ShortenedUrl, ClickEvent, AnalyticsSummary


class UrlRepository(ABC):
    """Abstract port for URL persistence operations."""

    @abstractmethod
    def save(self, url: ShortenedUrl) -> ShortenedUrl:
        """Persist or update a shortened URL entity."""
        pass

    @abstractmethod
    def find_by_short_code(self, short_code: str) -> Optional[ShortenedUrl]:
        """Lookup shortened URL by its short code."""
        pass

    @abstractmethod
    def exists(self, short_code: str) -> bool:
        """Check whether a short code already exists."""
        pass

    @abstractmethod
    def increment_click_count(self, short_code: str) -> int:
        """Atomically increment click counter for a short code."""
        pass

    @abstractmethod
    def delete(self, short_code: str) -> bool:
        """Remove a short code from persistence."""
        pass


class AnalyticsRepository(ABC):
    """Abstract port for click analytics persistence and aggregation."""

    @abstractmethod
    def record_click(self, event: ClickEvent) -> None:
        """Persist a click event for a short code."""
        pass

    @abstractmethod
    def get_summary(self, short_code: str) -> Optional[AnalyticsSummary]:
        """Aggregate and retrieve click statistics for a short code."""
        pass


class CacheService(ABC):
    """Abstract port for low-latency key-value caching."""

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Retrieve cached string value by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        """Set cached value with optional expiration TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Evict key from cache."""
        pass

    @abstractmethod
    def increment(self, key: str, ttl_seconds: Optional[int] = None) -> int:
        """Atomically increment an integer counter."""
        pass


class RateLimiterService(ABC):
    """Abstract port for rate limiting client requests."""

    @abstractmethod
    def is_allowed(self, client_id: str, max_requests: int, window_seconds: int) -> bool:
        """Determines whether a client request is permitted within the rate limit window."""
        pass
