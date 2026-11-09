import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from tests.integration.conftest import MAX_UPLOAD_BYTES
from tests.samples import png_header


def _row_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("SELECT count(*) FROM images")).scalar_one())


class TestUploadImage:
    def test_each_upload_gets_a_unique_id(self, client: TestClient, make_image: Callable[[str], bytes]) -> None:
        image = make_image("PNG")
        ids = {client.post("/images", files={"file": ("a.png", image, "image/png")}).json()["id"] for _ in range(5)}
        assert len(ids) == 5

    def test_original_filename_is_recorded_and_the_blob_is_stored_under_a_generated_key(
        self, client: TestClient, make_image: Callable[[str], bytes], engine: Engine, tmp_path: Path
    ) -> None:
        image = make_image("PNG")

        image_id = client.post("/images", files={"file": ("../My Holiday.png", image, "image/png")}).json()["id"]

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT original_filename, storage_key, size_bytes FROM images WHERE id = :id"), {"id": image_id}
            ).one()
        assert row == ("My Holiday.png", f"{image_id}.png", len(image))
        assert (tmp_path / row.storage_key).read_bytes() == image

    def test_non_images_leave_no_row_behind(self, client: TestClient, engine: Engine) -> None:
        client.post("/images", files={"file": ("a.png", b"not an image", "image/png")})
        assert _row_count(engine) == 0

    def test_rejects_non_images(self, client: TestClient) -> None:
        response = client.post("/images", files={"file": ("a.png", b"not an image", "image/png")})
        assert response.status_code == 422

    def test_rejects_empty_file(self, client: TestClient) -> None:
        response = client.post("/images", files={"file": ("a.png", b"", "image/png")})
        assert response.status_code == 422

    def test_requires_a_file(self, client: TestClient) -> None:
        assert client.post("/images").status_code == 422


class TestUploadLimits:
    """Each kind of rejection gets its own status code, and none leaves anything behind."""

    def test_unsupported_format_is_415(
        self, client: TestClient, make_image: Callable[[str], bytes], engine: Engine
    ) -> None:
        response = client.post("/images", files={"file": ("a.tiff", make_image("TIFF"), "image/tiff")})
        assert response.status_code == 415
        assert "TIFF" in response.json()["detail"]
        assert _row_count(engine) == 0

    def test_truncated_image_is_422(self, client: TestClient, truncated_png: bytes) -> None:
        response = client.post("/images", files={"file": ("a.png", truncated_png, "image/png")})
        assert response.status_code == 422

    def test_decompression_bomb_header_is_422_not_500(self, client: TestClient) -> None:
        response = client.post("/images", files={"file": ("bomb.png", png_header(100_000, 100_000), "image/png")})
        assert response.status_code == 422

    def test_body_over_the_request_limit_is_413_before_parsing(self, client: TestClient, engine: Engine) -> None:
        huge = b"\0" * (MAX_UPLOAD_BYTES * 4)  # well past the image limit plus multipart headroom
        response = client.post("/images", files={"file": ("big.png", huge, "image/png")})
        assert response.status_code == 413
        assert _row_count(engine) == 0

    def test_file_just_over_the_image_limit_is_413_from_the_validator(
        self, client: TestClient, make_image: Callable[[str], bytes], engine: Engine
    ) -> None:
        # Fits in the request headroom, so the middleware lets it through and the validator catches it.
        padded = make_image("PNG") + b"\0" * MAX_UPLOAD_BYTES
        response = client.post("/images", files={"file": ("big.png", padded, "image/png")})
        assert response.status_code == 413
        assert response.json()["detail"] == f"Image exceeds the {MAX_UPLOAD_BYTES}-byte limit"
        assert _row_count(engine) == 0


class TestGetImage:
    @pytest.mark.parametrize(
        ("fmt", "content_type"), [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("GIF", "image/gif")]
    )
    def test_upload_then_retrieve_returns_the_same_image(
        self, client: TestClient, make_image: Callable[[str], bytes], fmt: str, content_type: str
    ) -> None:
        original = make_image(fmt)

        upload = client.post("/images", files={"file": ("photo", original, "application/octet-stream")})
        assert upload.status_code == 201
        image_id = upload.json()["id"]

        fetched = client.get(f"/images/{image_id}")
        assert fetched.status_code == 200
        assert fetched.content == original
        assert fetched.headers["content-type"] == content_type

    @pytest.mark.parametrize(("fmt", "extension"), [("PNG", ".png"), ("JPEG", ".jpg"), ("GIF", ".gif")])
    def test_served_bytes_carry_security_and_cache_headers(
        self, client: TestClient, make_image: Callable[[str], bytes], fmt: str, extension: str
    ) -> None:
        upload = client.post("/images", files={"file": ("../evil.html", make_image(fmt), "text/html")})
        image_id = upload.json()["id"]

        headers = client.get(f"/images/{image_id}").headers

        assert headers["x-content-type-options"] == "nosniff"
        assert headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert headers["cache-control"] == "private, max-age=31536000, immutable"
        assert headers["content-disposition"] == f'inline; filename="{image_id}{extension}"'
        assert "ratelimit-limit" in headers  # still carried over

    def test_unknown_id_is_404(self, client: TestClient) -> None:
        response = client.get(f"/images/{uuid.uuid7()}")
        assert response.status_code == 404
        assert "immutable" not in response.headers.get("cache-control", "")  # a miss must not be cached

    def test_malformed_id_is_rejected(self, client: TestClient) -> None:
        assert client.get("/images/not-a-valid-id").status_code == 422


class TestListImages:
    def test_empty_when_nothing_is_stored(self, client: TestClient) -> None:
        response = client.get("/images")
        assert response.status_code == 200
        assert response.json() == {"items": []}

    def test_lists_every_upload_newest_first_without_the_storage_key(
        self, client: TestClient, make_image: Callable[[str], bytes]
    ) -> None:
        image = make_image("PNG")
        ids = [client.post("/images", files={"file": (f"{n}.png", image, "image/png")}).json()["id"] for n in range(3)]

        items = client.get("/images").json()["items"]

        assert [item["id"] for item in items] == ids[::-1]
        assert items[0].keys() == {"id", "original_filename", "content_type", "size_bytes", "created_at"}
        assert items[0]["original_filename"] == "2.png"
        assert items[0]["content_type"] == "image/png"
        assert items[0]["size_bytes"] == len(image)

    def test_requires_credentials(self, anonymous_client: TestClient) -> None:
        assert anonymous_client.get("/images").status_code == 401
