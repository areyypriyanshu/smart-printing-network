"""The route the identity provider sends its events to.

The route is public, so the signature is the only thing that makes a
delivery worth reading. These tests are about what a delivery is allowed
to change once it has been proved.
"""

import json
import time

from app.config import get_settings
from app.gateways.webhooks.svix import expected_signature
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import create_user

WEBHOOK = "/api/v1/webhooks/clerk"


def _secret() -> str:
    """The key this deployment accepts deliveries signed with.

    It is the configured one rather than one the test makes up, so that
    the test proves the route agrees with the configuration and not
    merely that it agrees with itself.
    """
    return get_settings().clerk_webhook_signing_secret


def _delivery(
    body: dict[str, object], *, message_id: str = "msg_1", timestamp: str | None = None
) -> tuple[bytes, dict[str, str]]:
    """The body and the headers of a delivery that the provider signed."""
    raw = json.dumps(body).encode()
    stamp = timestamp if timestamp is not None else str(int(time.time()))
    signature = expected_signature(
        signing_secret=_secret(), message_id=message_id, timestamp=stamp, body=raw
    )
    return raw, {
        "svix-id": message_id,
        "svix-timestamp": stamp,
        "svix-signature": f"v1,{signature}",
    }


def _person(subject: str, **details: str) -> dict[str, object]:
    return {
        "data": {
            "id": subject,
            "first_name": details.get("first_name", "New"),
            "last_name": details.get("last_name", "Name"),
        },
        "object": "event",
        "type": details.get("type", "user.updated"),
        "timestamp": int(time.time() * 1000),
    }


def test_a_delivery_with_no_signature_is_refused(client: TestClient) -> None:
    response = client.post(WEBHOOK, json={"type": "user.updated", "data": {"id": "user_x"}})

    assert response.status_code == 401


def test_a_delivery_signed_with_the_wrong_key_is_refused(client: TestClient) -> None:
    raw, headers = _delivery(_person("user_x"))
    headers["svix-signature"] = "v1," + "A" * 43 + "="

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 401


def test_a_delivery_whose_body_was_changed_is_refused(client: TestClient) -> None:
    raw, headers = _delivery(_person("user_x"))
    changed = raw.replace(b"New", b"Old")

    response = client.post(WEBHOOK, content=changed, headers=headers)

    assert response.status_code == 401


def test_a_delivery_from_long_ago_is_refused(client: TestClient) -> None:
    """A captured delivery cannot be sent again later."""
    raw, headers = _delivery(_person("user_x"), timestamp=str(int(time.time()) - 3600))

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 401


def test_a_delivery_that_the_provider_signed_is_accepted(client: TestClient) -> None:
    """A delivery with a good signature is read rather than refused."""
    raw, headers = _delivery(_person("user_x"))

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    # The account does not exist, so there is nothing to correct, and
    # the delivery is ignored rather than refused.
    assert response.json() == {"status": "ignored"}


def test_a_delivery_corrects_the_name_on_the_account(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(db_session, email="named@example.com", full_name="Old Name")
    raw, headers = _delivery(
        _person(user.clerk_user_id or "", first_name="Fresh", last_name="Name")
    )

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.full_name == "Fresh Name"


def test_a_ban_switches_the_account_off(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="banned@example.com")
    raw, headers = _delivery(_person(user.clerk_user_id or "", type="user.banned"))

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.is_active is False


def test_an_unban_does_not_switch_the_account_back_on(
    client: TestClient, db_session: Session
) -> None:
    """The provider does not know why this application closed an account.

    Switching an account back on is the team's decision, made in the
    admin area, and not something a delivery may do.
    """
    user = create_user(db_session, email="closed@example.com")
    user.is_active = False
    db_session.commit()
    raw, headers = _delivery(_person(user.clerk_user_id or "", type="user.unbanned"))

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.is_active is False


def test_a_delivery_cannot_change_the_role(client: TestClient, db_session: Session) -> None:
    """The role is this application's decision, not the provider's."""
    user = create_user(db_session, email="customer@example.com", role="customer")
    body = _person(user.clerk_user_id or "")
    body["data"]["role"] = "admin"
    raw, headers = _delivery(body)

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.role == "customer"


def test_a_delivery_for_an_account_that_does_not_exist_is_ignored(
    client: TestClient, db_session: Session
) -> None:
    raw, headers = _delivery(_person("user_never_signed_in"))

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_the_same_delivery_twice_changes_nothing_new(
    client: TestClient, db_session: Session
) -> None:
    """Deliveries come more than once, and that has to be harmless."""
    user = create_user(db_session, email="twice@example.com", full_name="Old")
    raw, headers = _delivery(_person(user.clerk_user_id or "", first_name="Twice"))

    first = client.post(WEBHOOK, content=raw, headers=headers)
    second = client.post(WEBHOOK, content=raw, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    db_session.refresh(user)
    assert user.full_name == "Twice Name"
