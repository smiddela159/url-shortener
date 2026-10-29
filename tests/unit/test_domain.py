"""Unit tests for domain entities, value objects, and invariants."""

from datetime import datetime, timedelta, timezone
import pytest

from src.url_shortener.domain.exceptions import (
    DomainPolicyViolationError,
    InvalidUrlError,
    UrlExpiredError,
)
from src.url_shortener.domain.models import ShortenedUrl
from src.url_shortener.domain.value_objects import ShortCode, OriginalUrl, SlugType


class TestValueObjects:
    def test_valid_short_code(self) -> None:
        sc = ShortCode("abc123Z")
        assert sc.value == "abc123Z"
        assert str(sc) == "abc123Z"

    def test_invalid_short_code_characters(self) -> None:
        with pytest.raises(DomainPolicyViolationError):
            ShortCode("invalid@slug!")

    def test_reserved_slug_rejection(self) -> None:
        for reserved in ["api", "health", "metrics", "docs", "admin"]:
            with pytest.raises(DomainPolicyViolationError, match="reserved system keyword"):
                ShortCode(reserved)

    def test_short_code_length_bounds(self) -> None:
        with pytest.raises(DomainPolicyViolationError):
            ShortCode("ab")  # Too short (< 3)
        with pytest.raises(DomainPolicyViolationError):
            ShortCode("a" * 65)  # Too long (> 64)

    def test_valid_original_url(self) -> None:
        url = OriginalUrl("https://www.schwab.com/investment-advice")
        assert str(url) == "https://www.schwab.com/investment-advice"

    def test_invalid_url_scheme(self) -> None:
        with pytest.raises(InvalidUrlError, match="HTTP or HTTPS"):
            OriginalUrl("ftp://files.example.com")

    def test_invalid_url_empty(self) -> None:
        with pytest.raises(InvalidUrlError):
            OriginalUrl("")

    def test_invalid_url_no_host(self) -> None:
        with pytest.raises(InvalidUrlError, match="network location"):
            OriginalUrl("https://")


class TestShortenedUrlAggregate:
    def test_unexpired_url(self) -> None:
        url = ShortenedUrl(
            short_code=ShortCode("valid123"),
            original_url=OriginalUrl("https://example.com"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert not url.is_expired()
        url.validate_accessible()

    def test_expired_url_raises_error(self) -> None:
        url = ShortenedUrl(
            short_code=ShortCode("expired1"),
            original_url=OriginalUrl("https://example.com"),
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        assert url.is_expired()
        with pytest.raises(UrlExpiredError):
            url.validate_accessible()

    def test_inactive_url_raises_error(self) -> None:
        url = ShortenedUrl(
            short_code=ShortCode("inactive1"),
            original_url=OriginalUrl("https://example.com"),
            is_active=False,
        )
        with pytest.raises(UrlExpiredError):
            url.validate_accessible()

    def test_record_click(self) -> None:
        url = ShortenedUrl(
            short_code=ShortCode("click12"),
            original_url=OriginalUrl("https://example.com"),
        )
        assert url.click_count == 0
        url.record_click()
        assert url.click_count == 1
