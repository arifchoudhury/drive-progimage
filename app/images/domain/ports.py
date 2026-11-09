"""Ports: the interfaces ImageService depends on. Concrete adapters live in app/images/infrastructure/."""

import uuid
from typing import Protocol

from app.images.domain.entities import Image


class ImageStorage(Protocol):
    """Stores opaque bytes under a caller-chosen key. The key is recorded in the database (images.storage_key)."""

    def save(self, key: str, data: bytes) -> None: ...

    def load(self, key: str) -> bytes | None: ...


class ImageRepository(Protocol):
    """Persists image metadata (the Image entity)."""

    def add(self, image: Image) -> None: ...

    def get(self, image_id: uuid.UUID) -> Image | None: ...

    def list(self) -> list[Image]:
        """Every image, newest first.

        TODO(pagination): unbounded for now. Before the table grows, take a `limit` and an `after` cursor
        on `id` (uuid7 ids are time-ordered and unique, so they make a stable keyset key).
        """
        ...
