from collections.abc import Callable
from pathlib import Path

import pytest

from app.images.domain.ports import ImageStorage
from app.images.infrastructure.storage import LocalImageStorage, S3ImageStorage

StorageFactory = Callable[[Path], ImageStorage]

BACKENDS: dict[str, StorageFactory] = {
    "local": lambda tmp_path: LocalImageStorage(tmp_path),
    "s3": lambda _: S3ImageStorage("bucket"),
}


@pytest.fixture(params=BACKENDS)
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> ImageStorage:
    """Every ImageStorage implementation must satisfy the same behaviour."""
    if request.param == "s3":
        request.getfixturevalue("fake_s3")  # only the s3 backend needs boto3 patched
    return BACKENDS[request.param](tmp_path)


class TestImageStorageContract:
    def test_save_then_load_round_trips_bytes(self, storage: ImageStorage) -> None:
        storage.save("abc.png", b"\x00\x01data")
        assert storage.load("abc.png") == b"\x00\x01data"

    def test_load_of_unknown_key_is_none(self, storage: ImageStorage) -> None:
        assert storage.load("missing.png") is None

    def test_images_are_isolated_by_key(self, storage: ImageStorage) -> None:
        storage.save("a.png", b"1")
        storage.save("b.jpg", b"2")
        assert (storage.load("a.png"), storage.load("b.jpg")) == (b"1", b"2")
