import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from app.images.api.body_limit import MaxBodySizeMiddleware

LIMIT = 100


@pytest.fixture
def calls() -> list[int]:
    return []


@pytest.fixture
def client(calls: list[int]) -> TestClient:
    """A tiny app that reads the whole body, so we can see whether (and how far) the handler ran."""
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=LIMIT)

    @app.post("/echo-size")
    async def echo_size(request: Request) -> dict[str, int]:
        calls.append(1)
        return {"size": len(await request.body())}

    return TestClient(app)


def _chunks(total: int, size: int = 10) -> Iterator[bytes]:
    """A body sent without Content-Length (chunked), so only the streaming check can catch it."""
    for _ in range(total // size):
        yield b"x" * size


class TestMaxBodySizeMiddleware:
    @pytest.mark.parametrize("size", [0, LIMIT - 1, LIMIT])
    def test_bodies_up_to_the_limit_pass_through(self, client: TestClient, size: int) -> None:
        response = client.post("/echo-size", content=b"x" * size)
        assert (response.status_code, response.json()) == (200, {"size": size})

    def test_declared_content_length_over_the_limit_is_refused_before_the_handler_runs(
        self, client: TestClient, calls: list[int]
    ) -> None:
        response = client.post("/echo-size", content=b"x" * (LIMIT + 1))
        assert response.status_code == 413
        assert "100-byte limit" in response.json()["detail"]
        assert calls == []

    def test_streamed_body_over_the_limit_is_refused(self, client: TestClient) -> None:
        response = client.post("/echo-size", content=_chunks(LIMIT * 3))
        assert response.status_code == 413

    def test_streamed_body_under_the_limit_passes(self, client: TestClient) -> None:
        response = client.post("/echo-size", content=_chunks(LIMIT))
        assert (response.status_code, response.json()) == (200, {"size": LIMIT})

    def test_non_http_scopes_are_passed_through(self) -> None:
        seen: list[str] = []

        async def inner(scope: Scope, receive: Receive, send: Send) -> None:
            seen.append(scope["type"])

        middleware = MaxBodySizeMiddleware(inner, max_bytes=LIMIT)
        asyncio.run(middleware({"type": "lifespan"}, _never_receive, _never_send))
        assert seen == ["lifespan"]


async def _never_receive() -> Message:
    raise AssertionError("not called")


async def _never_send(message: Message) -> None:
    raise AssertionError("not called")
