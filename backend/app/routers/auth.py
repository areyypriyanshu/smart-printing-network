from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import get_current_user
from app.errors import Unauthenticated
from app.models import User
from app.rate_limit import rate_limit
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


@router.post(
    "/auth/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    dependencies=[Depends(rate_limit(5, 60, "register"))],
)
def register(body: RegisterRequest, session: Session = Depends(get_db)) -> User:
    return auth_service.register_customer(
        session, email=str(body.email), password=body.password, full_name=body.full_name
    )


@router.post(
    "/auth/register-vendor",
    status_code=status.HTTP_201_CREATED,
    response_model=VendorRegistrationResponse,
    dependencies=[Depends(rate_limit(5, 60, "register"))],
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
    dependencies=[Depends(rate_limit(10, 60, "login"))],
)
def login(
    body: LoginRequest, response: Response, session: Session = Depends(get_db)
) -> AccessTokenResponse:
    _user, tokens = auth_service.login(session, email=str(body.email), password=body.password)
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessTokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/auth/refresh", response_model=AccessTokenResponse)
def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=auth_service.REFRESH_COOKIE),
    session: Session = Depends(get_db),
) -> AccessTokenResponse:
    if refresh_token is None:
        raise Unauthenticated("No refresh token")
    _user, tokens = auth_service.refresh(session, refresh_token)
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessTokenResponse(access_token=tokens.access_token, expires_in=tokens.expires_in)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=auth_service.REFRESH_COOKIE),
    session: Session = Depends(get_db),
) -> None:
    if refresh_token is not None:
        auth_service.logout(session, refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user


def _set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        auth_service.REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.env == "production",
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        auth_service.REFRESH_COOKIE,
        path="/api/v1/auth",
        httponly=True,
        samesite="lax",
        secure=settings.env == "production",
    )
