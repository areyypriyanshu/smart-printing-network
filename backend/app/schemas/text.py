"""Text that the database is able to hold.

PostgreSQL's `text` type cannot store a NUL byte. A request that carries
one reaches the database as a `DataError`, and the API reports that as an
internal error: a 500 caused by what the user typed, with a stack trace
in the log and no request id on the answer. So every string that is
written to the database is checked here, at the boundary, before it is
passed on.

The rule has two parts, and each part has a reason.

* No control characters. They have no place in a name, an address or a
  reason, and the ones that are invisible are how a string breaks
  something that was not expecting one. Tab and newline are allowed
  where the field is genuinely more than one line.
* No bidi overrides. The Unicode characters that force the text after
  them to be displayed in the opposite direction are how one string is
  made to read as another. A shop name is shown to a customer, and a
  name that reads backwards says something other than what it says.

The invisible characters that real scripts use, a zero width joiner in
Devanagari or a right to left mark in Arabic, are left alone. Those are
letters, not tricks.
"""

from typing import Annotated

from pydantic import AfterValidator

#: The C0 control characters, and DEL.
_CONTROL_CHARACTERS = frozenset(chr(code) for code in range(0x20)) | {chr(0x7F)}

#: The characters a multi line field is allowed to have.
_LINE_BREAKS = frozenset({"\t", "\n"})

#: Nothing at all.
_NO_LINE_BREAKS: frozenset[str] = frozenset()

#: The bidi embedding, override and isolate characters. They change the
#: direction the text after them is displayed in, and nothing else.
_BIDI_OVERRIDES = frozenset(
    chr(code) for code in (0x202A, 0x202B, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069)
)


def _check(value: str, *, allowed: frozenset[str]) -> str:
    for character in value:
        if character in _CONTROL_CHARACTERS and character not in allowed:
            raise ValueError("the value contains a control character")
        if character in _BIDI_OVERRIDES:
            raise ValueError(
                "the value contains a character that changes how the text is displayed"
            )
    return value


def single_line(value: str) -> str:
    """A value the database holds on one line."""
    return _check(value, allowed=_NO_LINE_BREAKS)


def multi_line(value: str) -> str:
    """A value the database holds, which may break the line."""
    return _check(value, allowed=_LINE_BREAKS)


#: A string the database can store, with no line breaks in it.
SingleLine = Annotated[str, AfterValidator(single_line)]

#: A string the database can store, which may break the line.
MultiLine = Annotated[str, AfterValidator(multi_line)]
