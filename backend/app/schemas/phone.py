"""Phone numbers.

A shop's phone number is how a customer reaches the shop that is
printing their project, so it has to be a number a person can dial.

The rule is deliberately loose about the shape and strict about the
digits, because the same number is written down in many ways: with
spaces, with dashes, with brackets, with a country code. Anything that
holds between 7 and 15 digits is a phone number.
"""

import re
from typing import Annotated

from pydantic import AfterValidator, WithJsonSchema

PHONE_PATTERN = re.compile(r"^[0-9+() .-]{7,25}$")
MIN_DIGITS = 7
MAX_DIGITS = 15


def _looks_like_a_phone(value: str) -> str:
    stripped = value.strip()
    if not PHONE_PATTERN.match(stripped):
        raise ValueError("That does not look like a phone number")
    digits = re.sub(r"\D", "", stripped)
    if not MIN_DIGITS <= len(digits) <= MAX_DIGITS:
        raise ValueError(f"A phone number has between {MIN_DIGITS} and {MAX_DIGITS} digits")
    return stripped


Phone = Annotated[
    str,
    AfterValidator(_looks_like_a_phone),
    WithJsonSchema({"type": "string", "format": "phone"}),
]
