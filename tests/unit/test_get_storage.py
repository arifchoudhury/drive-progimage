from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.images.api import dependencies
from app.images.api.dependencies import get_storage
from app.images.infrastructure.storage import LocalImageStorage, S3ImageStorage
from tests.fake_s3 import FakeS3Client


def _settings(**kwargs: object) -> Settings:
    return Settings(auth_username="u", auth_password="p", database_url="postgresql+psycopg://x/y", **kwargs)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    get_storage.cache_clear()
    yield
    get_storage.cache_clear()


class TestGetStorage:
    def test_local_is_the_default(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(dependencies, "get_settings", lambda: _settings(storage_dir=tmp_path))
        assert isinstance(get_storage(), LocalImageStorage)

    def test_s3_backend_builds_s3_storage(self, monkeypatch: pytest.MonkeyPatch, fake_s3: FakeS3Client) -> None:
        settings = _settings(storage_backend="s3", s3_bucket="bucket", aws_secret_access_key="x")
        monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
        assert isinstance(get_storage(), S3ImageStorage)

    def test_instance_is_built_once(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(dependencies, "get_settings", lambda: _settings(storage_dir=tmp_path))
        assert get_storage() is get_storage()

    def test_s3_backend_requires_a_bucket(self) -> None:
        with pytest.raises(ValidationError, match="PROGIMAGE_S3_BUCKET"):
            _settings(storage_backend="s3")
