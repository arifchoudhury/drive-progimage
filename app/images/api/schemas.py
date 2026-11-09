import uuid

from pydantic import BaseModel


class ImageUploadResponse(BaseModel):
    id: uuid.UUID
