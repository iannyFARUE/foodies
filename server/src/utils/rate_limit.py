"""In-memory fixed-window rate limiter for gating costly/abusable endpoints."""

import threading
import time
from collections import defaultdict
from typing import Callable, Dict, List

from fastapi import Request

from src.utils.exceptions import RateLimitExceededError


class InMemoryRateLimiter:
    """
    Tracks request timestamps per key (e.g. client IP) and rejects once a key
    exceeds max_requests within the trailing window_seconds. Single-process
    only: state isn't shared across workers, which is fine for this app's
    one-process deployment.
    """

    def __init__(self, max_requests: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = self._clock()
        window_start = now - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < window_start:
                hits.pop(0)
            if len(hits) >= self.max_requests:
                retry_after = max(0.0, hits[0] + self.window_seconds - now)
                raise RateLimitExceededError(retry_after=retry_after)
            hits.append(now)


def make_rate_limiter(limiter: InMemoryRateLimiter):
    """Build a FastAPI dependency that rate-limits by client IP using the given limiter."""

    def _check_rate_limit(request: Request) -> None:
        client_key = request.client.host if request.client else "unknown"
        limiter.check(client_key)

    return _check_rate_limit
