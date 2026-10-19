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
    assert response.json() == {"status": "ok", "database": "ok"}
