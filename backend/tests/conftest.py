from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.db import get_db
from app.gateways.storage import MemoryStorage
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

TEST_DATABASE = "spn_test"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = make_url(get_settings().database_url)
    test_url = url.set(database=TEST_DATABASE)

    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DATABASE}
        ).scalar()
        if exists is None:
            connection.exec_driver_sql(f'CREATE DATABASE "{TEST_DATABASE}"')
    admin_engine.dispose()

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["database_url"] = test_url.render_as_string(hide_password=False)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(test_url, pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app = create_app()
    app.state.storage = MemoryStorage()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
