import uuid
from datetime import datetime

from pydantic import BaseModel


class ImageUploadResponse(BaseModel):
    id: uuid.UUID


class ImageSummary(BaseModel):
    """Public metadata for one image. Deliberately omits the internal storage key."""

    id: uuid.UUID
    original_filename: str | None
    content_type: str
    size_bytes: int
    created_at: datetime


class ImageListResponse(BaseModel):
    # An object rather than a bare array so pagination (e.g. `next_cursor`) can be added without breaking clients.
    items: list[ImageSummary]
