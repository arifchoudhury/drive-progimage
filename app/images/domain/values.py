from pydantic import BaseModel, ConfigDict


class ImageContent(BaseModel):
    """Value object: an image's bytes, MIME type and file extension, equal when all are equal."""

    model_config = ConfigDict(frozen=True)

    data: bytes
    content_type: str
    extension: str


class ImageInfo(BaseModel):
    """Value object: what inspecting an image's bytes reveals."""

    model_config = ConfigDict(frozen=True)

    content_type: str
    extension: str
    size_bytes: int
