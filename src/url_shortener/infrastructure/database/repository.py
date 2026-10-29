"""Repository implementations for SQLAlchemy and In-Memory storage."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import threading
from typing import Dict, List, Optional

from sqlalchemy import create_engine, select, update, func
from sqlalchemy.orm import sessionmaker, Session

from src.url_shortener.domain.models import ShortenedUrl, ClickEvent, AnalyticsSummary
from src.url_shortener.domain.value_objects import ShortCode, OriginalUrl, ClickMetadata, SlugType
from src.url_shortener.domain.repositories import UrlRepository, AnalyticsRepository
from src.url_shortener.infrastructure.database.models import Base, ShortenedUrlModel, ClickEventModel


class SqlAlchemyUrlRepository(UrlRepository, AnalyticsRepository):
    """SQLAlchemy implementation of URL and Analytics repositories."""

    def __init__(self, database_url: str = "sqlite:///./url_shortener.db") -> None:
        self.engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
            pool_pre_ping=True
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _get_session(self) -> Session:
        return self.SessionLocal()

    def save(self, url: ShortenedUrl) -> ShortenedUrl:
        with self._get_session() as session:
            record = session.query(ShortenedUrlModel).filter_by(short_code=url.short_code.value).first()
            if record:
                record.original_url = url.original_url.value
                record.expires_at = url.expires_at
                record.is_active = url.is_active
                record.click_count = url.click_count
            else:
                record = ShortenedUrlModel(
                    short_code=url.short_code.value,
                    original_url=url.original_url.value,
                    created_at=url.created_at,
                    expires_at=url.expires_at,
                    is_active=url.is_active,
                    click_count=url.click_count,
                    created_by=url.created_by,
                )
                session.add(record)
            session.commit()
            session.refresh(record)
            url.id = record.id
            return url

    def find_by_short_code(self, short_code: str) -> Optional[ShortenedUrl]:
        with self._get_session() as session:
            record = session.query(ShortenedUrlModel).filter_by(short_code=short_code).first()
            if not record:
                return None
            return ShortenedUrl(
                id=record.id,
                short_code=ShortCode(record.short_code),
                original_url=OriginalUrl(record.original_url),
                created_at=record.created_at,
                expires_at=record.expires_at,
                is_active=record.is_active,
                click_count=record.click_count,
                created_by=record.created_by,
            )

    def exists(self, short_code: str) -> bool:
        with self._get_session() as session:
            count = session.query(ShortenedUrlModel.id).filter_by(short_code=short_code).count()
            return count > 0

    def increment_click_count(self, short_code: str) -> int:
        with self._get_session() as session:
            record = session.query(ShortenedUrlModel).filter_by(short_code=short_code).first()
            if record:
                record.click_count += 1
                session.commit()
                return record.click_count
            return 0

    def delete(self, short_code: str) -> bool:
        with self._get_session() as session:
            record = session.query(ShortenedUrlModel).filter_by(short_code=short_code).first()
            if record:
                session.delete(record)
                session.commit()
                return True
            return False

    def record_click(self, event: ClickEvent) -> None:
        with self._get_session() as session:
            record = ClickEventModel(
                short_code=event.short_code,
                timestamp=event.metadata.timestamp,
                ip_address=event.metadata.ip_address,
                user_agent=event.metadata.user_agent,
                referrer=event.metadata.referrer,
                device_type=event.metadata.device_type,
                country=event.metadata.country,
            )
            session.add(record)
            session.commit()

    def get_summary(self, short_code: str) -> Optional[AnalyticsSummary]:
        url = self.find_by_short_code(short_code)
        if not url:
            return None

        with self._get_session() as session:
            clicks = session.query(ClickEventModel).filter_by(short_code=short_code).all()

            clicks_by_date: Dict[str, int] = Counter(c.timestamp.strftime("%Y-%m-%d") for c in clicks)
            top_referrers: Dict[str, int] = Counter(c.referrer for c in clicks if c.referrer)
            top_devices: Dict[str, int] = Counter(c.device_type for c in clicks if c.device_type)

            return AnalyticsSummary(
                short_code=url.short_code.value,
                original_url=url.original_url.value,
                total_clicks=url.click_count,
                created_at=url.created_at,
                is_active=url.is_active,
                is_expired=url.is_expired(),
                clicks_by_date=dict(clicks_by_date),
                top_referrers=dict(top_referrers),
                top_devices=dict(top_devices),
            )


class InMemoryUrlRepository(UrlRepository, AnalyticsRepository):
    """High-speed thread-safe in-memory repository for testing and benchmarking."""

    def __init__(self) -> None:
        self._urls: Dict[str, ShortenedUrl] = {}
        self._clicks: Dict[str, List[ClickEvent]] = defaultdict(list)
        self._lock = threading.Lock()
        self._id_counter = 1

    def save(self, url: ShortenedUrl) -> ShortenedUrl:
        with self._lock:
            if url.id is None:
                url.id = self._id_counter
                self._id_counter += 1
            self._urls[url.short_code.value] = url
            return url

    def find_by_short_code(self, short_code: str) -> Optional[ShortenedUrl]:
        with self._lock:
            return self._urls.get(short_code)

    def exists(self, short_code: str) -> bool:
        with self._lock:
            return short_code in self._urls

    def increment_click_count(self, short_code: str) -> int:
        with self._lock:
            url = self._urls.get(short_code)
            if url:
                url.record_click()
                return url.click_count
            return 0

    def delete(self, short_code: str) -> bool:
        with self._lock:
            if short_code in self._urls:
                del self._urls[short_code]
                self._clicks.pop(short_code, None)
                return True
            return False

    def record_click(self, event: ClickEvent) -> None:
        with self._lock:
            self._clicks[event.short_code].append(event)

    def get_summary(self, short_code: str) -> Optional[AnalyticsSummary]:
        with self._lock:
            url = self._urls.get(short_code)
            if not url:
                return None
            clicks = list(self._clicks.get(short_code, []))

        clicks_by_date: Dict[str, int] = Counter(c.metadata.timestamp.strftime("%Y-%m-%d") for c in clicks)
        top_referrers: Dict[str, int] = Counter(c.metadata.referrer for c in clicks if c.metadata.referrer)
        top_devices: Dict[str, int] = Counter(c.metadata.device_type for c in clicks if c.metadata.device_type)

        return AnalyticsSummary(
            short_code=url.short_code.value,
            original_url=url.original_url.value,
            total_clicks=url.click_count,
            created_at=url.created_at,
            is_active=url.is_active,
            is_expired=url.is_expired(),
            clicks_by_date=dict(clicks_by_date),
            top_referrers=dict(top_referrers),
            top_devices=dict(top_devices),
        )

    def clear(self) -> None:
        with self._lock:
            self._urls.clear()
            self._clicks.clear()
