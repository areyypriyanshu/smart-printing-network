from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.errors import AppError, exception_handler, http_exception_handler
from app.gateways.payments import build_payment_gateway
from app.gateways.storage import S3Storage
from app.logging import RequestIdMiddleware, setup_logging
from app.rate_limit import RateLimiter
from app.routers import (
    admin,
    auth,
    health,
    orders,
    quotes,
    shops,
    uploads,
    vendor,
    webhooks,
)

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Smart Printing Network API", version="0.1.0")
    app.state.rate_limiter = RateLimiter()
    app.state.payment_gateway = build_payment_gateway(settings)
    app.state.storage = S3Storage(
        endpoint_url=settings.s3_endpoint_url or None,
        bucket=settings.s3_bucket,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, exception_handler)
    app.add_exception_handler(RequestValidationError, exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, exception_handler)
    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(shops.router, prefix=API_PREFIX)
    app.include_router(vendor.router, prefix=API_PREFIX)
    app.include_router(uploads.router, prefix=API_PREFIX)
    app.include_router(quotes.router, prefix=API_PREFIX)
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
