"""Authorized WebSocket channels for the vendor board and customer orders."""

import asyncio
import json
import logging
import time
import uuid
from typing import Literal

from anyio import to_thread
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.domain.origin import origin_allowed
from app.errors import AppError, Forbidden, NotFound, Unauthenticated
from app.services.authorization_service import (
    active_user_for_subject,
    order_for_customer,
    shop_for_vendor,
)
from app.services.live_service import _Subscription

logger = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

Scope = Literal["vendor", "order"]
REAUTH_INTERVAL_SECONDS = 30.0
MAX_AUTH_FRAME_CHARS = 16_384
MAX_TOKEN_CHARS = 8192
MAX_AUTH_ATTEMPTS_PER_MINUTE = 10


@router.websocket("/ws/vendor")
async def vendor_live(websocket: WebSocket) -> None:
    await _serve(websocket, scope="vendor")


@router.websocket("/ws/orders/{order_id}")
async def order_live(websocket: WebSocket, order_id: uuid.UUID) -> None:
    await _serve(websocket, scope="order", order_id=order_id)


async def _serve(websocket: WebSocket, *, scope: Scope, order_id: uuid.UUID | None = None) -> None:
    client_host = websocket.client.host if websocket.client else "unknown"
    retry_after = websocket.app.state.rate_limiter.check(
        f"ws-auth:{client_host}", MAX_AUTH_ATTEMPTS_PER_MINUTE, 60
    )
    if retry_after is not None:
        await websocket.close(code=4429)
        return
    if not origin_allowed(websocket.headers.get("origin", ""), websocket.app.state.allowed_origins):
        await websocket.close(code=4403)
        return
    if not _supports_protocol(websocket):
        await websocket.close(code=4401)
        return
    token = await _receive_token(websocket)
    if token is None:
        await websocket.close(code=4401)
        return
    try:
        identity = await to_thread.run_sync(websocket.app.state.token_verifier.verify, token)
        channel = await to_thread.run_sync(_authorize, websocket, identity.subject, scope, order_id)
    except AppError as exc:
        await websocket.close(code=_close_code(exc))
        return
    except Exception:  # noqa: BLE001 - never expose an authorization failure detail
        logger.error("websocket authorization failed", exc_info=True)
        await websocket.close(code=1011)
        return

    subscription = websocket.app.state.event_hub.subscribe(channel, connection_key=client_host)
    if subscription is None:
        await websocket.close(code=4429)
        return
    try:
        await websocket.send_json({"type": "subscribed", "channel": channel})
        await _forward(
            websocket,
            subscription,
            token=token,
            scope=scope,
            order_id=order_id,
        )
    except WebSocketDisconnect:
        pass
    finally:
        websocket.app.state.event_hub.unsubscribe(subscription)


def _supports_protocol(websocket: WebSocket) -> bool:
    parts = [
        part.strip() for part in websocket.headers.get("sec-websocket-protocol", "").split(",")
    ]
    return "spn.v1" in parts


async def _receive_token(websocket: WebSocket) -> str | None:
    """Accept the application protocol, then read one bounded auth frame."""
    await websocket.accept(subprotocol="spn.v1")
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        if len(raw) > MAX_AUTH_FRAME_CHARS:
            return None
        message = json.loads(raw)
    except (TimeoutError, ValueError, TypeError, WebSocketDisconnect, json.JSONDecodeError):
        return None
    if not isinstance(message, dict) or message.get("type") != "authenticate":
        return None
    token = message.get("token")
    return token if isinstance(token, str) and 0 < len(token) <= MAX_TOKEN_CHARS else None


def _authorize(websocket: WebSocket, subject: str, scope: Scope, order_id: uuid.UUID | None) -> str:
    """Authorize once, then close the short database session before streaming."""
    with websocket.app.state.session_factory() as session:
        user = active_user_for_subject(session, subject)
        if scope == "vendor":
            return f"vendor:{shop_for_vendor(session, user).id}"
        if order_id is None:
            raise NotFound("Order not found")
        return f"order:{order_for_customer(session, user, order_id).id}"


def _close_code(error: AppError) -> int:
    if isinstance(error, Unauthenticated):
        return 4401
    if isinstance(error, Forbidden):
        return 4403
    if isinstance(error, NotFound):
        return 4404
    return 1011


async def _forward(
    websocket: WebSocket,
    subscription: _Subscription,
    *,
    token: str,
    scope: Scope,
    order_id: uuid.UUID | None,
) -> None:
    """Forward messages while watching disconnect, keepalive and reauthorization."""
    tasks: set[asyncio.Task[object]] = set()
    last_auth = time.monotonic()
    try:
        while True:
            if time.monotonic() - last_auth >= REAUTH_INTERVAL_SECONDS:
                identity = await to_thread.run_sync(
                    websocket.app.state.token_verifier.verify, token
                )
                await to_thread.run_sync(_authorize, websocket, identity.subject, scope, order_id)
                last_auth = time.monotonic()
            receive_task = asyncio.create_task(websocket.receive())
            event_task = asyncio.create_task(subscription.get())
            tasks = {receive_task, event_task}
            wait_seconds = max(
                0.0,
                min(25.0, REAUTH_INTERVAL_SECONDS - (time.monotonic() - last_auth)),
            )
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED, timeout=wait_seconds
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if not done:
                await websocket.send_json({"type": "ping"})
                continue
            if receive_task in done and not receive_task.cancelled():
                received = receive_task.result()
                if received["type"] == "websocket.disconnect":
                    return
                # Client messages are not part of this read-only protocol.
            if event_task in done and not event_task.cancelled():
                event = event_task.result()
                if event is None:
                    return
                await websocket.send_json(event)
    except asyncio.CancelledError:
        return
    except AppError as exc:
        await websocket.close(code=_close_code(exc))
    except Exception:  # noqa: BLE001 - the client gets a generic close only
        logger.error("websocket stream failed", exc_info=True)
        await websocket.close(code=1011)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
