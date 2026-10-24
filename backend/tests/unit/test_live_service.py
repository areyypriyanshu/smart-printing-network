import asyncio
import json
import uuid
from datetime import UTC, datetime

import anyio
import pytest
from app.services.live_service import (
    EventHub,
    TransitionMessage,
    _message_from_json,
    order_channel,
    vendor_channel,
)

SHOP = uuid.UUID("aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa")
ORDER = uuid.UUID("bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb")


def _message(order_id=ORDER, shop_id=SHOP, status="PAID"):
    return TransitionMessage(
        event_id=1,
        order_id=order_id,
        shop_id=shop_id,
        from_status="PENDING_PAYMENT",
        to_status=status,
        at=datetime(2026, 1, 1, tzinfo=UTC),
    ).as_dict()


def test_hub_uses_channel_barriers_without_cross_shop_leakage() -> None:
    async def run() -> None:
        hub = EventHub()
        hub.set_available(True)
        first = hub.subscribe(vendor_channel(SHOP))
        other_shop = uuid.uuid4()
        second = hub.subscribe(vendor_channel(other_shop))
        assert first is not None and second is not None
        first_message = _message(status="ACCEPTED")
        second_message = _message(order_id=uuid.uuid4(), shop_id=other_shop, status="PRINTING")
        hub.publish(vendor_channel(SHOP), first_message)
        hub.publish(vendor_channel(other_shop), second_message)

        assert await asyncio.wait_for(first.get(), 1) == first_message
        assert await asyncio.wait_for(second.get(), 1) == second_message
        hub.unsubscribe(first)
        hub.unsubscribe(second)

    anyio.run(run)


def test_listener_outage_closes_subscriptions_and_recovery_resyncs() -> None:
    async def run() -> None:
        hub = EventHub()
        hub.set_available(True)
        subscription = hub.subscribe(order_channel(ORDER))
        assert subscription is not None
        hub.set_available(False)

        assert hub.available is False
        assert await asyncio.wait_for(subscription.get(), 1) is None
        assert hub.subscriber_count(order_channel(ORDER)) == 0

        hub.set_available(True)
        recovered = hub.subscribe(order_channel(ORDER))
        assert recovered is not None
        hub.set_available(True)
        assert await asyncio.wait_for(recovered.get(), 1) == {"type": "resync"}
        hub.unsubscribe(recovered)
        assert hub.available is True

    anyio.run(run)


def test_broken_subscriber_does_not_block_a_healthy_channel() -> None:
    async def run() -> None:
        hub = EventHub()
        hub.set_available(True)
        broken = hub.subscribe(order_channel(ORDER))
        healthy = hub.subscribe(order_channel(ORDER))
        assert broken is not None and healthy is not None
        hub.unsubscribe(broken)
        message = _message()
        hub.publish(order_channel(ORDER), message)

        assert await asyncio.wait_for(healthy.get(), 1) == message
        hub.unsubscribe(healthy)

    anyio.run(run)


def test_connection_limit_is_released_on_unsubscribe() -> None:
    async def run() -> None:
        hub = EventHub(max_connections_per_key=1, max_connections=1)
        hub.set_available(True)
        first = hub.subscribe("a", connection_key="ip")
        assert first is not None
        assert hub.subscribe("b", connection_key="ip") is None
        hub.unsubscribe(first)
        second = hub.subscribe("b", connection_key="ip")
        assert second is not None
        hub.close_all()
        assert hub.available is False
        closed = hub.subscribe("a")
        assert closed is not None
        assert closed.active is False
        assert await closed.get() is None

    anyio.run(run)


def test_notification_parser_accepts_only_tiny_valid_transition_messages() -> None:
    message = _message()
    parsed = _message_from_json(json.dumps(message))
    assert parsed.order_id == ORDER
    assert parsed.shop_id == SHOP
    assert parsed.to_status == "PAID"

    for bad in (
        "not-json",
        "{}",
        json.dumps({**message, "to_status": "NOT_A_STATUS"}),
        json.dumps({**message, "event_id": 0}),
        json.dumps({**message, "at": "2026-01-01T00:00:00"}),
    ):
        with pytest.raises(ValueError):
            _message_from_json(bad)
