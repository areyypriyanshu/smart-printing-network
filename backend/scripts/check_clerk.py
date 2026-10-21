"""Check that the Clerk instance is set up the way this project needs it.

This is the "is it working?" tool for the identity provider, and it
answers two different questions:

1. Is the instance reachable and shaped the way the backend expects?
   That is: the Frontend API URL is the one we were given, the public
   key set is published there, the key set is RSA, and the origins the
   deployment allows are the ones it should be.

2. Is a particular session token a token this application would
   accept? That is: the signature verifies against the instance's own
   public key, the issuer is this instance, the origin is one we
   allow, the token is inside its lifetime, and it names a user.

The second check is the one that matters most, because it is exactly
what the backend will do with a real request. The checks here are the
same ones the token verifier will make, so a token that passes here
will pass there, and a token that fails here fails for a reason worth
reading.

Usage:

    # Is the instance set up correctly?
    CLERK_FAPI_URL=https://your-app.clerk.accounts.dev \\
        uv run python scripts/check_clerk.py

    # Is this token one we would accept?
    CLERK_FAPI_URL=https://your-app.clerk.accounts.dev \\
        uv run python scripts/check_clerk.py --token "$CLERK_TOKEN"

    # ... and is it from an origin we allow?
    CLERK_FAPI_URL=https://your-app.clerk.accounts.dev \\
        CLERK_ALLOWED_ORIGINS=http://localhost:5173 \\
        uv run python scripts/check_clerk.py --token "$CLERK_TOKEN"

Exit status is 0 when every check passed and 1 when one did not, so
it can be used in a script.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWKClientError

#: How long to wait for the key set. A key set is small and the
#: instance is usually close, so a slow answer is a real answer.
FETCH_TIMEOUT_SECONDS = 15

#: The algorithm Clerk signs with. It is the only one allowed, so a
#: token that asks for something else is refused rather than checked
#: with a key that was never meant to verify it.
ALLOWED_ALGORITHMS = ["RS256"]

#: The clock skew allowed on the lifetime claims, in seconds. A token
#: that expired four seconds ago is not a security problem; a token
#: that looks expired because two clocks disagree is a broken setup.
CLOCK_SKEW_SECONDS = 5


class Report:
    """The checks, and whether they passed.

    A check is a line of prose and a truth value. The prose says what
    was expected and what was found, so a failure explains itself
    without a stack trace.
    """

    def __init__(self) -> None:
        self.lines: list[tuple[bool, str]] = []
        self.details: list[str] = []

    def add(self, passed: bool, message: str) -> None:
        self.lines.append((passed, message))

    def detail(self, text: str) -> None:
        self.details.append(text)

    @property
    def ok(self) -> bool:
        return all(passed for passed, _ in self.lines)

    def print(self) -> None:
        for passed, message in self.lines:
            mark = "ok  " if passed else "FAIL"
            print(f"  [{mark}] {message}")
        for text in self.details:
            print(text)


def _fetch_json(url: str) -> Any:
    """Fetch a JSON document, or raise with the reason."""
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def check_instance(fapi_url: str, allowed_origins: list[str], report: Report) -> None:
    """The instance is reachable and shaped the way the backend expects."""
    print(f"\nInstance: {fapi_url}")

    jwks_url = f"{fapi_url.rstrip('/')}/.well-known/jwks.json"
    print(f"Key set:  {jwks_url}\n")

    try:
        key_set = _fetch_json(jwks_url)
    except urllib.error.HTTPError as exc:
        report.add(False, f"the key set could not be fetched: HTTP {exc.code} {exc.reason}")
        return
    except urllib.error.URLError as exc:
        report.add(False, f"the key set could not be reached: {exc.reason}")
        return

    keys = key_set.get("keys") if isinstance(key_set, dict) else None
    if not isinstance(keys, list) or not keys:
        report.add(False, "the key set is empty, so no token could ever be verified")
        return
    report.add(True, f"the key set is published and holds {len(keys)} key(s)")

    algorithms = {key.get("alg") for key in keys if isinstance(key, dict)}
    report.add(
        algorithms <= set(ALLOWED_ALGORITHMS) and bool(algorithms),
        f"the key set signs with {sorted(a for a in algorithms if a)}, "
        f"and the backend allows {ALLOWED_ALGORITHMS}",
    )

    key_ids = [key.get("kid") for key in keys if isinstance(key, dict) and key.get("kid")]
    report.add(
        bool(key_ids),
        "the keys are named, so a token can be matched to one: "
        f"{', '.join(str(k) for k in key_ids)}",
    )

    if allowed_origins:
        report.add(
            True,
            f"the deployment allows {len(allowed_origins)} origin(s): {', '.join(allowed_origins)}",
        )
    else:
        report.add(
            False,
            "no origin is configured, so no token could be accepted. "
            "Set CLERK_ALLOWED_ORIGINS to the address the front end is served from.",
        )


def check_token(
    fapi_url: str,
    allowed_origins: list[str],
    token: str,
    report: Report,
) -> None:
    """This token is one the backend would accept."""
    print(f"\nToken: {token[:24]}... ({len(token)} characters)\n")

    jwks_url = f"{fapi_url.rstrip('/')}/.well-known/jwks.json"
    try:
        client = PyJWKClient(
            jwks_url,
            cache_keys=True,
            cache_jwk_set=True,
            lifespan=300,
            cooldown_duration=30,
            timeout=FETCH_TIMEOUT_SECONDS,
        )
        signing_key = client.get_signing_key_from_jwt(token)
    except PyJWKClientError as exc:
        report.add(False, f"the token does not match any published key: {exc}")
        return
    except Exception as exc:  # noqa: BLE001 - the reason is reported, not raised
        report.add(False, f"the key set could not be read: {exc}")
        return

    report.add(True, f"the signature verifies against key {signing_key.key_id}")

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=None,
            options={
                "verify_aud": False,
                "verify_exp": True,
                "verify_nbf": True,
                "require": ["sub", "iss", "exp"],
            },
            leeway=CLOCK_SKEW_SECONDS,
        )
    except jwt.ExpiredSignatureError:
        report.add(False, "the token has expired")
        return
    except jwt.InvalidTokenError as exc:
        report.add(False, f"the token is not valid: {exc}")
        return

    report.add(True, "the signature, the lifetime and the required claims are all good")

    issuer = claims.get("iss")
    report.add(
        issuer == fapi_url.rstrip("/"),
        f"the issuer is {issuer}, and this instance is {fapi_url.rstrip('/')}",
    )

    origin = claims.get("azp")
    if origin is None:
        report.add(
            bool(allowed_origins),
            "the token names no origin, so there is nothing to check it against",
        )
    elif allowed_origins:
        report.add(
            origin in allowed_origins,
            f"the token was minted for {origin}, and the deployment allows "
            f"{', '.join(allowed_origins)}",
        )
    else:
        report.add(False, f"the token was minted for {origin}, and no origin is allowed")

    subject = claims.get("sub")
    if isinstance(subject, str) and subject != "":
        report.add(
            True,
            f"the token names the user {subject!r}, and that is the key the "
            "local account is found by",
        )
    else:
        report.add(
            False,
            "the token names no user, and that is the key the local account is found by",
        )

    lines = ["\nClaims:"]
    for name in sorted(claims):
        value = claims[name]
        if isinstance(value, str) and len(value) > 60:
            value = value[:57] + "..."
        lines.append(f"  {name:>6} = {value}")
    report.detail("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check that the Clerk instance is set up the way this project needs it, "
            "and that a given session token is one the backend would accept."
        ),
        epilog=(
            "Examples:\n"
            "  # Is the instance set up correctly?\n"
            "  CLERK_FAPI_URL=https://your-app.clerk.accounts.dev \\\n"
            "      uv run python scripts/check_clerk.py\n"
            "\n"
            "  # Is this token one we would accept?\n"
            "  CLERK_FAPI_URL=https://your-app.clerk.accounts.dev \\\n"
            '      uv run python scripts/check_clerk.py --token "$CLERK_TOKEN"\n'
            "\n"
            "  # ... and is it from an origin we allow?\n"
            "  CLERK_FAPI_URL=https://your-app.clerk.accounts.dev \\\n"
            "  CLERK_ALLOWED_ORIGINS=http://localhost:5173 \\\n"
            '      uv run python scripts/check_clerk.py --token "$CLERK_TOKEN"\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--token",
        default="",
        help="a session token to check. Without it, only the instance is checked.",
    )
    parser.add_argument(
        "--fapi-url",
        default=os.environ.get("CLERK_FAPI_URL", ""),
        help="the Frontend API URL. Defaults to CLERK_FAPI_URL.",
    )
    parser.add_argument(
        "--origins",
        default=os.environ.get("CLERK_ALLOWED_ORIGINS", ""),
        help="the origins whose tokens are accepted, comma separated. "
        "Defaults to CLERK_ALLOWED_ORIGINS.",
    )
    args = parser.parse_args()

    if not args.fapi_url:
        print(
            "No Frontend API URL. Set CLERK_FAPI_URL, or pass --fapi-url.\n"
            "It is on the Clerk Dashboard, at API keys, and it is the address\n"
            "in the Publishable Key: pk_test_<base64> decodes to it.",
            file=sys.stderr,
        )
        return 1

    origins = [origin.strip() for origin in args.origins.split(",") if origin.strip()]

    report = Report()
    check_instance(args.fapi_url, origins, report)
    if args.token:
        check_token(args.fapi_url, origins, args.token, report)
    report.print()

    print("\n" + ("All checks passed." if report.ok else "Some checks failed."))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
