from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.errors import AppError, exception_handler, http_exception_handler
from app.gateways.email import build_email_sender
from app.gateways.oauth import build_oauth_provider
from app.gateways.payments import build_payment_gateway
from app.gateways.storage import S3Storage
from app.logging import RequestIdMiddleware, setup_logging
from app.rate_limit import RateLimiter
from app.routers import (
    admin,
    auth,
    health,
    oauth,
    orders,
    quality,
    quotes,
    shops,
    uploads,
    vendor,
    webhooks,
)

API_PREFIX = "/api/v1"
#: How much room the multipart envelope gets on top of the file itself.
ENVELOPE_BYTES = 1024 * 1024


class BodyLimitMiddleware:
    """Cap the request body before the multipart parser can spool it to disk.

    FastAPI parses a form body before it runs the route's dependencies, so an
    unauthenticated caller can put an unbounded body on the container's
    filesystem. The limit has to be applied to the stream, not to the parsed
    form.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        declared = headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            response = JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "FILE_TOO_LARGE",
                        "message": "The file is larger than the limit",
                        "details": {},
                    }
                },
            )
            await response(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise HTTPException(status_code=413, detail="The file is larger than the limit")
            return message

        await self.app(scope, limited_receive, send)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Smart Printing Network API", version="0.1.0")
    app.state.rate_limiter = RateLimiter()
    app.state.payment_gateway = build_payment_gateway(settings)
    app.state.email_sender = build_email_sender(settings)
    # The providers that this deployment offers. A provider that is not
    # configured is not there at all, and the front end hides the button.
    app.state.oauth_providers = {
        name: provider
        for name in ("google",)
        if (provider := build_oauth_provider(settings, name)) is not None
    }
    app.state.storage = S3Storage(
        endpoint_url=settings.s3_endpoint_url or None,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
    app.add_middleware(
        BodyLimitMiddleware,
        max_bytes=settings.max_upload_mb * 1024 * 1024 + ENVELOPE_BYTES,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, exception_handler)
    app.add_exception_handler(RequestValidationError, exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, exception_handler)
    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(oauth.router, prefix=API_PREFIX)
    app.include_router(shops.router, prefix=API_PREFIX)
    app.include_router(vendor.router, prefix=API_PREFIX)
    app.include_router(uploads.router, prefix=API_PREFIX)
    app.include_router(quotes.router, prefix=API_PREFIX)
    app.include_router(quality.router, prefix=API_PREFIX)
    app.include_router(orders.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(webhooks.router, prefix=API_PREFIX)
    # Shadowing the method on the instance is the documented way to change
    # the OpenAPI document FastAPI produces.
    app.openapi = lambda: build_openapi(app)  # type: ignore[method-assign]
    return app


def build_openapi(app: FastAPI) -> dict[str, Any]:
    """The OpenAPI document, with the upload part described properly.

    FastAPI describes a file part as an opaque binary string. This API
    only accepts a PDF, and a non empty one, so the contract should say
    so. The contract fuzzer found the gap: it sent an empty body, which
    the schema allowed and the server rightly refused.
    """
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    _describe_the_uploaded_pdf(schema)
    app.openapi_schema = schema
    return schema


def _describe_the_uploaded_pdf(schema: dict[str, Any]) -> None:
    request = schema.get("paths", {}).get(f"{API_PREFIX}/uploads", {}).get("post", {})
    content = request.get("requestBody", {}).get("content", {})
    components = schema.get("components", {}).get("schemas", {})
    for media in content.values():
        reference = media.get("schema", {}).get("$ref", "")
        name = reference.rsplit("/", 1)[-1]
        part = components.get(name, {}).get("properties", {}).get("file")
        if part is None:
            continue
        part["contentMediaType"] = "application/pdf"
        part["minLength"] = 1


app = create_app()
