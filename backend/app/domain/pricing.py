from app.domain.limits import MAX_PRICE_PAISE


class PriceOutOfRange(ValueError):
    """The price of the job is more than the platform can hold.

    The price of an order is pages x copies x rate, and it is held in
    a column that is a 32 bit integer. A rate that was stored before
    the ceiling on a rate existed can still produce a price that does
    not fit, and the order would fail to be written with a fault that
    says nothing about what went wrong.

    So the price is refused where it is worked out, with a reason, and
    the caller decides what to tell the person. The order and the
    quote refuse it. The search leaves the shop out, because one
    shop's rate must not break the answer for everybody.
    """


def quote_paise(
    pages: int,
    copies: int,
    rate_paise: int,
    min_order_paise: int = 0,
) -> int:
    if pages < 1 or copies < 1 or rate_paise < 1 or min_order_paise < 0:
        raise ValueError("invalid pricing input")
    price = max(pages * copies * rate_paise, min_order_paise)
    if price > MAX_PRICE_PAISE:
        raise PriceOutOfRange(
            f"the price of {price} paise is more than the {MAX_PRICE_PAISE} the platform can hold"
        )
    return price
