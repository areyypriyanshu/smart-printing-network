"""The real verifier: tokens signed by the identity provider.

The provider publishes its public keys at a well known address, and
signs every session token with a private key that never leaves it. The
application fetches the public keys, finds the one the token names, and
checks the signature.

Four things are checked, and the order matters. The algorithm is
checked first, so that a token asking to be read as something else is
refused before anything is interpreted. Then the signature, which is
the only check that proves the token came from the provider. Then the
issuer, so that a token from a different instance is refused. Then the
origin, so that a token minted for another application on the same
instance is refused.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
from jwt.algorithms import RSAAlgorithm

from app.errors import Unauthenticated
from app.gateways.identity.base import VerifiedIdentity

#: The only signature algorithm this application accepts. A provider
#: that can sign with something else must not be able to talk the
#: application into accepting it.
ALLOWED_ALGORITHMS = ("RS256",)

#: How far the clock is allowed to be wrong, in seconds. A token that
#: expired a second ago is accepted, because the machines do not agree
#: on the time to the second.
LEEWAY_SECONDS = 5

#: How long a fetched key set is used before it is fetched again, in
#: seconds.
JWKS_LIFETIME_SECONDS = 300


@dataclass(frozen=True)
class Jwk:
    """One public key, as the provider published it."""

    kid: str
    key: Any


class JwksCache:
    """The provider's public keys, kept so a request does not need a fetch.

    The key set is fetched once and used for a few minutes, because a
    fetch on every request would make the application depend on the
    provider's response time for every call.

    When a fetch fails, the last set that was fetched is used. A
    provider that is briefly unreachable should not sign everybody out:
    the keys do not change often, and a token that was signed with a key
    that has since been withdrawn is a problem the provider's own
    revocation is for. A token that is signed with a key this cache has
    never seen is refused, whether the fetch worked or not.
    """

    def __init__(
        self,
        url: str,
        *,
        lifetime_seconds: int = JWKS_LIFETIME_SECONDS,
        timeout_seconds: int = 15,
    ) -> None:
        self._url = url
        self._lifetime = lifetime_seconds
        self._timeout = timeout_seconds
        self._keys: dict[str, Jwk] = {}
        self._fetched_at: float = 0.0

    def key_for(self, kid: str) -> Jwk:
        """The key with this identifier.

        Raises `Unauthenticated` when there is no such key, including
        when the key set could not be fetched and the last known one
        does not have it.
        """
        keys = self._current_keys()
        key = keys.get(kid)
        if key is None:
            raise Unauthenticated("Invalid or expired token")
        return key

    def _current_keys(self) -> dict[str, Jwk]:
        now = time.monotonic()
        if self._keys and (now - self._fetched_at) < self._lifetime:
            return self._keys
        try:
            keys = self._fetch()
        except (OSError, ValueError, urllib.error.URLError):
            if self._keys:
                # The provider could not be reached and there is a set
                # from before. It is used, and the next request tries
                # again.
                return self._keys
            raise Unauthenticated("Invalid or expired token") from None
        self._keys = keys
        self._fetched_at = now
        return keys

    def _fetch(self) -> dict[str, Jwk]:
        request = urllib.request.Request(self._url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=self._timeout) as response:
            body = response.read()
        document = json.loads(body)
        entries = document.get("keys")
        if not isinstance(entries, list):
            raise ValueError("the key set has no keys in it")
        keys: dict[str, Jwk] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            kid = entry.get("kid")
            if not isinstance(kid, str) or not kid:
                continue
            # A key that is not for signing, or that is not the
            # algorithm this application accepts, is not used.
            if entry.get("use") not in (None, "sig"):
                continue
            if entry.get("alg") not in (None, *ALLOWED_ALGORITHMS):
                continue
            keys[kid] = Jwk(kid=kid, key=RSAAlgorithm.from_jwk(json.dumps(entry)))
        if not keys:
            raise ValueError("the key set holds no usable key")
        return keys


class ClerkTokenVerifier:
    """Turns a provider session token into the identity it names."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        allowed_origins: tuple[str, ...],
        jwks_cache: JwksCache | None = None,
    ) -> None:
        self._issuer = issuer.rstrip("/")
        self._allowed_origins = frozenset(allowed_origins)
        self._jwks = jwks_cache if jwks_cache is not None else JwksCache(jwks_url)

    @property
    def allowed_origins(self) -> frozenset[str]:
        return self._allowed_origins

    def verify(self, token: str) -> VerifiedIdentity:
        """The identity the token names, or a refusal.

        The claims are read without trusting them first, so that the
        algorithm and the key are known before anything the token says
        is acted on.
        """
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise Unauthenticated("Invalid or expired token") from exc

        algorithm = header.get("alg")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise Unauthenticated("Invalid or expired token")

        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise Unauthenticated("Invalid or expired token")

        key = self._jwks.key_for(kid)

        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=list(ALLOWED_ALGORITHMS),
                options={
                    "verify_aud": False,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iss": False,
                    "require": ["sub", "iss", "exp"],
                },
                leeway=LEEWAY_SECONDS,
            )
        except jwt.InvalidTokenError as exc:
            raise Unauthenticated("Invalid or expired token") from exc

        issuer = claims.get("iss")
        if not isinstance(issuer, str) or issuer.rstrip("/") != self._issuer:
            raise Unauthenticated("Invalid or expired token")

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject:
            raise Unauthenticated("Invalid or expired token")

        origin = claims.get("azp")
        if origin is not None and (
            not isinstance(origin, str) or origin not in self._allowed_origins
        ):
            # The token was minted for an address this deployment does
            # not serve. It is refused for the same reason a foreign
            # signature is: it is not a token for this application.
            raise Unauthenticated("Invalid or expired token")
        # A token that names no origin is one the provider minted for
        # something other than a browser, and the provider's own API is
        # the only way to get one: it takes the instance's secret key.
        # The secret key can already do everything this application can
        # do, and more, so refusing such a token would break the
        # machine's use of the instance without closing a way in.

        session_id = claims.get("sid")
        return VerifiedIdentity(
            subject=subject,
            session_id=session_id if isinstance(session_id, str) else None,
            origin=origin if isinstance(origin, str) else None,
        )
