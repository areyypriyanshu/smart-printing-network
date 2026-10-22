from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def storable_json(document: Any) -> Any:
    """A document the database is able to keep.

    A JSON document can carry a NUL byte inside a string, and
    PostgreSQL's jsonb cannot hold one. A row that holds a delivery is
    written before the delivery is acted on, so a document that cannot
    be stored would stop the delivery from being acted on at all. The
    byte carries no meaning, so it is taken out of the copy that is
    kept. The decision is still made from the document as it arrived.
    """
    if isinstance(document, dict):
        return {key: storable_json(value) for key, value in document.items()}
    if isinstance(document, list):
        return [storable_json(value) for value in document]
    if isinstance(document, str):
        return document.replace("\x00", "")
    return document
