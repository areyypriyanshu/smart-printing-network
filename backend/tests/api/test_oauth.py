"""Signing in with an account at a provider.

The flow is tested against a fake provider, so the suite needs no
network and no Google account. What matters here is that the state is
checked, that an account is made when it should be, and that an
account is never taken over by an address that somebody else claimed.
"""

from app.gateways.oauth import FakeOAuthProvider, OAuthProfile
from app.models import OAuthIdentity, User
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.factories import create_user

START = "/api/v1/auth/oauth/google/start"
CALLBACK = "/api/v1/auth/oauth/google/callback"
STATE_COOKIE = "spn_oauth"


def _profile(*, subject: str = "google-1", email: str = "person@example.com") -> OAuthProfile:
    return OAuthProfile(
        subject=subject,
        email=email,
        email_verified=True,
        name="A Person",
    )


def _use_provider(client: TestClient, profile: OAuthProfile | None = None) -> FakeOAuthProvider:
    provider = FakeOAuthProvider(profile if profile is not None else _profile(), name="google")
    client.app.state.oauth_providers = {"google": provider}
    return provider


def _start(client: TestClient) -> str:
    response = client.post(START)
    assert response.status_code == 200, response.text
    return response.json()["url"]


def _state_from(client: TestClient) -> str:
    """The state that the server put in the cookie."""
    cookie = client.cookies.get(STATE_COOKIE)
    assert cookie is not None
    body, _, _signature = cookie.rpartition(".")
    import base64
    import json

    padding = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body + padding))["state"]


def test_starting_a_sign_in_answers_with_an_address_and_keeps_the_state(
    client: TestClient,
) -> None:
    _use_provider(client)

    response = client.post(START)

    assert response.status_code == 200, response.text
    assert response.json()["url"].startswith("https://provider.example/authorize")
    assert "code_challenge=" in response.json()["url"]
    assert client.cookies.get(STATE_COOKIE) is not None


def test_a_provider_this_deployment_does_not_offer_is_refused(
    client: TestClient,
) -> None:
    client.app.state.oauth_providers = {}

    response = client.post(START)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OAUTH_PROVIDER_UNAVAILABLE"


def test_a_new_identity_makes_an_account_that_can_order(
    client: TestClient, db_session: Session
) -> None:
    provider = _use_provider(client)
    _start(client)
    state = _state_from(client)

    response = client.get(
        CALLBACK, params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 302
    assert response.headers["location"].endswith(":5173")
    user = db_session.scalar(select(User).where(User.email == "person@example.com"))
    assert user is not None
    assert user.email_verified is True
    identity = db_session.scalar(select(OAuthIdentity))
    assert identity is not None
    assert identity.provider == "google"
    assert identity.provider_subject == "google-1"
    assert provider.exchanged[0]["code"] == "the-code"


def test_the_sign_in_sets_the_refresh_cookie(client: TestClient) -> None:
    _use_provider(client)
    _start(client)
    state = _state_from(client)

    response = client.get(
        CALLBACK, params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert "spn_refresh" in response.cookies or client.cookies.get("spn_refresh")


def test_a_known_identity_signs_the_account_in(client: TestClient, db_session: Session) -> None:
    user = create_user(db_session, email="person@example.com")
    provider = _use_provider(client)
    _start(client)
    state = _state_from(client)
    db_session.add(OAuthIdentity(user_id=user.id, provider="google", provider_subject="google-1"))
    db_session.commit()

    response = client.get(
        CALLBACK, params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 302
    assert "oauth_error" not in response.headers["location"]
    assert provider.exchanged[0]["code"] == "the-code"


def test_a_state_that_does_not_match_is_refused(client: TestClient) -> None:
    _use_provider(client)
    _start(client)

    response = client.get(
        CALLBACK,
        params={"code": "the-code", "state": "a-state-nobody-sent"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "oauth_error=OAUTH_STATE_INVALID" in response.headers["location"]


def test_a_sign_in_without_the_cookie_is_refused(client: TestClient) -> None:
    """The cookie is what holds the state, so without it there is nothing to check."""
    _use_provider(client)

    response = client.get(
        CALLBACK, params={"code": "the-code", "state": "some-state"}, follow_redirects=False
    )

    assert response.status_code == 302
    assert "oauth_error=OAUTH_STATE_INVALID" in response.headers["location"]


def test_an_address_that_is_already_an_account_is_not_taken_over(
    client: TestClient, db_session: Session
) -> None:
    """The rule that matters: a proved address is not a claim on an account."""
    create_user(db_session, email="person@example.com")
    _use_provider(client)
    _start(client)
    state = _state_from(client)

    response = client.get(
        CALLBACK, params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 302
    assert "oauth_error=OAUTH_ACCOUNT_EXISTS" in response.headers["location"]
    assert db_session.scalar(select(OAuthIdentity)) is None


def test_a_signed_in_customer_connects_the_provider_to_their_own_account(
    client: TestClient, db_session: Session
) -> None:
    """The one case where the address is enough: they are already signed in."""
    user = create_user(db_session, email="person@example.com")
    _use_provider(client)
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "password-123"},
    ).json()["access_token"]
    client.post(START, headers={"Authorization": f"Bearer {token}"})
    state = _state_from(client)

    response = client.get(
        CALLBACK, params={"code": "the-code", "state": state}, follow_redirects=False
    )

    assert response.status_code == 302
    assert "oauth_error" not in response.headers["location"]
    identity = db_session.scalar(select(OAuthIdentity))
    assert identity is not None
    assert identity.user_id == user.id


def test_a_google_only_account_can_add_a_local_password(
    client: TestClient, db_session: Session
) -> None:
    _use_provider(client)
    _start(client)
    state = _state_from(client)
    response = client.get(
        CALLBACK, params={"code": "the-code", "state": state}, follow_redirects=False
    )
    assert response.status_code == 302
    user = db_session.scalar(select(User).where(User.email == "person@example.com"))
    assert user is not None
    token = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "anything"},
    )
    assert token.status_code == 401
    # The callback sets the refresh cookie. The browser uses it to get
    # the short-lived bearer token before calling the account endpoint.
    refresh = client.post("/api/v1/auth/refresh")
    assert refresh.status_code == 200
    set_password = client.post(
        "/api/v1/auth/set-password",
        headers={"Authorization": f"Bearer {refresh.json()['access_token']}"},
        json={"password": "new-local-password"},
    )
    assert set_password.status_code == 200, set_password.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "person@example.com", "password": "new-local-password"},
    )
    assert login.status_code == 200, login.text
