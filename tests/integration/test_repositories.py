"""Integration tests for repositories (SQLAlchemy and In-Memory)."""

from datetime import datetime, timezone
import pytest

from src.url_shortener.domain.models import ShortenedUrl, ClickEvent
from src.url_shortener.domain.value_objects import ShortCode, OriginalUrl, ClickMetadata
from src.url_shortener.infrastructure.database.repository import (
    InMemoryUrlRepository,
    SqlAlchemyUrlRepository,
)


@pytest.mark.parametrize("repo_factory", [
    lambda: InMemoryUrlRepository(),
    lambda: SqlAlchemyUrlRepository("sqlite:///:memory:"),
])
def test_repository_save_find_and_delete(repo_factory) -> None:
    repo = repo_factory()
    url = ShortenedUrl(
        short_code=ShortCode("testCode1"),
        original_url=OriginalUrl("https://www.example.com"),
    )

    # Save
    saved = repo.save(url)
    assert saved.id is not None
    assert repo.exists("testCode1") is True

    # Find
    found = repo.find_by_short_code("testCode1")
    assert found is not None
    assert found.short_code.value == "testCode1"
    assert found.original_url.value == "https://www.example.com"

    # Delete
    deleted = repo.delete("testCode1")
    assert deleted is True
    assert repo.exists("testCode1") is False
    assert repo.find_by_short_code("testCode1") is None


@pytest.mark.parametrize("repo_factory", [
    lambda: InMemoryUrlRepository(),
    lambda: SqlAlchemyUrlRepository("sqlite:///:memory:"),
])
def test_repository_analytics_recording_and_summary(repo_factory) -> None:
    repo = repo_factory()
    url = ShortenedUrl(
        short_code=ShortCode("analyticsTest"),
        original_url=OriginalUrl("https://www.example.com/target"),
    )
    repo.save(url)

    # Record 3 clicks
    event1 = ClickEvent(
        short_code="analyticsTest",
        metadata=ClickMetadata(
            ip_address="198.51.100.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0)",
            referrer="https://google.com",
            device_type="desktop",
            country="US",
        )
    )
    event2 = ClickEvent(
        short_code="analyticsTest",
        metadata=ClickMetadata(
            ip_address="198.51.100.2",
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
            referrer="https://twitter.com",
            device_type="mobile",
            country="UK",
        )
    )

    repo.record_click(event1)
    repo.increment_click_count("analyticsTest")
    repo.record_click(event2)
    repo.increment_click_count("analyticsTest")

    # Get summary
    summary = repo.get_summary("analyticsTest")
    assert summary is not None
    assert summary.total_clicks == 2
    assert summary.top_devices.get("desktop") == 1
    assert summary.top_devices.get("mobile") == 1
    assert summary.top_referrers.get("https://google.com") == 1
