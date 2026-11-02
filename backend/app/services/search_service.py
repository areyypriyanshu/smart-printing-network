"""Finding the shops around a point, and what they would charge.

This is the search the order wizard's shop step wants: one request
instead of one request per shop, and the prices from the same function
the order flow uses.

Two rules hold here, and both are the reason this file exists.

The distance is measured by the database, on the geography column, with
`ST_DWithin`, so the index on that column is used and a shop outside
the radius is not in the answer at all. And the price is computed by
`domain.pricing.quote_paise`, the same function that computes the
price of an order, so the number the customer is shown is the number
the customer is charged.
"""

import base64
import binascii
import json
import math
import uuid
from collections.abc import Sequence
from typing import Any
from typing import cast as type_cast

from geoalchemy2 import Geography, Geometry
from geoalchemy2.elements import WKTElement
from sqlalchemy import BigInteger, cast, func, select, tuple_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.domain.pricing import PriceOutOfRange, quote_paise
from app.errors import FileUnavailable, ValidationError
from app.gateways.geocoding import Geocoder
from app.models import Shop, ShopRate
from app.schemas.shop import (
    NearestShop,
    ShopSearchItem,
    ShopSearchQuery,
    ShopSearchResponse,
)
from app.services import estimate_service
from app.services.geocoding_service import geocode
from app.services.upload_service import get_upload


def search_shops(
    session: Session,
    *,
    customer_id: uuid.UUID,
    query: ShopSearchQuery,
    geocoder: Geocoder | None = None,
) -> ShopSearchResponse:
    """The shops that match the search, with what they would charge.

    A shop that is not verified, or that is not taking orders, is not in
    the answer. A shop that does not offer the options the customer
    chose is not in the answer either, when prices were asked for: a
    comparison of shops that cannot do the job is not a comparison.
    """
    point = _point_for(query, geocoder)
    pages = _pages_for(session, customer_id, query)
    _check_the_sort(query, point, pages)

    stmt = select(
        Shop,
        func.ST_Y(cast(Shop.location, Geometry)).label("lat"),
        func.ST_X(cast(Shop.location, Geometry)).label("lng"),
    ).where(Shop.is_verified.is_(True), Shop.accepting_orders.is_(True))

    distance_expression: ColumnElement[Any] | None = None
    if point is not None:
        point_element = WKTElement(f"POINT({point[1]} {point[0]})", srid=4326)
        distance_expression = func.ST_Distance(
            cast(Shop.location, Geography), cast(point_element, Geography)
        ).label("distance_m")
        stmt = stmt.add_columns(distance_expression).where(
            func.ST_DWithin(
                cast(Shop.location, Geography),
                cast(point_element, Geography),
                query.radius_m,
            )
        )

    price_expression: ColumnElement[Any] | None = None
    if pages is not None:
        # Joining the rate is what excludes a shop that does not offer
        # these options: the shop is not in the answer at all, rather
        # than in the answer with a price nobody can pay.
        stmt = stmt.join(ShopRate, ShopRate.shop_id == Shop.id).where(
            ShopRate.paper_size == query.paper_size,
            ShopRate.color == query.color,
            ShopRate.duplex == query.duplex,
        )
        stmt = stmt.add_columns(ShopRate.rate_paise.label("rate_paise"))
        # The order of the shops is decided here, and the price that
        # decides it is the same arithmetic the order flow uses, written
        # out for the database so that the limit keeps the cheapest.
        #
        # The operands are cast, and not the result. The rate column is
        # a 32 bit integer, and so is the product of three of them, and
        # a rate that is large enough would overflow the product
        # before the result was ever cast. Postgres works out
        # `integer * integer` as an integer, so `cast(a * b as bigint)`
        # overflows exactly like `a * b` does.
        #
        # An overflow here would break the search for every customer
        # because of one shop's rate, and the answer would blame the
        # customer. The price that is shown is worked out in Python,
        # where the arithmetic does not overflow, and this is only the
        # order.
        price_expression = func.greatest(
            cast(pages, BigInteger)
            * cast(query.copies or 1, BigInteger)
            * cast(ShopRate.rate_paise, BigInteger),
            cast(Shop.min_order_paise, BigInteger),
        )

    order_expression, order_kind = _order_for(query, distance_expression, price_expression)
    scope = _cursor_scope(query, point, pages, order_kind)
    if query.cursor is not None:
        last_value, last_name, last_id = _decode_cursor(
            query.cursor, expected_scope=scope, expected_kind=order_kind
        )
        stmt = stmt.where(
            tuple_(order_expression, Shop.name, Shop.id) > tuple_(last_value, last_name, last_id)
        )
    stmt = stmt.add_columns(order_expression.label("sort_value"))
    stmt = stmt.order_by(order_expression.asc(), Shop.name.asc(), Shop.id.asc())
    stmt = stmt.limit(query.limit + 1)

    rows = list(session.execute(stmt).all())
    has_more = len(rows) > query.limit
    rows = rows[: query.limit]
    items = []
    for row in rows:
        item = _item(
            list(row),
            has_distance=distance_expression is not None,
            has_rate=pages is not None,
            pages=pages,
            copies=query.copies or 1,
        )
        if item is not None:
            items.append(item)
    estimates = estimate_service.estimates_for_shops_or_empty(session, [item.id for item in items])
    for item in items:
        item.wait_estimate = estimates.get(item.id)
    return ShopSearchResponse(
        items=items,
        next_cursor=(
            _encode_cursor(
                sort_kind=order_kind,
                sort_value=rows[-1][-1],
                name=rows[-1][0].name,
                shop_id=rows[-1][0].id,
                scope=scope,
            )
            if has_more and rows
            else None
        ),
        attribution=geocoder.attribution if geocoder is not None else None,
        nearest=(_nearest_shop(session, point) if not items and point is not None else None),
    )


def _nearest_shop(session: Session, point: tuple[float, float]) -> NearestShop | None:
    """The closest shop, even when it is outside the radius.

    A customer who is told "there is nothing near you" and nothing else
    is left guessing. Told where the closest one is and how far it is,
    they can widen the radius, look at another area, or understand that
    there is no shop in their city yet.
    """
    point_element = WKTElement(f"POINT({point[1]} {point[0]})", srid=4326)
    distance = func.ST_Distance(cast(Shop.location, Geography), cast(point_element, Geography))
    row = session.execute(
        select(Shop.name, Shop.address, distance.label("distance_m"))
        .where(Shop.is_verified.is_(True), Shop.accepting_orders.is_(True))
        .order_by(distance.asc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return NearestShop(name=row[0], address=row[1], distance_m=round(float(row[2])))


def _point_for(query: ShopSearchQuery, geocoder: Geocoder | None) -> tuple[float, float] | None:
    """Where the search is centred.

    The point the customer gave comes first, because it is the more
    precise of the two. The typed address is looked up only when there
    is no point.
    """
    if query.latitude is not None and query.longitude is not None:
        return query.latitude, query.longitude
    if query.address is not None and query.address.strip():
        found = geocode(geocoder, query.address.strip())
        return found.latitude, found.longitude
    return None


def _pages_for(session: Session, customer_id: uuid.UUID, query: ShopSearchQuery) -> int | None:
    """How many pages the file has, when a price was asked for."""
    if not query.wants_prices or query.upload_id is None:
        return None
    upload = get_upload(session, upload_id=query.upload_id, customer_id=customer_id)
    if upload.file_deleted_at is not None:
        # The object is gone from storage, so there is nothing to
        # print and nothing to price.
        raise FileUnavailable(
            "This file is no longer stored, so it cannot be printed. "
            "Upload it once more and we will print it again."
        )
    return upload.page_count


def _check_the_sort(
    query: ShopSearchQuery, point: tuple[float, float] | None, pages: int | None
) -> None:
    """Refuse an order that cannot be carried out."""
    if query.sort == "distance" and point is None:
        raise ValidationError(
            "We need a location to sort the shops by distance. "
            "Ask the browser for your location, or type an address."
        )
    if query.sort == "price" and pages is None:
        raise ValidationError("Choose a file and the print options to compare the prices.")


def _order_for(
    query: ShopSearchQuery,
    distance_expression: ColumnElement[Any] | None,
    price_expression: ColumnElement[Any] | None,
) -> tuple[ColumnElement[Any], str]:
    """The order the shops come back in.

    The customer chooses it. Without a choice the server picks the one
    that means most: nearest when the customer said where they are,
    cheapest when they asked for prices, and by name when there is
    nothing to compare.
    """
    if query.sort == "price" and price_expression is not None:
        return price_expression, "price"
    if query.sort == "distance" and distance_expression is not None:
        return distance_expression, "distance"
    if query.sort is None:
        if distance_expression is not None:
            return distance_expression, "distance"
        if price_expression is not None:
            return price_expression, "price"
    return type_cast(ColumnElement[Any], Shop.name), "name"


def _cursor_scope(
    query: ShopSearchQuery,
    point: tuple[float, float] | None,
    pages: int | None,
    order_kind: str,
) -> list[Any]:
    """Bind a search cursor to the location, radius, sort and price inputs."""
    return [
        repr(point[0]) if point is not None else None,
        repr(point[1]) if point is not None else None,
        query.radius_m if point is not None else None,
        query.sort,
        order_kind,
        str(query.upload_id) if query.upload_id is not None else None,
        query.paper_size,
        query.color,
        query.duplex,
        query.copies,
        pages,
    ]


def _encode_cursor(
    *, sort_kind: str, sort_value: Any, name: str, shop_id: uuid.UUID, scope: list[Any]
) -> str:
    value = repr(float(sort_value)) if sort_kind == "distance" else sort_value
    raw = json.dumps(
        {"kind": sort_kind, "value": value, "name": name, "shop_id": str(shop_id), "scope": scope},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(
    cursor: str, *, expected_scope: list[Any], expected_kind: str
) -> tuple[Any, str, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        value = json.loads(raw)
        name = value["name"]
        if not isinstance(name, str):
            raise ValueError("invalid shop name")
        shop_id_raw = value["shop_id"]
        if not isinstance(shop_id_raw, str):
            raise ValueError("invalid shop id")
        shop_id = uuid.UUID(shop_id_raw)

        sort_value = value["value"]
        if expected_kind == "distance":
            sort_value = float(sort_value)
            if not math.isfinite(sort_value):
                raise ValueError("invalid distance")
        elif expected_kind == "price":
            if isinstance(sort_value, bool) or not isinstance(sort_value, int):
                raise ValueError("invalid price")
        elif not isinstance(sort_value, str):
            raise ValueError("invalid shop name")
        if value["scope"] != expected_scope or value["kind"] != expected_kind:
            raise ValidationError("Cursor does not match this shop search")
        return sort_value, name, shop_id
    except ValidationError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValidationError("Invalid cursor") from exc


def _item(
    row: Sequence[Any],
    *,
    has_distance: bool,
    has_rate: bool,
    pages: int | None,
    copies: int,
) -> ShopSearchItem | None:
    """One shop, with the price the customer would pay.

    `None` means the shop is left out. A shop whose rate is so large
    that the job cannot be priced inside the column that holds the
    price cannot take the job, and one shop's rate must not break the
    answer for everybody else.
    """
    shop = row[0]
    latitude = float(row[1])
    longitude = float(row[2])
    index = 3
    distance_m: int | None = None
    if has_distance:
        distance_m = round(float(row[index]))
        index += 1
    rate_paise: int | None = None
    if has_rate:
        rate_paise = int(row[index])
    price_paise: int | None = None
    if pages is not None and rate_paise is not None:
        try:
            price_paise = quote_paise(pages, copies, rate_paise, shop.min_order_paise)
        except PriceOutOfRange:
            return None
    return ShopSearchItem(
        id=shop.id,
        name=shop.name,
        address=shop.address,
        phone=shop.phone,
        latitude=latitude,
        longitude=longitude,
        min_order_paise=shop.min_order_paise,
        distance_m=distance_m,
        price_paise=price_paise,
        rate_paise=rate_paise,
    )
