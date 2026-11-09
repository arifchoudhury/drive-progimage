import pytest

from app.core.rate_limit import InMemoryRateLimiter, RateLimitResult


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock: FakeClock) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(clock=clock)


class TestInMemoryRateLimiter:
    def test_allows_up_to_the_limit_then_refuses(self, limiter: InMemoryRateLimiter) -> None:
        results = [limiter.hit("k", 3, 60) for _ in range(4)]
        assert [r.allowed for r in results] == [True, True, True, False]
        assert [r.remaining for r in results] == [2, 1, 0, 0]

    def test_window_resets_after_it_expires(self, limiter: InMemoryRateLimiter, clock: FakeClock) -> None:
        limiter.hit("k", 1, 60)
        assert not limiter.hit("k", 1, 60).allowed
        clock.now += 60
        assert limiter.hit("k", 1, 60).allowed

    def test_reset_after_counts_down_from_the_first_hit(self, limiter: InMemoryRateLimiter, clock: FakeClock) -> None:
        assert limiter.hit("k", 5, 60).reset_after == 60
        clock.now += 20.5
        assert limiter.hit("k", 5, 60).reset_after == 40  # 39.5 rounded up

    def test_keys_are_counted_separately(self, limiter: InMemoryRateLimiter) -> None:
        limiter.hit("a", 1, 60)
        assert limiter.hit("b", 1, 60).allowed

    def test_expired_windows_are_pruned(
        self, limiter: InMemoryRateLimiter, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.core.rate_limit.memory._PRUNE_ABOVE_KEYS", 2)
        limiter.hit("old-1", 5, 60)
        limiter.hit("old-2", 5, 60)
        clock.now += 61
        limiter.hit("new", 5, 60)
        assert set(limiter._windows) == {"new"}


class TestRateLimitResult:
    def test_allowed_result_has_ratelimit_headers_but_no_retry_after(self) -> None:
        result = RateLimitResult.from_count(count=1, limit=10, reset_after=30)
        assert result.headers() == {"RateLimit-Limit": "10", "RateLimit-Remaining": "9", "RateLimit-Reset": "30"}

    def test_refused_result_adds_retry_after(self) -> None:
        result = RateLimitResult.from_count(count=11, limit=10, reset_after=12.2)
        assert not result.allowed
        assert result.headers()["Retry-After"] == "13"

    def test_reset_after_is_never_zero(self) -> None:
        assert RateLimitResult.from_count(count=1, limit=1, reset_after=0).reset_after == 1
