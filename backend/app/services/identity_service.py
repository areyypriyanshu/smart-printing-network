"""Finding and creating the local account behind an identity.

The identity provider says who someone is. This module is where that
answer becomes a row in this application's database, and where the
row's role is decided.

Two rules hold everywhere in here. The role is read from the database
and never from the token, because a token is something the caller
presents and a role is a thing the application decides. And the local
row is created exactly once, in one place, so that there is never a
question of which of two paths made it.
"""

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import Conflict, EmailTaken, NotFound, ProviderUnavailable
from app.gateways.identity.clerk_admin import (
    ClerkAdminClient,
    ClerkAdminError,
    ClerkUser,
    ClerkUserNotFound,
)
from app.models import Shop, User

#: The role a person has when they come here to print something.
CUSTOMER = "customer"
#: The role a person has when they come here to run a shop.
VENDOR = "vendor"


def find_by_subject(session: Session, subject: str) -> User | None:
    """The account the provider's identifier names, if there is one."""
    if not subject:
        return None
    return session.scalar(select(User).where(User.clerk_user_id == subject))


def find_by_email(session: Session, email: str) -> User | None:
    """The account with this address, if there is one."""
    return session.scalar(select(User).where(User.email == email))


def create_account(
    session: Session,
    *,
    subject: str,
    email: str,
    full_name: str,
    role: str,
) -> User:
    """The account for a person who has just chosen what they are here for.

    The provider's identifier is stored, so that the next request finds
    this row by the subject in the token rather than by the address.

    The address is unique. An address that is already on an account
    cannot be put on a second one, because the second sign in would be
    a different person claiming the first one's address, and there is
    no way to tell them apart.
    """
    if role not in (CUSTOMER, VENDOR):
        raise Conflict("That is not a role this application has")
    existing = find_by_subject(session, subject)
    if existing is not None:
        return existing
    if find_by_email(session, email) is not None:
        raise Conflict("An account already uses that email address")

    user = User(
        email=email,
        clerk_user_id=subject,
        full_name=full_name,
        role=role,
        is_active=True,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        # Two requests for the same address at the same time both find
        # that the address is free, and one of them loses. That is a
        # conflict and not a fault, and the answer says so.
        session.rollback()
        raise Conflict("An account already uses that email address") from exc
    return user


def create_vendor_account(
    session: Session,
    *,
    subject: str,
    email: str,
    full_name: str,
    shop_name: str,
    shop_address: str,
    phone: str | None,
    latitude: float,
    longitude: float,
) -> tuple[User, Shop]:
    """The account and the shop for a person who runs a print shop.

    The shop is not published until the team approves it, which is the
    same rule as it has always been: an account can run a shop before
    anybody has looked at it.
    """
    user = create_account(session, subject=subject, email=email, full_name=full_name, role=VENDOR)
    if user.role != VENDOR:
        raise Conflict("That account is not a shop owner")
    # The shop needs the owner's id, so the user row is flushed before
    # the shop is built. That flush is where the unique email constraint
    # is hit, so it has to sit inside the same guard as the commit.
    # Otherwise a duplicate email escapes as a 500 instead of the 409
    # the API promises.
    try:
        session.flush()
        shop = Shop(
            owner_id=user.id,
            name=shop_name,
            address=shop_address,
            phone=phone,
            location=WKTElement(f"POINT({longitude} {latitude})", srid=4326),
        )
        session.add(shop)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailTaken("An account with this email already exists") from exc
    return user, shop


def read_person(reader: ClerkAdminClient, subject: str) -> ClerkUser:
    """What the provider knows about the person behind a subject.

    It is the provider's own answer, read from the provider's own API,
    so the address on the local account is the address the provider has
    proved rather than one the browser offered.
    """
    try:
        return reader.get_user(subject)
    except ClerkUserNotFound as exc:
        raise NotFound("That account no longer exists") from exc
    except ClerkAdminError as exc:
        raise ProviderUnavailable(
            "The identity provider could not be reached. Try again in a moment."
        ) from exc
