"""Disposable live-update hints, bridged by PostgreSQL LISTEN/NOTIFY.

The notification is written in the same transaction as the order event, so a
rollback cannot publish it. The API turns committed notifications into
in-process messages for its own subscribers. Notifications are not durable:
a disconnected client must always resync.
"""

import asyncio
import json
import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime

import psycopg
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.domain.order_state import ALL_STATUSES
from app.models import Order, OrderEvent

logger = logging.getLogger(__name__)

CHANNEL = "spn_order_transition"
Message = dict[str, object]


@dataclass(frozen=True)
class TransitionMessage:
    event_id: int
    order_id: uuid.UUID
    shop_id: uuid.UUID
    from_status: str | None
    to_status: str
    at: datetime

    def as_dict(self) -> Message:
        return {
            "type": "order.transition",
            "event_id": self.event_id,
            "order_id": str(self.order_id),
            "shop_id": str(self.shop_id),
            "from_status": self.from_status,
            "to_status": self.to_status,
            "at": self.at.isoformat(),
        }


def vendor_channel(shop_id: uuid.UUID) -> str:
    return f"vendor:{shop_id}"


def order_channel(order_id: uuid.UUID) -> str:
    return f"order:{order_id}"


def notify_transition(session: Session, *, order: Order, event: OrderEvent) -> None:
    """Queue a notification inside the order's transaction, before its commit.

    The savepoint contains a failed hint without rolling back the order. A
    notification is delivered by PostgreSQL only when the outer commit wins.
    """
    try:
        message = TransitionMessage(
            event_id=event.id,
            order_id=order.id,
            shop_id=order.shop_id,
            from_status=event.from_status,
            to_status=event.to_status,
            at=event.at,
        )
        payload = json.dumps(message.as_dict(), separators=(",", ":"))
        with session.begin_nested():
            session.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": CHANNEL, "payload": payload},
            )
    except Exception:  # noqa: BLE001 - live hints are deliberately best effort
        logger.error("order_live_notification_failed", extra={"order_id": str(order.id)})


class _Subscription:
    """One connection's bounded queue, touched only on its own event loop."""

    def __init__(
        self,
        channel: str,
        loop: asyncio.AbstractEventLoop,
        maxsize: int,
        connection_key: str | None,
    ) -> None:
        self.channel = channel
        self.loop = loop
        self.connection_key = connection_key
        self.queue: asyncio.Queue[Message | None] = asyncio.Queue(maxsize=maxsize)
        self.active = True

    def offer(self, message: Message) -> None:
        if not self.active:
            return
        if self.queue.full():
            # Coalesce old hints rather than growing memory or blocking a
            # committed order. A later resync or poll fills any gap.
            self.queue.get_nowait()
        self.queue.put_nowait(message)

    def close(self) -> None:
        self.active = False
        while self.queue.full():
            self.queue.get_nowait()
        self.queue.put_nowait(None)

    async def get(self) -> Message | None:
        return await self.queue.get()


class EventHub:
    """A thread-safe, per-process fan-out of disposable messages."""

    def __init__(
        self,
        *,
        max_queue_size: int = 32,
        max_connections_per_key: int = 8,
        max_connections: int = 100,
    ) -> None:
        self._max_queue_size = max_queue_size
        self._max_connections_per_key = max_connections_per_key
        self._max_connections = max_connections
        self._channels: dict[str, set[_Subscription]] = {}
        self._connection_counts: dict[str, int] = {}
        self._lock = threading.Lock()
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        with self._lock:
            self._available = available
        if available:
            # A listener may have missed notifications while it was down.
            self.publish_all({"type": "resync"})
        else:
            self.close_all()

    def subscribe(self, channel: str, *, connection_key: str | None = None) -> _Subscription | None:
        with self._lock:
            if not self._available:
                subscription = _Subscription(
                    channel, asyncio.get_running_loop(), self._max_queue_size, None
                )
                subscription.close()
                return subscription
            total = sum(self._connection_counts.values())
            if connection_key is not None and (
                total >= self._max_connections
                or self._connection_counts.get(connection_key, 0) >= self._max_connections_per_key
            ):
                return None
            if connection_key is not None:
                self._connection_counts[connection_key] = (
                    self._connection_counts.get(connection_key, 0) + 1
                )
            subscription = _Subscription(
                channel, asyncio.get_running_loop(), self._max_queue_size, connection_key
            )
            self._channels.setdefault(channel, set()).add(subscription)
            return subscription

    def unsubscribe(self, subscription: _Subscription) -> None:
        with self._lock:
            subscribers = self._channels.get(subscription.channel)
            if subscribers is not None:
                subscribers.discard(subscription)
                if not subscribers:
                    self._channels.pop(subscription.channel, None)
            if subscription.connection_key is not None:
                remaining = self._connection_counts.get(subscription.connection_key, 0) - 1
                if remaining > 0:
                    self._connection_counts[subscription.connection_key] = remaining
                else:
                    self._connection_counts.pop(subscription.connection_key, None)
        subscription.close()

    def close_all(self) -> None:
        with self._lock:
            self._available = False
            subscriptions = [item for group in self._channels.values() for item in group]
            self._channels.clear()
            self._connection_counts.clear()
        for subscription in subscriptions:
            subscription.close()

    def subscriber_count(self, channel: str) -> int:
        with self._lock:
            return len(self._channels.get(channel, set()))

    def publish(self, channel: str, message: Message) -> None:
        with self._lock:
            subscriptions = list(self._channels.get(channel, set()))
        for subscription in subscriptions:
            self._offer(subscription, message)

    def publish_all(self, message: Message) -> None:
        with self._lock:
            subscriptions = [item for group in self._channels.values() for item in group]
        for subscription in subscriptions:
            self._offer(subscription, message)

    def _offer(self, subscription: _Subscription, message: Message) -> None:
        if not subscription.active:
            return
        try:
            subscription.loop.call_soon_threadsafe(subscription.offer, message)
        except RuntimeError:
            # The loop may have closed during shutdown. Its subscription is
            # already dead, so there is nothing useful left to deliver.
            self.unsubscribe(subscription)


async def listen_for_transitions(
    *,
    database_url: str,
    hub: EventHub,
    ready_event: threading.Event | None = None,
    retry_seconds: float = 1.0,
) -> None:
    """Listen until cancelled, reconnecting and resyncing after failures."""
    dsn = make_url(database_url).set(drivername="postgresql").render_as_string(hide_password=False)
    try:
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(
                    dsn, autocommit=True
                ) as connection:
                    await connection.execute(f"LISTEN {CHANNEL}")
                    hub.set_available(True)
                    if ready_event is not None:
                        ready_event.set()
                    async for notification in connection.notifies():
                        try:
                            message = _message_from_json(notification.payload)
                        except ValueError:
                            logger.warning("invalid order transition notification discarded")
                            continue
                        hub.publish(vendor_channel(message.shop_id), message.as_dict())
                        hub.publish(order_channel(message.order_id), message.as_dict())
            except (psycopg.Error, OSError) as exc:
                logger.warning(
                    "order transition listener stopped: %s; retrying", type(exc).__name__
                )
                hub.set_available(False)
                await asyncio.sleep(retry_seconds)
    finally:
        hub.close_all()


def _message_from_json(payload: str) -> TransitionMessage:
    try:
        document = json.loads(payload)
        if document.get("type") != "order.transition":
            raise ValueError("unexpected message type")
        event_id = int(document["event_id"])
        if event_id <= 0:
            raise ValueError("event id must be positive")
        to_status = str(document["to_status"])
        if to_status not in ALL_STATUSES:
            raise ValueError("unknown status")
        from_status = document.get("from_status")
        if from_status is not None and from_status not in ALL_STATUSES:
            raise ValueError("unknown previous status")
        at = datetime.fromisoformat(str(document["at"]))
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timestamp must be aware")
        return TransitionMessage(
            event_id=event_id,
            order_id=uuid.UUID(str(document["order_id"])),
            shop_id=uuid.UUID(str(document["shop_id"])),
            from_status=from_status,
            to_status=to_status,
            at=at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid transition message") from exc
