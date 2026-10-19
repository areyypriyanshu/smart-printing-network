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


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": get_request_id(),
        }
    }


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
