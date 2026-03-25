"""Simple in-memory rate limiter for public waitlist POSTs."""

from __future__ import annotations

import threading
import time


class InMemoryWaitlistRateLimiter:
    """
    Fixed-window style limiter using request timestamps per key.
    Not reliable across multiple workers; v1 guardrail only.
    """

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max = max_requests
        self._window = float(window_seconds)
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """Return True if under limit; False if rate limited."""
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            ts = self._hits.setdefault(key, [])
            ts[:] = [t for t in ts if t > cutoff]
            if len(ts) >= self._max:
                return False
            ts.append(now)
            return True
