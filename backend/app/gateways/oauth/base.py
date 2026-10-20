"""Signing in with an account at somebody else's provider.

The application must not know how a provider is talked to, and the
provider must be replaceable in a test without a network. There is one
real implementation (Google) and one fake, and the application only
ever sees a profile: an identifier at the provider, an address, and
whether the provider says the address is proved.

The provider's own tokens are not part of the interface. The platform
asks the provider who the person is, and then keeps the answer. A
stored refresh token would be a secret with a life of its own and
nothing in the product needs it.
"""

from dataclasses import dataclass
from typing import Protocol


class OAuthError(Exception):
    """The provider could not be talked to, or would not say who it is.

    It is a different thing from the errors the application raises for
    a request it understood and refused. This one means the round trip
    to the provider did not work, and the customer is told to try again
    rather than that they did something wrong.
    """


@dataclass(frozen=True)
class OAuthProfile:
    """Who the person is, according to the provider.

    `subject` is the identifier the provider gave for the account. It
    is the one thing that identifies the account: the address can
    change, and two providers can be given the same address by two
    different people.

    `email_verified` is what the provider says about the address. It is
    the provider's word, and the application believes it, because the
    answer came over a connection the server authenticated.
    """

    subject: str
    email: str
    email_verified: bool
    name: str | None = None


class OAuthProvider(Protocol):
    """A provider the platform can sign in with."""

    #: The name the identities are stored under. It is part of the key,
    #: so it cannot change once an identity has been stored.
    name: str

    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        """The address to send the browser to."""
        ...

    def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> OAuthProfile:
        """Turn the code the provider sent back into a profile."""
        ...
