"""Domain value objects with strict invariants."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from urllib.parse import urlparse

from src.url_shortener.domain.exceptions import InvalidUrlError, DomainPolicyViolationError


RESERVED_SLUGS = frozenset({
    "api", "health", "metrics", "docs", "redoc", "openapi.json",
    "admin", "login", "auth", "static", "favicon.ico", "robots.txt"
})

SLUG_REGEX = re.compile(r"^[a-zA-Z0-9_-]{3,64}$")


class SlugType(str, Enum):
    """Categorizes whether shortcode was auto-generated or custom-defined."""
    GENERATED = "GENERATED"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class ShortCode:
    """Immutable value object representing a validated short code."""
    value: str
    slug_type: SlugType = SlugType.GENERATED

    def __post_init__(self) -> None:
        if not self.value:
            raise DomainPolicyViolationError("Short code cannot be empty.")
        if not SLUG_REGEX.match(self.value):
            raise DomainPolicyViolationError(
                f"Short code '{self.value}' is invalid. Must be 3-64 alphanumeric characters, hyphens, or underscores."
            )
        if self.value.lower() in RESERVED_SLUGS:
            raise DomainPolicyViolationError(f"Short code '{self.value}' is a reserved system keyword.")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OriginalUrl:
    """Immutable value object representing a destination URL."""
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidUrlError("URL cannot be empty.")
        if len(self.value) > 2048:
            raise InvalidUrlError("URL exceeds maximum length of 2048 characters.")

        try:
            parsed = urlparse(self.value)
        except Exception as exc:
            raise InvalidUrlError(f"Could not parse URL: {exc}") from exc

        if parsed.scheme.lower() not in ("http", "https"):
            raise InvalidUrlError("URL scheme must be HTTP or HTTPS.")
        if not parsed.netloc:
            raise InvalidUrlError("URL must include a valid network location (domain/host).")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ClickMetadata:
    """Immutable metadata captured during URL redirection."""
    ip_address: str
    user_agent: str
    referrer: str
    timestamp: datetime = datetime.now(timezone.utc)
    country: str = "UNKNOWN"
    device_type: str = "UNKNOWN"
