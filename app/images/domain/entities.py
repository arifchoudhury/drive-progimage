import uuid
from datetime import datetime

from pydantic import BaseModel


class Image(BaseModel):
    """Entity: identified by `id`. Metadata only; the bytes live in ImageStorage under `storage_key`."""

    id: uuid.UUID
    original_filename: str | None
    storage_key: str
    content_type: str
    size_bytes: int
    created_at: datetime
