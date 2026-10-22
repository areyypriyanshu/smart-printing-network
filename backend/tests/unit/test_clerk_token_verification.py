"""The checks the identity provider's tokens have to pass.

These are the tests for the part of the application that decides
whether a token is one it accepts. A token that is not accepted is
refused with the same answer whatever was wrong with it, so a caller
cannot tell a malformed token from an expired one from a foreign one.
"""

import base64
import json
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import jwt
import pytest
from app.errors import Unauthenticated
from app.gateways.identity.clerk import (
    ALLOWED_ALGORITHMS,
    ClerkTokenVerifier,
    JwksCache,
)

ISSUER = "https://instance.clerk.accounts.dev"
JWKS_URL = "https://instance.clerk.accounts.dev/.well-known/jwks.json"
ALLOWED_ORIGIN = "http://localhost:5173"


def _key_pair() -> tuple[str, dict[str, object]]:
    """A signing key and its public half, in the shape a provider uses."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    return private_pem, public_jwk


def _token(
    private_pem: str,
    *,
    kid: str = "ins_test",
    issuer: str = ISSUER,
    origin: str | None = ALLOWED_ORIGIN,
    subject: str = "user_abc",
    expires_in: int = 60,
    algorithm: str = "RS256",
) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": subject,
        "iss": issuer,
        "iat": now,
        "nbf": now,
        "exp": now + expires_in,
    }
    if origin is not None:
        claims["azp"] = origin
    return jwt.encode(claims, private_pem, algorithm=algorithm, headers={"kid": kid})


class _JwksHandler(BaseHTTPRequestHandler):
    """Serves a key set, so that the cache can be tested without a network."""

    keys: list[dict[str, object]] = []

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"keys": self.keys}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


class _Jwks:
    """A key set being served, and the server serving it."""

    def __init__(self) -> None:
        self.keys: list[dict[str, object]] = []
        self.server = HTTPServer(("127.0.0.1", 0), _JwksHandler)
        _JwksHandler.keys = self.keys
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/.well-known/jwks.json"

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def publish(self, kid: str = "ins_test") -> str:
        """A published key, and the private half that signs with it."""
        private_pem, public_jwk = _key_pair()
        public_jwk["kid"] = kid
        self.keys.append(public_jwk)
        return private_pem


@pytest.fixture
def jwks_server() -> Iterator[_Jwks]:
    server = _Jwks()
    yield server
    server.stop()


def _verifier(jwks_url: str, *, origins: tuple[str, ...] = (ALLOWED_ORIGIN,)) -> ClerkTokenVerifier:
    return ClerkTokenVerifier(jwks_url=jwks_url, issuer=ISSUER, allowed_origins=origins)


def test_a_token_signed_by_the_provider_is_accepted(jwks_server: _Jwks) -> None:
    private_pem = jwks_server.publish()

    identity = _verifier(jwks_server.url).verify(_token(private_pem))

    assert identity.subject == "user_abc"


def test_a_token_signed_by_somebody_else_is_refused(jwks_server: _Jwks) -> None:
    jwks_server.publish()
    other_private, _ = _key_pair()

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify(_token(other_private))


def test_a_token_that_has_expired_is_refused(jwks_server: _Jwks) -> None:
    private_pem = jwks_server.publish()

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify(_token(private_pem, expires_in=-600))


def test_a_token_from_another_instance_is_refused(jwks_server: _Jwks) -> None:
    private_pem = jwks_server.publish()

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify(
            _token(private_pem, issuer="https://other.clerk.accounts.dev")
        )


def test_a_token_minted_for_another_origin_is_refused(jwks_server: _Jwks) -> None:
    """A token for another application on the same instance is not this one's."""
    private_pem = jwks_server.publish()

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify(_token(private_pem, origin="https://other.example.com"))


def test_a_token_that_names_no_origin_is_accepted(jwks_server: _Jwks) -> None:
    """The origin names the application a token was minted for.

    A token that names none is one the provider minted for something
    other than a browser, and the provider's own API is the only way
    to get one: it takes the instance's secret key, and the secret key
    can already do everything this application can do and more. So a
    token like that is not a way in that was not there before, and
    refusing it would break the machine's own use of the instance for
    no gain.
    """
    private_pem = jwks_server.publish()
    token = _token(private_pem, origin=None)

    identity = _verifier(jwks_server.url).verify(token)

    assert identity.subject == "user_abc"
    assert identity.origin is None


def test_a_token_with_no_subject_is_refused(jwks_server: _Jwks) -> None:
    private_pem = jwks_server.publish()
    token = jwt.encode(
        {"iss": ISSUER, "exp": int(time.time()) + 60},
        private_pem,
        algorithm="RS256",
        headers={"kid": "ins_test"},
    )

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify(token)


def test_a_token_that_names_a_key_the_provider_does_not_have_is_refused(
    jwks_server: _Jwks,
) -> None:
    private_pem = jwks_server.publish()

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify(_token(private_pem, kid="ins_never_published"))


def test_something_that_is_not_a_token_is_refused(jwks_server: _Jwks) -> None:
    jwks_server.publish()

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify("not-a-token")


def test_a_token_asking_to_be_read_as_another_algorithm_is_refused(
    jwks_server: _Jwks,
) -> None:
    """The algorithm is checked before anything the token says is read.

    This is the oldest attack against a token verifier: a token that
    says it was signed with nothing at all, and carries no signature.
    """
    jwks_server.publish()
    header = {"alg": "none", "typ": "JWT", "kid": "ins_test"}
    payload = {"sub": "user_abc", "iss": ISSUER, "exp": int(time.time()) + 60}

    def segment(value: dict[str, object]) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    forged = f"{segment(header)}.{segment(payload)}."

    with pytest.raises(Unauthenticated):
        _verifier(jwks_server.url).verify(forged)


def test_the_key_set_is_fetched_once_and_kept(jwks_server: _Jwks) -> None:
    """A request must not cost a fetch every time."""
    jwks_server.publish()
    cache = JwksCache(jwks_server.url)

    first = cache.key_for("ins_test")
    second = cache.key_for("ins_test")

    assert first is second


def test_the_last_known_keys_are_used_when_the_provider_cannot_be_reached(
    jwks_server: _Jwks,
) -> None:
    """A provider that is briefly unreachable should not sign everybody out."""
    jwks_server.publish()
    cache = JwksCache(jwks_server.url, lifetime_seconds=0)
    cache.key_for("ins_test")

    # The provider is gone now, so the next fetch cannot work.
    jwks_server.stop()

    assert cache.key_for("ins_test").kid == "ins_test"


def test_only_rs256_is_allowed() -> None:
    assert ALLOWED_ALGORITHMS == ("RS256",)
