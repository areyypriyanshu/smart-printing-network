import re

from app.domain.pickup_code import generate_pickup_code
from hypothesis import given
from hypothesis import strategies as st


def test_pickup_code_is_six_digits() -> None:
    assert re.fullmatch(r"[0-9]{6}", generate_pickup_code())


def test_pickup_code_is_zero_padded() -> None:
    codes = [generate_pickup_code() for _ in range(2000)]
    assert all(code.startswith("0") or int(code) >= 100000 for code in codes)


def test_pickup_code_differs_between_calls() -> None:
    codes = {generate_pickup_code() for _ in range(50)}
    assert len(codes) > 1


@given(st.integers(min_value=0, max_value=999_999))
def test_pickup_code_always_fits_six_digits(seed: int) -> None:
    code = generate_pickup_code()
    assert 0 <= int(code) <= 999_999
    assert len(code) == 6
