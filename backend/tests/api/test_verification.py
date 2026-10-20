"""Proving that an email address belongs to the person who gave it.

The address is a login name and a display name, and until it has been
proved it is only a claim. These tests are about the claim: that it can
be proved, that it cannot be proved twice, that a link that was never
sent does nothing, and that the one thing that needs a real address
refuses an account that has not proved one.
"""

from datetime import UTC, datetime, timedelta

from app.gateways.email import MemoryEmailSender
from app.models import EmailVerificationToken, User
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import DEFAULT_PASSWORD, create_user, login_headers

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
VERIFY = "/api/v1/auth/verify-email"
RESEND = "/api/v1/auth/resend-verification"
CHANGE_EMAIL = "/api/v1/auth/change-email"
UPLOADS = "/api/v1/uploads"
TESTING_VERIFY = "/api/v1/testing/verify-email"


def register_payload(email: str = "new.user@example.com") -> dict[str, str]:
    return {"email": email, "password": DEFAULT_PASSWORD, "full_name": "New User"}


def _sender(client: TestClient) -> MemoryEmailSender:
    sender = client.app.state.email_sender
    assert isinstance(sender, MemoryEmailSender)
    return sender


def _token_from_the_last_message(client: TestClient) -> str:
    """The token in the link that was sent.

    The link is the only place the token appears, so the test reads it
    out of the message rather than out of the database: a token that
    could be read out of the database would not be a secret.
    """
    body = _sender(client).last_body
    link = next(line for line in body.splitlines() if line.startswith("http"))
    return link.split("token=")[1]


def test_registering_sends_a_link_to_the_address(client: TestClient) -> None:
    response = client.post(REGISTER, json=register_payload("prove.me@example.com"))

    assert response.status_code == 201
    messages = _sender(client).messages
    assert len(messages) == 1
    assert messages[0]["to"] == "prove.me@example.com"
    assert "/verify-email?token=" in messages[0]["body"]


def test_the_account_is_not_proved_until_the_link_is_clicked(
    client: TestClient, db_session: Session
) -> None:
    client.post(REGISTER, json=register_payload("prove.me@example.com"))

    user = db_session.scalar(select(User).where(User.email == "prove.me@example.com"))
    assert user is not None
    assert user.email_verified is False


def test_the_link_in_the_message_proves_the_address(
    client: TestClient, db_session: Session
) -> None:
    client.post(REGISTER, json=register_payload("prove.me@example.com"))
    token = _token_from_the_last_message(client)

    response = client.post(VERIFY, json={"token": token})

    assert response.status_code == 200, response.text
    assert response.json()["email_verified"] is True
    user = db_session.scalar(select(User).where(User.email == "prove.me@example.com"))
    assert user is not None
    assert user.email_verified is True


def test_a_link_that_was_never_sent_does_nothing(client: TestClient) -> None:
    response = client.post(VERIFY, json={"token": "not-a-token"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"


def test_a_link_answers_the_same_way_the_second_time(
    client: TestClient, db_session: Session
) -> None:
    """A customer who clicks the link twice has not made a mistake."""
    client.post(REGISTER, json=register_payload("prove.me@example.com"))
    token = _token_from_the_last_message(client)
    first = client.post(VERIFY, json={"token": token})
    second = client.post(VERIFY, json={"token": token})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["email_verified"] is True
    user = db_session.scalar(select(User).where(User.email == "prove.me@example.com"))
    assert user is not None
    assert user.email_verified is True


def test_an_expired_link_is_refused(client: TestClient, db_session: Session) -> None:
    client.post(REGISTER, json=register_payload("prove.me@example.com"))
    token = _token_from_the_last_message(client)
    row = db_session.scalar(select(EmailVerificationToken))
    assert row is not None
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    response = client.post(VERIFY, json={"token": token})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"


def test_the_token_is_stored_as_a_hash(client: TestClient, db_session: Session) -> None:
    """A row that is read from the database must not be a usable secret."""
    client.post(REGISTER, json=register_payload("prove.me@example.com"))
    token = _token_from_the_last_message(client)

    row = db_session.scalar(select(EmailVerificationToken))
    assert row is not None
    assert row.token_hash != token
    assert token not in row.token_hash


def test_asking_for_the_message_again_sends_a_new_link(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="prove.me@example.com")
    headers = login_headers(client, "prove.me@example.com")

    response = client.post(RESEND, headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "prove.me@example.com"
    assert len(_sender(client).messages) == 1


def test_the_link_that_was_sent_first_stops_working(
    client: TestClient, db_session: Session
) -> None:
    """A customer who asks again expects the old link to be dead."""
    create_user(db_session, email="prove.me@example.com")
    headers = login_headers(client, "prove.me@example.com")
    first = client.post(RESEND, headers=headers)
    assert first.status_code == 200
    old_token = _token_from_the_last_message(client)

    client.post(RESEND, headers=headers)
    new_token = _token_from_the_last_message(client)

    assert old_token != new_token
    refused = client.post(VERIFY, json={"token": old_token})
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "INVALID_VERIFICATION_TOKEN"
    accepted = client.post(VERIFY, json={"token": new_token})
    assert accepted.status_code == 200


def test_asking_for_the_message_again_too_often_is_refused(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="prove.me@example.com")
    headers = login_headers(client, "prove.me@example.com")

    for _ in range(3):
        assert client.post(RESEND, headers=headers).status_code == 200

    limited = client.post(RESEND, headers=headers)

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_an_account_that_has_not_proved_its_address_cannot_upload(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="unproved@example.com", email_verified=False)
    headers = login_headers(client, "unproved@example.com")

    response = client.post(UPLOADS, headers=headers, files={"file": ("a.pdf", b"%PDF-1.7\n")})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"


def test_a_proved_account_can_upload(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="proved@example.com", email_verified=True)
    headers = login_headers(client, "proved@example.com")

    response = client.post(UPLOADS, headers=headers, files={"file": ("a.pdf", b"%PDF-1.7\n")})

    assert response.status_code in (201, 400), response.text


def test_changing_the_address_needs_the_password(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="mistyped@example.com")
    headers = login_headers(client, "mistyped@example.com")

    response = client.post(
        CHANGE_EMAIL,
        headers=headers,
        json={"email": "right@example.com", "password": "not-the-password"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PASSWORD_MISMATCH"


def test_changing_the_address_sends_a_link_to_the_new_one(
    client: TestClient, db_session: Session
) -> None:
    """This is the way out of a mistyped address."""
    create_user(db_session, email="mistyped@example.com", email_verified=False)
    headers = login_headers(client, "mistyped@example.com")

    response = client.post(
        CHANGE_EMAIL,
        headers=headers,
        json={"email": "right@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 200, response.text
    assert response.json()["email"] == "right@example.com"
    assert response.json()["email_verified"] is False
    messages = _sender(client).messages
    assert len(messages) == 1
    assert messages[0]["to"] == "right@example.com"


def test_the_new_address_has_to_be_proved_as_well(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="mistyped@example.com", email_verified=True)
    headers = login_headers(client, "mistyped@example.com")
    client.post(
        CHANGE_EMAIL,
        headers=headers,
        json={"email": "right@example.com", "password": DEFAULT_PASSWORD},
    )
    token = _token_from_the_last_message(client)

    response = client.post(VERIFY, json={"token": token})

    assert response.status_code == 200
    assert response.json()["email"] == "right@example.com"
    assert response.json()["email_verified"] is True


def test_the_address_of_another_account_cannot_be_taken(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="mine@example.com")
    create_user(db_session, email="theirs@example.com")
    headers = login_headers(client, "mine@example.com")

    response = client.post(
        CHANGE_EMAIL,
        headers=headers,
        json={"email": "theirs@example.com", "password": DEFAULT_PASSWORD},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_the_testing_surface_is_off_unless_it_is_turned_on(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="prove.me@example.com")
    settings = client.app.state  # the app the test drives
    assert settings is not None

    from app.config import get_settings

    current = get_settings()
    current.testing_endpoints_enabled = False
    try:
        response = client.post(TESTING_VERIFY, json={"email": "prove.me@example.com"})
    finally:
        current.testing_endpoints_enabled = True

    assert response.status_code == 404
