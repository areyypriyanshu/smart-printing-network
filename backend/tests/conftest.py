from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from app.config import get_settings
from app.db import get_db
from app.gateways.email import MemoryEmailSender
from app.gateways.storage import MemoryStorage
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from tests.factories import FAKE_WEBHOOK_SECRET

TEST_DATABASE = "spn_test"


@pytest.fixture(autouse=True, scope="session")
def fake_gateway_is_keyed() -> Iterator[None]:
    """The fake gateway is keyed with the test secret, and the testing
    surface is on.

    The fake gateway takes no default secret, because a key that lives in
    the application package is a key that ships in the repository. The
    application and the test gateways have to agree on the key, so it is set
    here for the whole session, and the testing routes are switched on the
    same way the cash-at-store feature is.
    """
    settings = get_settings()
    original_secret = settings.fake_webhook_secret
    original_testing = settings.testing_endpoints_enabled
    settings.fake_webhook_secret = FAKE_WEBHOOK_SECRET
    settings.testing_endpoints_enabled = True
    yield
    settings.fake_webhook_secret = original_secret
    settings.testing_endpoints_enabled = original_testing


@pytest.fixture(autouse=True, scope="session")
def cash_at_store_is_on() -> Iterator[None]:
    """Paying at the shop is switched on for the test suite.

    The feature is off by default in the code, so a deployment that has
    not been configured for it cannot create a cash order by accident.
    The tests need it on, and the one test that checks the disabled path
    turns it off for itself.
    """
    settings = get_settings()
    original = settings.cash_at_store_enabled
    settings.cash_at_store_enabled = True
    yield
    settings.cash_at_store_enabled = original


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
    app = create_app()
    app.state.storage = MemoryStorage()
    app.state.email_sender = MemoryEmailSender()
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
    app = create_app()
    app.state.storage = MemoryStorage()
    app.state.email_sender = MemoryEmailSender()
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
    app = create_app()
    app.state.storage = MemoryStorage()
    app.state.email_sender = MemoryEmailSender()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
