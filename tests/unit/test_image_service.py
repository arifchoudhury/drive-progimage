import uuid
from collections.abc import Callable

import pytest

from app.images.domain.exceptions import (
    ImageNotFoundError,
    ImageRejectedError,
    ImageTooLargeError,
    InvalidImageError,
    UnsupportedImageFormatError,
)
from app.images.domain.validation import ImageValidator
from app.images.service import ImageService
from tests.fakes import InMemoryImageRepository, InMemoryStorage

MAX_BYTES = 4096  # bigger than every fixture image, so only the oversized case trips it


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def repository() -> InMemoryImageRepository:
    return InMemoryImageRepository()


@pytest.fixture
def service(storage: InMemoryStorage, repository: InMemoryImageRepository) -> ImageService:
    return ImageService(storage, repository, ImageValidator(max_bytes=MAX_BYTES, max_pixels=1_000_000))


class TestUpload:
    def test_returns_a_uuid7_and_stores_the_bytes_under_the_recorded_key(
        self,
        service: ImageService,
        storage: InMemoryStorage,
        repository: InMemoryImageRepository,
        make_image: Callable[[str], bytes],
    ) -> None:
        data = make_image("PNG")

        image_id = service.upload(data)

        assert image_id.version == 7
        image = repository.images[image_id]
        assert image.storage_key == f"{image_id}.png"
        assert storage.files == {image.storage_key: data}

    @pytest.mark.parametrize(
        ("fmt", "extension", "content_type"),
        [("PNG", "png", "image/png"), ("JPEG", "jpg", "image/jpeg"), ("GIF", "gif", "image/gif")],
    )
    def test_records_metadata_matching_the_detected_format(
        self,
        service: ImageService,
        repository: InMemoryImageRepository,
        make_image: Callable[[str], bytes],
        fmt: str,
        extension: str,
        content_type: str,
    ) -> None:
        data = make_image(fmt)

        image = repository.images[service.upload(data)]

        assert image.storage_key.endswith(f".{extension}")
        assert image.content_type == content_type
        assert image.size_bytes == len(data)

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("holiday.png", "holiday.png"),
            ("../../etc/passwd.png", "passwd.png"),
            ("C:\\Users\\me\\cat.png", "cat.png"),
            ("nul\x00byte.png", "nulbyte.png"),
            ("", None),
            (None, None),
            ("a" * 400, "a" * 255),
        ],
    )
    def test_keeps_a_sanitised_original_filename(
        self,
        service: ImageService,
        repository: InMemoryImageRepository,
        make_image: Callable[[str], bytes],
        filename: str | None,
        expected: str | None,
    ) -> None:
        image = repository.images[service.upload(make_image("PNG"), filename)]

        assert image.original_filename == expected

    def test_same_filename_twice_gets_distinct_keys(
        self, service: ImageService, repository: InMemoryImageRepository, make_image: Callable[[str], bytes]
    ) -> None:
        first = repository.images[service.upload(make_image("PNG"), "photo.png")]
        second = repository.images[service.upload(make_image("PNG"), "photo.png")]

        assert first.storage_key != second.storage_key

    @pytest.mark.parametrize(
        ("make_data", "error"),
        [
            (lambda make_image: b"", InvalidImageError),
            (lambda make_image: b"not an image", InvalidImageError),
            (lambda make_image: make_image("PNG")[:40], InvalidImageError),
            (lambda make_image: make_image("TIFF"), UnsupportedImageFormatError),
            (lambda make_image: make_image("PNG") + b"\0" * MAX_BYTES, ImageTooLargeError),
        ],
        ids=["empty", "not-an-image", "truncated", "unsupported-format", "too-large"],
    )
    def test_rejected_uploads_store_nothing(
        self,
        service: ImageService,
        storage: InMemoryStorage,
        repository: InMemoryImageRepository,
        make_image: Callable[[str], bytes],
        make_data: Callable[[Callable[[str], bytes]], bytes],
        error: type[ImageRejectedError],
    ) -> None:
        with pytest.raises(error):
            service.upload(make_data(make_image))
        assert storage.files == {}
        assert repository.images == {}


class TestGet:
    @pytest.mark.parametrize(
        ("fmt", "content_type"), [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("GIF", "image/gif")]
    )
    def test_returns_the_bytes_with_the_recorded_content_type(
        self, service: ImageService, make_image: Callable[[str], bytes], fmt: str, content_type: str
    ) -> None:
        data = make_image(fmt)
        image_id = service.upload(data)

        stored = service.get(image_id)

        assert stored.data == data
        assert stored.content_type == content_type

    def test_unknown_id_raises_not_found(self, service: ImageService) -> None:
        with pytest.raises(ImageNotFoundError):
            service.get(uuid.uuid4())

    def test_row_whose_blob_is_missing_raises_not_found(
        self, service: ImageService, storage: InMemoryStorage, make_image: Callable[[str], bytes]
    ) -> None:
        image_id = service.upload(make_image("PNG"))
        storage.files.clear()

        with pytest.raises(ImageNotFoundError):
            service.get(image_id)


class TestList:
    def test_is_empty_before_any_upload(self, service: ImageService) -> None:
        assert service.list() == []

    def test_returns_uploaded_images_newest_first(
        self, service: ImageService, repository: InMemoryImageRepository, make_image: Callable[[str], bytes]
    ) -> None:
        first = service.upload(make_image("PNG"), "a.png")
        second = service.upload(make_image("PNG"), "b.png")
        assert [image.id for image in service.list()] == [second, first]
