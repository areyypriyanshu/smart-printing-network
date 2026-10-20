"""Signing in with an account at a provider.

Two routes. The first one answers with the address to open, and keeps
the state in a signed cookie. The second one is where the provider
sends the browser back, and it either signs the customer in or sends
them back to the front end with a reason.

The second one is a browser navigation, so its answers are redirects
rather than bodies. A customer who cannot sign in with a provider is
sent to the sign in page with the reason in the address, and the front
end says what happened.
"""

from fastapi import APIRouter, Cookie, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.deps import get_optional_user
from app.errors import AppError, OAuthProviderUnavailable
from app.gateways.oauth import OAuthProvider
from app.models import User
from app.routers.cookies import set_refresh_cookie
from app.schemas.errors import ERROR_RESPONSES
from app.services import auth_service, oauth_service

router = APIRouter(tags=["auth"], responses=ERROR_RESPONSES)


def _provider(request: Request, name: str) -> OAuthProvider:
    """The provider with that name, if this deployment offers it.

    The providers are on the application rather than built per request,
    because building one reads the configuration and there is no
    reason to read it again for every sign in.
    """
    providers: dict[str, OAuthProvider] = request.app.state.oauth_providers
    provider = providers.get(name.strip().lower())
    if provider is None:
        raise OAuthProviderUnavailable(
            "Signing in with that provider is not available on this deployment."
        )
    return provider


@router.get("/auth/oauth/providers")
def providers(request: Request) -> dict[str, list[str]]:
    """The providers this deployment offers.

    The front end asks, because a deployment that has not configured
    Google should not show a button that cannot work.
    """
    available: dict[str, OAuthProvider] = request.app.state.oauth_providers
    return {"providers": sorted(available)}


@router.post("/auth/oauth/{provider}/start")
def start(
    provider: str,
    request: Request,
    response: Response,
    user: User | None = Depends(get_optional_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """The address to open to sign in with the provider.

    The state and the code verifier travel in a signed cookie, so there
    is nothing to keep on the server and nothing to clean up.
    """
    oauth_provider = _provider(request, provider)
    url, cookie = oauth_service.start(oauth_provider, settings, user=user)
    response.set_cookie(
        oauth_service.STATE_COOKIE,
        cookie,
        max_age=oauth_service.STATE_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/api/v1/auth/oauth",
    )
    return {"url": url}


@router.get("/auth/oauth/{provider}/callback")
def callback(
    provider: str,
    request: Request,
    code: str = Query(min_length=1),
    state: str = Query(min_length=1),
    state_cookie: str | None = Cookie(default=None, alias=oauth_service.STATE_COOKIE),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    """Where the provider sends the browser back to."""
    oauth_provider = _provider(request, provider)
    try:
        user = oauth_service.callback(
            session,
            oauth_provider,
            settings,
            code=code,
            state=state,
            cookie=state_cookie,
        )
    except AppError as exc:
        return RedirectResponse(
            url=_failure_url(settings, exc.code),
            status_code=status.HTTP_302_FOUND,
        )
    bundle = auth_service.sign_in(session, user)
    redirect = RedirectResponse(
        url=settings.app_base_url.rstrip("/"),
        status_code=status.HTTP_302_FOUND,
    )
    set_refresh_cookie(redirect, bundle.refresh_token, request)
    return redirect


def _failure_url(settings: Settings, code: str) -> str:
    """The front end, with the reason in the address."""
    base = settings.app_base_url.rstrip("/")
    return f"{base}/login?oauth_error={code}"
