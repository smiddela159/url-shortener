"""High-performance caching layer with Redis support and in-memory fallback."""

from dataclasses import dataclass
import threading
import time
from typing import Dict, Optional, Tuple

from src.url_shortener.domain.repositories import CacheService


@dataclass
class CacheEntry:
    value: str
    expires_at: Optional[float]


class InMemoryCacheService(CacheService):
    """Thread-safe in-memory cache with TTL support and observability metrics."""

    def __init__(self) -> None:
        self._store: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[str]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.expires_at is not None and now > entry.expires_at:
                del self._store[key]
                self._misses += 1
                return None

            self._hits += 1
            return entry.value

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds is not None else None
        with self._lock:
            self._store[key] = CacheEntry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def increment(self, key: str, ttl_seconds: Optional[int] = None) -> int:
        with self._lock:
            current_str = self.get(key)
            current_val = int(current_str) if current_str else 0
            new_val = current_val + 1
            self.set(key, str(new_val), ttl_seconds=ttl_seconds)
            return new_val

    def get_stats(self) -> Dict[str, float]:
        """Returns cache telemetry: hits, misses, and hit ratio."""
        with self._lock:
            total = self._hits + self._misses
            ratio = (self._hits / total) if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "total_requests": total,
                "hit_ratio": round(ratio, 4),
                "entry_count": len(self._store),
            }

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0
