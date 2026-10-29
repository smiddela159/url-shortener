"""Application use cases orchestrating domain rules and persistence."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.url_shortener.domain.exceptions import (
    ShortCodeNotFoundError,
    SlugCollisionError,
    UrlExpiredError,
    DomainPolicyViolationError,
)
from src.url_shortener.domain.models import ShortenedUrl, ClickEvent
from src.url_shortener.domain.value_objects import ShortCode, OriginalUrl, ClickMetadata, SlugType
from src.url_shortener.domain.repositories import UrlRepository, AnalyticsRepository, CacheService
from src.url_shortener.application.dto import (
    CreateShortUrlCommand,
    ShortUrlResult,
    ResolveRedirectCommand,
    RedirectResult,
    AnalyticsResult,
)
from src.url_shortener.infrastructure.encoding.base62 import Base62CodeGenerator
from src.url_shortener.infrastructure.security.ssrf import SSRFValidator


class CreateShortUrlUseCase:
    """Orchestrates validation, slug generation/collision checking, and storage."""

    def __init__(
        self,
        url_repo: UrlRepository,
        cache_service: CacheService,
        code_generator: Base62CodeGenerator,
        ssrf_validator: Optional[SSRFValidator] = None,
        base_url: str = "http://localhost:8000",
        max_collision_retries: int = 5,
    ) -> None:
        self.url_repo = url_repo
        self.cache_service = cache_service
        self.code_generator = code_generator
        self.ssrf_validator = ssrf_validator or SSRFValidator(resolve_dns=False)
        self.base_url = base_url.rstrip("/")
        self.max_collision_retries = max_collision_retries

    def execute(self, cmd: CreateShortUrlCommand) -> ShortUrlResult:
        # 1. Domain validations
        orig_url = OriginalUrl(cmd.url)

        # 2. SSRF Security Gate
        self.ssrf_validator.validate(orig_url.value)

        # 3. Slug selection & collision resolution
        is_custom = bool(cmd.custom_slug)
        if is_custom:
            slug_val = cmd.custom_slug.strip()  # type: ignore[union-attr]
            short_code_vo = ShortCode(slug_val, slug_type=SlugType.CUSTOM)
            if self.url_repo.exists(short_code_vo.value):
                raise SlugCollisionError(short_code_vo.value)
        else:
            # Auto-generate Base62 code with collision retry loop
            slug_val = None
            for _ in range(self.max_collision_retries):
                candidate = self.code_generator.generate_code()
                if not self.url_repo.exists(candidate):
                    slug_val = candidate
                    break
            if not slug_val:
                raise DomainPolicyViolationError("Failed to generate a unique short code after maximum retries.")
            short_code_vo = ShortCode(slug_val, slug_type=SlugType.GENERATED)

        # 4. TTL / Expiration calculation
        expires_at: Optional[datetime] = None
        if cmd.ttl_seconds is not None and cmd.ttl_seconds > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=cmd.ttl_seconds)

        # 5. Domain Aggregate Construction & Persistence
        entity = ShortenedUrl(
            short_code=short_code_vo,
            original_url=orig_url,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            is_active=True,
            created_by=cmd.created_by,
        )
        saved = self.url_repo.save(entity)

        # 6. Cache warming (Cache-aside pre-population)
        cache_key = f"redirect:{saved.short_code.value}"
        ttl = cmd.ttl_seconds if cmd.ttl_seconds and cmd.ttl_seconds > 0 else 3600
        self.cache_service.set(cache_key, saved.original_url.value, ttl_seconds=ttl)

        return ShortUrlResult(
            short_code=saved.short_code.value,
            short_url=f"{self.base_url}/{saved.short_code.value}",
            original_url=saved.original_url.value,
            created_at=saved.created_at,
            expires_at=saved.expires_at,
            is_custom=is_custom,
        )


class ResolveRedirectUseCase:
    """Orchestrates low-latency redirect resolution with cache-aside and click logging."""

    def __init__(
        self,
        url_repo: UrlRepository,
        analytics_repo: AnalyticsRepository,
        cache_service: CacheService,
    ) -> None:
        self.url_repo = url_repo
        self.analytics_repo = analytics_repo
        self.cache_service = cache_service

    def execute(self, cmd: ResolveRedirectCommand) -> RedirectResult:
        cache_key = f"redirect:{cmd.short_code}"

        # 1. Attempt Cache Hit
        cached_url = self.cache_service.get(cache_key)
        if cached_url:
            # Asynchronously / immediately log click
            self._record_click_event(cmd)
            self.url_repo.increment_click_count(cmd.short_code)
            return RedirectResult(
                original_url=cached_url,
                short_code=cmd.short_code,
                is_cached=True,
            )

        # 2. Database Lookup on Cache Miss
        entity = self.url_repo.find_by_short_code(cmd.short_code)
        if not entity:
            raise ShortCodeNotFoundError(cmd.short_code)

        # 3. Check expiration & active status
        entity.validate_accessible()

        # 4. Update Cache (Cache-Aside pattern)
        ttl = None
        if entity.expires_at:
            delta = (entity.expires_at - datetime.now(timezone.utc)).total_seconds()
            ttl = int(max(delta, 1))
        self.cache_service.set(cache_key, entity.original_url.value, ttl_seconds=ttl or 3600)

        # 5. Record Click & Telemetry
        self._record_click_event(cmd)
        self.url_repo.increment_click_count(cmd.short_code)

        return RedirectResult(
            original_url=entity.original_url.value,
            short_code=cmd.short_code,
            is_cached=False,
        )

    def _record_click_event(self, cmd: ResolveRedirectCommand) -> None:
        metadata = ClickMetadata(
            ip_address=cmd.ip_address,
            user_agent=cmd.user_agent,
            referrer=cmd.referrer,
            timestamp=datetime.now(timezone.utc),
            country=cmd.country,
            device_type=cmd.device_type,
        )
        event = ClickEvent(short_code=cmd.short_code, metadata=metadata)
        self.analytics_repo.record_click(event)


class GetAnalyticsUseCase:
    """Retrieves aggregated click telemetry for a short code."""

    def __init__(self, analytics_repo: AnalyticsRepository) -> None:
        self.analytics_repo = analytics_repo

    def execute(self, short_code: str) -> AnalyticsResult:
        summary = self.analytics_repo.get_summary(short_code)
        if not summary:
            raise ShortCodeNotFoundError(short_code)

        return AnalyticsResult(
            short_code=summary.short_code,
            original_url=summary.original_url,
            total_clicks=summary.total_clicks,
            created_at=summary.created_at,
            is_active=summary.is_active,
            is_expired=summary.is_expired,
            clicks_by_date=summary.clicks_by_date,
            top_referrers=summary.top_referrers,
            top_devices=summary.top_devices,
        )


class DeleteUrlUseCase:
    """Removes a shortened URL from persistence and evicts from cache."""

    def __init__(self, url_repo: UrlRepository, cache_service: CacheService) -> None:
        self.url_repo = url_repo
        self.cache_service = cache_service

    def execute(self, short_code: str) -> bool:
        self.cache_service.delete(f"redirect:{short_code}")
        deleted = self.url_repo.delete(short_code)
        if not deleted:
            raise ShortCodeNotFoundError(short_code)
        return True
