import uuid
from collections.abc import Callable

import httpx2

from tests.e2e.conftest import MAX_UPLOAD_BYTES


class TestImageRoundTrip:
    def test_upload_then_fetch_over_real_http(self, http: httpx2.Client, make_image: Callable[[str], bytes]) -> None:
        original = make_image("PNG")

        upload = http.post("/images", files={"file": ("photo.png", original, "image/png")})
        assert upload.status_code == 201

        fetched = http.get(f"/images/{upload.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.content == original
        assert fetched.headers["content-type"] == "image/png"

    def test_unknown_id_is_404(self, http: httpx2.Client) -> None:
        assert http.get(f"/images/{uuid.uuid7()}").status_code == 404

    def test_non_image_upload_is_422(self, http: httpx2.Client) -> None:
        response = http.post("/images", files={"file": ("a.png", b"not an image", "image/png")})
        assert response.status_code == 422

    def test_unauthenticated_request_is_401(self, anonymous_http: httpx2.Client) -> None:
        assert anonymous_http.get(f"/images/{uuid.uuid7()}").status_code == 401

    def test_oversized_upload_is_413(self, http: httpx2.Client) -> None:
        huge = b"\0" * (MAX_UPLOAD_BYTES * 4)
        response = http.post("/images", files={"file": ("big.png", huge, "image/png")})
        assert response.status_code == 413

    def test_unsupported_format_is_415(self, http: httpx2.Client, make_image: Callable[[str], bytes]) -> None:
        response = http.post("/images", files={"file": ("a.tiff", make_image("TIFF"), "image/tiff")})
        assert response.status_code == 415

    def test_uploaded_image_appears_in_the_list(self, http: httpx2.Client, make_image: Callable[[str], bytes]) -> None:
        image_id = http.post("/images", files={"file": ("p.png", make_image("PNG"), "image/png")}).json()["id"]

        listed = http.get("/images")

        assert listed.status_code == 200
        assert image_id in [item["id"] for item in listed.json()["items"]]
