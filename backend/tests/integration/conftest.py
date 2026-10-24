"""Shared committed-row fixtures for live-update integration tests."""

import pytest
from app.db import get_db
from app.gateways.identity.fake import FakeIdentityReader, FakeTokenVerifier
from app.gateways.storage import MemoryStorage
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


@pytest.fixture
def live_client(engine: Engine, test_database: str):
    """An app with a real listener and independent auth sessions per call."""
    with Session(engine) as session:
        app = create_app(
            enable_transition_listener=True,
            transition_database_url=test_database,
            session_factory=lambda: Session(engine),
        )
        app.state.storage = MemoryStorage()
        app.state.identity_reader = FakeIdentityReader()
        app.state.token_verifier = FakeTokenVerifier()
        app.state.db_session = session
        app.dependency_overrides[get_db] = lambda: session
        with TestClient(app) as client:
            assert app.state.transition_ready.wait(2), "LISTEN did not become ready"
            yield client, session
        app.dependency_overrides.clear()
