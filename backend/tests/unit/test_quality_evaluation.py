"""The evaluation of the quality rules against the labelled fixture set.

The requirement says the report must flag at least 90% of the known bad
pages and at most 10% of the known good ones. These tests are that
check, run every time the suite runs, so the numbers cannot drift
without somebody noticing.
"""

from app.domain.pdf_rules import QualityThresholds
from app.quality.fixtures import all_fixtures, calibration_fixtures, holdout_fixtures
from scripts.evaluate_quality import (
    TARGET_FALSE_POSITIVE_RATE,
    TARGET_RECALL,
    choose_blur_threshold,
    evaluate,
    measure,
)


def test_the_fixture_set_has_at_least_thirty_pages_of_both_kinds() -> None:
    fixtures = all_fixtures()
    assert len(fixtures) >= 30
    assert any(fixture.expected_bad for fixture in fixtures)
    assert any(not fixture.expected_bad for fixture in fixtures)


def test_a_kind_is_never_in_both_halves_of_the_set() -> None:
    calibration_kinds = {fixture.kind for fixture in calibration_fixtures()}
    holdout_kinds = {fixture.kind for fixture in holdout_fixtures()}
    assert calibration_kinds.isdisjoint(holdout_kinds)


def test_the_thresholds_meet_the_targets_on_the_held_out_half() -> None:
    measurements = measure(all_fixtures())
    holdout = [m for m in measurements if m.split == "holdout"]
    thresholds = QualityThresholds(
        min_blur_score=choose_blur_threshold([m for m in measurements if m.split == "calibration"])
    )
    report = evaluate(holdout, thresholds)
    assert report["recall_on_bad_pages"] >= TARGET_RECALL
    assert report["false_positive_rate_on_good_pages"] <= TARGET_FALSE_POSITIVE_RATE


def test_the_thresholds_meet_the_targets_on_the_calibration_half() -> None:
    measurements = measure(all_fixtures())
    calibration = [m for m in measurements if m.split == "calibration"]
    thresholds = QualityThresholds(min_blur_score=choose_blur_threshold(calibration))
    report = evaluate(calibration, thresholds)
    assert report["recall_on_bad_pages"] >= TARGET_RECALL
    assert report["false_positive_rate_on_good_pages"] <= TARGET_FALSE_POSITIVE_RATE
