"""Plain authorization helpers shared by HTTP dependencies and WebSockets."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AccountNotProvisioned, Forbidden, NotFound, Unauthenticated
from app.models import Order, Shop, User
from app.services import identity_service


def active_user_for_subject(session: Session, subject: str) -> User:
    """Resolve a provider subject to an active local account."""
    user = identity_service.find_by_subject(session, subject)
    if user is None:
        raise AccountNotProvisioned(
            "This account has not been set up yet. Choose what you are here for."
        )
    if not user.is_active:
        raise Unauthenticated("Authentication required")
    return user


def require_role(user: User, *roles: str) -> User:
    """Enforce the local database role, never a role claimed by a token."""
    if user.role not in roles:
        raise Forbidden("Your role cannot perform this action")
    return user


def shop_for_vendor(session: Session, user: User) -> Shop:
    """Return the shop owned by this vendor, with no shop id from the caller."""
    require_role(user, "vendor")
    shop = session.scalar(select(Shop).where(Shop.owner_id == user.id))
    if shop is None:
        raise NotFound("Shop not found")
    return shop


def order_for_customer(session: Session, user: User, order_id: uuid.UUID) -> Order:
    """Return an order only when it belongs to the calling customer."""
    require_role(user, "customer")
    order = session.scalar(select(Order).where(Order.id == order_id, Order.customer_id == user.id))
    if order is None:
        raise NotFound("Order not found")
    return order
