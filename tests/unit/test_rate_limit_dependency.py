from collections.abc import Callable

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.rate_limit import InMemoryRateLimiter, RateLimitResult, enforce_rate_limit, get_rate_limiter


class BrokenLimiter:
    def hit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        raise ConnectionError("redis is down")


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://unused",
        "auth_username": "u",
        "auth_password": "p",
        "rate_limit_write_per_minute": 2,
        "rate_limit_read_per_minute": 3,
    }
    return Settings.model_validate(values | overrides)


@pytest.fixture
def make_client() -> Callable[..., TestClient]:
    def _make(settings: Settings | None = None, limiter: object | None = None) -> TestClient:
        app = FastAPI(dependencies=[Depends(enforce_rate_limit)])

        @app.get("/thing")
        def read() -> dict[str, str]:
            return {}

        @app.post("/thing")
        def write() -> dict[str, str]:
            return {}

        resolved_settings = settings or _settings()
        resolved_limiter = limiter or InMemoryRateLimiter()
        app.dependency_overrides[get_settings] = lambda: resolved_settings
        app.dependency_overrides[get_rate_limiter] = lambda: resolved_limiter
        return TestClient(app)

    return _make


class TestEnforceRateLimit:
    def test_writes_are_refused_past_their_limit_with_429_and_retry_after(
        self, make_client: Callable[..., TestClient]
    ) -> None:
        client = make_client()
        codes = [client.post("/thing").status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        refused = client.post("/thing")
        assert refused.json() == {"detail": "Rate limit exceeded"}
        assert int(refused.headers["retry-after"]) > 0
        assert refused.headers["ratelimit-remaining"] == "0"

    def test_reads_and_writes_have_separate_quotas(self, make_client: Callable[..., TestClient]) -> None:
        client = make_client()
        for _ in range(2):
            client.post("/thing")
        assert client.post("/thing").status_code == 429
        assert [client.get("/thing").status_code for _ in range(4)] == [200, 200, 200, 429]

    def test_allowed_responses_carry_ratelimit_headers(self, make_client: Callable[..., TestClient]) -> None:
        response = make_client().get("/thing")
        assert (response.headers["ratelimit-limit"], response.headers["ratelimit-remaining"]) == ("3", "2")
        assert "retry-after" not in response.headers

    def test_fails_open_when_the_limiter_errors(
        self, make_client: Callable[..., TestClient], caplog: pytest.LogCaptureFixture
    ) -> None:
        client = make_client(limiter=BrokenLimiter())
        assert [client.post("/thing").status_code for _ in range(5)] == [200] * 5
        assert "rate limiter unavailable" in caplog.text

    def test_disabled_never_limits(self, make_client: Callable[..., TestClient]) -> None:
        client = make_client(settings=_settings(rate_limit_enabled=False))
        assert [client.post("/thing").status_code for _ in range(5)] == [200] * 5


class TestRateLimitSettings:
    def test_redis_backend_requires_a_url(self) -> None:
        with pytest.raises(ValueError, match="PROGIMAGE_REDIS_URL"):
            _settings(rate_limit_backend="redis")
