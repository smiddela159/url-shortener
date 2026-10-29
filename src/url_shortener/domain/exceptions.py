"""Domain layer exceptions for URL Shortener Service."""

from typing import Optional


class DomainError(Exception):
    """Base exception for all domain errors."""
    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class InvalidUrlError(DomainError):
    """Raised when an invalid URL string is supplied."""
    def __init__(self, message: str = "The provided URL is invalid."):
        super().__init__(message, code="INVALID_URL")


class ShortCodeNotFoundError(DomainError):
    """Raised when a requested short code does not exist."""
    def __init__(self, short_code: str):
        super().__init__(f"Short code '{short_code}' not found.", code="NOT_FOUND")
        self.short_code = short_code


class SlugCollisionError(DomainError):
    """Raised when a custom alias slug is already in use."""
    def __init__(self, slug: str):
        super().__init__(f"Custom slug '{slug}' is already in use.", code="SLUG_COLLISION")
        self.slug = slug


class UrlExpiredError(DomainError):
    """Raised when accessing a shortened URL that has exceeded its TTL."""
    def __init__(self, short_code: str):
        super().__init__(f"Short code '{short_code}' has expired.", code="URL_EXPIRED")
        self.short_code = short_code


class SSRFSecurityViolationError(DomainError):
    """Raised when a URL targets a private, internal, or loopback network address."""
    def __init__(self, target: str, reason: str):
        super().__init__(f"SSRF violation: target '{target}' blocked ({reason}).", code="SSRF_SECURITY_VIOLATION")
        self.target = target
        self.reason = reason


class RateLimitExceededError(DomainError):
    """Raised when a client exceeds allowed request frequency."""
    def __init__(self, client_id: str, retry_after: int = 60):
        super().__init__(f"Rate limit exceeded for client '{client_id}'. Retry after {retry_after}s.", code="RATE_LIMIT_EXCEEDED")
        self.client_id = client_id
        self.retry_after = retry_after


class DomainPolicyViolationError(DomainError):
    """Raised when an operation violates business domain policies."""
    def __init__(self, message: str):
        super().__init__(message, code="POLICY_VIOLATION")
