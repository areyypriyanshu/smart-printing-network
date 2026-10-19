from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.config import get_settings
from app.errors import AppError, exception_handler
from app.logging import RequestIdMiddleware, setup_logging
from app.rate_limit import RateLimiter
from app.routers import auth, health, shops, vendor

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Smart Printing Network API", version="0.1.0")
    app.state.rate_limiter = RateLimiter()
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, exception_handler)
    app.add_exception_handler(RequestValidationError, exception_handler)
    app.add_exception_handler(Exception, exception_handler)
    app.include_router(health.router)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(shops.router, prefix=API_PREFIX)
    app.include_router(vendor.router, prefix=API_PREFIX)
    return app


app = create_app()
