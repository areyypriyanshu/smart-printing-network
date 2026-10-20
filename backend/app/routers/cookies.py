"""The cookies the session travels in.

The refresh cookie is the only thing that keeps a session alive, so
the two rules about it are the two rules that matter: it is only sent
over TLS when the request arrived over TLS, and a script cannot read
it.
"""

from fastapi import Request, Response

from app.config import get_settings
from app.services.auth_service import REFRESH_COOKIE


def is_secure(request: Request) -> bool:
    """Whether the request arrived over TLS.

    The Secure attribute of the refresh cookie is a statement about the
    transport the cookie travels over, so it is decided by the transport
    and not by a configuration string. A configuration string can be
    mis-set; the scheme cannot. The origin sets the forwarded scheme
    itself, so a client cannot talk the cookie into being sent in the
    clear.
    """
    return request.url.scheme == "https"


def set_refresh_cookie(response: Response, token: str, request: Request) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_days * 86400,
        httponly=True,
        samesite="lax",
        secure=is_secure(request),
        path="/api/v1/auth",
    )


def clear_refresh_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path="/api/v1/auth",
        httponly=True,
        samesite="lax",
        secure=is_secure(request),
    )
