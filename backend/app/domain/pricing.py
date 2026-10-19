def quote_paise(
    pages: int,
    copies: int,
    rate_paise: int,
    min_order_paise: int = 0,
) -> int:
    if pages < 1 or copies < 1 or rate_paise < 1 or min_order_paise < 0:
        raise ValueError("invalid pricing input")
    return max(pages * copies * rate_paise, min_order_paise)
