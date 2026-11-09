import threading
import time
from collections.abc import Callable

from app.core.rate_limit.ports import RateLimitResult

_PRUNE_ABOVE_KEYS = 10_000


class InMemoryRateLimiter:
    """RateLimiter for a single process: local runs and tests.

    Counts are per process, so with N uvicorn workers the effective limit is N x limit. Use RedisRateLimiter
    anywhere that runs more than one worker or replica.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()  # endpoints are sync `def`, so hits arrive from threadpool threads
        self._windows: dict[str, tuple[float, int]] = {}  # key -> (window start, count)

    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now: float = self._clock()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= window_seconds:
                start, count = now, 0
            count += 1
            self._windows[key] = (start, count)
            if len(self._windows) > _PRUNE_ABOVE_KEYS:
                self._prune(now, window_seconds)
        return RateLimitResult.from_count(count, limit, start + window_seconds - now)

    def _prune(self, now: float, window_seconds: int) -> None:
        """Drop expired windows so one-off clients don't grow the dict forever."""
        self._windows = {k: v for k, v in self._windows.items() if now - v[0] < window_seconds}
