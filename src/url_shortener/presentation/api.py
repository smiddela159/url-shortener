"""FastAPI REST Presentation Layer for Enterprise URL Shortener."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse

from src.url_shortener.domain.exceptions import (
    DomainError,
    InvalidUrlError,
    ShortCodeNotFoundError,
    SlugCollisionError,
    UrlExpiredError,
    SSRFSecurityViolationError,
    RateLimitExceededError,
    DomainPolicyViolationError,
)
from src.url_shortener.domain.repositories import UrlRepository, AnalyticsRepository, CacheService, RateLimiterService
from src.url_shortener.infrastructure.config import settings
from src.url_shortener.infrastructure.cache.service import InMemoryCacheService
from src.url_shortener.infrastructure.database.repository import SqlAlchemyUrlRepository, InMemoryUrlRepository
from src.url_shortener.infrastructure.encoding.base62 import Base62CodeGenerator
from src.url_shortener.infrastructure.security.ssrf import SSRFValidator
from src.url_shortener.infrastructure.security.rate_limiter import SlidingWindowRateLimiter
from src.url_shortener.application.dto import (
    CreateShortUrlCommand,
    ResolveRedirectCommand,
)
from src.url_shortener.application.use_cases import (
    CreateShortUrlUseCase,
    ResolveRedirectUseCase,
    GetAnalyticsUseCase,
    DeleteUrlUseCase,
)
from src.url_shortener.presentation.schemas import (
    CreateUrlRequest,
    CreateUrlResponse,
    AnalyticsResponse,
    HealthResponse,
    MetricsResponse,
    ErrorEnvelope,
)
from src.url_shortener.presentation.middleware import SecurityHeadersMiddleware, RateLimitingMiddleware


def create_app(
    url_repo: Optional[UrlRepository] = None,
    analytics_repo: Optional[AnalyticsRepository] = None,
    cache_service: Optional[CacheService] = None,
    rate_limiter: Optional[RateLimiterService] = None,
    ssrf_validator: Optional[SSRFValidator] = None,
) -> FastAPI:
    """Application factory for the URL Shortener service."""

    app = FastAPI(
        title="Enterprise URL Shortener Service",
        description="High-reliability, financial-grade URL shortener with analytics and security guardrails.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Initialize persistence and services
    if url_repo is None or analytics_repo is None:
        db_repo = SqlAlchemyUrlRepository(settings.DATABASE_URL)
        active_url_repo = url_repo or db_repo
        active_analytics_repo = analytics_repo or db_repo
    else:
        active_url_repo = url_repo
        active_analytics_repo = analytics_repo

    active_cache = cache_service or InMemoryCacheService()
    active_rate_limiter = rate_limiter or SlidingWindowRateLimiter()
    active_ssrf = ssrf_validator or SSRFValidator(resolve_dns=settings.ENABLE_SSRF_PROTECTION)
    code_generator = Base62CodeGenerator()

    # Wire Use Cases
    create_use_case = CreateShortUrlUseCase(
        url_repo=active_url_repo,
        cache_service=active_cache,
        code_generator=code_generator,
        ssrf_validator=active_ssrf,
        base_url=settings.BASE_URL,
        max_collision_retries=settings.MAX_COLLISION_RETRIES,
    )
    resolve_use_case = ResolveRedirectUseCase(
        url_repo=active_url_repo,
        analytics_repo=active_analytics_repo,
        cache_service=active_cache,
    )
    analytics_use_case = GetAnalyticsUseCase(
        analytics_repo=active_analytics_repo,
    )
    delete_use_case = DeleteUrlUseCase(
        url_repo=active_url_repo,
        cache_service=active_cache,
    )

    # Attach Middlewares
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitingMiddleware, rate_limiter=active_rate_limiter)

    # State handles for health/metrics
    app.state.cache = active_cache
    app.state.url_repo = active_url_repo

    # Register Exception Handlers
    @app.exception_handler(InvalidUrlError)
    async def invalid_url_handler(request: Request, exc: InvalidUrlError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorEnvelope(
                error="InvalidUrl",
                code=exc.code,
                message=exc.message,
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(ShortCodeNotFoundError)
    async def not_found_handler(request: Request, exc: ShortCodeNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorEnvelope(
                error="NotFound",
                code=exc.code,
                message=exc.message,
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(SlugCollisionError)
    async def collision_handler(request: Request, exc: SlugCollisionError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorEnvelope(
                error="SlugCollision",
                code=exc.code,
                message=exc.message,
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(UrlExpiredError)
    async def expired_handler(request: Request, exc: UrlExpiredError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            content=ErrorEnvelope(
                error="UrlExpired",
                code=exc.code,
                message=exc.message,
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(SSRFSecurityViolationError)
    async def ssrf_handler(request: Request, exc: SSRFSecurityViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content=ErrorEnvelope(
                error="SecurityViolation",
                code=exc.code,
                message=f"SSRF violation: Access to destination is prohibited.",
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(DomainPolicyViolationError)
    async def policy_handler(request: Request, exc: DomainPolicyViolationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorEnvelope(
                error="PolicyViolation",
                code=exc.code,
                message=exc.message,
                timestamp=datetime.now(timezone.utc),
            ).model_dump(mode="json"),
        )

    # Routes
    @app.post(
        "/api/v1/urls",
        response_model=CreateUrlResponse,
        status_code=status.HTTP_201_CREATED,
        summary="Create a shortened URL",
    )
    def create_short_url(payload: CreateUrlRequest) -> CreateUrlResponse:
        cmd = CreateShortUrlCommand(
            url=payload.url,
            custom_slug=payload.custom_slug,
            ttl_seconds=payload.ttl_seconds,
        )
        result = create_use_case.execute(cmd)
        return CreateUrlResponse(
            short_code=result.short_code,
            short_url=result.short_url,
            original_url=result.original_url,
            created_at=result.created_at,
            expires_at=result.expires_at,
            is_custom=result.is_custom,
        )

    @app.get(
        "/api/v1/urls/{short_code}",
        response_model=CreateUrlResponse,
        summary="Retrieve shortened URL metadata",
    )
    def get_short_url_metadata(short_code: str) -> CreateUrlResponse:
        entity = active_url_repo.find_by_short_code(short_code)
        if not entity:
            raise ShortCodeNotFoundError(short_code)
        return CreateUrlResponse(
            short_code=entity.short_code.value,
            short_url=f"{settings.BASE_URL}/{entity.short_code.value}",
            original_url=entity.original_url.value,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
            is_custom=(entity.short_code.slug_type == SlugType.CUSTOM),
        )

    @app.get(
        "/api/v1/urls/{short_code}/analytics",
        response_model=AnalyticsResponse,
        summary="Retrieve click analytics for a short URL",
    )
    def get_url_analytics(short_code: str) -> AnalyticsResponse:
        res = analytics_use_case.execute(short_code)
        return AnalyticsResponse(
            short_code=res.short_code,
            original_url=res.original_url,
            total_clicks=res.total_clicks,
            created_at=res.created_at,
            is_active=res.is_active,
            is_expired=res.is_expired,
            clicks_by_date=res.clicks_by_date,
            top_referrers=res.top_referrers,
            top_devices=res.top_devices,
        )

    @app.delete(
        "/api/v1/urls/{short_code}",
        status_code=status.HTTP_204_NO_CONTENT,
        summary="Delete a shortened URL",
    )
    def delete_short_url(short_code: str) -> Response:
        delete_use_case.execute(short_code)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/health", response_model=HealthResponse, summary="Service health status")
    def health_check() -> HealthResponse:
        return HealthResponse(timestamp=datetime.now(timezone.utc))

    @app.get("/metrics", response_model=MetricsResponse, summary="Telemetry metrics")
    def metrics() -> MetricsResponse:
        cache_stats = getattr(active_cache, "get_stats", lambda: {})()
        return MetricsResponse(
            cache=cache_stats,
            timestamp=datetime.now(timezone.utc),
        )

    @app.get(
        "/{short_code}",
        response_class=RedirectResponse,
        status_code=status.HTTP_302_FOUND,
        summary="Resolve redirect for short code",
    )
    def redirect_short_url(short_code: str, request: Request) -> RedirectResponse:
        # Avoid intercepting documentation/health routes
        if short_code in ("health", "metrics", "docs", "redoc", "openapi.json", "favicon.ico"):
            raise ShortCodeNotFoundError(short_code)

        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "127.0.0.1")
        user_agent = request.headers.get("User-Agent", "unknown")
        referrer = request.headers.get("Referer", "")

        ua_lower = user_agent.lower()
        device_type = "mobile" if any(k in ua_lower for k in ("mobi", "iphone", "android", "ipad")) else "desktop"

        cmd = ResolveRedirectCommand(
            short_code=short_code,
            ip_address=client_ip,
            user_agent=user_agent,
            referrer=referrer,
            device_type=device_type,
        )
        res = resolve_use_case.execute(cmd)
        return RedirectResponse(url=res.original_url, status_code=status.HTTP_302_FOUND)

    return app


# Default app instance
app = create_app()
