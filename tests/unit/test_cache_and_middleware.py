"""Additional unit tests covering caching, rate limit middleware, and edge cases."""

from datetime import datetime, timezone
import pytest
from starlette.testclient import TestClient

from src.url_shortener.domain.exceptions import ShortCodeNotFoundError
from src.url_shortener.domain.value_objects import ShortCode, OriginalUrl
from src.url_shortener.infrastructure.cache.service import InMemoryCacheService
from src.url_shortener.infrastructure.database.repository import InMemoryUrlRepository
from src.url_shortener.infrastructure.security.rate_limiter import SlidingWindowRateLimiter
from src.url_shortener.application.use_cases import DeleteUrlUseCase, ResolveRedirectUseCase
from src.url_shortener.application.dto import ResolveRedirectCommand
from src.url_shortener.presentation.api import create_app


from src.url_shortener.infrastructure.security.ssrf import SSRFValidator


def test_in_memory_cache_operations() -> None:
    cache = InMemoryCacheService()

    # set and get
    cache.set("key1", "val1", ttl_seconds=60)
    assert cache.get("key1") == "val1"

    # increment
    count1 = cache.increment("counter")
    assert count1 == 1
    count2 = cache.increment("counter")
    assert count2 == 2

    # delete
    cache.delete("key1")
    assert cache.get("key1") is None

    # stats
    stats = cache.get_stats()
    assert "hit_ratio" in stats
    assert stats["hits"] >= 1

    # clear
    cache.clear()
    assert cache.get("counter") is None


def test_delete_nonexistent_url_raises_not_found() -> None:
    repo = InMemoryUrlRepository()
    cache = InMemoryCacheService()
    use_case = DeleteUrlUseCase(url_repo=repo, cache_service=cache)

    with pytest.raises(ShortCodeNotFoundError):
        use_case.execute("nonexistent123")


def test_resolve_redirect_cache_hit_path() -> None:
    repo = InMemoryUrlRepository()
    cache = InMemoryCacheService()
    use_case = ResolveRedirectUseCase(url_repo=repo, analytics_repo=repo, cache_service=cache)

    # Pre-populate cache directly
    cache.set("redirect:cachedCode", "https://cached-target.com")

    cmd = ResolveRedirectCommand(short_code="cachedCode")
    res = use_case.execute(cmd)
    assert res.is_cached is True
    assert res.original_url == "https://cached-target.com"


def test_rate_limiting_middleware_429() -> None:
    repo = InMemoryUrlRepository()
    cache = InMemoryCacheService()
    rate_limiter = SlidingWindowRateLimiter()
    ssrf_validator = SSRFValidator(resolve_dns=False)

    app = create_app(
        url_repo=repo,
        analytics_repo=repo,
        cache_service=cache,
        rate_limiter=rate_limiter,
        ssrf_validator=ssrf_validator,
    )
    client = TestClient(app)

    # Send 105 requests to trigger the 100 req/min limit
    client_ip = "203.0.113.195"
    triggered_429 = False

    for _ in range(105):
        resp = client.post(
            "/api/v1/urls",
            json={"url": "https://www.example.com"},
            headers={"X-Forwarded-For": client_ip},
        )
        if resp.status_code == 429:
            triggered_429 = True
            assert resp.json()["code"] == "RATE_LIMIT_EXCEEDED"
            break

    assert triggered_429 is True
