"""Pure, advisory rules for turning page measurements into quality flags.

These thresholds are intentionally simple, explainable rules. They are not an
AI score, and they must be calibrated against the labelled fixture
evaluation rather than trusted as folklore.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PageMeasurements:
    """What the analyzer measured on one page."""

    page_number: int
    #: The lowest effective resolution of the pictures on the page, in dots
    #: per inch. None when the page has no picture on it.
    min_effective_dpi: float | None
    #: The sharpness score of the pictures on the page. None when the page
    #: has no picture on it.
    blur_score: float | None


@dataclass(frozen=True)
class QualityThresholds:
    """The numbers the rules use.

    They come from the measured evaluation, not from taste. The blur
    threshold of 90 is the one the calibration half of the labelled
    fixture set chose: it flags every known bad page and no known good
    one, and the held out half agrees. The sweep in
    `scripts/evaluate_quality.py` shows the range where that holds.
    """

    min_dpi: float = 150.0
    very_low_dpi: float = 100.0
    min_blur_score: float = 90.0


@dataclass(frozen=True)
class PageQuality:
    page_number: int
    min_effective_dpi: float | None
    blur_score: float | None
    flags: tuple[str, ...]

    @property
    def flagged(self) -> bool:
        return bool(self.flags)


def assess_page(
    measurements: PageMeasurements, thresholds: QualityThresholds | None = None
) -> PageQuality:
    """The flags for one page.

    A page with no picture on it has no flags: vector text and vector art
    are as sharp as they can be, and a warning about them would be
    wrong.
    """
    limits = thresholds or QualityThresholds()
    flags: list[str] = []
    if measurements.min_effective_dpi is not None:
        if measurements.min_effective_dpi < limits.very_low_dpi:
            flags.append("VERY_LOW_RESOLUTION")
        elif measurements.min_effective_dpi < limits.min_dpi:
            flags.append("LOW_RESOLUTION")
    if measurements.blur_score is not None and measurements.blur_score < limits.min_blur_score:
        flags.append("BLURRY")
    return PageQuality(
        page_number=measurements.page_number,
        min_effective_dpi=measurements.min_effective_dpi,
        blur_score=measurements.blur_score,
        flags=tuple(flags),
    )


def assess_document(
    measurements: list[PageMeasurements], thresholds: QualityThresholds | None = None
) -> list[PageQuality]:
    return [assess_page(page, thresholds) for page in measurements]
