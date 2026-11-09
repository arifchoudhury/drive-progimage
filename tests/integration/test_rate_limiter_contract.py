import os
import uuid
from collections.abc import Callable

import pytest

from app.core.rate_limit import InMemoryRateLimiter, RateLimiter, RedisRateLimiter

# The docker-compose Redis (`make db-up`), on a database number dev runs don't use.
TEST_REDIS_URL = os.environ.get("PROGIMAGE_TEST_REDIS_URL", "redis://localhost:6380/15")


def _redis() -> RateLimiter:
    redis = pytest.importorskip("redis")
    try:
        redis.Redis.from_url(TEST_REDIS_URL, socket_connect_timeout=0.5).ping()
    except redis.ConnectionError:
        pytest.skip(f"Redis not reachable at {TEST_REDIS_URL} (run `make db-up`)")
    return RedisRateLimiter(TEST_REDIS_URL, prefix=f"test:{uuid.uuid4()}:")  # fresh keys per test


BACKENDS: dict[str, Callable[[], RateLimiter]] = {"memory": InMemoryRateLimiter, "redis": _redis}


@pytest.fixture(params=BACKENDS)
def limiter(request: pytest.FixtureRequest) -> RateLimiter:
    """Every RateLimiter implementation must satisfy the same behaviour."""
    return BACKENDS[request.param]()


class TestRateLimiterContract:
    def test_allows_up_to_the_limit_then_refuses(self, limiter: RateLimiter) -> None:
        assert [limiter.hit("k", 2, 60).allowed for _ in range(3)] == [True, True, False]

    def test_remaining_counts_down_to_zero(self, limiter: RateLimiter) -> None:
        assert [limiter.hit("k", 2, 60).remaining for _ in range(3)] == [1, 0, 0]

    def test_keys_are_counted_separately(self, limiter: RateLimiter) -> None:
        limiter.hit("a", 1, 60)
        assert limiter.hit("b", 1, 60).allowed

    def test_reset_after_is_within_the_window(self, limiter: RateLimiter) -> None:
        assert 1 <= limiter.hit("k", 5, 60).reset_after <= 60
