"""Admin operations on shops.

The admin's job in this product is narrow and deliberate: decide which
shops are allowed to take orders. Everything in this module is about that
and nothing else. There is no admin endpoint that can read a customer's
orders, move money, or see a customer's uploads, and there is no reason for
one to exist yet.

Two rules shape the code here.

The first is that every action is recorded. An approval or a suspension
writes a row to `admin_actions` in the same transaction as the change to
the shop, so the log cannot disagree with the state. A student who has a
bad experience at a shop needs somewhere to point, and "who approved this"
is the first question anyone would ask.

The second is that a suspension never touches orders. A shop that is taken
offline may already have orders it has accepted, printed or be printing.
Those customers have already paid and they are owed a printout. Stranding a
customer because of a moderation decision about the shop would punish them
for something they did not do, so the orders are left alone and the shop
simply stops receiving new ones.
"""

import base64
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select, tuple_
from sqlalchemy.orm import Session

from app.errors import NotFound, ShopAlreadyVerified, ShopNotVerified, ValidationError
from app.models import AdminAction, Shop, ShopRate, User
from app.schemas.admin import (
    AdminActionListResponse,
    AdminActionResponse,
    AdminShopListResponse,
    AdminShopResponse,
)

SHOP_STATUSES = ("pending", "verified", "all")


def list_shops(
    session: Session, *, status: str, limit: int, cursor: str | None
) -> AdminShopListResponse:
    """The shops the admin can act on.

    The list is ordered oldest first, so the shop that has been waiting
    longest for a decision is at the top. That is the order a queue should
    be in, and it is the opposite of the customer facing list, which is
    ordered by price.
    """
    if status not in SHOP_STATUSES:
        raise ValidationError("Unknown shop status filter")

    stmt = (
        select(
            Shop,
            User.email.label("owner_email"),
            User.full_name.label("owner_name"),
            func.ST_Y(cast(Shop.location, Geometry)).label("lat"),
            func.ST_X(cast(Shop.location, Geometry)).label("lng"),
        )
        .join(User, User.id == Shop.owner_id)
        .order_by(Shop.created_at.asc(), Shop.id.asc())
        .limit(limit + 1)
    )
    if status == "pending":
        stmt = stmt.where(Shop.is_verified.is_(False))
    elif status == "verified":
        stmt = stmt.where(Shop.is_verified.is_(True))

    if cursor is not None:
        created_at, shop_id = _decode_cursor(cursor)
        stmt = stmt.where(tuple_(Shop.created_at, Shop.id) > tuple_(created_at, shop_id))

    rows = list(session.execute(stmt).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    rate_counts = _rate_counts(session, [row[0].id for row in rows])
    items = [
        AdminShopResponse(
            id=shop.id,
            name=shop.name,
            address=shop.address,
            owner_email=owner_email,
            owner_full_name=owner_name,
            latitude=float(lat),
            longitude=float(lng),
            is_verified=shop.is_verified,
            accepting_orders=shop.accepting_orders,
            rate_count=rate_counts.get(shop.id, 0),
            created_at=shop.created_at,
            updated_at=shop.updated_at,
        )
        for shop, owner_email, owner_name, lat, lng in rows
    ]
    next_cursor = _encode_cursor(rows[-1][0]) if has_more and rows else None
    return AdminShopListResponse(items=items, next_cursor=next_cursor)


def approve_shop(
    session: Session, *, shop_id: uuid.UUID, admin_id: uuid.UUID | None
) -> AdminShopResponse:
    """Let a shop take orders.

    A shop that registers starts unverified, so its customers cannot order
    from it. Approval clears that and puts it on the market.
    """
    shop = _shop(session, shop_id)
    if shop.is_verified and shop.accepting_orders:
        raise ShopAlreadyVerified("This shop is already verified and taking orders")
    shop.is_verified = True
    shop.accepting_orders = True
    session.add(AdminAction(admin_id=admin_id, action="shop_approved", shop_id=shop.id))
    session.commit()
    session.refresh(shop)
    return shop_response(session, shop)


def suspend_shop(
    session: Session, *, shop_id: uuid.UUID, admin_id: uuid.UUID | None, reason: str
) -> AdminShopResponse:
    """Take a shop off the market.

    The shop stops being verified and stops accepting orders, so no new
    customer can pick it. Its existing orders are untouched: a customer
    who already paid for a printout is owed that printout, and the shop
    that is printing it still has to be able to finish it.
    """
    shop = _shop(session, shop_id)
    if not shop.is_verified:
        raise ShopNotVerified("This shop is not verified")
    shop.is_verified = False
    shop.accepting_orders = False
    session.add(
        AdminAction(
            admin_id=admin_id,
            action="shop_suspended",
            shop_id=shop.id,
            reason=reason,
        )
    )
    session.commit()
    session.refresh(shop)
    return shop_response(session, shop)


def list_actions(session: Session, *, limit: int, cursor: str | None) -> AdminActionListResponse:
    """The moderation log, newest first."""
    stmt = (
        select(
            AdminAction,
            Shop.name.label("shop_name"),
            User.email.label("admin_email"),
        )
        .join(Shop, Shop.id == AdminAction.shop_id)
        .outerjoin(User, User.id == AdminAction.admin_id)
        .order_by(AdminAction.at.desc(), AdminAction.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        at, action_id = _decode_action_cursor(cursor)
        stmt = stmt.where(tuple_(AdminAction.at, AdminAction.id) < tuple_(at, action_id))

    rows = list(session.execute(stmt).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    items = [
        AdminActionResponse(
            id=action.id,
            action=action.action,
            shop_id=action.shop_id,
            shop_name=shop_name,
            admin_id=action.admin_id,
            admin_email=admin_email,
            reason=action.reason,
            at=action.at,
        )
        for action, shop_name, admin_email in rows
    ]
    next_cursor = _encode_action_cursor(rows[-1][0]) if has_more and rows else None
    return AdminActionListResponse(items=items, next_cursor=next_cursor)


def shop_response(session: Session, shop: Shop) -> AdminShopResponse:
    owner = session.get(User, shop.owner_id)
    lat, lng = session.execute(
        select(
            func.ST_Y(cast(Shop.location, Geometry)),
            func.ST_X(cast(Shop.location, Geometry)),
        ).where(Shop.id == shop.id)
    ).one()
    return AdminShopResponse(
        id=shop.id,
        name=shop.name,
        address=shop.address,
        owner_email=owner.email if owner is not None else "",
        owner_full_name=owner.full_name if owner is not None else "",
        latitude=float(lat),
        longitude=float(lng),
        is_verified=shop.is_verified,
        accepting_orders=shop.accepting_orders,
        rate_count=_rate_counts(session, [shop.id]).get(shop.id, 0),
        created_at=shop.created_at,
        updated_at=shop.updated_at,
    )


def _shop(session: Session, shop_id: uuid.UUID) -> Shop:
    shop = session.get(Shop, shop_id)
    if shop is None:
        raise NotFound("Shop not found")
    return shop


def _rate_counts(session: Session, shop_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not shop_ids:
        return {}
    rows = session.execute(
        select(ShopRate.shop_id, func.count())
        .where(ShopRate.shop_id.in_(shop_ids))
        .group_by(ShopRate.shop_id)
    ).all()
    return dict(rows)


def _encode_cursor(shop: Shop) -> str:
    raw = f"{shop.created_at.isoformat()}|{shop.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp_raw, id_raw = raw.split("|", 1)
        return datetime.fromisoformat(timestamp_raw), uuid.UUID(id_raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("Invalid cursor") from exc


def _encode_action_cursor(action: AdminAction) -> str:
    raw = f"{action.at.isoformat()}|{action.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_action_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        timestamp_raw, id_raw = raw.split("|", 1)
        return datetime.fromisoformat(timestamp_raw), int(id_raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("Invalid cursor") from exc
