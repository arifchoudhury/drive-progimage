from collections.abc import Callable, Iterator

import httpx2
import pytest

from tests.e2e.conftest import PASSWORD, USERNAME, serve

WRITE_LIMIT = 2


@pytest.fixture(scope="module")
def limited_http(tmp_path_factory: pytest.TempPathFactory, database_url: str) -> Iterator[httpx2.Client]:
    """Its own server with a tiny write quota, so exhausting it can't affect the shared e2e server."""
    with (
        serve(tmp_path_factory, database_url, PROGIMAGE_RATE_LIMIT_WRITE_PER_MINUTE=str(WRITE_LIMIT)) as url,
        httpx2.Client(base_url=url, auth=(USERNAME, PASSWORD)) as client,
    ):
        yield client


class TestRateLimitOverRealHttp:
    def test_uploads_past_the_limit_get_429_with_retry_after(
        self, limited_http: httpx2.Client, make_image: Callable[[str], bytes]
    ) -> None:
        upload = {"file": ("a.png", make_image("PNG"), "image/png")}
        responses = [limited_http.post("/images", files=upload) for _ in range(WRITE_LIMIT + 1)]

        assert [r.status_code for r in responses] == [201] * WRITE_LIMIT + [429]
        assert responses[0].headers["ratelimit-limit"] == str(WRITE_LIMIT)
        assert 1 <= int(responses[-1].headers["retry-after"]) <= 60

    def test_health_is_never_limited(self, limited_http: httpx2.Client) -> None:
        assert {limited_http.get("/healthz").status_code for _ in range(5)} == {200}
