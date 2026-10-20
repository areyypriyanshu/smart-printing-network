"""Signing in with a Google account.

The flow is the authorization code flow with PKCE, and the profile comes
from the userinfo endpoint rather than from an id token.

An id token is a signed statement about the person, and reading it
means verifying a signature, which means a library for signing things.
The userinfo endpoint says the same three things over a connection the
server authenticates with the access token it was just given, so there
is nothing to verify and nothing to add to the dependencies.

The tokens the provider gives are used once and dropped. The platform
keeps the answer, not the credentials.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.gateways.oauth.base import OAuthError, OAuthProfile

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"

#: What the platform asks the provider for. `openid` is what makes the
#: provider give an identifier that belongs to the account rather than
#: to the address.
SCOPE = "openid email profile"

REQUEST_TIMEOUT_SECONDS = 10.0


class GoogleOAuthProvider:
    """Talks to Google."""

    name = "google"

    def __init__(self, *, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret

    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        query = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": SCOPE,
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{AUTHORIZATION_ENDPOINT}?{query}"

    def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> OAuthProfile:
        token = self._token(code=code, code_verifier=code_verifier, redirect_uri=redirect_uri)
        access_token = token.get("access_token")
        if not isinstance(access_token, str) or access_token == "":
            raise OAuthError("the provider did not give an access token")
        return self._profile(access_token=access_token)

    def _token(self, *, code: str, code_verifier: str, redirect_uri: str) -> dict[str, Any]:
        body = urllib.parse.urlencode(
            {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        ).encode()
        request = urllib.request.Request(
            TOKEN_ENDPOINT,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        payload = self._read(request)
        if not isinstance(payload, dict):
            raise OAuthError("the provider did not answer with a token")
        return payload

    def _profile(self, *, access_token: str) -> OAuthProfile:
        request = urllib.request.Request(
            USERINFO_ENDPOINT,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )
        payload = self._read(request)
        if not isinstance(payload, dict):
            raise OAuthError("the provider did not answer with a profile")
        subject = payload.get("sub")
        email = payload.get("email")
        if not isinstance(subject, str) or subject == "":
            raise OAuthError("the provider did not say who the account is")
        if not isinstance(email, str) or email == "":
            raise OAuthError("the provider did not give an address")
        name = payload.get("name")
        return OAuthProfile(
            subject=subject,
            email=email,
            email_verified=payload.get("email_verified") is True,
            name=name if isinstance(name, str) else None,
        )

    def _read(self, request: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(  # noqa: S310 - the address is a constant
                request, timeout=REQUEST_TIMEOUT_SECONDS
            ) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            # The answer may hold the reason, and it may not. Either way
            # the platform must not put a provider token in a log.
            raise OAuthError("the provider could not be reached") from exc
