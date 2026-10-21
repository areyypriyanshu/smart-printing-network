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
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import Unauthenticated
from app.gateways.webhooks.svix import verify_signature
from app.models import User

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

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
    if person_id is None:
        return {"status": "ignored"}

    user = session.scalar(select(User).where(User.clerk_user_id == person_id))
    if user is None:
        # The account has not been created yet. Nothing to correct.
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
            user.full_name = name

    session.commit()
    return {"status": "ok"}
