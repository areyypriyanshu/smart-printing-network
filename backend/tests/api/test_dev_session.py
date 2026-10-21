"""The local way in, which the end to end suite signs in through.

It is a route like any other, and it is held to the same rules: a
request that cannot be answered is answered with a refusal rather than
with a server error, and two requests for the same account at the same
time do not fight over it.
"""

import pytest
from app.errors import Conflict
from app.models import User
from app.services import identity_service
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

DEV_SESSION = "/api/v1/auth/dev-session"


def test_the_local_way_in_makes_the_account(client: TestClient) -> None:
    response = client.post(DEV_SESSION, json={"email": "made@example.com", "full_name": "Made"})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"].startswith("fake:")


def test_the_local_way_in_signs_the_same_account_in_again(client: TestClient) -> None:
    first = client.post(DEV_SESSION, json={"email": "again@example.com"})
    second = client.post(DEV_SESSION, json={"email": "again@example.com"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["access_token"] == second.json()["access_token"]


def test_the_local_way_in_refuses_a_shop_with_no_place(client: TestClient) -> None:
    """A shop needs a name, an address and a place.

    The refusal is a conflict and not a server error, because the
    request is wrong and not the server.
    """
    response = client.post(DEV_SESSION, json={"email": "shop@example.com", "role": "vendor"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_the_local_way_in_recovers_from_a_lost_race(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two requests for the same account at the same time.

    The fuzzer sends the same request from four workers at once, and
    the one that loses the race used to answer with a server error
    rather than with the account the other one made. The answer is
    found by reading the account again.
    """
    made = client.post(DEV_SESSION, json={"email": "race@example.com"})
    assert made.status_code == 200

    real_find = identity_service.find_by_email
    looks = {"count": 0}

    def lose_the_race(*args: object, **kwargs: object) -> User:
        """The address is taken; the other request made it."""
        raise Conflict("An account already uses that email address")

    def find_after_the_race(session: Session, email: str) -> User | None:
        """The first look says the account is not there; the second finds it."""
        looks["count"] += 1
        if looks["count"] == 1:
            return None
        return real_find(session, email)

    monkeypatch.setattr(identity_service, "create_account", lose_the_race)
    monkeypatch.setattr(identity_service, "find_by_email", find_after_the_race)

    response = client.post(DEV_SESSION, json={"email": "race@example.com"})

    assert response.status_code == 200
    assert response.json()["access_token"].startswith("fake:")


def test_the_local_way_in_is_refused_when_it_is_switched_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is a local tool, and a deployment that is not local cannot have it."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "spn_dev_auth", False)

    response = client.post(DEV_SESSION, json={"email": "closed@example.com"})

    assert response.status_code == 404
