"""Turning an identity into an account.

The identity provider says who someone is. These tests are about the
step after that, where the person says what they are here for and the
application makes the row.

The rules that matter here are that the address comes from the provider
and not from the browser, that the account is made exactly once, and
that the role is the one the person chose and never changes afterwards.
"""

from app.gateways.identity.clerk_admin import ClerkUser
from app.gateways.identity.fake import dev_subject_for
from app.models import Shop, User
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import create_user, identity_headers

ONBOARDING = "/api/v1/auth/onboarding"
ME = "/api/v1/me"
SUBJECT = "user_newcomer"


def _tell_the_provider_about(client: TestClient, subject: str, **details: str) -> None:
    """What the provider knows about the person."""
    reader = client.app.state.identity_reader
    reader.people[subject] = ClerkUser(
        id=subject,
        email=details.get("email", "newcomer@example.com"),
        full_name=details.get("full_name", "New Comer"),
        email_verified=True,
    )


def test_a_person_who_has_signed_in_has_no_account_yet(client: TestClient) -> None:
    """The account is made by the onboarding, not by the sign in.

    The answer says so, and it is not a refusal: the token is good and
    the person simply has to answer one question first. The front end
    reads the code and sends them to the page that asks.
    """
    response = client.get(ME, headers=identity_headers(client, SUBJECT))

    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "ACCOUNT_NOT_PROVISIONED"


def test_a_person_who_says_they_are_here_to_print_gets_an_account(
    client: TestClient, db_session: Session
) -> None:
    _tell_the_provider_about(client, SUBJECT)

    response = client.post(
        ONBOARDING, json={"role": "customer"}, headers=identity_headers(client, SUBJECT)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "customer"
    assert body["email"] == "newcomer@example.com"

    user = db_session.scalar(select(User).where(User.clerk_user_id == SUBJECT))
    assert user is not None
    assert user.role == "customer"


def test_a_person_who_says_they_run_a_shop_gets_a_shop(
    client: TestClient, db_session: Session
) -> None:
    _tell_the_provider_about(client, SUBJECT)

    response = client.post(
        ONBOARDING,
        json={
            "role": "vendor",
            "shop_name": "Corner Prints",
            "shop_address": "3 Example Street",
            "latitude": 22.5726,
            "longitude": 88.3639,
        },
        headers=identity_headers(client, SUBJECT),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "vendor"

    shop = db_session.scalar(select(Shop).where(Shop.owner_id == response.json()["id"]))
    assert shop is not None
    assert shop.name == "Corner Prints"


def test_a_shop_owner_without_a_shop_is_refused(client: TestClient) -> None:
    _tell_the_provider_about(client, SUBJECT)

    response = client.post(
        ONBOARDING, json={"role": "vendor"}, headers=identity_headers(client, SUBJECT)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_the_address_comes_from_the_provider_and_not_from_the_body(
    client: TestClient, db_session: Session
) -> None:
    """The body cannot put an address on the account.

    The provider proved the address, so the account carries the one the
    provider has. A body that offers a different one is ignored.
    """
    _tell_the_provider_about(client, SUBJECT, email="proved@example.com")

    response = client.post(
        ONBOARDING,
        json={"role": "customer", "email": "somebody-else@example.com"},
        headers=identity_headers(client, SUBJECT),
    )

    assert response.status_code == 200
    assert response.json()["email"] == "proved@example.com"

    user = db_session.scalar(select(User).where(User.clerk_user_id == SUBJECT))
    assert user is not None
    assert user.email == "proved@example.com"


def test_the_account_is_made_once(client: TestClient, db_session: Session) -> None:
    """Coming back to the page gives the account they already have."""
    _tell_the_provider_about(client, SUBJECT)

    first = client.post(
        ONBOARDING, json={"role": "customer"}, headers=identity_headers(client, SUBJECT)
    )
    second = client.post(
        ONBOARDING, json={"role": "customer"}, headers=identity_headers(client, SUBJECT)
    )

    assert first.json()["id"] == second.json()["id"]
    accounts = db_session.scalars(select(User).where(User.clerk_user_id == SUBJECT)).all()
    assert len(accounts) == 1


def test_the_role_does_not_change_after_the_account_is_made(
    client: TestClient, db_session: Session
) -> None:
    """One account, one role, for good.

    A customer who later decides to run a shop needs a separate
    account. Letting the role change would mean a shop's history
    belonged to a customer.
    """
    _tell_the_provider_about(client, SUBJECT)
    client.post(ONBOARDING, json={"role": "customer"}, headers=identity_headers(client, SUBJECT))

    response = client.post(
        ONBOARDING, json={"role": "vendor"}, headers=identity_headers(client, SUBJECT)
    )

    assert response.status_code == 200
    assert response.json()["role"] == "customer"
    user = db_session.scalar(select(User).where(User.clerk_user_id == SUBJECT))
    assert user is not None
    assert user.role == "customer"


def test_an_address_that_is_already_taken_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """Two accounts cannot have the same address.

    The second sign in would be a different person claiming the first
    one's address, and there is no way to tell them apart.
    """
    create_user(db_session, email="newcomer@example.com")
    _tell_the_provider_about(client, SUBJECT)

    response = client.post(
        ONBOARDING, json={"role": "customer"}, headers=identity_headers(client, SUBJECT)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_a_person_the_provider_does_not_know_is_not_a_gateway_error(
    client: TestClient,
) -> None:
    """A person who is not there is not the provider being down.

    The two are different: one says the account was removed, and the
    other says to try again in a moment. The provider answers a
    question about somebody it has never heard of with a 404, and that
    is not a fault in another server.
    """
    from app.gateways.identity.clerk_admin import ClerkUserNotFound

    def unknown(*args: object, **kwargs: object) -> None:
        raise ClerkUserNotFound("the identity provider does not know the person")

    reader = client.app.state.identity_reader
    original = reader.get_user
    reader.get_user = unknown  # type: ignore[method-assign]
    try:
        response = client.post(
            ONBOARDING,
            json={"role": "customer"},
            headers=identity_headers(client, SUBJECT),
        )
    finally:
        reader.get_user = original  # type: ignore[method-assign]

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_the_provider_being_unreachable_is_a_gateway_error(client: TestClient) -> None:
    """A fault in another server is a gateway error, not a refusal."""
    from app.gateways.identity.clerk_admin import ClerkAdminError

    def unreachable(*args: object, **kwargs: object) -> None:
        raise ClerkAdminError("the identity provider could not be reached")

    reader = client.app.state.identity_reader
    original = reader.get_user
    reader.get_user = unreachable  # type: ignore[method-assign]
    try:
        response = client.post(
            ONBOARDING,
            json={"role": "customer"},
            headers=identity_headers(client, SUBJECT),
        )
    finally:
        reader.get_user = original  # type: ignore[method-assign]

    assert response.status_code == 502


def test_a_caller_with_no_token_cannot_reach_the_onboarding(client: TestClient) -> None:
    response = client.post(ONBOARDING, json={"role": "customer"})

    assert response.status_code == 401


def test_a_caller_who_is_not_signed_in_has_no_account(client: TestClient) -> None:
    response = client.get(ME)

    assert response.status_code == 401


def test_the_account_is_answered_once_it_exists(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="known@example.com", role="customer")

    response = client.get(
        ME, headers=identity_headers(client, dev_subject_for("known@example.com"))
    )

    assert response.status_code == 200
    assert response.json()["email"] == "known@example.com"


def test_an_account_that_has_been_switched_off_is_refused(
    client: TestClient, db_session: Session
) -> None:
    """A token that is good but names a closed account is not enough."""
    user = create_user(db_session, email="closed@example.com", role="customer")
    user.is_active = False
    db_session.commit()

    response = client.get(ME, headers=identity_headers(client, user.clerk_user_id or ""))

    assert response.status_code == 401
