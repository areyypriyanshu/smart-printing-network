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

import uuid
from collections.abc import Sequence
from typing import Any

from geoalchemy2 import Geography, Geometry
from geoalchemy2.elements import WKTElement
from sqlalchemy import BigInteger, cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.domain.pricing import PriceOutOfRange, quote_paise
from app.errors import FileUnavailable, ValidationError
from app.gateways.geocoding import Geocoder
from app.models import Shop, ShopRate
from app.schemas.shop import ShopSearchItem, ShopSearchQuery, ShopSearchResponse
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

    stmt = stmt.order_by(*_order_for(query, distance_expression, price_expression))
    stmt = stmt.limit(query.limit)

    rows = list(session.execute(stmt).all())
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
    return ShopSearchResponse(
        items=items,
        attribution=geocoder.attribution if geocoder is not None else None,
    )


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
) -> list[Any]:
    """The order the shops come back in.

    The customer chooses it. Without a choice the server picks the one
    that means most: nearest when the customer said where they are,
    cheapest when they asked for prices, and by name when there is
    nothing to compare.
    """
    if query.sort == "price" and price_expression is not None:
        return [price_expression.asc(), Shop.name.asc()]
    if query.sort == "distance" and distance_expression is not None:
        return [distance_expression.asc(), Shop.name.asc()]
    if query.sort is None:
        if distance_expression is not None:
            return [distance_expression.asc(), Shop.name.asc()]
        if price_expression is not None:
            return [price_expression.asc(), Shop.name.asc()]
    return [Shop.name.asc()]


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
