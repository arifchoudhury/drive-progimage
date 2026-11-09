import uuid

from sqlalchemy.orm import Session

from app.images.domain.entities import Image
from app.images.infrastructure.database.models import ImageRow


class SqlAlchemyImageRepository:
    """Postgres-backed ImageRepository. `add` commits, since each request stores exactly one image."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, image: Image) -> None:
        self._session.add(ImageRow(**image.model_dump()))
        self._session.commit()

    def get(self, image_id: uuid.UUID) -> Image | None:
        row = self._session.get(ImageRow, image_id)
        return Image.model_validate(row, from_attributes=True) if row else None
