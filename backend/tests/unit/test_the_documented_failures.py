"""The failures every route says it can answer.

A route that does not say it can be refused is a route whose refusals
are a surprise, and the contract run finds that: it sends a request
that is too large, or one that is refused, and answers with a status
the contract does not mention.

The check is on the schema the application produces, which is the one
a client is built from.
"""

from app.main import create_app
from app.schemas.errors import ERROR_RESPONSES

# The routes that do not carry the shared failures, and what they
# carry instead.
EXCEPTIONS = {
    # The health check asks nothing of the caller and reads nothing of
    # theirs, so it has one failure of its own: the database or the
    # object store is not reachable.
    "/healthz": {503},
    "/readyz": {503},
}


def _documented() -> dict[str, set[int]]:
    """The statuses every route says it can answer."""
    app = create_app(enable_transition_listener=False)
    schema = app.openapi()
    documented: dict[str, set[int]] = {}
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            documented[f"{method.upper()} {path}"] = {
                int(status) for status in operation["responses"]
            }
    return documented


def test_every_route_says_how_it_can_be_refused() -> None:
    """Every route but the few that say so carries the shared failures.

    The size of a request is refused before a route is reached, so
    every route that takes a body can answer that, and the shared
    failures are what a route that is not found, not allowed or not
    valid answers with.
    """
    documented = _documented()

    for name, statuses in documented.items():
        path = name.split(" ", 1)[1]
        expected = EXCEPTIONS.get(path, set(ERROR_RESPONSES))
        missing = expected - statuses
        assert not missing, f"{name} does not say it can answer {sorted(missing)}"


def test_the_contract_knows_the_same_routes() -> None:
    """The schema the contract run reads is the one the application makes."""
    app = create_app(enable_transition_listener=False)
    schema = app.openapi()

    assert "/api/v1/webhooks/clerk" in schema["paths"]
    assert "/api/v1/auth/onboarding" in schema["paths"]
    # And the old sign in is gone: the provider holds the password now.
    assert "/api/v1/auth/login" not in schema["paths"]
    assert "/api/v1/auth/register" not in schema["paths"]
