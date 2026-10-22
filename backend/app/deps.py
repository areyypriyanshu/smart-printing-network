from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AccountNotProvisioned, Forbidden, NotFound, Unauthenticated
from app.gateways.email import EmailSender
from app.gateways.geocoding import Geocoder
from app.gateways.identity import TokenVerifier, VerifiedIdentity
from app.gateways.identity.clerk_admin import ClerkAdminClient
from app.gateways.payments import PaymentGatewayRouter
from app.gateways.storage import Storage
from app.models import Shop, User
from app.services import identity_service

_bearer = HTTPBearer(auto_error=False)


def get_token_verifier(request: Request) -> TokenVerifier:
    """The verifier this deployment uses to read a token."""
    verifier: TokenVerifier = request.app.state.token_verifier
    return verifier


def get_identity_reader(request: Request) -> ClerkAdminClient:
    """The reader this deployment uses to ask the provider about a person."""
    reader: ClerkAdminClient = request.app.state.identity_reader
    return reader


def get_current_identity(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> VerifiedIdentity:
    """Who the caller says they are, with no local account behind it yet.

    This is what the route that creates the account uses. A person who
    has signed in but has not chosen yet has a good token and no row,
    and asking for the row would refuse them for the very thing they
    came to do.
    """
    if credentials is None:
        raise Unauthenticated("Authentication required")
    return verifier.verify(credentials.credentials)


def get_current_user(
    identity: VerifiedIdentity = Depends(get_current_identity),
    session: Session = Depends(get_db),
) -> User:
    """The caller, if the token they presented names one.

    The token says who they are. The role comes from the database, and
    so does whether the account is allowed in: a token that names an
    account that has been switched off is refused here even though the
    token itself is perfectly good.
    """
    user = identity_service.find_by_subject(session, identity.subject)
    if user is None:
        # The token is good and the person has signed in, but they have
        # not said what they are here for, so there is no account yet.
        # The front end reads this and sends them to the page that asks.
        raise AccountNotProvisioned(
            "This account has not been set up yet. Choose what you are here for."
        )
    if not user.is_active:
        raise Unauthenticated("Authentication required")
    return user


def get_provisioned_user(
    user: User = Depends(get_current_user),
) -> User:
    """The caller, once they have said what they are here for.

    A person who has signed in but has not chosen yet has no local
    account, and the request that needs one is answered with a refusal
    that says so, so that the front end can send them to the page that
    asks.
    """
    return user


def require_role(*roles: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise Forbidden("Your role cannot perform this action")
        return user

    return dependency


_vendor_only = require_role("vendor")
_customer_only = require_role("customer")


def get_customer(user: User = Depends(_customer_only)) -> User:
    return user


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def get_email_sender(request: Request) -> EmailSender:
    """The sender the application uses.

    It is on the application rather than built per request, because
    building it opens no connection: the connection is opened when a
    message is sent and closed again straight away.
    """
    sender: EmailSender = request.app.state.email_sender
    return sender


def get_geocoder(request: Request) -> Geocoder | None:
    """The geocoder this deployment uses, if it has one.

    There is no key, there is no geocoder, and the caller has to cope
    with that: a shop owner types the coordinates of their shop, and a
    customer who cannot share a location sees the whole list.
    """
    geocoder: Geocoder | None = request.app.state.geocoder
    return geocoder


def get_attribution(request: Request) -> str | None:
    """What has to be shown when the provider's data is shown.

    OpenStreetMap asks for its attribution to be displayed wherever its
    data is displayed, and this is where the answer comes from: the
    provider that is actually in use.
    """
    geocoder: Geocoder | None = request.app.state.geocoder
    return geocoder.attribution if geocoder is not None else None


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_db),
    verifier: TokenVerifier = Depends(get_token_verifier),
) -> User | None:
    """The caller, if there is one.

    Some routes are for everybody and behave differently for a signed in
    caller. The list of shops is one: it is the same list either way,
    and the only thing that changes is whether the signed in caller can
    see the shop they own.
    """
    if credentials is None:
        return None
    try:
        identity = verifier.verify(credentials.credentials)
    except Unauthenticated:
        return None
    user = identity_service.find_by_subject(session, identity.subject)
    if user is None or not user.is_active:
        return None
    return user


def get_payment_gateway(request: Request) -> PaymentGatewayRouter:
    """The gateway the application uses: the online provider and cash.

    It is the concrete router rather than the interface because the local
    simulate-payment endpoint has to sign a body the way the fake provider
    does, and only the router knows which implementation is in use.
    """
    gateway: PaymentGatewayRouter = request.app.state.payment_gateway
    return gateway


def get_current_shop(
    user: User = Depends(_vendor_only),
    session: Session = Depends(get_db),
) -> Shop:
    shop = session.scalar(select(Shop).where(Shop.owner_id == user.id))
    if shop is None:
        raise NotFound("Shop not found")
    return shop
