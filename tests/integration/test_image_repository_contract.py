import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.images.domain.entities import Image
from app.images.domain.ports import ImageRepository
from app.images.infrastructure.database.repository import SqlAlchemyImageRepository
from tests.fakes import InMemoryImageRepository


@pytest.fixture(params=["in_memory", "postgres"])
def repository(request: pytest.FixtureRequest) -> Iterator[ImageRepository]:
    """Every ImageRepository implementation must satisfy the same behaviour."""
    if request.param == "in_memory":
        yield InMemoryImageRepository()
        return
    engine: Engine = request.getfixturevalue("clean_database")
    with Session(engine, expire_on_commit=False) as session:
        yield SqlAlchemyImageRepository(session)


def _image(**overrides: object) -> Image:
    fields: dict[str, object] = {
        "id": uuid.uuid7(),
        "original_filename": "holiday.png",
        "storage_key": "key.png",
        "content_type": "image/png",
        "size_bytes": 123,
        "created_at": datetime.now(UTC),
    }
    return Image.model_validate(fields | overrides)


class TestImageRepositoryContract:
    def test_add_then_get_round_trips_every_field(self, repository: ImageRepository) -> None:
        image = _image()
        repository.add(image)
        assert repository.get(image.id) == image

    def test_filename_may_be_absent(self, repository: ImageRepository) -> None:
        image = _image(original_filename=None)
        repository.add(image)
        assert repository.get(image.id) == image

    def test_get_of_unknown_id_is_none(self, repository: ImageRepository) -> None:
        assert repository.get(uuid.uuid7()) is None

    def test_images_are_isolated_by_id(self, repository: ImageRepository) -> None:
        a, b = _image(storage_key="a.png"), _image(storage_key="b.png")
        repository.add(a)
        repository.add(b)
        assert (repository.get(a.id), repository.get(b.id)) == (a, b)

    def test_list_of_an_empty_repository_is_empty(self, repository: ImageRepository) -> None:
        assert repository.list() == []

    def test_list_returns_every_image_newest_first(self, repository: ImageRepository) -> None:
        older, newer = _image(storage_key="a.png"), _image(storage_key="b.png")
        repository.add(older)
        repository.add(newer)
        assert repository.list() == [newer, older]
