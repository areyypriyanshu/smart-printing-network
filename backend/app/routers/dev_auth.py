"""The local way in, for the end to end suite.

The end to end suite has to run in continuous integration, offline and
the same way every time. It cannot sign in through the identity
provider, because that needs the network and a real account.

This route is the stand-in. It is switched on by a setting that is
refused in production, so a deployment that is not local cannot have
it, and it carries no password: the account it names is a test
account, and the only thing it proves is that the application reads a
session the way it always did.

The token it returns is read by the same verifier interface the real
one is, so the path through the application is the same path. The only
thing that is different is who signed the token.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import NotFound
from app.gateways.identity.fake import FakeTokenVerifier, dev_subject_for
from app.services import identity_service

router = APIRouter(prefix="/auth", tags=["auth"])


class DevSessionRequest(BaseModel):
    """Which account the suite wants to be signed in as."""

    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(default="End To End Customer", min_length=1, max_length=200)


class DevSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/dev-session", response_model=DevSessionResponse)
def dev_session(
    body: DevSessionRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> DevSessionResponse:
    """A session for an account the suite already has.

    The account has to exist. The suite creates it through the same
    route a person would, so that the account is a real one with a
    real role, and this route only signs it in.
    """
    settings = get_settings()
    if not settings.spn_dev_auth:
        raise NotFound("Account not found")

    verifier = request.app.state.token_verifier
    if not isinstance(verifier, FakeTokenVerifier):
        raise NotFound("Account not found")

    user = identity_service.find_by_email(session, body.email)
    if user is None:
        user = identity_service.create_account(
            session,
            subject=dev_subject_for(body.email),
            email=body.email,
            full_name=body.full_name,
            role=identity_service.CUSTOMER,
        )
    if user.clerk_user_id is None:
        raise NotFound("Account not found")

    return DevSessionResponse(access_token=verifier.issue(user.clerk_user_id))
