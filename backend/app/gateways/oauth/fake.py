"""The provider that is not a provider.

It answers with whatever the test told it to, so the sign in flow can
be tested without a network and without a Google account.
"""

from app.gateways.oauth.base import OAuthError, OAuthProfile


class FakeOAuthProvider:
    """Answers with the profile the test gave it.

    The name is the one the identity is stored under, and a test that
    stands in for Google gives the name Google has.
    """

    def __init__(self, profile: OAuthProfile | None = None, *, name: str = "fake") -> None:
        self.name = name
        self.profile = profile
        self.exchanged: list[dict[str, str]] = []
        self.raised: OAuthError | None = None

    def authorization_url(self, *, state: str, code_challenge: str, redirect_uri: str) -> str:
        return (
            "https://provider.example/authorize"
            f"?state={state}&code_challenge={code_challenge}&redirect_uri={redirect_uri}"
        )

    def exchange(self, *, code: str, code_verifier: str, redirect_uri: str) -> OAuthProfile:
        self.exchanged.append(
            {"code": code, "code_verifier": code_verifier, "redirect_uri": redirect_uri}
        )
        if self.raised is not None:
            raise self.raised
        if self.profile is None:
            raise OAuthError("the fake provider has no profile")
        return self.profile
