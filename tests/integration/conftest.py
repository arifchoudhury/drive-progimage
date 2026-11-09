from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.images.api.dependencies import get_image_validator, get_storage
from app.images.domain.validation import ImageValidator
from app.images.infrastructure.storage import LocalImageStorage
from app.main import create_app

USERNAME = "tester"
PASSWORD = "s3cret"
MAX_UPLOAD_BYTES = 64 * 1024  # small, so size-limit tests don't need to send megabytes


@pytest.fixture
def anonymous_client(tmp_path: Path, clean_database: Engine, database_url: str) -> Iterator[TestClient]:
    """Client with no credentials attached, backed by a local tmp dir and the (emptied) test Postgres."""

    def session() -> Iterator[Session]:
        with Session(clean_database, expire_on_commit=False) as s:
            yield s

    settings = Settings(
        storage_dir=tmp_path,
        auth_username=USERNAME,
        auth_password=PASSWORD,
        database_url=database_url,
        max_upload_bytes=MAX_UPLOAD_BYTES,
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_storage] = lambda: LocalImageStorage(tmp_path)
    app.dependency_overrides[get_image_validator] = lambda: ImageValidator(
        max_bytes=settings.max_upload_bytes, max_pixels=settings.max_image_pixels
    )
    app.dependency_overrides[get_session] = session
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(anonymous_client: TestClient) -> TestClient:
    """Client that sends valid Basic credentials by default."""
    anonymous_client.auth = (USERNAME, PASSWORD)
    return anonymous_client
