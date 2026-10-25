"""Application-listener lifecycle and notification edge cases."""

import uuid

from app.gateways.identity.fake import FakeIdentityReader, FakeTokenVerifier
from app.gateways.storage import MemoryStorage
from app.main import create_app
from app.schemas.order import OrderCreateRequest
from app.services import order_service
from fastapi.testclient import TestClient
from sqlalchemy import TextClause
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from tests.factories import create_reserved_order, create_upload_row
from tests.integration.test_live_updates import _auth, _cleanup, _connect, _receive, _seed, _token


def test_listener_lifecycles_do_not_duplicate_connections(
    engine: Engine, test_database: str
) -> None:
    app = create_app(
        enable_transition_listener=True,
        transition_database_url=test_database,
        session_factory=lambda: Session(engine),
    )
    app.state.storage = MemoryStorage()
    app.state.identity_reader = FakeIdentityReader()
    app.state.token_verifier = FakeTokenVerifier()
    with TestClient(app):
        assert app.state.transition_ready.wait(2)
        first = app.state.transition_listener
        assert first is not None
    assert first.done()
    assert not app.state.event_hub.available

    with TestClient(app):
        assert app.state.transition_ready.wait(2)
        second = app.state.transition_listener
        assert second is not None
    assert second.done()
    assert first is not second
    assert not app.state.event_hub.available


def test_notification_failure_does_not_roll_back_an_order(live_client, monkeypatch) -> None:
    client, session = live_client
    customer, _other, vendor_a, _vendor_b, shop_a, _shop_b, _order_a, _order_b = _seed(
        client, session, uuid.uuid4().hex[:8]
    )
    original_execute = session.execute

    def fail_only_notification(statement, *args, **kwargs):
        if isinstance(statement, TextClause) and "pg_notify" in statement.text:
            raise RuntimeError("notification unavailable")
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(session, "execute", fail_only_notification)
    order = create_reserved_order(session, customer=customer, shop=shop_a)
    try:
        assert order.status == "RESERVED"
        assert order.pickup_code is not None
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, _other.id, vendor_a.id, _vendor_b.id],
            [order.id, _order_a.id, _order_b.id],
        )


def test_idempotent_create_does_not_emit_an_opening_event_twice(live_client) -> None:
    client, session = live_client
    customer, _other, vendor_a, _vendor_b, shop_a, _shop_b, _order_a, _order_b = _seed(
        client, session, uuid.uuid4().hex[:8]
    )
    upload = create_upload_row(session, customer=customer)
    request = OrderCreateRequest(
        upload_id=upload.id,
        shop_id=shop_a.id,
        paper_size="A4",
        color=False,
        duplex=False,
        copies=1,
    )
    try:
        with _connect(client, "/ws/vendor") as socket:
            _auth(socket, _token(client, vendor_a.email))
            assert _receive(socket)["type"] == "subscribed"
            first = order_service.create_order(
                session,
                customer_id=customer.id,
                request=request,
                idempotency_key="repeat-live-test",
            )
            second = order_service.create_order(
                session,
                customer_id=customer.id,
                request=request,
                idempotency_key="repeat-live-test",
            )
            assert second.id == first.id
            first_message = _receive(socket)
            assert first_message["order_id"] == str(first.id)
            barrier = create_reserved_order(session, customer=customer, shop=shop_a)
            next_message = _receive(socket)
            assert next_message["order_id"] == str(barrier.id)
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, _other.id, vendor_a.id, _vendor_b.id],
            [first.id, second.id, barrier.id, _order_a.id, _order_b.id],
        )
