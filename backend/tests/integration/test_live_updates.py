"""Committed-row tests for WebSocket authorization and LISTEN/NOTIFY delivery."""

import queue
import threading
import uuid
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

import pytest
from app.models import Order, OrderEvent, Payment, Shop, ShopRate, Upload, User
from app.services import order_service
from app.services.live_service import order_channel, vendor_channel
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect
from tests.factories import (
    create_full_rate_table,
    create_paid_order,
    create_reserved_order,
    create_shop,
    create_user,
    login_headers,
)

ORIGIN = "http://localhost:5173"
NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _user(session: Session, email: str, role: str = "customer", **kwargs: object) -> User:
    return create_user(session, email=email, role=role, **kwargs)


def _shop(session: Session, owner: User, name: str) -> Shop:
    shop = create_shop(session, owner=owner, name=name)
    create_full_rate_table(session, shop)
    return shop


def _token(client: TestClient, email: str) -> str:
    return login_headers(client, email)["Authorization"].removeprefix("Bearer ")


def _connect(client: TestClient, path: str, origin: str = ORIGIN):
    return client.websocket_connect(path, subprotocols=["spn.v1"], headers={"origin": origin})


def _auth(socket, token: str) -> None:
    socket.send_json({"type": "authenticate", "token": token})


def _receive(socket) -> dict[str, object]:
    result: queue.Queue[tuple[bool, object]] = queue.Queue()

    def receive() -> None:
        try:
            result.put((True, socket.receive_json()))
        except Exception as exc:  # noqa: BLE001 - propagate the protocol exception to the test
            result.put((False, exc))

    threading.Thread(target=receive, daemon=True).start()
    try:
        success, value = result.get(timeout=3)
    except queue.Empty as exc:
        raise TimeoutError("WebSocket receive timed out") from exc
    if success:
        return value  # type: ignore[return-value]
    raise value  # type: ignore[misc]


def _receive_until_close(socket) -> dict[str, object]:
    while True:
        body = _receive(socket)
        if body.get("type") not in {"ping", "resync"}:
            return body


def _expect_close(
    client: TestClient, path: str, token: str, code: int, origin: str = ORIGIN
) -> None:
    with pytest.raises(WebSocketDisconnect) as error, _connect(client, path, origin) as socket:
        _auth(socket, token)
        _receive(socket)
    assert error.value.code == code


def _seed(client: TestClient, session: Session, run_id: str):
    customer = _user(session, f"customer-{run_id}@example.com")
    other = _user(session, f"other-{run_id}@example.com")
    vendor_a = _user(session, f"vendor-a-{run_id}@example.com", "vendor")
    vendor_b = _user(session, f"vendor-b-{run_id}@example.com", "vendor")
    shop_a = _shop(session, vendor_a, f"Shop A {run_id}")
    shop_b = _shop(session, vendor_b, f"Shop B {run_id}")
    order_a = create_paid_order(session, customer=customer, shop=shop_a)
    order_b = create_paid_order(session, customer=customer, shop=shop_b)
    return customer, other, vendor_a, vendor_b, shop_a, shop_b, order_a, order_b


def _cleanup(engine: Engine, user_ids: list[uuid.UUID], order_ids: list[uuid.UUID]) -> None:
    with Session(engine) as session:
        session.execute(delete(OrderEvent).where(OrderEvent.order_id.in_(order_ids)))
        session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
        session.execute(delete(Order).where(Order.id.in_(order_ids)))
        session.execute(delete(Upload).where(Upload.customer_id.in_(user_ids)))
        session.execute(
            delete(ShopRate).where(
                ShopRate.shop_id.in_(select(Shop.id).where(Shop.owner_id.in_(user_ids)))
            )
        )
        session.execute(delete(Shop).where(Shop.owner_id.in_(user_ids)))
        session.execute(delete(User).where(User.id.in_(user_ids)))
        session.commit()


def test_transition_reaches_only_the_right_shop_and_order_channels(live_client) -> None:
    client, session = live_client
    run_id = uuid.uuid4().hex[:8]
    customer, _other, vendor_a, vendor_b, shop_a, shop_b, order_a, order_b = _seed(
        client, session, run_id
    )
    try:
        with ExitStack() as stack:
            ws_a = stack.enter_context(_connect(client, "/ws/vendor"))
            ws_b = stack.enter_context(_connect(client, "/ws/vendor"))
            ws_customer = stack.enter_context(_connect(client, f"/ws/orders/{order_a.id}"))
            _auth(ws_a, _token(client, vendor_a.email))
            _auth(ws_b, _token(client, vendor_b.email))
            _auth(ws_customer, _token(client, customer.email))
            assert _receive(ws_a)["channel"] == vendor_channel(shop_a.id)
            assert _receive(ws_b)["channel"] == vendor_channel(shop_b.id)
            assert _receive(ws_customer)["channel"] == order_channel(order_a.id)

            order_service.transition(
                session,
                order_id=order_a.id,
                to_status="ACCEPTED",
                actor_type="vendor",
                actor_id=vendor_a.id,
                now=NOW,
            )
            first = _receive(ws_a)
            assert first["order_id"] == str(order_a.id)
            assert first["shop_id"] == str(shop_a.id)
            assert first["to_status"] == "ACCEPTED"
            assert _receive(ws_customer)["order_id"] == str(order_a.id)

            # B is a barrier: if A leaked to B, the next message would be A.
            order_service.transition(
                session,
                order_id=order_b.id,
                to_status="ACCEPTED",
                actor_type="vendor",
                actor_id=vendor_b.id,
                now=NOW,
            )
            second = _receive(ws_b)
            assert second["order_id"] == str(order_b.id)
            assert second["shop_id"] == str(shop_b.id)

            order_service.transition(
                session,
                order_id=order_a.id,
                to_status="PRINTING",
                actor_type="vendor",
                actor_id=vendor_a.id,
                now=NOW,
            )
            third = _receive(ws_a)
            assert third["order_id"] == str(order_a.id)
            assert third["to_status"] == "PRINTING"
            assert _receive(ws_customer)["to_status"] == "PRINTING"
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, _other.id, vendor_a.id, vendor_b.id],
            [order_a.id, order_b.id],
        )


def test_cash_creation_and_worker_transition_are_published(live_client) -> None:
    client, session = live_client
    run_id = uuid.uuid4().hex[:8]
    customer, _other, vendor_a, _vendor_b, shop_a, _shop_b, order_a, _order_b = _seed(
        client, session, run_id
    )
    other_order = create_reserved_order(session, customer=customer, shop=shop_a)
    try:
        with _connect(client, "/ws/vendor") as socket:
            _auth(socket, _token(client, vendor_a.email))
            assert _receive(socket)["type"] == "subscribed"
            cash = create_reserved_order(session, customer=customer, shop=shop_a)
            created = _receive(socket)
            assert created["order_id"] == str(cash.id)
            assert created["to_status"] == "RESERVED"

            order_a.reserved_at = NOW - timedelta(minutes=20)
            order_a.paid_at = NOW - timedelta(minutes=20)
            session.commit()
            from app.jobs import auto_reject

            assert auto_reject.run(session, now=NOW) == 1
            rejected = _receive(socket)
            assert rejected["order_id"] == str(order_a.id)
            assert rejected["to_status"] == "REJECTED"
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, _other.id, vendor_a.id, _vendor_b.id],
            [order_a.id, _order_b.id, other_order.id, cash.id],
        )


def test_rollback_does_not_notify_but_a_real_commit_does(live_client, monkeypatch) -> None:
    client, session = live_client
    run_id = uuid.uuid4().hex[:8]
    customer, _other, vendor_a, _vendor_b, shop_a, _shop_b, _order_a, _order_b = _seed(
        client, session, run_id
    )
    first = None
    second = None
    try:
        with _connect(client, "/ws/vendor") as socket:
            _auth(socket, _token(client, vendor_a.email))
            assert _receive(socket)["type"] == "subscribed"
            original_commit = session.commit

            def fail_commit() -> None:
                raise RuntimeError("force rollback")

            monkeypatch.setattr(session, "commit", fail_commit)
            with pytest.raises(RuntimeError):
                first = create_reserved_order(session, customer=customer, shop=shop_a)
            session.commit = original_commit
            session.rollback()

            second = create_reserved_order(session, customer=customer, shop=shop_a)
            delivered = _receive(socket)
            assert delivered["order_id"] == str(second.id)
            assert delivered["to_status"] == "RESERVED"
            if first is not None:
                assert delivered["order_id"] != str(first.id)
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, _other.id, vendor_a.id, _vendor_b.id],
            [order.id for order in (first, second, _order_a, _order_b) if order is not None],
        )


def test_customer_role_and_cross_tenant_subscription_are_refused(live_client) -> None:
    client, session = live_client
    run_id = uuid.uuid4().hex[:8]
    customer, other, vendor_a, _vendor_b, _shop_a, _shop_b, order_a, _order_b = _seed(
        client, session, run_id
    )
    try:
        _expect_close(client, "/ws/vendor", _token(client, customer.email), 4403)
        _expect_close(client, f"/ws/orders/{order_a.id}", _token(client, vendor_a.email), 4403)
        _expect_close(client, f"/ws/orders/{order_a.id}", _token(client, other.email), 4404)
        _expect_close(client, f"/ws/orders/{uuid.uuid4()}", _token(client, customer.email), 4404)
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, other.id, vendor_a.id, _vendor_b.id],
            [order_a.id, _order_b.id],
        )


def test_invalid_tokens_inactive_accounts_and_bad_protocols_are_refused(live_client) -> None:
    client, session = live_client
    run_id = uuid.uuid4().hex[:8]
    inactive = _user(session, f"inactive-{run_id}@example.com", is_active=False)
    try:
        _expect_close(client, "/ws/vendor", "not-a-token", 4401)
        _expect_close(client, "/ws/vendor", _token(client, inactive.email), 4401)
        _expect_close(
            client,
            "/ws/vendor",
            _token(client, inactive.email),
            4403,
            origin="https://evil.example",
        )
        with (
            pytest.raises(WebSocketDisconnect) as error,
            client.websocket_connect("/ws/vendor", headers={"origin": ORIGIN}) as socket,
        ):
            _receive(socket)
        assert error.value.code == 4401
        with pytest.raises(WebSocketDisconnect) as error, _connect(client, "/ws/vendor") as socket:
            socket.send_text("not-json")
            _receive(socket)
        assert error.value.code == 4401
        with pytest.raises(WebSocketDisconnect) as error, _connect(client, "/ws/vendor") as socket:
            socket.send_json({"type": "authenticate", "token": "x" * 16_385})
            _receive(socket)
        assert error.value.code == 4401
    finally:
        _cleanup(client.app.state.db_session.bind.engine, [inactive.id], [])


def test_customer_can_subscribe_to_their_own_order(live_client) -> None:
    client, session = live_client
    run_id = uuid.uuid4().hex[:8]
    customer, _other, _vendor_a, _vendor_b, _shop_a, _shop_b, order_a, _order_b = _seed(
        client, session, run_id
    )
    try:
        with _connect(client, f"/ws/orders/{order_a.id}") as socket:
            _auth(socket, _token(client, customer.email))
            body = _receive(socket)
            assert body["type"] == "subscribed"
            assert body["channel"] == order_channel(order_a.id)
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, _other.id, _vendor_a.id, _vendor_b.id],
            [order_a.id, _order_b.id],
        )


def test_reauthorization_closes_a_deactivated_users_socket(live_client, monkeypatch) -> None:
    client, session = live_client
    run_id = uuid.uuid4().hex[:8]
    customer, _other, vendor_a, _vendor_b, _shop_a, _shop_b, _order_a, _order_b = _seed(
        client, session, run_id
    )
    monkeypatch.setattr("app.routers.ws.REAUTH_INTERVAL_SECONDS", 0.01)
    try:
        with _connect(client, "/ws/vendor") as socket:
            _auth(socket, _token(client, vendor_a.email))
            assert _receive(socket)["type"] == "subscribed"
            vendor_a.is_active = False
            session.commit()
            with pytest.raises(WebSocketDisconnect) as error:
                _receive_until_close(socket)
            assert error.value.code == 4401
    finally:
        _cleanup(
            client.app.state.db_session.bind.engine,
            [customer.id, _other.id, vendor_a.id, _vendor_b.id],
            [_order_a.id, _order_b.id],
        )


def test_a_binary_frame_before_auth_is_refused_not_an_unhandled_error(live_client) -> None:
    """An unauthenticated socket that sends bytes is refused, not crashed."""
    client, _session = live_client
    with pytest.raises(WebSocketDisconnect) as error, _connect(client, "/ws/vendor") as socket:
        socket.send_bytes(b"\x00\x01\x02")
        _receive(socket)
    assert error.value.code == 4401
