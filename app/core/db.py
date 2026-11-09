from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    # Explicit constraint names keep Alembic autogenerate diffs and downgrades deterministic.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """One engine (and connection pool) per process. Tests swap `get_session` via dependency_overrides."""
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session
