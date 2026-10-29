"""Data Transfer Objects (DTOs) for Application Use Cases."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass(frozen=True)
class CreateShortUrlCommand:
    """Command payload to request URL shortening."""
    url: str
    custom_slug: Optional[str] = None
    ttl_seconds: Optional[int] = None
    created_by: Optional[str] = None


@dataclass(frozen=True)
class ShortUrlResult:
    """Result data returned upon successful URL shortening."""
    short_code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    is_custom: bool


@dataclass(frozen=True)
class ResolveRedirectCommand:
    """Command payload to resolve a redirect and track analytics."""
    short_code: str
    ip_address: str = "127.0.0.1"
    user_agent: str = "unknown"
    referrer: str = ""
    country: str = "UNKNOWN"
    device_type: str = "UNKNOWN"


@dataclass(frozen=True)
class RedirectResult:
    """Result data returned from resolving a short code redirect."""
    original_url: str
    short_code: str
    is_cached: bool


@dataclass(frozen=True)
class AnalyticsResult:
    """Result data returned from querying short code analytics."""
    short_code: str
    original_url: str
    total_clicks: int
    created_at: datetime
    is_active: bool
    is_expired: bool
    clicks_by_date: Dict[str, int]
    top_referrers: Dict[str, int]
    top_devices: Dict[str, int]
