import uuid
from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings


def _limit(client: TestClient, **limits: int) -> None:
    """Lower the rate limits for this test's app."""
    app: FastAPI = client.app  # type: ignore[assignment]
    settings: Settings = app.dependency_overrides[get_settings]()
    lowered = settings.model_copy(update=limits)
    app.dependency_overrides[get_settings] = lambda: lowered


class TestImagesRateLimit:
    def test_uploads_past_the_limit_are_429(self, client: TestClient, make_image: Callable[[str], bytes]) -> None:
        _limit(client, rate_limit_write_per_minute=2)
        upload = {"file": ("a.png", make_image("PNG"), "image/png")}
        codes = [client.post("/images", files=upload).status_code for _ in range(3)]
        assert codes == [201, 201, 429]

    def test_refused_upload_stores_nothing(self, client: TestClient, make_image: Callable[[str], bytes]) -> None:
        _limit(client, rate_limit_write_per_minute=1)
        client.post("/images", files={"file": ("a.png", make_image("PNG"), "image/png")})
        client.post("/images", files={"file": ("b.png", make_image("PNG"), "image/png")})
        assert len(client.get("/images").json()["items"]) == 1

    def test_failed_logins_count_against_the_limit(self, anonymous_client: TestClient) -> None:
        _limit(anonymous_client, rate_limit_read_per_minute=2)
        url = f"/images/{uuid.uuid4()}"
        codes = [anonymous_client.get(url, auth=("x", "wrong")).status_code for _ in range(3)]
        assert codes == [401, 401, 429]

    def test_served_image_carries_ratelimit_headers(
        self, client: TestClient, make_image: Callable[[str], bytes]
    ) -> None:
        original = make_image("PNG")
        image_id = client.post("/images", files={"file": ("a.png", original, "image/png")}).json()["id"]

        response = client.get(f"/images/{image_id}")

        assert response.content == original
        assert response.headers["content-length"] == str(len(original))
        assert response.headers["ratelimit-limit"] == "600"

    def test_health_probes_are_never_limited(self, anonymous_client: TestClient) -> None:
        _limit(anonymous_client, rate_limit_read_per_minute=1)
        assert {anonymous_client.get("/healthz").status_code for _ in range(5)} == {200}
