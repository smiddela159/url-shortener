"""Domain entity models for URL Shortener Service."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from src.url_shortener.domain.exceptions import UrlExpiredError
from src.url_shortener.domain.value_objects import ShortCode, OriginalUrl, ClickMetadata


@dataclass
class ShortenedUrl:
    """Core domain aggregate representing a shortened URL."""
    short_code: ShortCode
    original_url: OriginalUrl
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    is_active: bool = True
    click_count: int = 0
    id: Optional[int] = None
    created_by: Optional[str] = None

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        """Determines whether the URL has expired based on its TTL."""
        if self.expires_at is None:
            return False
        now = current_time or datetime.now(timezone.utc)
        # Ensure timezone-aware comparison
        if self.expires_at.tzinfo is None:
            expires = self.expires_at.replace(tzinfo=timezone.utc)
        else:
            expires = self.expires_at
        return now > expires

    def validate_accessible(self) -> None:
        """Validates that the URL is active and unexpired."""
        if not self.is_active:
            raise UrlExpiredError(self.short_code.value)
        if self.is_expired():
            raise UrlExpiredError(self.short_code.value)

    def record_click(self) -> None:
        """Increment internal click count."""
        self.click_count += 1


@dataclass
class ClickEvent:
    """Domain entity representing a discrete access event."""
    short_code: str
    metadata: ClickMetadata
    id: Optional[int] = None


@dataclass
class AnalyticsSummary:
    """Domain model summarizing click analytics for a specific short code."""
    short_code: str
    original_url: str
    total_clicks: int
    created_at: datetime
    is_active: bool
    is_expired: bool
    clicks_by_date: Dict[str, int] = field(default_factory=dict)
    top_referrers: Dict[str, int] = field(default_factory=dict)
    top_devices: Dict[str, int] = field(default_factory=dict)
