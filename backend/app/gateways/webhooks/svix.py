"""Checking that a webhook really came from the identity provider.

The provider signs each delivery with a key it holds and the application
holds a copy of. The signature covers the message id, the timestamp and
the body, so a body that has been changed, a message that has been
replayed from another message, and a delivery that did not come from the
provider are all refused.

The comparison is constant time, because a signature that is compared
one byte at a time leaks how many leading bytes were right.
"""

import base64
import hashlib
import hmac
import time

#: How far a delivery's timestamp may be from the clock, in seconds. A
#: delivery that is older than this is refused, so that a signature that
#: was captured cannot be replayed later.
TIMESTAMP_TOLERANCE_SECONDS = 300

#: The version of the signature this application accepts.
SIGNATURE_VERSION = "v1"


def secret_bytes(signing_secret: str) -> bytes:
    """The key the provider signs with, from the secret it gave us.

    The secret is the word `whsec` and then the key in base64. Both
    alphabets are accepted, because a base64 string with a dash or an
    underscore in it is not standard base64 and would otherwise be read
    as the wrong key.
    """
    raw = signing_secret.split("_", 1)[1] if "_" in signing_secret else signing_secret
    raw = raw.replace("-", "+").replace("_", "/")
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.b64decode(raw)
    except (ValueError, TypeError):
        return b""


def signed_content(*, message_id: str, timestamp: str, body: bytes) -> bytes:
    """What the provider signed.

    It is the message id, the timestamp and the body, joined with full
    stops. The body is the raw body, byte for byte: a body that has
    been parsed and put back together is not the body that was signed.
    """
    return b".".join([message_id.encode("utf-8"), timestamp.encode("utf-8"), body])


def expected_signature(*, signing_secret: str, message_id: str, timestamp: str, body: bytes) -> str:
    """The signature the provider should have sent, in base64."""
    key = secret_bytes(signing_secret)
    content = signed_content(message_id=message_id, timestamp=timestamp, body=body)
    digest = hmac.new(key, content, hashlib.sha256)
    return base64.b64encode(digest.digest()).decode("ascii")


def verify_signature(
    *,
    signing_secret: str,
    message_id: str | None,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now: float | None = None,
    tolerance_seconds: int = TIMESTAMP_TOLERANCE_SECONDS,
) -> bool:
    """Whether the delivery carries a signature this application accepts.

    Every part of the delivery is needed: the id, the timestamp and the
    signature itself. A delivery that is missing one of them is
    refused, because a missing part cannot be checked.
    """
    if not message_id or not timestamp or not signature:
        return False
    if not secret_bytes(signing_secret):
        return False

    # The timestamp has to be close to now, so that a captured delivery
    # cannot be sent again later.
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False
    current = time.time() if now is None else now
    if abs(current - sent_at) > tolerance_seconds:
        return False

    expected = expected_signature(
        signing_secret=signing_secret, message_id=message_id, timestamp=timestamp, body=body
    )

    # The header holds a list of signatures, each with its version in
    # front of it. Any one of them matching is enough.
    for part in signature.split(" "):
        version, _, value = part.partition(",")
        if version != SIGNATURE_VERSION or not value:
            continue
        if hmac.compare_digest(expected, value):
            return True
    return False
