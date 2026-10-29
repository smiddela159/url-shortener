"""Unit tests for enterprise security guards: SSRF and Rate Limiting."""

import pytest

from src.url_shortener.domain.exceptions import SSRFSecurityViolationError
from src.url_shortener.infrastructure.security.ssrf import SSRFValidator
from src.url_shortener.infrastructure.security.rate_limiter import SlidingWindowRateLimiter


class TestSSRFValidator:
    def setup_method(self) -> None:
        # Use validator with resolve_dns=False to test IP / hostname heuristics deterministically
        self.validator = SSRFValidator(resolve_dns=False)

    def test_blocks_localhost(self) -> None:
        with pytest.raises(SSRFSecurityViolationError, match="blocked"):
            self.validator.validate("http://localhost/admin")

    def test_blocks_loopback_ip(self) -> None:
        with pytest.raises(SSRFSecurityViolationError, match="loopback"):
            self.validator.validate("http://127.0.0.1:8080/secret")

    def test_blocks_rfc1918_private_ips(self) -> None:
        private_urls = [
            "http://10.0.0.1/status",
            "http://172.16.1.50:80/db",
            "http://192.168.1.100/router",
        ]
        for url in private_urls:
            with pytest.raises(SSRFSecurityViolationError, match="private network address"):
                self.validator.validate(url)

    def test_blocks_aws_cloud_metadata(self) -> None:
        with pytest.raises(SSRFSecurityViolationError, match="cloud metadata"):
            self.validator.validate("http://169.254.169.254/latest/meta-data/")

    def test_blocks_internal_domain_suffixes(self) -> None:
        with pytest.raises(SSRFSecurityViolationError, match="internal namespace"):
            self.validator.validate("https://api.internal/v1/keys")
        with pytest.raises(SSRFSecurityViolationError, match="internal namespace"):
            self.validator.validate("https://database.local/admin")

    def test_allows_legitimate_public_urls(self) -> None:
        valid_urls = [
            "https://www.schwab.com",
            "https://github.com/google/gemini",
            "http://example.com:8080/path?query=1",
        ]
        for url in valid_urls:
            # Should not raise any exception
            self.validator.validate(url)


class TestSlidingWindowRateLimiter:
    def test_rate_limiter_enforces_limit(self) -> None:
        limiter = SlidingWindowRateLimiter()
        client_id = "test-client-1"

        # Allow 5 requests in a 10-second window
        for _ in range(5):
            assert limiter.is_allowed(client_id, max_requests=5, window_seconds=10) is True

        # 6th request within window must be rejected
        assert limiter.is_allowed(client_id, max_requests=5, window_seconds=10) is False

    def test_separate_clients_have_isolated_quotas(self) -> None:
        limiter = SlidingWindowRateLimiter()
        for _ in range(3):
            assert limiter.is_allowed("client-A", max_requests=3, window_seconds=10) is True

        # Client A exhausted
        assert limiter.is_allowed("client-A", max_requests=3, window_seconds=10) is False

        # Client B still has full quota
        assert limiter.is_allowed("client-B", max_requests=3, window_seconds=10) is True
