"""Token bucket and sliding-window rate limiter implementation."""

from collections import deque
import threading
import time
from typing import Dict, Tuple

from src.url_shortener.domain.repositories import RateLimiterService


class SlidingWindowRateLimiter(RateLimiterService):
    """In-memory thread-safe sliding-window rate limiter."""

    def __init__(self) -> None:
        self._clients: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_id: str, max_requests: int, window_seconds: int) -> bool:
        """Evaluates whether the client has remaining request quota."""
        now = time.time()
        window_start = now - window_seconds

        with self._lock:
            if client_id not in self._clients:
                self._clients[client_id] = deque()

            queue = self._clients[client_id]

            # Evict timestamps older than current window
            while queue and queue[0] < window_start:
                queue.popleft()

            if len(queue) >= max_requests:
                return False

            queue.append(now)
            return True

    def reset(self) -> None:
        """Clear all rate limit state (useful for test isolation)."""
        with self._lock:
            self._clients.clear()
