from app.config import Settings
from app.gateways.oauth.base import OAuthError, OAuthProfile, OAuthProvider
from app.gateways.oauth.fake import FakeOAuthProvider
from app.gateways.oauth.google import GoogleOAuthProvider

__all__ = [
    "FakeOAuthProvider",
    "GoogleOAuthProvider",
    "OAuthError",
    "OAuthProfile",
    "OAuthProvider",
    "build_oauth_provider",
]


def build_oauth_provider(settings: Settings, name: str) -> OAuthProvider | None:
    """The provider with that name, or nothing when it is not configured.

    A provider that is not configured is not an error. A deployment that
    has not set the client id and the client secret simply does not
    offer the provider, and the front end hides the button.
    """
    provider = name.strip().lower()
    if provider == "google":
        if not settings.google_client_id or not settings.google_client_secret:
            return None
        return GoogleOAuthProvider(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
    return None
