"""The route the identity provider sends its events to.

The route is public, because a delivery carries no session: it comes
from the provider's servers and it is proved by its signature rather
than by a token. The signature is checked against the raw body, before
anything in the body is read.

What a delivery may change is narrow. It may correct the name on an
account and it may switch an account off. It may not change a role, it
may not link a different account to this one, and it may not switch an
account on. Those are decisions this application makes, and a delivery
from a provider is not allowed to make them.
"""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db, storable_json
from app.errors import Unauthenticated
from app.gateways.webhooks.svix import verify_signature
from app.models import User, WebhookEvent
from app.schemas.errors import ERROR_RESPONSES

# The route is public, so it has no session to be refused, but it
# can still be refused for a body that is too large or a request
# that is not valid, and it says so.
router = APIRouter(prefix="/webhooks", tags=["webhooks"], responses=ERROR_RESPONSES)

#: The name this application gives the provider in the inbox table,
#: where a delivery is recorded so that it is acted on once.
PROVIDER = "clerk"

#: The event types this application acts on. Everything else is
#: accepted and ignored, because the provider sends many events and a
#: delivery of an event this application does not use is not a failure.
IGNORED_EVENTS = frozenset(
    {
        "user.created",
        "user.updated",
        "user.deleted",
        "user.banned",
        "user.unbanned",
    }
)


def _event_type(document: dict[str, Any]) -> str:
    value = document.get("type")
    return value if isinstance(value, str) else ""


def _person_id(document: dict[str, Any]) -> str | None:
    data = document.get("data")
    if not isinstance(data, dict):
        return None
    value = data.get("id")
    return value if isinstance(value, str) and value else None


def _person_name(document: dict[str, Any]) -> str | None:
    data = document.get("data")
    if not isinstance(data, dict):
        return None
    parts = []
    for key in ("first_name", "last_name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return " ".join(parts) if parts else None


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    svix_id: str | None = Header(default=None, alias="svix-id"),
    svix_timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    svix_signature: str | None = Header(default=None, alias="svix-signature"),
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Take a delivery from the identity provider.

    A delivery that does not carry a signature this deployment accepts
    is refused. The check is on the raw body, byte for byte, because a
    body that has been parsed and put back together is not the body
    that was signed.
    """
    from app.config import get_settings

    body = await request.body()
    settings = get_settings()
    if not verify_signature(
        signing_secret=settings.clerk_webhook_signing_secret,
        message_id=svix_id,
        timestamp=svix_timestamp,
        signature=svix_signature,
        body=body,
    ):
        raise Unauthenticated("Invalid webhook signature")

    try:
        document = json.loads(body)
    except ValueError:
        return {"status": "ignored"}
    if not isinstance(document, dict):
        return {"status": "ignored"}

    event_type = _event_type(document)
    if event_type not in IGNORED_EVENTS:
        return {"status": "ignored"}

    person_id = _person_id(document)
    if person_id is None or svix_id is None:
        return {"status": "ignored"}

    # A delivery is acted on once. The provider retries a delivery it
    # does not get an answer for, and a delivery that is replayed is
    # still a valid signature, so the record of what has been seen is
    # what stops it being applied twice.
    event = session.get(WebhookEvent, svix_id)
    if event is not None and event.processed_at is not None:
        return {"status": "duplicate"}
    if event is None:
        try:
            session.add(
                WebhookEvent(
                    event_id=svix_id,
                    provider=PROVIDER,
                    event_type=event_type,
                    payload=storable_json(document),
                )
            )
            # Flushed, not committed: the record becomes durable
            # together with the effect, so a failure before the effect
            # rolls the delivery back instead of spending it, and the
            # provider's retry can still apply it.
            session.flush()
        except IntegrityError:
            session.rollback()
            return {"status": "duplicate"}

    user = session.scalar(select(User).where(User.clerk_user_id == person_id))
    if user is None:
        # The account has not been created yet. Nothing to correct.
        event = session.get(WebhookEvent, svix_id)
        if event is not None:
            event.processed_at = datetime.now(UTC)
        session.commit()
        return {"status": "ignored"}

    if event_type in ("user.deleted", "user.banned"):
        # The provider has taken the account away. This application
        # keeps the record, because the orders are tied to it, and
        # stops letting it in.
        #
        # It is never the other way round. The provider unblocking an
        # account does not switch it back on here, because this
        # application may have switched it off for a reason of its own
        # that the provider knows nothing about. Switching an account
        # back on is the team's decision, made in the admin area.
        user.is_active = False
    else:
        name = _person_name(document)
        if name:
            # A name from the provider is a name a person chose, and
            # the byte that cannot be stored in a text column carries
            # no meaning in it.
            user.full_name = name.replace("\x00", "")

    event = session.get(WebhookEvent, svix_id)
    if event is not None:
        event.processed_at = datetime.now(UTC)
    session.commit()
    return {"status": "ok"}
