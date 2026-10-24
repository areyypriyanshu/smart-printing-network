import base64
import uuid
from datetime import datetime

from geoalchemy2 import Geography, Geometry
from geoalchemy2.elements import WKTElement
from sqlalchemy import cast, delete, func, select, tuple_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import NotFound, ValidationError
from app.models import Shop, ShopRate
from app.schemas.shop import (
    RateItem,
    RateToSet,
    ShopListResponse,
    ShopResponse,
    VendorShopResponse,
    VendorShopUpdate,
)
from app.services import estimate_service


def list_public_shops(
    session: Session,
    *,
    limit: int,
    cursor: str | None,
    attribution: str | None = None,
) -> ShopListResponse:
    stmt = (
        select(
            Shop,
            func.ST_Y(cast(Shop.location, Geometry)).label("lat"),
            func.ST_X(cast(Shop.location, Geometry)).label("lng"),
        )
        .where(Shop.is_verified.is_(True), Shop.accepting_orders.is_(True))
        .order_by(Shop.created_at.desc(), Shop.id.desc())
        .limit(limit + 1)
    )
    if cursor is not None:
        created_at, shop_id = _decode_cursor(cursor)
        stmt = stmt.where(tuple_(Shop.created_at, Shop.id) < tuple_(created_at, shop_id))

    rows = list(session.execute(stmt).all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    rates_by_shop = _rates_for(session, [row[0].id for row in rows])
    estimates = estimate_service.estimates_for_shops_or_empty(session, [row[0].id for row in rows])
    items = [
        ShopResponse(
            id=shop.id,
            name=shop.name,
            address=shop.address,
            phone=shop.phone,
            latitude=float(lat),
            longitude=float(lng),
            min_order_paise=shop.min_order_paise,
            rates=rates_by_shop.get(shop.id, []),
            wait_estimate=estimates.get(shop.id),
        )
        for shop, lat, lng in rows
    ]
    next_cursor = _encode_cursor(rows[-1][0]) if has_more and rows else None
    return ShopListResponse(
        items=items,
        next_cursor=next_cursor,
        cash_at_store_enabled=get_settings().cash_at_store_enabled,
        attribution=attribution,
    )


def list_nearby_shops(
    session: Session,
    *,
    latitude: float,
    longitude: float,
    radius_m: int,
    limit: int,
    attribution: str | None = None,
) -> ShopListResponse:
    """The shops within a radius, nearest first.

    The distance is measured on the sphere, in metres, which is what the
    customer means by "nearby". The shop table has a geography column
    with a spatial index on it, so the radius search does not scan the
    table.
    """
    point = WKTElement(f"POINT({longitude} {latitude})", srid=4326)
    distance = func.ST_Distance(cast(Shop.location, Geography), cast(point, Geography))
    stmt = (
        select(
            Shop,
            func.ST_Y(cast(Shop.location, Geometry)).label("lat"),
            func.ST_X(cast(Shop.location, Geometry)).label("lng"),
            distance.label("distance_m"),
        )
        .where(
            Shop.is_verified.is_(True),
            Shop.accepting_orders.is_(True),
            func.ST_DWithin(cast(Shop.location, Geography), cast(point, Geography), radius_m),
        )
        .order_by(distance.asc(), Shop.name.asc())
        .limit(limit)
    )
    rows = list(session.execute(stmt).all())
    rates_by_shop = _rates_for(session, [row[0].id for row in rows])
    estimates = estimate_service.estimates_for_shops_or_empty(session, [row[0].id for row in rows])
    items = [
        ShopResponse(
            id=shop.id,
            name=shop.name,
            address=shop.address,
            phone=shop.phone,
            latitude=float(lat),
            longitude=float(lng),
            min_order_paise=shop.min_order_paise,
            rates=rates_by_shop.get(shop.id, []),
            distance_m=round(float(metres)),
            wait_estimate=estimates.get(shop.id),
        )
        for shop, lat, lng, metres in rows
    ]
    return ShopListResponse(
        items=items,
        next_cursor=None,
        cash_at_store_enabled=get_settings().cash_at_store_enabled,
        attribution=attribution,
    )


def get_public_shop(
    session: Session, shop_id: uuid.UUID, attribution: str | None = None
) -> ShopResponse:
    row = session.execute(
        select(
            Shop,
            func.ST_Y(cast(Shop.location, Geometry)).label("lat"),
            func.ST_X(cast(Shop.location, Geometry)).label("lng"),
        ).where(Shop.id == shop_id, Shop.is_verified.is_(True))
    ).one_or_none()
    if row is None:
        raise NotFound("Shop not found")
    shop, lat, lng = row
    return ShopResponse(
        id=shop.id,
        name=shop.name,
        address=shop.address,
        phone=shop.phone,
        latitude=float(lat),
        longitude=float(lng),
        min_order_paise=shop.min_order_paise,
        rates=_rates_for(session, [shop.id]).get(shop.id, []),
        attribution=attribution,
    )


def get_vendor_shop(session: Session, owner_id: uuid.UUID) -> Shop:
    shop = session.scalar(select(Shop).where(Shop.owner_id == owner_id))
    if shop is None:
        raise NotFound("Shop not found")
    return shop


def update_vendor_shop(session: Session, shop: Shop, update: VendorShopUpdate) -> Shop:
    if update.name is not None:
        shop.name = update.name
    if update.address is not None:
        shop.address = update.address
    if update.phone is not None:
        shop.phone = update.phone
    if update.min_order_paise is not None:
        shop.min_order_paise = update.min_order_paise
    if update.accepting_orders is not None:
        shop.accepting_orders = update.accepting_orders
    session.commit()
    session.refresh(shop)
    return shop


def get_rates(session: Session, shop_id: uuid.UUID) -> list[ShopRate]:
    return list(
        session.scalars(
            select(ShopRate)
            .where(ShopRate.shop_id == shop_id)
            .order_by(ShopRate.paper_size, ShopRate.color, ShopRate.duplex)
        )
    )


def rate_items(rows: list[ShopRate]) -> list[RateItem]:
    return [
        RateItem(
            paper_size=row.paper_size,
            color=row.color,
            duplex=row.duplex,
            rate_paise=row.rate_paise,
        )
        for row in rows
    ]


def vendor_shop_response(session: Session, shop: Shop) -> VendorShopResponse:
    lat, lng = session.execute(
        select(
            func.ST_Y(cast(Shop.location, Geometry)),
            func.ST_X(cast(Shop.location, Geometry)),
        ).where(Shop.id == shop.id)
    ).one()
    return VendorShopResponse(
        id=shop.id,
        name=shop.name,
        address=shop.address,
        phone=shop.phone,
        latitude=float(lat),
        longitude=float(lng),
        min_order_paise=shop.min_order_paise,
        is_verified=shop.is_verified,
        accepting_orders=shop.accepting_orders,
        created_at=shop.created_at,
        updated_at=shop.updated_at,
    )


def replace_rates(session: Session, shop_id: uuid.UUID, items: list[RateToSet]) -> list[ShopRate]:
    session.execute(delete(ShopRate).where(ShopRate.shop_id == shop_id))
    session.add_all(
        [
            ShopRate(
                shop_id=shop_id,
                paper_size=item.paper_size,
                color=item.color,
                duplex=item.duplex,
                rate_paise=item.rate_paise,
            )
            for item in items
        ]
    )
    session.commit()
    return get_rates(session, shop_id)


def _rates_for(session: Session, shop_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[RateItem]]:
    if not shop_ids:
        return {}
    grouped: dict[uuid.UUID, list[RateItem]] = {}
    for rate in session.scalars(
        select(ShopRate)
        .where(ShopRate.shop_id.in_(shop_ids))
        .order_by(ShopRate.paper_size, ShopRate.color, ShopRate.duplex)
    ):
        grouped.setdefault(rate.shop_id, []).append(
            RateItem(
                paper_size=rate.paper_size,
                color=rate.color,
                duplex=rate.duplex,
                rate_paise=rate.rate_paise,
            )
        )
    return grouped


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
