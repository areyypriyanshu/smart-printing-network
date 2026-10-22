import logging
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DataError

from app.logging import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)


class AppError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.headers = headers or {}


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422


class Unauthenticated(AppError):
    code = "UNAUTHENTICATED"
    status_code = 401


class Forbidden(AppError):
    code = "FORBIDDEN"
    status_code = 403


class NotFound(AppError):
    code = "NOT_FOUND"
    status_code = 404


class Conflict(AppError):
    code = "CONFLICT"
    status_code = 409


class EmailTaken(AppError):
    code = "EMAIL_TAKEN"
    status_code = 409


class EmailNotVerified(AppError):
    """The address has not been proved yet.

    The customer is signed in and the account works. This one thing
    needs the address to be real, because the address is what the
    printout and the pickup code are tied to.
    """

    code = "EMAIL_NOT_VERIFIED"
    status_code = 403


class InvalidVerificationToken(AppError):
    """The link is not one this server sent, or it is too old to use.

    The answer does not say which of the three it was, so that a link
    cannot be probed to find out whether it was ever valid.
    """

    code = "INVALID_VERIFICATION_TOKEN"
    status_code = 400


class PasswordMismatch(AppError):
    """The password that was given is not the one on the account.

    It is a 422 and not a 401 on purpose. The session is perfectly
    good; it is one field of the request that is wrong, and a 401
    would log the customer out for it.
    """

    code = "PASSWORD_MISMATCH"
    status_code = 422


class AccountNotProvisioned(AppError):
    """The caller has signed in but has not said what they are here for.

    It is not a failure and it is not a refusal: the token is good and
    the person simply has no account yet. The front end reads this and
    sends them to the page that asks.
    """

    status_code = 403
    code = "ACCOUNT_NOT_PROVISIONED"


class ProviderUnavailable(AppError):
    """The identity provider could not be read.

    It is a fault in a dependency rather than anything the caller did,
    so it is a gateway error and not a 404. The caller can try again.
    """

    status_code = 502


class RateLimited(AppError):
    code = "RATE_LIMITED"
    status_code = 429


class FileNotPDF(AppError):
    code = "FILE_NOT_PDF"
    status_code = 400


class FileTooLarge(AppError):
    code = "FILE_TOO_LARGE"
    status_code = 413


class PdfEncrypted(AppError):
    code = "PDF_ENCRYPTED"
    status_code = 400


class PdfCorrupt(AppError):
    code = "PDF_CORRUPT"
    status_code = 400


class PdfTooManyPages(AppError):
    code = "PDF_TOO_MANY_PAGES"
    status_code = 400


class UploadAlreadyUsed(AppError):
    code = "UPLOAD_ALREADY_USED"
    status_code = 409


class ShopUnavailable(AppError):
    code = "SHOP_UNAVAILABLE"
    status_code = 409


class RateNotSet(AppError):
    code = "RATE_NOT_SET"
    status_code = 409


class PriceChanged(AppError):
    code = "PRICE_CHANGED"
    status_code = 409


class PriceTooLarge(AppError):
    """The job would cost more than the platform can charge.

    It is the shop's rate that is too large for a job of this size,
    and the answer says so, because the person reading it can ask the
    shop to lower it. It is a 422: nothing is wrong with the request.
    """

    code = "PRICE_TOO_LARGE"
    status_code = 422


class InvalidTransition(AppError):
    code = "INVALID_TRANSITION"
    status_code = 409


class PaymentNotApplied(AppError):
    """The payment could not be applied to the order.

    The provider retries a delivery it was told failed, so this is
    answered with a status that says "try again". The event is not
    recorded as applied, so the retry can still apply it.
    """

    code = "PAYMENT_NOT_APPLIED"
    status_code = 503


class ShopAlreadyVerified(AppError):
    """The shop is already approved, so there is nothing to approve."""

    code = "SHOP_ALREADY_VERIFIED"
    status_code = 409


class ShopNotVerified(AppError):
    """The shop was never approved, so there is nothing to suspend."""

    code = "SHOP_NOT_VERIFIED"
    status_code = 409


class PaymentGatewayError(AppError):
    code = "PAYMENT_GATEWAY_ERROR"
    status_code = 502


class WebhookSignatureInvalid(AppError):
    code = "WEBHOOK_SIGNATURE_INVALID"
    status_code = 400


class PickupCodeInvalid(AppError):
    code = "PICKUP_CODE_INVALID"
    status_code = 400


class FileUnavailable(AppError):
    """The file is no longer stored, so it cannot be printed again."""

    code = "FILE_UNAVAILABLE"
    status_code = 409


class CashPaymentDisabled(AppError):
    """Paying at the shop is not switched on.

    The feature is off by default, so a deployment that has not been
    configured for it refuses the request rather than quietly booking a
    cash order it cannot settle.
    """

    code = "CASH_PAYMENT_DISABLED"
    status_code = 409


class AddressNotFound(AppError):
    """The address could not be found on the map.

    It is a 422 and not a 404: the request was fine, the address in it
    is not a place anybody has heard of, and the caller can fix it by
    typing a different one.
    """

    code = "ADDRESS_NOT_FOUND"
    status_code = 422


class GeocodingUnavailable(AppError):
    """This deployment cannot look an address up.

    The feature needs a key from the map provider, and a deployment
    without one cannot do it. The answer says so rather than pretending
    that the address does not exist, because the two are different
    problems with different fixes.
    """

    code = "GEOCODING_UNAVAILABLE"
    status_code = 503


class CoordinatesRequired(AppError):
    """The shop's place on the map could not be worked out.

    The shop owner can type the coordinates, and when there is no way to
    look the address up, that is the only way to place the shop. The
    message says so, because the fix belongs to the person reading it.
    """

    code = "COORDINATES_REQUIRED"
    status_code = 422


def error_body(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id if request_id is not None else get_request_id(),
        }
    }


def _request_id(request: Request) -> str:
    """The id of the request being answered.

    The context variable is the usual source, but it is empty by the
    time an unhandled exception reaches the outermost handler, because
    the middleware that set it has already unwound. The scope keeps a
    copy of the id, so a 500 can still name the request that caused it.
    """
    state = request.scope.get("state") or {}
    scoped = state.get("request_id")
    if scoped:
        return str(scoped)
    return get_request_id()


def _headers(request: Request, headers: dict[str, str] | None) -> dict[str, str]:
    """The headers of an error answer, including the request id.

    The request id is on the answer as well as in the body, so a client
    can quote it without reading the body, and so a 500 that the
    middleware never saw still carries one.
    """
    merged = dict(headers or {})
    merged[REQUEST_ID_HEADER] = _request_id(request)
    return merged


# The code that goes with an HTTP status raised by the framework rather
# than by the application: a body that could not be parsed, an unknown
# route, a method that is not allowed.
HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "FILE_TOO_LARGE",
    429: "RATE_LIMITED",
}


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """Give framework errors the same shape as the rest of the API.

    FastAPI answers a body it cannot parse, an unknown route and a wrong
    method with `{"detail": ...}`. Every other failure in this app uses
    the standard error body, so a client would otherwise have to handle
    two shapes. This puts them all in one.
    """
    status_code = getattr(exc, "status_code", 500)
    detail = getattr(exc, "detail", None)
    message = detail if isinstance(detail, str) else "The request could not be handled"
    code = HTTP_STATUS_CODES.get(status_code, "HTTP_ERROR")
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=status_code,
        content=error_body(code, message, request_id=_request_id(request)),
        headers=_headers(request, headers),
    )


async def exception_handler(request: Request, exc: Exception) -> Response:
    if isinstance(exc, AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details, request_id=_request_id(request)),
            headers=_headers(request, exc.headers),
        )
    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"fields": jsonable_encoder(exc.errors())},
                request_id=_request_id(request),
            ),
            headers=_headers(request, None),
        )
    if isinstance(exc, DataError):
        # The database refused a value. In this app that is a value from
        # the request that the column cannot hold, most often a NUL byte.
        # The boundary is meant to catch that before it gets here, so this
        # is the net under the net: the caller gets a 422 and a message
        # that says what to fix, rather than a 500 and a stack trace.
        logger.warning(
            "database_rejected_value",
            exc_info=exc,
            extra={"request_id": _request_id(request)},
        )
        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR",
                "The request contained a value that could not be stored",
                request_id=_request_id(request),
            ),
            headers=_headers(request, None),
        )
    logger.exception(
        "unhandled_exception", exc_info=exc, extra={"request_id": _request_id(request)}
    )
    return JSONResponse(
        status_code=500,
        content=error_body(
            "INTERNAL_ERROR", "An unexpected error occurred", request_id=_request_id(request)
        ),
        headers=_headers(request, None),
    )
