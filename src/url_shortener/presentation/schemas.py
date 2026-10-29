"""Pydantic request and response schemas for REST API."""

from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field, HttpUrl


class CreateUrlRequest(BaseModel):
    """Payload to shorten a new URL."""
    url: str = Field(
        ...,
        description="The destination HTTP or HTTPS URL to shorten.",
        examples=["https://www.schwab.com/research"]
    )
    custom_slug: Optional[str] = Field(
        None,
        min_length=3,
        max_length=64,
        description="Optional custom vanity alias for the shortened URL.",
        examples=["schwab-research"]
    )
    ttl_seconds: Optional[int] = Field(
        None,
        ge=1,
        description="Optional time-to-live in seconds before the short link expires.",
        examples=[86400]
    )


class CreateUrlResponse(BaseModel):
    """Response returned upon successful URL shortening."""
    short_code: str = Field(..., examples=["aB3d9Z1"])
    short_url: str = Field(..., examples=["http://localhost:8000/aB3d9Z1"])
    original_url: str = Field(..., examples=["https://www.schwab.com/research"])
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_custom: bool = False


class AnalyticsResponse(BaseModel):
    """Detailed analytics breakdown for a shortened URL."""
    short_code: str
    original_url: str
    total_clicks: int
    created_at: datetime
    is_active: bool
    is_expired: bool
    clicks_by_date: Dict[str, int]
    top_referrers: Dict[str, int]
    top_devices: Dict[str, int]


class HealthResponse(BaseModel):
    """Service health and uptime status."""
    status: str = "healthy"
    service: str = "enterprise-url-shortener"
    timestamp: datetime
    version: str = "1.0.0"


class MetricsResponse(BaseModel):
    """Operational cache and throughput metrics."""
    cache: Dict[str, float]
    timestamp: datetime


class ErrorEnvelope(BaseModel):
    """RFC-compliant error envelope."""
    error: str
    code: str
    message: str
    timestamp: datetime
