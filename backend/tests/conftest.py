import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.db import get_db
from app.gateways.email import MemoryEmailSender
from app.gateways.identity.fake import FakeIdentityReader, FakeTokenVerifier
from app.gateways.storage import MemoryStorage
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

TEST_DATABASE = f"spn_test_{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True, scope="session")
def the_local_way_in_is_on() -> Iterator[None]:
    """The local way in is on for the test suite.

    The end to end suite signs in through it, because it has to run
    offline, and the tests here do the same. The setting is refused in
    production, and the route behind it is the only place it is used.
    """
    settings = get_settings()
    original = settings.spn_dev_auth
    settings.spn_dev_auth = True
    yield
    settings.spn_dev_auth = original


@pytest.fixture(scope="session")
def test_database() -> Iterator[str]:
    """The test database, built from scratch for every run.

    It is dropped and recreated rather than reused. Nothing in it is
    worth keeping, and a database left behind by an earlier run is a
    source of failures that have nothing to do with the change under
    test. Two ways it bites:

    - A test that needs real committed rows, such as the one that runs two
      workers against each other, cannot use the transaction fixture, so
      it commits for real and cleans up by hand. When that hand written
      cleanup misses a row, the row survives and the next run sees it.
      The failures that causes look nothing like the cause: a shop list
      with one shop too many, or a query that suddenly returns two rows.
    - The database remembers which migration it is on. A branch that
      adds or removes a migration leaves the database at a version the
      branch does not have, and every test then fails to set up.

    Rebuilding it once per session makes the suite independent of what
    any earlier run left behind, and of which branch it is on.
    """
    url = make_url(get_settings().database_url)
    test_url = url.set(database=TEST_DATABASE)

    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        # WITH (FORCE) closes any connection left over from a previous
        # run, so the drop cannot block on it.
        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)')
        connection.exec_driver_sql(f'CREATE DATABASE "{TEST_DATABASE}"')
    admin_engine.dispose()

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.attributes["database_url"] = test_url.render_as_string(hide_password=False)
    command.upgrade(alembic_cfg, "head")

    yield test_url.render_as_string(hide_password=False)


@pytest.fixture
def engine(test_database: str) -> Iterator[Engine]:
    engine = create_engine(test_database, pool_pre_ping=True)
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
    app = create_app(enable_transition_listener=False, session_factory=lambda: db_session)
    app.state.storage = MemoryStorage()
    app.state.email_sender = MemoryEmailSender()
    app.state.token_verifier = FakeTokenVerifier()
    app.state.identity_reader = FakeIdentityReader()
    app.state.db_session = db_session
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_that_reports_failures(db_session: Session) -> Iterator[TestClient]:
    """A client that answers a server error instead of raising it.

    The default test client re-raises an exception that escaped a route,
    which is useful for most tests and useless for the ones that check
    that a route answers 5xx. A payment provider retries a delivery it
    was told failed, so "the route answers 5xx" is a behaviour worth
    testing on its own.
    """
    app = create_app(enable_transition_listener=False, session_factory=lambda: db_session)
    app.state.storage = MemoryStorage()
    app.state.email_sender = MemoryEmailSender()
    app.state.token_verifier = FakeTokenVerifier()
    app.state.identity_reader = FakeIdentityReader()
    app.state.db_session = db_session
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def https_client(db_session: Session) -> Iterator[TestClient]:
    """A client whose requests arrive over TLS.

    Whether the refresh cookie is marked Secure is decided by the
    transport the request arrived on, so the test has to be able to make
    a request that arrived over TLS.
    """
    app = create_app(enable_transition_listener=False, session_factory=lambda: db_session)
    app.state.storage = MemoryStorage()
    app.state.email_sender = MemoryEmailSender()
    app.state.token_verifier = FakeTokenVerifier()
    app.state.identity_reader = FakeIdentityReader()
    app.state.db_session = db_session
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
