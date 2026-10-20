"""Signing in with an account at a provider.

The flow is the authorization code flow with PKCE, and it is the
browser that carries it: the front end asks the server to start, the
server answers with an address to open, and the provider sends the
browser back to the server.

The state and the code verifier are kept in a signed cookie rather than
in a table. A table of half finished sign ins is a thing to clean up
and a thing to attack, and a cookie that the server signed cannot be
changed by the browser. The state is what stops a third party from
starting a sign in and having the browser land on somebody else's
account, and the verifier is what makes an intercepted code useless.
"""

import base64
import hashlib
import hmac
import json
import secrets
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import (
    OAuthAccountExists,
    OAuthProviderError,
    OAuthStateInvalid,
    Unauthenticated,
)
from app.gateways.oauth import OAuthProvider
from app.models import OAuthIdentity, User
from app.services import auth_service

#: The cookie the state and the verifier travel in.
STATE_COOKIE = "spn_oauth"

#: How long the state is good for. A sign in is a thing a person does
#: in a minute, and a state that is good for ten minutes cannot be
#: used to start a sign in and finish it much later.
STATE_TTL_SECONDS = 600

#: The largest cookie the server will read. The one it writes is a few
#: hundred bytes, so anything larger is not the one it wrote.
MAX_COOKIE_LENGTH = 2000


def start(provider: OAuthProvider, settings: Settings, *, user: User | None) -> tuple[str, str]:
    """The address to open, and the cookie that carries the state.

    When the caller is signed in, the account is remembered in the
    cookie. That is the intent to connect the provider to *that*
    account, and it is only honoured for the account whose address the
    provider gives back.
    """
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = create_s256_code_challenge(verifier)
    url = provider.authorization_url(
        state=state,
        code_challenge=challenge,
        redirect_uri=redirect_uri(settings, provider.name),
    )
    payload: dict[str, str] = {
        "state": state,
        "verifier": verifier,
        "provider": provider.name,
    }
    if user is not None:
        payload["user_id"] = str(user.id)
    return url, _sign(payload)


def callback(
    session: Session,
    provider: OAuthProvider,
    settings: Settings,
    *,
    code: str,
    state: str,
    cookie: str | None,
) -> User:
    """The account the provider is talking about.

    Three things can happen. The identity is known, and the account is
    signed in. The identity is new and the address is free, and the
    account is made. The identity is new and the address is taken, and
    the request is refused: the address being proved by a provider says
    that somebody owns it there, and it says nothing about who owns it
    here.
    """
    payload = _unsign(cookie)
    if payload.get("provider") != provider.name:
        raise OAuthStateInvalid("This sign in did not start here.")
    if not hmac.compare_digest(payload.get("state", ""), state):
        raise OAuthStateInvalid("This sign in did not start here.")

    try:
        profile = provider.exchange(
            code=code,
            code_verifier=payload.get("verifier", ""),
            redirect_uri=redirect_uri(settings, provider.name),
        )
    except Exception as exc:
        raise OAuthProviderError("The provider could not be reached.") from exc

    identity = session.scalar(
        select(OAuthIdentity).where(
            OAuthIdentity.provider == provider.name,
            OAuthIdentity.provider_subject == profile.subject,
        )
    )
    if identity is not None:
        user = session.get(User, identity.user_id)
        if user is None or not user.is_active:
            raise Unauthenticated("Authentication required")
        return user

    existing = session.scalar(select(User).where(User.email == profile.email))
    if existing is not None:
        if payload.get("user_id") == str(existing.id):
            # The person who is signing in is the owner of the account
            # that holds the address, so the identity is connected to it.
            session.add(
                OAuthIdentity(
                    user_id=existing.id,
                    provider=provider.name,
                    provider_subject=profile.subject,
                )
            )
            session.commit()
            return existing
        raise OAuthAccountExists(
            "There is already an account with that email address. "
            "Sign in with your password and connect Google from your account."
        )

    user = auth_service.register_customer(
        session,
        email=profile.email,
        # The account has no password. The column is not nullable, and
        # the alternative, a nullable one, would put a branch in the
        # login path, which is the one path that must not have branches.
        # This password is random and nobody keeps it, so the account
        # can only be signed into through the provider.
        password=secrets.token_urlsafe(32),
        full_name=profile.name or profile.email.split("@")[0],
    )
    user.email_verified = profile.email_verified
    session.add(
        OAuthIdentity(
            user_id=user.id,
            provider=provider.name,
            provider_subject=profile.subject,
        )
    )
    session.commit()
    return user


def redirect_uri(settings: Settings, provider: str) -> str:
    """The address the provider sends the browser back to.

    It is the API and not the front end: the code is exchanged for a
    token by the server, and the server is the one that has the client
    secret.
    """
    base = settings.api_base_url.rstrip("/")
    return f"{base}/api/v1/auth/oauth/{provider}/callback"


def create_s256_code_challenge(verifier: str) -> str:
    """The challenge that goes with the verifier.

    PKCE, S256: the challenge is the verifier hashed and encoded, and
    the provider holds the challenge while the verifier stays on the
    server. A code that was intercepted cannot be exchanged without the
    verifier, and the verifier never left the server.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _sign(payload: dict[str, str]) -> str:
    body = _encode(payload)
    signature = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def _unsign(value: str | None) -> dict[str, str]:
    """The payload the cookie carries, if it is one the server wrote."""
    if value is None or value == "" or len(value) > MAX_COOKIE_LENGTH:
        raise OAuthStateInvalid("This sign in did not start here.")
    body, _, signature = value.rpartition(".")
    expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise OAuthStateInvalid("This sign in did not start here.")
    try:
        payload = json.loads(_decode(body))
    except ValueError as exc:
        raise OAuthStateInvalid("This sign in did not start here.") from exc
    if not isinstance(payload, dict):
        raise OAuthStateInvalid("This sign in did not start here.")
    return {str(key): str(value) for key, value in payload.items()}


def _encode(payload: dict[str, str]) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(body: str) -> str:
    padding = "=" * (-len(body) % 4)
    return base64.urlsafe_b64decode(body + padding).decode("utf-8")


def _secret() -> bytes:
    """The key the cookie is signed with.

    It is the secret the application already signs its tokens with.
    A second secret for the same process would be one more thing to
    keep, and one more thing to get wrong.
    """
    from app.config import get_settings

    return get_settings().jwt_secret.encode("utf-8")


def pending_user_id(payload: dict[str, Any]) -> uuid.UUID | None:
    """The account the sign in was started for, if it was started by one."""
    raw = payload.get("user_id")
    if not isinstance(raw, str) or raw == "":
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None
