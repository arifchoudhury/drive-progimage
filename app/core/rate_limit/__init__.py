"""App-level rate limiting: a RateLimiter port, in-memory and Redis adapters, and the FastAPI dependency.

This is the per-caller, per-endpoint layer. Coarse per-IP flood protection belongs at the gateway or ingress, in front
of the app, and is deployment config rather than code here.
"""

from app.core.rate_limit.dependency import enforce_rate_limit, get_rate_limiter
from app.core.rate_limit.memory import InMemoryRateLimiter
from app.core.rate_limit.ports import RateLimiter, RateLimitResult
from app.core.rate_limit.redis import RedisRateLimiter

__all__ = [
    "InMemoryRateLimiter",
    "RateLimitResult",
    "RateLimiter",
    "RedisRateLimiter",
    "enforce_rate_limit",
    "get_rate_limiter",
]
