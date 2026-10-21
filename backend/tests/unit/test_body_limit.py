"""The limit on the size of a request body.

The multipart parser runs before the route's dependencies, so a body that
is larger than the platform will accept is written to the container's
disk before anybody gets a chance to refuse it. The limit therefore has
to be applied to the stream, not to the parsed form.
"""

from app.main import ENVELOPE_BYTES, BodyLimitMiddleware
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route


async def _echo_length(request):  # type: ignore[no-untyped-def]
    body = await request.body()
    return PlainTextResponse(str(len(body)))


def _client(max_bytes: int) -> TestClient:
    app = Starlette(routes=[Route("/", _echo_length, methods=["POST"])])
    app.add_middleware(BodyLimitMiddleware, max_bytes=max_bytes)
    return TestClient(app)


def test_a_body_inside_the_limit_goes_through() -> None:
    client = _client(1024)

    response = client.post("/", content=b"x" * 512)

    assert response.status_code == 200
    assert response.text == "512"


def test_a_body_over_the_limit_is_refused() -> None:
    client = _client(1024)

    response = client.post("/", content=b"x" * 2048)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_a_body_over_the_limit_is_refused_in_the_usual_shape() -> None:
    """The refusal is a failure like every other failure.

    A caller reads a failure the same way whichever limit refused it,
    so the body has the same fields the other failures have, including
    the request id.
    """
    client = _client(1024)

    response = client.post("/", content=b"x" * 2048)

    body = response.json()["error"]
    assert set(body) == {"code", "message", "details", "request_id"}
    assert body["message"]


def test_a_body_that_says_it_is_over_the_limit_is_refused() -> None:
    """A declared length is refused before the body is read.

    The body never reaches the parser, so nothing is written to disk.
    """
    client = _client(1024)

    response = client.post("/", content=b"x" * 16, headers={"Content-Length": "100000"})

    assert response.status_code == 413


def test_the_limit_leaves_room_for_the_multipart_envelope() -> None:
    """The limit on the request is above the limit on the file.

    The envelope is the part headers, the boundaries and the form fields,
    so a request limit that was exactly the file limit would refuse every
    file that was exactly at the limit.
    """
    assert ENVELOPE_BYTES == 1024 * 1024
    assert ENVELOPE_BYTES > 0
