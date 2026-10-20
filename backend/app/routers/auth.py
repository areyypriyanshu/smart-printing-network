import hashlib

from fastapi import APIRouter, Cookie, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.deps import get_current_user
from app.errors import Unauthenticated
from app.models import User
from app.rate_limit import account_rate_limit, registration_limit
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RegisterRequest,
    RegisterVendorRequest,
    UserResponse,
)
from app.schemas.errors import ERROR_RESPONSES
from app.schemas.shop import VendorRegistrationResponse
from app.services import auth_service, shop_service

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
def register(body: RegisterRequest, session: Session = Depends(get_db)) -> User:
    return auth_service.register_customer(
        session, email=str(body.email), password=body.password, full_name=body.full_name
    )


@router.post(
    "/auth/register-vendor",
    status_code=status.HTTP_201_CREATED,
    response_model=VendorRegistrationResponse,
    dependencies=[Depends(registration_limit(_account_from_request))],
)
def register_vendor(
    body: RegisterVendorRequest, session: Session = Depends(get_db)
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
    return VendorRegistrationResponse(
        user=UserResponse.model_validate(user),
        shop=shop_service.vendor_shop_response(session, shop),
    )


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
