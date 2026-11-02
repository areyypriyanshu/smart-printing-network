"""The route the identity provider sends its events to.

The route is public, so the signature is the only thing that makes a
delivery worth reading. These tests are about what a delivery is allowed
to change once it has been proved.
"""

import json
import time

from app.config import get_settings
from app.gateways.identity.clerk_admin import ClerkAdminError, ClerkUser, ClerkUserNotFound
from app.gateways.webhooks.svix import expected_signature
from app.models import WebhookEvent
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
    body.setdefault("timestamp", int(time.time() * 1000))
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


def _provider_person(
    client: TestClient,
    subject: str,
    *,
    email: str,
    full_name: str,
    email_verified: bool,
    updated_at: int = 0,
) -> None:
    reader = client.app.state.identity_reader
    reader.people[subject] = ClerkUser(
        id=subject,
        email=email,
        full_name=full_name,
        email_verified=email_verified,
        updated_at=updated_at,
    )


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
    _provider_person(
        client,
        user.clerk_user_id or "",
        email=user.email,
        full_name="Fresh Name",
        email_verified=True,
    )
    raw, headers = _delivery(
        _person(user.clerk_user_id or "", first_name="Stale", last_name="Name")
    )

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.full_name == "Fresh Name"


def test_a_user_update_syncs_the_current_primary_email_and_verification(
    client: TestClient, db_session: Session
) -> None:
    user = create_user(
        db_session,
        email="old-address@example.com",
        full_name="Old Name",
        email_verified=False,
    )
    subject = user.clerk_user_id or ""
    _provider_person(
        client,
        subject,
        email="new-address@example.com",
        full_name="Current Name",
        email_verified=True,
    )
    raw, headers = _delivery(
        _person(subject, first_name="Old Event", last_name="Name"), message_id="msg_email"
    )

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.email == "new-address@example.com"
    assert user.full_name == "Current Name"
    assert user.email_verified is True


def test_a_temporary_provider_failure_leaves_the_webhook_unprocessed(
    client_that_reports_failures: TestClient, db_session: Session
) -> None:
    user = create_user(db_session, email="retry@example.com", email_verified=False)
    reader = client_that_reports_failures.app.state.identity_reader

    def unavailable(_subject: str) -> ClerkUser:
        raise ClerkAdminError("provider unavailable")

    reader.get_user = unavailable  # type: ignore[method-assign]
    raw, headers = _delivery(_person(user.clerk_user_id or ""), message_id="msg_provider_retry")

    response = client_that_reports_failures.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code in {502, 503}
    assert db_session.get(WebhookEvent, "msg_provider_retry") is None


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
    _provider_person(
        client,
        user.clerk_user_id or "",
        email=user.email,
        full_name="Twice Name",
        email_verified=True,
    )
    raw, headers = _delivery(_person(user.clerk_user_id or "", first_name="Twice"))

    first = client.post(WEBHOOK, content=raw, headers=headers)
    second = client.post(WEBHOOK, content=raw, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    db_session.refresh(user)
    assert user.full_name == "Twice Name"


def test_a_delivery_is_acted_on_once(client: TestClient, db_session: Session) -> None:
    """The provider retries a delivery it does not get an answer for.

    A delivery that arrives twice is still a valid signature, so the
    record of what has been seen is what stops it being applied twice.
    """
    subject = "user_once"
    user = create_user(db_session, email="once@example.com", role="customer")
    user.clerk_user_id = subject
    db_session.commit()
    _provider_person(
        client,
        subject,
        email=user.email,
        full_name="Once Name",
        email_verified=True,
    )

    body = {"type": "user.updated", "data": {"id": subject, "first_name": "Once"}}
    raw, headers = _delivery(body, message_id="msg_once")

    first = client.post(WEBHOOK, content=raw, headers=headers)
    second = client.post(WEBHOOK, content=raw, headers=headers)

    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"


def test_a_replayed_delivery_does_not_set_an_older_name(
    client: TestClient, db_session: Session
) -> None:
    """A delivery that is replayed is a delivery from the past.

    The name on the account is the newer one, and a replay must not put
    the older one back.
    """
    subject = "user_replay"
    user = create_user(db_session, email="replay@example.com", role="customer")
    user.clerk_user_id = subject
    user.full_name = "Newer"
    db_session.commit()
    _provider_person(
        client,
        subject,
        email=user.email,
        full_name="Newer",
        email_verified=True,
    )

    old, old_headers = _delivery(
        {"type": "user.updated", "data": {"id": subject, "first_name": "Older"}},
        message_id="msg_old",
    )
    new, new_headers = _delivery(
        {"type": "user.updated", "data": {"id": subject, "first_name": "Newer"}},
        message_id="msg_new",
    )

    assert client.post(WEBHOOK, content=old, headers=old_headers).status_code == 200
    assert client.post(WEBHOOK, content=new, headers=new_headers).status_code == 200
    # The older delivery, sent again.
    replay = client.post(WEBHOOK, content=old, headers=old_headers)

    assert replay.status_code == 200
    assert replay.json()["status"] == "duplicate"
    db_session.expire_all()
    assert db_session.get(type(user), user.id).full_name == "Newer"


def test_a_late_profile_response_cannot_restore_an_older_verification_state(
    client: TestClient, db_session: Session
) -> None:
    subject = "user_profile_version"
    user = create_user(db_session, email="profile-version@example.com", role="customer")
    user.clerk_user_id = subject
    db_session.commit()

    _provider_person(
        client,
        subject,
        email=user.email,
        full_name="Current Profile",
        email_verified=False,
        updated_at=2000,
    )
    newer, newer_headers = _delivery(
        {
            "type": "user.updated",
            "timestamp": 3000,
            "data": {"id": subject},
        },
        message_id="msg_profile_newer",
    )
    assert client.post(WEBHOOK, content=newer, headers=newer_headers).status_code == 200

    # Simulate an earlier provider response finishing after the current
    # response. Its profile version must not undo the newer result.
    _provider_person(
        client,
        subject,
        email=user.email,
        full_name="Stale Verified Profile",
        email_verified=True,
        updated_at=1000,
    )
    older, older_headers = _delivery(
        {
            "type": "user.updated",
            "timestamp": 2000,
            "data": {"id": subject},
        },
        message_id="msg_profile_older",
    )
    assert client.post(WEBHOOK, content=older, headers=older_headers).status_code == 200

    db_session.refresh(user)
    assert user.email_verified is False
    assert user.full_name == "Current Profile"
    assert user.clerk_profile_updated_at == 2000


def test_an_update_arriving_after_provider_deletion_is_recorded_and_deactivates(
    client: TestClient, db_session: Session, monkeypatch
) -> None:
    subject = "user_deleted_before_update"
    user = create_user(db_session, email="deleted-before-update@example.com", role="customer")
    user.clerk_user_id = subject
    db_session.commit()

    def deleted(_subject: str) -> ClerkUser:
        raise ClerkUserNotFound("The identity provider no longer has this account")

    monkeypatch.setattr(client.app.state.identity_reader, "get_user", deleted)
    raw, headers = _delivery(
        {"type": "user.updated", "data": {"id": subject}},
        message_id="msg_update_after_delete",
    )

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.refresh(user)
    assert user.is_active is False
    event = db_session.get(WebhookEvent, "msg_update_after_delete")
    assert event is not None
    assert event.processed_at is not None
    replay = client.post(WEBHOOK, content=raw, headers=headers)
    assert replay.json()["status"] == "duplicate"


def test_a_name_the_database_cannot_hold_does_not_stop_the_delivery(
    client: TestClient, db_session: Session
) -> None:
    """The byte that cannot be stored carries no meaning in a name."""
    subject = "user_nul"
    user = create_user(db_session, email="nul@example.com", role="customer")
    user.clerk_user_id = subject
    db_session.commit()
    _provider_person(
        client,
        subject,
        email=user.email,
        full_name="Na\x00me",
        email_verified=True,
    )

    body = {"type": "user.updated", "data": {"id": subject, "first_name": "Na\u0000me"}}
    raw, headers = _delivery(body, message_id="msg_nul")

    response = client.post(WEBHOOK, content=raw, headers=headers)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(type(user), user.id).full_name == "Name"
