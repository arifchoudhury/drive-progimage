import io
import os
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from tests.fake_s3 import FakeS3Client

TIERS = ("unit", "integration", "e2e")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark every test with its tier, taken from the folder it lives in."""
    root = Path(__file__).parent
    for item in items:
        tier = Path(item.path).relative_to(root).parts[0]
        if tier in TIERS:
            item.add_marker(getattr(pytest.mark, tier))


@pytest.fixture
def make_image() -> Callable[[str], bytes]:
    """Build a tiny valid image in the given PIL format (PNG, JPEG, GIF, ...)."""

    def _make(fmt: str) -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (20, 10), (255, 0, 0)).save(buffer, format=fmt)
        return buffer.getvalue()

    return _make


@pytest.fixture
def truncated_png(make_image: Callable[[str], bytes]) -> bytes:
    """A real PNG cut off half way through: the header parses, the body doesn't."""
    data = make_image("PNG")
    return data[: len(data) // 2]


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3Client:
    """Make `boto3.client(...)` return an in-memory fake, so S3ImageStorage needs no AWS."""
    boto3 = pytest.importorskip("boto3")
    fake = FakeS3Client()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: fake)
    return fake


# A dedicated database on the docker-compose Postgres (`make services`), so tests never touch dev data.
TEST_DATABASE_URL = os.environ.get(
    "PROGIMAGE_TEST_DATABASE_URL", "postgresql+psycopg://progimage:progimage@localhost:5433/progimage_test"
)


@pytest.fixture(scope="session")
def database_url() -> str:
    """Create the test database if needed and migrate it to head, once per test session."""
    url = make_url(TEST_DATABASE_URL)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()

    config = Config(str(Path(__file__).parent.parent / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def clean_database(engine: Engine) -> Engine:
    """Empty the images table before the test."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE images"))
    return engine
