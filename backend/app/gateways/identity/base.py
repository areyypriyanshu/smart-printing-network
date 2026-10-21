"""The interface the application uses to find out who is calling.

The application does not know how an identity is proved. It knows that
a token was presented, and it needs the answer to a question: who is
this? The interface is that seam, and the two implementations of it are
the real identity provider and a stand-in for the test suite.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VerifiedIdentity:
    """Who a token says the caller is.

    `subject` is the provider's own identifier for the person, and it is
    the only thing the application stores about them. The provider owns
    the address, the name and whether the account is allowed to sign in;
    the application stores what it needs to do business with, and it
    looks the person up by this.

    `origin` is the address that asked for the token, when the provider
    records one. It is checked against the origins this deployment
    accepts, because a token minted for another application on the same
    provider is not a token for this one.
    """

    subject: str
    session_id: str | None = None
    origin: str | None = None


class TokenVerifier(Protocol):
    """Turns a token into the identity it names, or refuses it."""

    def verify(self, token: str) -> VerifiedIdentity:
        """The identity the token names.

        Raises `Unauthenticated` when the token is not one this
        deployment accepts. It never raises anything else for a token it
        does not like: a caller must not be able to tell a malformed
        token from an expired one from a foreign one.
        """
        ...
