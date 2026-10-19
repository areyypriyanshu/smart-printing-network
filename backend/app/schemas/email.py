import re
from typing import Annotated

from pydantic import AfterValidator
from pydantic.json_schema import WithJsonSchema

# A syntactically plausible address: something, an at sign, and a domain
# with at least one dot in it.
#
# The app sends no email in Phase 1. Notifications are out of scope, so an
# address is only a login name and a display name, and what actually
# matters is that it is unique, which the database enforces. Reserving
# whole top level domains would therefore buy nothing, while it would
# make the published OpenAPI contract disagree with the server: the
# contract says "format: email" and the fuzzer proved that a string
# matching that format was refused. The rule here is exactly what the
# contract says it is.
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


def _looks_like_an_email(value: str) -> str:
    if len(value) > 254 or not EMAIL_PATTERN.fullmatch(value):
        raise ValueError("value is not a valid email address")
    return value


Email = Annotated[
    str,
    AfterValidator(_looks_like_an_email),
    WithJsonSchema({"type": "string", "format": "email"}),
]
