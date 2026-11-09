from dataclasses import dataclass
from typing import Protocol, Self


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """The outcome of counting one request against a key's current window."""

    allowed: bool
    limit: int
    remaining: int
    reset_after: int  # whole seconds until the window resets, at least 1

    @classmethod
    def from_count(cls, count: int, limit: int, reset_after: float) -> Self:
        """`count` includes the request being decided."""
        return cls(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            reset_after=max(1, int(-(-reset_after // 1))),  # ceil, never 0
        )

    def headers(self) -> dict[str, str]:
        """IETF draft RateLimit headers, plus Retry-After when the request is refused."""
        headers = {
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(self.remaining),
            "RateLimit-Reset": str(self.reset_after),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.reset_after)
        return headers


class RateLimiter(Protocol):
    """Fixed-window counter: every hit counts, refused ones included, and the window starts at a key's first hit."""

    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult: ...
