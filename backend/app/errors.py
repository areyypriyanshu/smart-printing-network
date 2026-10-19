import logging
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.logging import get_request_id

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


class InvalidTransition(AppError):
    code = "INVALID_TRANSITION"
    status_code = 409


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


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
        }
    }


# The code that goes with an HTTP status raised by the framework rather
# than by the application: a body that could not be parsed, an unknown
# route, a method that is not allowed.
HTTP_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
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
        content=error_body(code, message),
        headers=headers,
    )


async def exception_handler(request: Request, exc: Exception) -> Response:
    if isinstance(exc, AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )
    if isinstance(exc, RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_body(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"fields": jsonable_encoder(exc.errors())},
            ),
        )
    logger.exception("unhandled_exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "An unexpected error occurred"),
    )
