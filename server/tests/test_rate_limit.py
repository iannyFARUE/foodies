"""
Unit tests for the in-memory fixed-window rate limiter used to protect the
Voyage-AI-backed /vector-search endpoint from cost/availability abuse.
"""

import pytest
from src.utils.exceptions import RateLimitExceededError
from src.utils.rate_limit import InMemoryRateLimiter


@pytest.mark.unit
class TestInMemoryRateLimiter:
    def test_allows_requests_up_to_the_limit(self):
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)

        limiter.check("client-a")
        limiter.check("client-a")
        limiter.check("client-a")

    def test_rejects_request_beyond_the_limit(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        limiter.check("client-a")
        limiter.check("client-a")

        with pytest.raises(RateLimitExceededError):
            limiter.check("client-a")

    def test_tracks_clients_independently(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        limiter.check("client-a")

        limiter.check("client-b")

    def test_allows_requests_again_after_window_elapses(self):
        fake_time = [0.0]
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=10, clock=lambda: fake_time[0])
        limiter.check("client-a")

        fake_time[0] = 11.0

        limiter.check("client-a")
