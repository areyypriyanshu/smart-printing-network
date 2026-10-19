import re

from app.domain.pickup_code import generate_pickup_code, verify_pickup_code
from hypothesis import given
from hypothesis import strategies as st


def test_pickup_code_is_six_digits() -> None:
    assert re.fullmatch(r"[0-9]{6}", generate_pickup_code())


def test_pickup_code_is_zero_padded() -> None:
    codes = [generate_pickup_code() for _ in range(5000)]

    assert all(len(code) == 6 and code.isdigit() for code in codes)
    # A code below 100000 must keep its leading zeros. Without padding it
    # would be a five character string and the customer could not type it
    # into a six box code field.
    below = [code for code in codes if int(code) < 100000]
    assert below, "expected at least one code below 100000 in 5000 samples"
    assert all(code.startswith("0") for code in below)


def test_pickup_code_differs_between_calls() -> None:
    codes = {generate_pickup_code() for _ in range(50)}
    assert len(codes) > 1


@given(st.integers(min_value=0, max_value=999_999))
def test_pickup_code_always_fits_six_digits(seed: int) -> None:
    code = generate_pickup_code()
    assert 0 <= int(code) <= 999_999
    assert len(code) == 6


def test_the_right_code_verifies() -> None:
    assert verify_pickup_code("123456", "123456")


def test_a_wrong_code_does_not_verify() -> None:
    assert not verify_pickup_code("123456", "123457")
    assert not verify_pickup_code("123456", "")


def test_verification_is_case_and_shape_sensitive() -> None:
    assert not verify_pickup_code("123456", "123456 ")
    assert not verify_pickup_code("012345", "12345")
