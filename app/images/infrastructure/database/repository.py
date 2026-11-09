import uuid

from sqlalchemy import ScalarResult, select
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
        row: ImageRow | None = self._session.get(ImageRow, image_id)
        return Image.model_validate(row, from_attributes=True) if row else None

    def list(self) -> list[Image]:
        rows: ScalarResult[ImageRow] = self._session.scalars(select(ImageRow).order_by(ImageRow.id.desc()))
        return [Image.model_validate(row, from_attributes=True) for row in rows]
