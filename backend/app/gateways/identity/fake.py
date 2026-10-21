"""A stand-in for the identity provider, for the test suite.

The real verifier talks to a network service, so the test suite does not
use it. A test that needs a signed-in caller is given a token this
issues instead, and the application treats it exactly as it would treat
a real one: the same interface, the same lookups, the same refusals.

The token is deliberately not a JWT. A test that wanted a forged token
would have to know how to sign one, and the whole point of the real
verifier is that a forged token is not accepted.
"""

from app.errors import Unauthenticated
from app.gateways.identity.base import VerifiedIdentity
from app.gateways.identity.clerk_admin import ClerkUser

#: Every token this issues starts with this, so that a token from
#: somewhere else is refused rather than read as a subject.
PREFIX = "fake:"


def dev_subject_for(email: str) -> str:
    """A stable identifier for a local test account.

    It is derived from the address, so the same address is the same
    account every time the suite runs. It is not a provider
    identifier, and it does not start with the prefix a real one
    would, so it can never be mistaken for one.
    """
    import hashlib

    return "dev_" + hashlib.sha256(email.lower().encode()).hexdigest()[:24]


class FakeTokenVerifier:
    """Issues and reads the tokens the test suite signs in with."""

    def __init__(self) -> None:
        self._issued: set[str] = set()

    def issue(self, subject: str) -> str:
        """A token that names this subject."""
        token = f"{PREFIX}{subject}"
        self._issued.add(token)
        return token

    def verify(self, token: str) -> VerifiedIdentity:
        if not token.startswith(PREFIX):
            raise Unauthenticated("Invalid or expired token")
        subject = token[len(PREFIX) :]
        if not subject:
            raise Unauthenticated("Invalid or expired token")
        return VerifiedIdentity(subject=subject, session_id="fake-session", origin=None)


class FakeIdentityReader:
    """Answers the question "who is this person" without a network.

    It is the stand-in for the provider's own API. A person it has not
    been told about is answered with an address derived from the
    subject, so that a test that has not set one up still gets a
    person, and the account it creates is still one of its own.
    """

    def __init__(self) -> None:
        self.people: dict[str, ClerkUser] = {}

    def add(self, subject: str, *, email: str, full_name: str = "Test Person") -> None:
        self.people[subject] = ClerkUser(
            id=subject, email=email, full_name=full_name, email_verified=True
        )

    def get_user(self, user_id: str) -> ClerkUser:
        person = self.people.get(user_id)
        if person is not None:
            return person
        return ClerkUser(
            id=user_id,
            email=f"{user_id}@example.test",
            full_name="Test Person",
            email_verified=True,
        )
