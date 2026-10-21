from typing import Any

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """The body of every failed request."""

    code: str = Field(description="Stable machine readable code, for example NOT_FOUND.")
    message: str = Field(description="Human readable message, safe to show to a user.")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra detail for the caller, for example the current price.",
    )
    request_id: str = Field(description="Identifier for this request, for support.")


class ErrorResponse(BaseModel):
    error: ErrorBody


def _response(description: str) -> dict[str, Any]:
    return {"model": ErrorResponse, "description": description}


# The error responses every endpoint can return. Documenting them makes
# the OpenAPI contract honest: a client generated from it knows which
# failures to expect, and the contract test can check them.
#: The answer when the identity provider could not be read. It is
#: not in the list above, because most of the API does not talk to the
#: provider and should not claim that it can fail this way.
PROVIDER_UNAVAILABLE_RESPONSE = _response(
    "The identity provider could not be reached. Try again in a moment."
)

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: _response("The request was rejected, for example a wrong pickup code."),
    401: _response("The access token is missing or expired."),
    403: _response("This account may not do that."),
    404: _response("Not found, or not yours. The two are deliberately the same."),
    409: _response("The state moved on, for example the price changed."),
    422: _response("The request body did not validate."),
    429: _response("Too many requests. The response carries a Retry-After header."),
}
