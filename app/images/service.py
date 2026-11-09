import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from app.images.domain.entities import Image
from app.images.domain.exceptions import ImageNotFoundError
from app.images.domain.ports import ImageRepository, ImageStorage
from app.images.domain.validation import ImageValidator
from app.images.domain.values import ImageContent, ImageInfo

_MAX_FILENAME_LENGTH = 255


def _clean_filename(name: str | None) -> str | None:
    """Reduce a client-supplied filename to a safe, informational basename (or None)."""
    if not name:
        return None
    basename: str = PurePosixPath(name.replace("\\", "/")).name
    printable: str = "".join(c for c in basename if c.isprintable()).strip()  # also drops NUL, which Postgres rejects
    return printable[:_MAX_FILENAME_LENGTH] or None


class ImageService:
    def __init__(self, storage: ImageStorage, repository: ImageRepository, validator: ImageValidator) -> None:
        self._storage = storage
        self._repository = repository
        self._validator = validator

    def upload(self, data: bytes, filename: str | None = None) -> uuid.UUID:
        info: ImageInfo = self._validator.validate(data)
        image_id = uuid.uuid7()
        # The blob is addressed by a key we generate, never by the client's filename (collisions, path traversal).
        image = Image(
            id=image_id,
            original_filename=_clean_filename(filename),
            storage_key=f"{image_id}.{info.extension}",
            content_type=info.content_type,
            size_bytes=info.size_bytes,
            created_at=datetime.now(UTC),
        )
        self._storage.save(image.storage_key, data)
        # Known gap: if this insert fails, the blob is orphaned (cleanup needs a delete on ImageStorage).
        self._repository.add(image)
        return image_id

    def get(self, image_id: uuid.UUID) -> ImageContent:
        image: Image | None = self._repository.get(image_id)
        if image is None:
            raise ImageNotFoundError(image_id)
        data: bytes | None = self._storage.load(image.storage_key)
        if data is None:  # row exists but the blob is gone: treat as missing rather than a server error
            raise ImageNotFoundError(image_id)
        extension: str = PurePosixPath(image.storage_key).suffix.lstrip(".")
        return ImageContent(data=data, content_type=image.content_type, extension=extension)

    def list(self) -> list[Image]:
        """All image metadata, newest first. TODO(pagination): see ImageRepository.list."""
        return self._repository.list()
