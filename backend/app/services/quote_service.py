import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.pricing import quote_paise
from app.errors import FileUnavailable, NotFound, RateNotSet, ShopUnavailable
from app.models import Shop, ShopRate
from app.schemas.quote import QuoteRequest, QuoteResponse
from app.services.upload_service import get_upload


def quote(
    session: Session,
    *,
    customer_id: uuid.UUID,
    request: QuoteRequest,
) -> QuoteResponse:
    upload = get_upload(session, upload_id=request.upload_id, customer_id=customer_id)
    if upload.file_deleted_at is not None:
        # The object is gone from storage, so there is nothing to print.
        # Refuse here, before a price is shown, rather than after the
        # customer has committed money to a job that cannot be done.
        raise FileUnavailable(
            "This file is no longer stored, so it cannot be printed. "
            "Upload it once more and we will print it again."
        )
    shop = session.get(Shop, request.shop_id)
    if shop is None:
        raise NotFound("Shop not found")
    if not shop.is_verified or not shop.accepting_orders:
        raise ShopUnavailable("This shop is not accepting orders right now")
    rate = session.scalar(
        select(ShopRate).where(
            ShopRate.shop_id == shop.id,
            ShopRate.paper_size == request.paper_size,
            ShopRate.color == request.color,
            ShopRate.duplex == request.duplex,
        )
    )
    if rate is None:
        raise RateNotSet("This shop does not offer the selected options")
    price_paise = quote_paise(
        upload.page_count, request.copies, rate.rate_paise, shop.min_order_paise
    )
    return QuoteResponse(
        upload_id=upload.id,
        shop_id=shop.id,
        page_count=upload.page_count,
        copies=request.copies,
        rate_paise=rate.rate_paise,
        min_order_paise=shop.min_order_paise,
        price_paise=price_paise,
    )
