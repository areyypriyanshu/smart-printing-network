import pytest
from app.schemas.text import multi_line, single_line


def test_an_ordinary_value_is_accepted() -> None:
    assert single_line("Asha Rao") == "Asha Rao"


def test_a_nul_byte_is_refused() -> None:
    # The database cannot store a NUL byte, so a value that carries one
    # has to be refused before it reaches the insert.
    with pytest.raises(ValueError):
        single_line("Asha\x00Rao")


@pytest.mark.parametrize("code", list(range(0x20)) + [0x7F])
def test_every_control_character_is_refused(code: int) -> None:
    with pytest.raises(ValueError):
        single_line(f"Asha{chr(code)}Rao")


def test_a_tab_and_a_newline_are_refused_on_one_line() -> None:
    with pytest.raises(ValueError):
        single_line("Asha\tRao")
    with pytest.raises(ValueError):
        single_line("Asha\nRao")


def test_a_tab_and_a_newline_are_allowed_over_several_lines() -> None:
    assert multi_line("Asha\tRao") == "Asha\tRao"
    assert multi_line("Shop 4\nSecond floor") == "Shop 4\nSecond floor"


def test_a_carriage_return_is_refused_even_over_several_lines() -> None:
    with pytest.raises(ValueError):
        multi_line("Asha\rRao")


@pytest.mark.parametrize(
    "character",
    ["‪", "‫", "‭", "‮", "⁦", "⁧", "⁨", "⁩"],
)
def test_a_bidi_override_is_refused(character: str) -> None:
    # These characters make the text after them read in the opposite
    # direction, so a name can be made to look like a different name.
    with pytest.raises(ValueError):
        single_line(f"Asha{character}Rao")


def test_a_zero_width_joiner_is_left_alone() -> None:
    # Devanagari and Arabic use invisible characters as letters. Those
    # are not tricks and a name may well contain one.
    assert single_line("शा‍श") == "शा‍श"
    assert single_line("علي‏") == "علي‏"
