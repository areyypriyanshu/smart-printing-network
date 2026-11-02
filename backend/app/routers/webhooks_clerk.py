"""The route the identity provider sends its events to.

The route is public, because a delivery carries no session: it comes
from the provider's servers and it is proved by its signature rather
than by a token. The signature is checked against the raw body, before
anything in the body is read.

What a delivery may change is narrow. It may synchronize the provider's
current profile and switch an account off. It may not change a role, link
a different account to this one, or switch an account on. Those are
decisions this application makes, and a delivery from a provider is not
allowed to make them.
"""

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db, storable_json
from app.deps import get_identity_reader
from app.errors import ProviderUnavailable, Unauthenticated
from app.gateways.identity.clerk_admin import (
    ClerkAdminClient,
    ClerkAdminError,
    ClerkUserNotFound,
)
from app.gateways.webhooks.svix import verify_signature
from app.models import User, WebhookEvent
from app.schemas.errors import ERROR_RESPONSES
from app.services.identity_service import sync_provider_profile

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


def _event_timestamp(document: dict[str, Any]) -> int | None:
    value = document.get("timestamp")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


@router.post("/clerk")
async def clerk_webhook(
    request: Request,
    svix_id: str | None = Header(default=None, alias="svix-id"),
    svix_timestamp: str | None = Header(default=None, alias="svix-timestamp"),
    svix_signature: str | None = Header(default=None, alias="svix-signature"),
    session: Session = Depends(get_db),
    reader: ClerkAdminClient = Depends(get_identity_reader),
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

    event_timestamp = _event_timestamp(document)
    if event_type in ("user.created", "user.updated") and event_timestamp is None:
        _record_ignored_event(session, svix_id, event_type, document)
        return {"status": "ignored"}

    # A delivery is acted on once. The provider retries a delivery it
    # does not get an answer for, and a delivery that is replayed is
    # still a valid signature, so the record of what has been seen is
    # what stops it being applied twice.
    event = session.get(WebhookEvent, svix_id)
    if event is not None and event.processed_at is not None:
        return {"status": "duplicate"}

    user = session.scalar(select(User).where(User.clerk_user_id == person_id))
    if user is None:
        # The account has not been created yet. Nothing to correct.
        _record_ignored_event(session, svix_id, event_type, document)
        return {"status": "ignored"}

    current_person = None
    provider_deleted = False
    if event_type in ("user.created", "user.updated"):
        # Clerk does not guarantee event ordering. Use the provider's
        # current profile instead of applying possibly stale event data.
        # Close the database transaction while waiting for the API.
        session.rollback()
        try:
            current_person = await run_in_threadpool(reader.get_user, person_id)
        except ClerkUserNotFound:
            # A late update after deletion is superseded, not transient.
            # Deactivate locally and record it so Clerk does not retry a
            # permanent 404 forever.
            provider_deleted = True
        except ClerkAdminError as exc:
            # Leave the delivery unrecorded so Clerk retries after a
            # transient provider failure.
            raise ProviderUnavailable(
                "The identity provider could not be reached. Try again in a moment."
            ) from exc
        if current_person is not None and current_person.id != person_id:
            raise ProviderUnavailable("The identity provider returned a different account")

    try:
        event = session.get(WebhookEvent, svix_id)
        if event is None:
            session.add(
                WebhookEvent(
                    event_id=svix_id,
                    provider=PROVIDER,
                    event_type=event_type,
                    payload=storable_json(document),
                )
            )
        else:
            event.provider = PROVIDER
            event.event_type = event_type
            event.payload = storable_json(document)
        # The event row and effect commit together. The uniqueness
        # constraint also makes simultaneous duplicate delivery safe.
        session.flush()
    except IntegrityError:
        session.rollback()
        return {"status": "duplicate"}

    # Re-read after the provider call and lock the row while applying it.
    user = session.scalar(select(User).where(User.clerk_user_id == person_id).with_for_update())
    if user is None:
        event = session.get(WebhookEvent, svix_id)
        if event is not None:
            event.processed_at = datetime.now(UTC)
        session.commit()
        return {"status": "ignored"}

    if provider_deleted or event_type in ("user.deleted", "user.banned"):
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
    elif current_person is not None:
        sync_provider_profile(
            session,
            user,
            current_person,
            event_timestamp=event_timestamp,
        )

    event = session.get(WebhookEvent, svix_id)
    if event is not None:
        event.processed_at = datetime.now(UTC)
    session.commit()
    return {"status": "ok"}


def _record_ignored_event(
    session: Session, event_id: str, event_type: str, document: dict[str, Any]
) -> None:
    """Deduplicate a valid delivery that has no local account to update."""
    try:
        session.add(
            WebhookEvent(
                event_id=event_id,
                provider=PROVIDER,
                event_type=event_type,
                payload=storable_json(document),
                processed_at=datetime.now(UTC),
            )
        )
        session.commit()
    except IntegrityError:
        session.rollback()
