from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.images.domain.ports import ImageRepository, ImageStorage
from app.images.domain.validation import ImageValidator
from app.images.infrastructure.database.repository import SqlAlchemyImageRepository
from app.images.infrastructure.storage import LocalImageStorage, S3ImageStorage
from app.images.service import ImageService


@lru_cache
def get_storage() -> ImageStorage:
    """The one place that maps configuration to a concrete ImageStorage, built once per process.

    Adding a backend = implement the ImageStorage protocol + add a case here.
    Tests swap it via `app.dependency_overrides[get_storage]`.
    """
    settings: Settings = get_settings()
    match settings.storage_backend:
        case "local":
            return LocalImageStorage(settings.storage_dir)
        case "s3":
            assert settings.s3_bucket is not None  # guaranteed by Settings validation
            secret = settings.aws_secret_access_key
            return S3ImageStorage(
                settings.s3_bucket,
                settings.s3_prefix,
                region_name=settings.s3_region,
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=secret.get_secret_value() if secret else None,
            )


@lru_cache
def get_image_validator() -> ImageValidator:
    """The upload policy, built once per process from settings."""
    settings: Settings = get_settings()
    return ImageValidator(max_bytes=settings.max_upload_bytes, max_pixels=settings.max_image_pixels)


def get_image_repository(session: Annotated[Session, Depends(get_session)]) -> ImageRepository:
    return SqlAlchemyImageRepository(session)


def get_image_service(
    storage: Annotated[ImageStorage, Depends(get_storage)],
    repository: Annotated[ImageRepository, Depends(get_image_repository)],
    validator: Annotated[ImageValidator, Depends(get_image_validator)],
) -> ImageService:
    return ImageService(storage, repository, validator)


ImageServiceDep = Annotated[ImageService, Depends(get_image_service)]
