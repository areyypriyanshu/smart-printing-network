"""Reading a person from the identity provider's own API.

The application needs two things about a person that the session token
does not carry: the address to put on the account, and the name to show.
The provider's backend API is where those come from, and it is the
authority on them.

The call is made once, when the local account is created. The local
account is then the record the application works from, so the call is
not made again on every request.

The request is built by a pure function and sent separately, so that
what is sent can be tested without a network.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

CLERK_API = "https://api.clerk.com/v1"

#: What this application calls itself when it asks the provider
#: something. The provider's API sits behind a bot protection that
#: refuses a request with no agent of its own, and the one the
#: standard library sends by default is refused. Naming the
#: application is the honest answer to that question.
USER_AGENT = "SmartPrintingNetwork/0.1"


class ClerkAdminError(Exception):
    """The provider's API could not be read.

    It is not an `AppError`: it is a fault in a dependency, and the
    route that hit it turns it into a 502 rather than pretending the
    caller did something wrong.
    """


class ClerkUserNotFound(ClerkAdminError):
    """The provider does not know the person.

    It is a different thing from the provider being unreachable. The
    token named somebody and the provider has no record of them, which
    means the account was removed between the token being made and the
    question being asked.
    """


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    body: bytes
    headers: dict[str, str]


@dataclass(frozen=True)
class ClerkUser:
    """What the provider knows about one person."""

    id: str
    email: str
    full_name: str
    email_verified: bool


def build_get_user_request(*, secret_key: str, user_id: str) -> HttpRequest:
    """The request that reads one person.

    The secret key is sent as a bearer token. It never appears in the
    body, so it cannot be logged with a body.
    """
    return HttpRequest(
        method="GET",
        url=f"{CLERK_API}/users/{user_id}",
        body=b"",
        headers={
            "Authorization": f"Bearer {secret_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )


def parse_user(document: dict[str, Any]) -> ClerkUser:
    """The person the provider's document describes.

    The address is the primary one, because that is the address the
    provider uses to reach them. A person with no address is an error
    rather than an account with an empty address, because the address
    is what the order is tied to.
    """
    user_id = document.get("id")
    if not isinstance(user_id, str) or not user_id:
        raise ClerkAdminError("the provider returned a person with no identifier")

    addresses = document.get("email_addresses")
    if not isinstance(addresses, list):
        raise ClerkAdminError("the provider returned a person with no addresses")

    primary_id = document.get("primary_email_address_id")
    chosen: dict[str, Any] | None = None
    for address in addresses:
        if not isinstance(address, dict):
            continue
        if chosen is None:
            chosen = address
        if isinstance(primary_id, str) and address.get("id") == primary_id:
            chosen = address
            break

    if chosen is None:
        raise ClerkAdminError("the provider returned a person with no address")

    email = chosen.get("email_address")
    if not isinstance(email, str) or not email:
        raise ClerkAdminError("the provider returned a person with no address")

    verification = chosen.get("verification")
    verified = isinstance(verification, dict) and verification.get("status") == "verified"

    first = document.get("first_name")
    last = document.get("last_name")
    parts = [part for part in (first, last) if isinstance(part, str) and part]
    full_name = " ".join(parts) if parts else email

    return ClerkUser(id=user_id, email=email, full_name=full_name, email_verified=verified)


class ClerkAdminClient:
    """Reads a person from the provider's backend API."""

    def __init__(self, *, secret_key: str, timeout_seconds: int = 10) -> None:
        self._secret_key = secret_key
        self._timeout = timeout_seconds

    def get_user(self, user_id: str) -> ClerkUser:
        request = build_get_user_request(secret_key=self._secret_key, user_id=user_id)
        try:
            with urllib.request.urlopen(
                urllib.request.Request(request.url, headers=request.headers),
                timeout=self._timeout,
            ) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ClerkUserNotFound("the identity provider does not know the person") from exc
            raise ClerkAdminError("the identity provider could not be reached") from exc
        except (OSError, urllib.error.URLError) as exc:
            raise ClerkAdminError("the identity provider could not be reached") from exc
        try:
            document = json.loads(body)
        except ValueError as exc:
            raise ClerkAdminError("the identity provider returned something unreadable") from exc
        if not isinstance(document, dict):
            raise ClerkAdminError("the identity provider returned something unreadable")
        return parse_user(document)
