"""Enterprise security and rate limiting middleware."""

from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.url_shortener.domain.repositories import RateLimiterService
from src.url_shortener.infrastructure.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Enforces financial enterprise HTTP security headers."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter per client IP."""

    def __init__(self, app, rate_limiter: RateLimiterService) -> None:
        super().__init__(app)
        self.rate_limiter = rate_limiter

    async def dispatch(self, request: Request, call_next) -> Response:
        # Exclude health and metrics endpoints from rate limiting
        path = request.url.path
        if path in ("/health", "/metrics", "/docs", "/redoc", "/openapi.json"):
            return await call_next(request)

        # Extract client IP
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host
        else:
            client_ip = "127.0.0.1"

        is_allowed = self.rate_limiter.is_allowed(
            client_id=client_ip,
            max_requests=settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        )

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "RateLimitExceeded",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit of {settings.RATE_LIMIT_REQUESTS_PER_MINUTE} requests per minute exceeded.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                headers={"Retry-After": str(settings.RATE_LIMIT_WINDOW_SECONDS)},
            )

        return await call_next(request)
