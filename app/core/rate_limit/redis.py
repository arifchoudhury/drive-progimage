from typing import cast

from app.core.rate_limit.ports import RateLimitResult


class RedisRateLimiter:
    """RateLimiter shared by every worker and replica: one Redis key per (scope, client) and window.

    INCR, EXPIRE NX and TTL run in one MULTI/EXEC, so the count and its expiry are set atomically. redis is imported
    lazily (optional `redis` extra), so local runs don't need it.
    """

    def __init__(self, url: str, prefix: str = "progimage:ratelimit:") -> None:
        import redis

        # Short timeouts: a slow Redis must not stall requests (the dependency fails open on errors).
        self._client = redis.Redis.from_url(url, socket_timeout=0.25, socket_connect_timeout=0.25)
        self._prefix = prefix

    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        name = self._prefix + key
        pipe = self._client.pipeline(transaction=True)
        pipe.incr(name)
        pipe.expire(name, window_seconds, nx=True)
        pipe.ttl(name)
        count, _, ttl = cast(tuple[int, bool, int], pipe.execute())
        return RateLimitResult.from_count(count, limit, ttl if ttl > 0 else window_seconds)
