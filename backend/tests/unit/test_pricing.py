import pytest
from app.domain.limits import MAX_PRICE_PAISE
from app.domain.pricing import PriceOutOfRange, quote_paise
from hypothesis import given
from hypothesis import strategies as st

# The rule is about the prices the platform can hold, so the examples
# are the ones the platform can be asked for: the most pages an order
# can be for, the most copies of it, and the most a page can cost.
# Anything bigger is refused, and there is a test for that below.
PAGES = st.integers(min_value=1, max_value=100)
COPIES = st.integers(min_value=1, max_value=50)
RATE = st.integers(min_value=1, max_value=50_000)
MIN_ORDER = st.integers(min_value=0, max_value=10_000_000)
EXTRA_PAGES = st.integers(min_value=1, max_value=100)
EXTRA_COPIES = st.integers(min_value=1, max_value=50)


@given(pages=PAGES, copies=COPIES, rate=RATE, min_order=MIN_ORDER)
def test_price_is_never_negative(pages: int, copies: int, rate: int, min_order: int) -> None:
    assert quote_paise(pages, copies, rate, min_order) >= 0


@given(pages=PAGES, copies=COPIES, rate=RATE, min_order=MIN_ORDER)
def test_price_equals_max_of_product_and_minimum(
    pages: int, copies: int, rate: int, min_order: int
) -> None:
    assert quote_paise(pages, copies, rate, min_order) == max(pages * copies * rate, min_order)


@given(pages=PAGES, extra=EXTRA_PAGES, copies=COPIES, rate=RATE, min_order=MIN_ORDER)
def test_price_is_monotonic_in_pages(
    pages: int, extra: int, copies: int, rate: int, min_order: int
) -> None:
    assert quote_paise(pages + extra, copies, rate, min_order) >= quote_paise(
        pages, copies, rate, min_order
    )


@given(pages=PAGES, copies=COPIES, extra=EXTRA_COPIES, rate=RATE, min_order=MIN_ORDER)
def test_price_is_monotonic_in_copies(
    pages: int, copies: int, extra: int, rate: int, min_order: int
) -> None:
    assert quote_paise(pages, copies + extra, rate, min_order) >= quote_paise(
        pages, copies, rate, min_order
    )


@given(copies=COPIES, rate=RATE, min_order=st.integers(min_value=1, max_value=1_000_000))
def test_tiny_jobs_are_charged_the_minimum_order(copies: int, rate: int, min_order: int) -> None:
    pages = 1
    if pages * copies * rate >= min_order:
        return
    assert quote_paise(pages, copies, rate, min_order) == min_order


def test_known_example_matches_hand_calculation() -> None:
    assert quote_paise(10, 3, 250) == 7500


def test_minimum_order_applies_when_product_is_smaller() -> None:
    assert quote_paise(1, 1, 100, min_order_paise=500) == 500


@pytest.mark.parametrize(
    ("pages", "copies", "rate", "min_order"),
    [
        (0, 1, 100, 0),
        (-1, 1, 100, 0),
        (1, 0, 100, 0),
        (1, -5, 100, 0),
        (1, 1, 0, 0),
        (1, 1, -100, 0),
        (1, 1, 100, -1),
    ],
)
def test_invalid_inputs_raise_value_error(
    pages: int, copies: int, rate: int, min_order: int
) -> None:
    with pytest.raises(ValueError):
        quote_paise(pages, copies, rate, min_order)


def test_a_price_the_platform_cannot_hold_is_refused() -> None:
    """A rate that was stored before the ceiling existed can still
    produce a price that does not fit, and the price is refused where
    it is worked out rather than failing later."""
    with pytest.raises(PriceOutOfRange):
        quote_paise(300, 100, 1_000_000)


def test_the_largest_price_the_platform_asks_for_is_still_a_price() -> None:
    """The rule is about the prices the platform can hold, and the
    largest one of them is a price."""
    assert quote_paise(300, 100, 50_000) <= MAX_PRICE_PAISE
