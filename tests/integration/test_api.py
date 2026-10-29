"""Integration tests for REST API endpoints using TestClient."""

from datetime import datetime, timedelta, timezone
from starlette.testclient import TestClient
import pytest

from src.url_shortener.presentation.api import create_app
from src.url_shortener.infrastructure.database.repository import InMemoryUrlRepository
from src.url_shortener.infrastructure.cache.service import InMemoryCacheService
from src.url_shortener.infrastructure.security.rate_limiter import SlidingWindowRateLimiter
from src.url_shortener.infrastructure.security.ssrf import SSRFValidator


@pytest.fixture
def test_client() -> TestClient:
    url_repo = InMemoryUrlRepository()
    cache_service = InMemoryCacheService()
    rate_limiter = SlidingWindowRateLimiter()
    ssrf_validator = SSRFValidator(resolve_dns=False)

    app = create_app(
        url_repo=url_repo,
        analytics_repo=url_repo,
        cache_service=cache_service,
        rate_limiter=rate_limiter,
        ssrf_validator=ssrf_validator,
    )
    return TestClient(app)


class TestApiEndpoints:
    def test_health_check(self, test_client: TestClient) -> None:
        response = test_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "enterprise-url-shortener"

    def test_metrics_endpoint(self, test_client: TestClient) -> None:
        response = test_client.get("/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "cache" in data

    def test_create_short_url_generated(self, test_client: TestClient) -> None:
        payload = {"url": "https://www.schwab.com/trading"}
        response = test_client.post("/api/v1/urls", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "short_code" in data
        assert data["original_url"] == "https://www.schwab.com/trading"
        assert data["is_custom"] is False
        assert len(data["short_code"]) >= 7

    def test_create_short_url_custom_slug(self, test_client: TestClient) -> None:
        payload = {
            "url": "https://www.schwab.com/etfs",
            "custom_slug": "schwab-etfs-2026",
        }
        response = test_client.post("/api/v1/urls", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["short_code"] == "schwab-etfs-2026"
        assert data["is_custom"] is True

    def test_custom_slug_collision_returns_409(self, test_client: TestClient) -> None:
        payload = {
            "url": "https://www.schwab.com/etfs",
            "custom_slug": "duplicate-slug",
        }
        # First creation succeeds
        res1 = test_client.post("/api/v1/urls", json=payload)
        assert res1.status_code == 201

        # Second creation with identical slug fails with 409 Conflict
        res2 = test_client.post("/api/v1/urls", json=payload)
        assert res2.status_code == 409
        data = res2.json()
        assert data["code"] == "SLUG_COLLISION"

    def test_ssrf_rejection_returns_403(self, test_client: TestClient) -> None:
        payload = {"url": "http://169.254.169.254/latest/meta-data"}
        response = test_client.post("/api/v1/urls", json=payload)
        assert response.status_code == 403
        data = response.json()
        assert data["code"] == "SSRF_SECURITY_VIOLATION"

    def test_redirect_flow_and_analytics(self, test_client: TestClient) -> None:
        # 1. Create short URL
        create_res = test_client.post(
            "/api/v1/urls",
            json={"url": "https://www.schwab.com/investing", "custom_slug": "invest-now"},
        )
        assert create_res.status_code == 201

        # 2. Perform redirect (follow_redirects=False to inspect 302)
        redirect_res = test_client.get(
            "/invest-now",
            headers={"User-Agent": "Mozilla/5.0 (iPhone)", "Referer": "https://twitter.com"},
            follow_redirects=False,
        )
        assert redirect_res.status_code == 302
        assert redirect_res.headers["location"] == "https://www.schwab.com/investing"

        # 3. Check analytics
        analytics_res = test_client.get("/api/v1/urls/invest-now/analytics")
        assert analytics_res.status_code == 200
        data = analytics_res.json()
        assert data["total_clicks"] == 1
        assert data["top_referrers"].get("https://twitter.com") == 1
        assert data["top_devices"].get("mobile") == 1

    def test_nonexistent_short_code_returns_404(self, test_client: TestClient) -> None:
        response = test_client.get("/nonexistent-slug", follow_redirects=False)
        assert response.status_code == 404
        assert response.json()["code"] == "NOT_FOUND"

    def test_delete_short_url(self, test_client: TestClient) -> None:
        test_client.post(
            "/api/v1/urls",
            json={"url": "https://www.example.com", "custom_slug": "to-delete"},
        )
        del_res = test_client.delete("/api/v1/urls/to-delete")
        assert del_res.status_code == 204

        # Verify it no longer exists
        get_res = test_client.get("/to-delete", follow_redirects=False)
        assert get_res.status_code == 404
