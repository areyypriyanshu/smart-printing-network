from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import security
from app.db import get_db
from app.errors import Forbidden, NotFound, Unauthenticated
from app.gateways.payments import PaymentGatewayRouter
from app.gateways.storage import Storage
from app.models import Shop, User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise Unauthenticated("Authentication required")
    user_id, _role = security.decode_access_token(credentials.credentials)
    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthenticated("Authentication required")
    return user


def require_role(*roles: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise Forbidden("Your role cannot perform this action")
        return user

    return dependency


_vendor_only = require_role("vendor")
_customer_only = require_role("customer")


def get_customer(user: User = Depends(_customer_only)) -> User:
    return user


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def get_payment_gateway(request: Request) -> PaymentGatewayRouter:
    """The gateway the application uses: the online provider and cash.

    It is the concrete router rather than the interface because the local
    simulate-payment endpoint has to sign a body the way the fake provider
    does, and only the router knows which implementation is in use.
    """
    gateway: PaymentGatewayRouter = request.app.state.payment_gateway
    return gateway


def get_current_shop(
    user: User = Depends(_vendor_only),
    session: Session = Depends(get_db),
) -> Shop:
    shop = session.scalar(select(Shop).where(Shop.owner_id == user.id))
    if shop is None:
        raise NotFound("Shop not found")
    return shop
