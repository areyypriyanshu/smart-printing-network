from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.errors import AppError, exception_handler, http_exception_handler
from app.gateways.payments import build_payment_gateway
from app.gateways.storage import S3Storage
from app.logging import RequestIdMiddleware, setup_logging
from app.rate_limit import RateLimiter
from app.routers import auth, health, orders, quotes, shops, uploads, vendor, webhooks

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
    app.include_router(webhooks.router, prefix=API_PREFIX)
    return app


app = create_app()
