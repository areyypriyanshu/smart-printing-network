"""What the API does with a request it cannot answer.

A request that carries a value the database cannot store is the caller's
mistake, not the server's, so it is answered with a 422. A request that
fails for a reason nobody planned for is answered with a 500, and the
answer names the request, so that the log line and the response can be
put next to each other.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DataError

REGISTER = "/api/v1/auth/register"


def register_payload(email: str = "new.user@example.com") -> dict[str, str]:
    return {"email": email, "password": "abcd1234", "full_name": "New User"}


def test_a_server_error_names_the_request_it_came_from(
    client_that_reports_failures: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 500 that cannot be correlated with a request is a 500 nobody can fix."""

    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("something nobody planned for")

    monkeypatch.setattr("app.routers.auth.auth_service.register_customer", explode)

    response = client_that_reports_failures.post(REGISTER, json=register_payload())

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["request_id"]
    assert response.headers["x-request-id"] == body["error"]["request_id"]


def test_a_value_the_database_refuses_is_a_validation_error(
    client_that_reports_failures: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The net under the boundary.

    The boundary is meant to refuse a value the database cannot hold
    before it reaches the insert. This is what happens when one gets
    through anyway: the caller is told what to fix, and the server does
    not report an internal error for the caller's mistake.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise DataError(
            "INSERT INTO users (email) VALUES (%(email)s)",
            {},
            Exception("PostgreSQL text fields cannot contain NUL (0x00) bytes"),
        )

    monkeypatch.setattr("app.routers.auth.auth_service.register_customer", refuse)

    response = client_that_reports_failures.post(REGISTER, json=register_payload())

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["request_id"]
    assert response.headers["x-request-id"] == body["error"]["request_id"]
