from fastapi.testclient import TestClient


def test_healthz_returns_ok_and_echoes_request_id(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-Id": "test-request-id"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["x-request-id"] == "test-request-id"


def test_healthz_generates_request_id_when_header_absent(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["x-request-id"]


def test_healthz_ignores_invalid_request_id_header(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-Id": "bad id with spaces!"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] != "bad id with spaces!"


def test_readyz_reports_database_ok(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "storage": "ok"}


def test_a_body_that_cannot_be_parsed_uses_the_standard_error_shape(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/auth/login",
        content=b"\x7f\xfe\x00%",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "BAD_REQUEST"
    assert "request_id" in body["error"]


def test_an_unknown_route_uses_the_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_wrong_method_uses_the_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/auth/login")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
