"""The routes that turn an identity into an account.

There are two of them. One says who the caller is, and the other is
where a person says what they are here for: to print something, or to
run a shop.

Nothing here takes an address or a name from the browser. The provider
holds both, and it proved them, so they are read from the provider.
The body carries the one thing the provider cannot know, which is what
the person wants to do.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_identity, get_current_user, get_identity_reader
from app.errors import Conflict
from app.gateways.identity.base import VerifiedIdentity
from app.gateways.identity.clerk_admin import ClerkAdminClient
from app.models import User
from app.rate_limit import onboarding_limit
from app.schemas.identity import OnboardingRequest, UserResponse
from app.services import identity_service

router = APIRouter(tags=["identity"])


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    """The account the caller is.

    A caller whose token is good but who has not chosen yet has no
    account, and gets the refusal that says so. The front end reads
    that and sends them to the page that asks.
    """
    return user


@router.post(
    "/auth/onboarding",
    response_model=UserResponse,
    dependencies=[Depends(onboarding_limit(5, 60))],
)
def onboard(
    body: OnboardingRequest,
    session: Session = Depends(get_db),
    reader: ClerkAdminClient = Depends(get_identity_reader),
    identity: VerifiedIdentity = Depends(get_current_identity),
) -> User:
    """Create the account for a person who has just said what they want.

    The account is created once. A person who comes back to this page
    gets the account they already have, not a second one.
    """
    subject = identity.subject
    person = identity_service.read_person(reader, subject)

    existing = identity_service.find_by_subject(session, subject)
    if existing is not None:
        return existing

    if body.role == identity_service.VENDOR:
        if (
            body.shop_name is None
            or body.shop_address is None
            or body.latitude is None
            or body.longitude is None
        ):
            raise Conflict("A shop needs a name, an address and a place")
        user, _shop = identity_service.create_vendor_account(
            session,
            subject=subject,
            email=person.email,
            full_name=person.full_name,
            shop_name=body.shop_name,
            shop_address=body.shop_address,
            phone=body.phone,
            latitude=body.latitude,
            longitude=body.longitude,
        )
        return user

    return identity_service.create_account(
        session,
        subject=subject,
        email=person.email,
        full_name=person.full_name,
        role=identity_service.CUSTOMER,
    )
