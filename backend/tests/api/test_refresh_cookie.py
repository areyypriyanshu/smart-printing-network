"""The Secure attribute of the refresh cookie.

The refresh cookie is the one credential the browser sends on its own.
Whether it is marked Secure is a statement about the transport it
travels over, so it is decided by the transport and not by a
configuration string: a configuration string can be mis-set, and the
scheme of the request cannot.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import create_user, login_headers

LOGIN = "/api/v1/auth/login"
AUTH = "/api/v1/auth"
CREDENTIALS = {"email": "customer@example.com", "password": "password-123"}


def _cookie_header(response) -> str:  # type: ignore[no-untyped-def]
    return response.headers.get("set-cookie", "")


def test_the_cookie_is_secure_over_https(https_client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="customer@example.com")

    response = https_client.post(LOGIN, json=CREDENTIALS)

    assert response.status_code == 200, response.text
    assert "Secure" in _cookie_header(response)


def test_the_cookie_is_not_secure_over_plain_http(client: TestClient, db_session: Session) -> None:
    """A local development server speaks plain HTTP.

    Marking the cookie secure there would mean the browser never sends
    it back, and the local sign-in would not work.
    """
    create_user(db_session, email="customer@example.com")

    response = client.post(LOGIN, json=CREDENTIALS)

    assert response.status_code == 200, response.text
    assert "Secure" not in _cookie_header(response)


def test_the_cookie_is_secure_whatever_the_mode_string_says(
    https_client: TestClient, db_session: Session, monkeypatch
) -> None:
    """The mode string does not decide it.

    Every production-only check was keyed on the exact string
    'production', so a spelling that was nearly right ran them in the
    wrong mode. The cookie's Secure attribute now follows the request.
    """
    create_user(db_session, email="customer@example.com")
    monkeypatch.setattr(
        "app.routers.auth.get_settings",
        lambda: type("Settings", (), {"env": "prod", "refresh_token_days": 7})(),
    )

    response = https_client.post(LOGIN, json=CREDENTIALS)

    assert response.status_code == 200, response.text
    assert "Secure" in _cookie_header(response)


def test_the_cookie_is_not_readable_by_a_script(
    https_client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="customer@example.com")

    response = https_client.post(LOGIN, json=CREDENTIALS)

    header = _cookie_header(response)
    assert "HttpOnly" in header
    assert "samesite=lax" in header.lower()


def test_logging_out_clears_the_cookie(https_client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="customer@example.com")
    headers = login_headers(https_client, "customer@example.com")

    response = https_client.post(f"{AUTH}/logout", headers=headers)

    assert response.status_code == 204
    assert "spn_refresh=" in _cookie_header(response)
