"""SQLAlchemy ORM models for URL Shortener persistence."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ShortenedUrlModel(Base):
    """Database representation of a shortened URL record."""
    __tablename__ = "shortened_urls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    short_code = Column(String(64), unique=True, nullable=False, index=True)
    original_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    click_count = Column(Integer, default=0, nullable=False)
    created_by = Column(String(128), nullable=True)

    clicks = relationship("ClickEventModel", back_populates="url", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_short_code_active", "short_code", "is_active"),
        Index("idx_expires_at", "expires_at"),
    )


class ClickEventModel(Base):
    """Database representation of an individual click analytics event."""
    __tablename__ = "click_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    short_code = Column(String(64), ForeignKey("shortened_urls.short_code", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    ip_address = Column(String(64), nullable=False)
    user_agent = Column(Text, nullable=False)
    referrer = Column(String(512), nullable=False)
    device_type = Column(String(64), nullable=False)
    country = Column(String(64), nullable=False)

    url = relationship("ShortenedUrlModel", back_populates="clicks")

    __table_args__ = (
        Index("idx_clicks_shortcode_time", "short_code", "timestamp"),
    )
