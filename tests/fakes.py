import uuid

from app.images.domain.entities import Image


class InMemoryStorage:
    """Fake ImageStorage: keeps blobs in a dict, touches no filesystem."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self.files[key] = data

    def load(self, key: str) -> bytes | None:
        return self.files.get(key)


class InMemoryImageRepository:
    """Fake ImageRepository: keeps image metadata in a dict, no database."""

    def __init__(self) -> None:
        self.images: dict[uuid.UUID, Image] = {}

    def add(self, image: Image) -> None:
        self.images[image.id] = image

    def get(self, image_id: uuid.UUID) -> Image | None:
        return self.images.get(image_id)

    def list(self) -> list[Image]:
        return sorted(self.images.values(), key=lambda image: image.id, reverse=True)
