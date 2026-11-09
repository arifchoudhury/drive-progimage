import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status

from app.core.config import Settings, get_settings
from app.core.rate_limit.memory import InMemoryRateLimiter
from app.core.rate_limit.ports import RateLimiter
from app.core.rate_limit.redis import RedisRateLimiter

logger = logging.getLogger(__name__)

WINDOW_SECONDS = 60
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """The one place that maps configuration to a concrete RateLimiter, built once per process.

    Tests swap it via `app.dependency_overrides[get_rate_limiter]`.
    """
    settings = get_settings()
    match settings.rate_limit_backend:
        case "memory":
            return InMemoryRateLimiter()
        case "redis":
            assert settings.redis_url is not None  # guaranteed by Settings validation
            return RedisRateLimiter(settings.redis_url)


def enforce_rate_limit(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> None:
    """Count the request against its client's write or read quota; 429 once the quota for the window is spent.

    Keyed by client IP, because the shared Basic credential carries no per-caller identity yet. Behind a proxy,
    uvicorn's --proxy-headers sets the client from X-Forwarded-For, trusting only FORWARDED_ALLOW_IPS.
    Fails open: if the limiter's backend is down, the request is allowed and the error logged.
    """
    if not settings.rate_limit_enabled:
        return
    if request.method in _WRITE_METHODS:
        scope, limit = "write", settings.rate_limit_write_per_minute
    else:
        scope, limit = "read", settings.rate_limit_read_per_minute
    client = request.client.host if request.client else "unknown"

    try:
        result = limiter.hit(f"{scope}:{client}", limit, WINDOW_SECONDS)
    except Exception:
        logger.exception("rate limiter unavailable; allowing the request")
        return

    if not result.allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded", headers=result.headers())
    response.headers.update(result.headers())
