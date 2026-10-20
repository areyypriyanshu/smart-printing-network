import hashlib

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.deps import get_current_user, get_email_sender
from app.errors import NotFound, Unauthenticated
from app.gateways.email import EmailSender
from app.models import User
from app.rate_limit import account_rate_limit, registration_limit, user_rate_limit
from app.schemas.auth import (
    AccessTokenResponse,
    ChangeEmailRequest,
    LoginRequest,
    RegisterRequest,
    RegisterVendorRequest,
    TestingVerifyEmailRequest,
    UserResponse,
    VerificationSentResponse,
    VerifyEmailRequest,
)
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.shop import VendorRegistrationResponse
from app.services import auth_service, shop_service, verification_service

router = APIRouter(tags=["auth"], responses=ERROR_RESPONSES)


def _email_from_body(raw: bytes) -> str | None:
    """The address a request body carries, if it carries one.

    Both the registration body and the login body carry an address, and
    either one may be what arrived, so both are tried. The body is
    validated on the way, which means an address that is not one is
    never used in a query.
    """
    for model in (RegisterRequest, LoginRequest):
        try:
            payload = model.model_validate_json(raw)
        except ValueError:
            continue
        return str(payload.email)
    return None


def _account_key(session: Session, email: str) -> str:
    """The rate-limit key for one account, however the address is spelled.

    The key is the account id the database resolves, so two spellings of one
    address cannot occupy two rate-limit buckets. An address that does not
    exist has no id, so it is keyed by a hash of the address itself: the
    same unknown address still shares one bucket, and a different one gets
    its own.
    """
    user_id = session.scalar(select(User.id).where(User.email == email))
    if user_id is not None:
        return f"account:{user_id}"
    return "unknown:" + hashlib.sha256(email.lower().encode()).hexdigest()


def _account_from_request(request: Request) -> str:
    """The account a request is trying to reach.

    The body has already been read by the time this runs, so it is read
    from the request's cache rather than from the stream. The key comes
    from the account the database resolves, not from the spelling the
    client sent.
    """
    try:
        raw = request._body  # noqa: SLF001
    except AttributeError:
        return "unknown"
    email = _email_from_body(raw)
    if email is None:
        return "unknown"
    with SessionLocal() as session:
        return _account_key(session, email)


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    dependencies=[Depends(registration_limit(_account_from_request))],
)
def register(
    body: RegisterRequest,
    session: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> User:
    user = auth_service.register_customer(
        session, email=str(body.email), password=body.password, full_name=body.full_name
    )
    # The account exists whether or not the message about it can be
    # sent, so the message is sent after the account is made and its
    # failure does not undo the account.
    verification_service.send_verification(session, sender, get_settings(), user=user)
    return user


@router.post(
    "/auth/register-vendor",
    status_code=status.HTTP_201_CREATED,
    response_model=VendorRegistrationResponse,
    dependencies=[Depends(registration_limit(_account_from_request))],
)
def register_vendor(
    body: RegisterVendorRequest,
    session: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> VendorRegistrationResponse:
    user, shop = auth_service.register_vendor(
        session,
        email=str(body.email),
        password=body.password,
        full_name=body.full_name,
        shop_name=body.shop_name,
        shop_address=body.shop_address,
        phone=body.phone,
        latitude=body.latitude,
        longitude=body.longitude,
    )
    verification_service.send_verification(session, sender, get_settings(), user=user)
    return VendorRegistrationResponse(
        user=UserResponse.model_validate(user),
        shop=shop_service.vendor_shop_response(session, shop),
    )


@router.post("/testing/verify-email")
def testing_verify_email(
    body: TestingVerifyEmailRequest,
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Mark an address as proved, for a test that cannot read a mail box.

    The route is off unless a deployment turns it on, and it is bound to
    an address rather than to a token, because the whole point is that
    the test has no mail box to read the token out of.
    """
    settings = get_settings()
    if not settings.testing_endpoints_enabled or settings.env == "production":
        raise NotFound("Not found")
    user = session.scalar(select(User).where(User.email == str(body.email)))
    if user is None:
        raise NotFound("Account not found")
    user.email_verified = True
    session.commit()
    return {"status": "verified", "email": user.email}


@router.post("/auth/verify-email", response_model=UserResponse)
def verify_email(
    body: VerifyEmailRequest,
    session: Session = Depends(get_db),
) -> User:
    """Prove the address from the link that was sent to it."""
    user = verification_service.verify(session, token=body.token)
    return user


@router.post(
    "/auth/resend-verification",
    response_model=VerificationSentResponse,
    dependencies=[Depends(user_rate_limit(3, 3600, "resend-verification"))],
)
def resend_verification(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> VerificationSentResponse:
    """Send the link again, to the address the account holds."""
    issued = verification_service.send_verification(session, sender, get_settings(), user=user)
    return VerificationSentResponse(email=user.email, expires_at=issued.expires_at)


@router.post("/auth/change-email", response_model=UserResponse)
def change_email(
    body: ChangeEmailRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> User:
    """Put a different address on the account and start proving it.

    This is the way out of a mistyped address. The new address has to
    be proved as well, because the old one was never proved.
    """
    verification_service.change_email(
        session, user=user, email=str(body.email), password=body.password
    )
    verification_service.send_verification(session, sender, get_settings(), user=user)
    return user


@router.post(
    "/auth/login",
    response_model=AccessTokenResponse,
    dependencies=[
        Depends(account_rate_limit(10, 60, "login", _account_from_request)),
    ],
)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
) -> AccessTokenResponse:
    _user, tokens = auth_service.login(session, email=str(body.email), password=body.password)
    _set_refresh_cookie(response, tokens.refresh_token, request)
    return AccessTokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/auth/refresh", response_model=AccessTokenResponse)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=auth_service.REFRESH_COOKIE),
    session: Session = Depends(get_db),
) -> AccessTokenResponse:
    if refresh_token is None:
        raise Unauthenticated("No refresh token")
    _user, tokens = auth_service.refresh(session, refresh_token)
    _set_refresh_cookie(response, tokens.refresh_token, request)
    return AccessTokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=auth_service.REFRESH_COOKIE),
    session: Session = Depends(get_db),
) -> None:
    if refresh_token is not None:
        auth_service.logout(session, refresh_token)
    _clear_refresh_cookie(response, request)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user


def _is_secure(request: Request) -> bool:
    """Whether the request arrived over TLS.

    The Secure attribute of the refresh cookie is a statement about the
    transport the cookie travels over, so it is decided by the transport and
    not by a configuration string. A configuration string can be mis-set;
    the scheme cannot. The origin sets the forwarded scheme itself, so a
    client cannot talk the cookie into being sent in the clear.
    """
    return request.url.scheme == "https"


def _set_refresh_cookie(response: Response, token: str, request: Request) -> None:
    settings = get_settings()
    response.set_cookie(
        auth_service.REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        samesite="lax",
        secure=_is_secure(request),
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        auth_service.REFRESH_COOKIE,
        path="/api/v1/auth",
        httponly=True,
        samesite="lax",
        secure=_is_secure(request),
    )
