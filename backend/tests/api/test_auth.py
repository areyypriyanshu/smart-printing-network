from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from tests.factories import DEFAULT_PASSWORD, create_user

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def register_payload(email: str = "new.user@example.com") -> dict[str, str]:
    return {"email": email, "password": DEFAULT_PASSWORD, "full_name": "New User"}


def test_register_creates_customer(client: TestClient) -> None:
    response = client.post(REGISTER, json=register_payload())

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "customer"
    assert body["email"] == "new.user@example.com"
    assert body["full_name"] == "New User"
    assert "password" not in response.text


def test_duplicate_email_is_rejected_case_insensitively(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="taken@example.com")

    response = client.post(REGISTER, json=register_payload("TAKEN@example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_rejects_weak_password(client: TestClient) -> None:
    payload = register_payload()
    payload["password"] = "short"

    response = client.post(REGISTER, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_register_rejects_invalid_email(client: TestClient) -> None:
    payload = register_payload()
    payload["email"] = "not-an-email"

    response = client.post(REGISTER, json=payload)

    assert response.status_code == 422


def test_login_returns_token_and_sets_httponly_refresh_cookie(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="login@example.com")

    response = client.post(LOGIN, json={"email": "login@example.com", "password": DEFAULT_PASSWORD})

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert response.json()["expires_in"] == 15 * 60
    set_cookie = response.headers["set-cookie"]
    assert "spn_refresh=" in set_cookie
    assert "HttpOnly" in set_cookie


def test_me_returns_current_user(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="me@example.com", full_name="Me Myself")
    login = client.post(LOGIN, json={"email": "me@example.com", "password": DEFAULT_PASSWORD})
    token = login.json()["access_token"]

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"
    assert response.json()["full_name"] == "Me Myself"


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_wrong_password_returns_unauthenticated(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="wrong@example.com")

    response = client.post(
        LOGIN, json={"email": "wrong@example.com", "password": "not-the-password"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_unknown_email_returns_same_error(client: TestClient) -> None:
    response = client.post(LOGIN, json={"email": "ghost@example.com", "password": "whatever1"})

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password"


def test_login_inactive_user_rejected(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="inactive@example.com", is_active=False)

    response = client.post(
        LOGIN, json={"email": "inactive@example.com", "password": DEFAULT_PASSWORD}
    )

    assert response.status_code == 401


def test_refresh_rotates_token_and_reuse_revokes_family(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="rotate@example.com")
    client.post(LOGIN, json={"email": "rotate@example.com", "password": DEFAULT_PASSWORD})
    first_cookie = client.cookies.get("spn_refresh")
    assert first_cookie

    rotated = client.post("/api/v1/auth/refresh")
    assert rotated.status_code == 200
    second_cookie = client.cookies.get("spn_refresh")
    assert second_cookie and second_cookie != first_cookie

    client.cookies.set("spn_refresh", first_cookie, path="/api/v1/auth")
    reuse = client.post("/api/v1/auth/refresh")
    assert reuse.status_code == 401

    client.cookies.set("spn_refresh", second_cookie, path="/api/v1/auth")
    after_reuse = client.post("/api/v1/auth/refresh")
    assert after_reuse.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient, db_session: Session) -> None:
    create_user(db_session, email="logout@example.com")
    client.post(LOGIN, json={"email": "logout@example.com", "password": DEFAULT_PASSWORD})

    logout = client.post("/api/v1/auth/logout")
    assert logout.status_code == 204

    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_without_cookie_returns_unauthenticated(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")

    assert response.status_code == 401


def test_register_is_rate_limited(client: TestClient) -> None:
    for index in range(5):
        response = client.post(REGISTER, json=register_payload(f"rl-{index}@example.com"))
        assert response.status_code == 201

    limited = client.post(REGISTER, json=register_payload("rl-6@example.com"))

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert int(limited.headers["retry-after"]) >= 1


REGISTER_VENDOR = "/api/v1/auth/register-vendor"


def register_vendor_payload(email: str = "shop@example.com") -> dict[str, object]:
    return {
        "email": email,
        "password": DEFAULT_PASSWORD,
        "full_name": "Shop Owner",
        "shop_name": "A Print Shop",
        "shop_address": "1 Test Street",
        "latitude": 22.5726,
        "longitude": 88.3639,
    }


def test_register_vendor_creates_a_shop(client: TestClient) -> None:
    response = client.post(REGISTER_VENDOR, json=register_vendor_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == "vendor"
    assert body["shop"]["name"] == "A Print Shop"
    assert body["shop"]["is_verified"] is False


def test_register_vendor_with_a_duplicate_email_is_rejected(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="taken@example.com")

    response = client.post(REGISTER_VENDOR, json=register_vendor_payload("taken@example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_vendor_with_a_duplicate_email_is_rejected_case_insensitively(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="taken@example.com")

    response = client.post(REGISTER_VENDOR, json=register_vendor_payload("TAKEN@example.com"))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_register_vendor_with_a_duplicate_email_leaves_no_shop_behind(
    client: TestClient, db_session: Session
) -> None:
    from app.models import Shop
    from sqlalchemy import func, select

    create_user(db_session, email="taken@example.com")
    before = db_session.scalar(select(func.count()).select_from(Shop))

    client.post(REGISTER_VENDOR, json=register_vendor_payload("taken@example.com"))

    after = db_session.scalar(select(func.count()).select_from(Shop))
    assert after == before


def test_repeated_logins_for_one_account_are_rate_limited(
    client: TestClient, db_session: Session
) -> None:
    """Guessing one password over and over is stopped."""
    create_user(db_session, email="victim@example.com")

    for _ in range(10):
        client.post(
            LOGIN,
            json={"email": "victim@example.com", "password": "wrong-password"},
        )

    limited = client.post(LOGIN, json={"email": "victim@example.com", "password": "wrong-password"})

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_logins_for_different_accounts_from_one_address_are_allowed(
    client: TestClient, db_session: Session
) -> None:
    """A college puts every student behind one address.

    One student signing in must not lock the rest of the campus out, so
    the limit for an account and the limit for the whole address are
    counted separately.
    """
    for index in range(6):
        email = f"student{index}@example.com"
        create_user(db_session, email=email)
        response = client.post(LOGIN, json={"email": email, "password": DEFAULT_PASSWORD})
        assert response.status_code == 200, response.text
