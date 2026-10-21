"""Calibrate the quality rules against the labelled fixture set.

The rules are thresholds, and a threshold is only a fact when it has been
measured. This script runs the analyzer over every labelled fixture page,
prints the recall on the bad pages, the false positive rate on the good
pages, and a sweep of the blur threshold, and writes the result to a file
so the numbers are part of the repository.

The threshold is chosen on the calibration half of the set and reported on
the held out half, so a number that only works on the pages it was tuned
on cannot be reported as a result.

Run it from the backend directory:

    uv run python scripts/evaluate_quality.py
"""

import json
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.domain.pdf_rules import PageMeasurements, QualityThresholds, assess_page
from app.quality.analyzer import analyze_pdf
from app.quality.fixtures import Fixture, all_fixtures, labels_csv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = BACKEND_ROOT / "quality_evaluation.json"
LABELS_PATH = BACKEND_ROOT / "quality_labels.csv"

#: The targets from the requirement: at least 90% of the bad pages
#: flagged, and at most 10% of the good pages flagged.
TARGET_RECALL = 0.90
TARGET_FALSE_POSITIVE_RATE = 0.10

#: The blur threshold candidates. The score is a variance of a Laplacian
#: on a rendering, so it is not a round number in any natural unit; the
#: candidates are the whole range the sweep prints.
BLUR_CANDIDATES = [float(value) for value in range(0, 400, 10)]


@dataclass(frozen=True)
class Measurement:
    fixture: str
    kind: str
    split: str
    expected_flags: tuple[str, ...]
    min_effective_dpi: float | None
    blur_score: float | None

    @property
    def expected_bad(self) -> bool:
        return bool(self.expected_flags)


def measure(fixtures: Iterable[Fixture]) -> list[Measurement]:
    measurements: list[Measurement] = []
    with tempfile.TemporaryDirectory() as directory:
        for fixture in fixtures:
            path = Path(directory) / f"{fixture.name}.pdf"
            path.write_bytes(fixture.render())
            result = analyze_pdf(path)
            for page in result.pages:
                measurements.append(
                    Measurement(
                        fixture=fixture.name,
                        kind=fixture.kind,
                        split=fixture.split,
                        expected_flags=fixture.expected_flags,
                        min_effective_dpi=page.min_effective_dpi,
                        blur_score=page.blur_score,
                    )
                )
    return measurements


def _flags(measurement: Measurement, thresholds: QualityThresholds) -> tuple[str, ...]:
    quality = assess_page(
        PageMeasurements(
            page_number=1,
            min_effective_dpi=measurement.min_effective_dpi,
            blur_score=measurement.blur_score,
        ),
        thresholds,
    )
    return quality.flags


def evaluate(measurements: list[Measurement], thresholds: QualityThresholds) -> dict[str, object]:
    bad = [m for m in measurements if m.expected_bad]
    good = [m for m in measurements if not m.expected_bad]
    bad_flagged = sum(1 for m in bad if _flags(m, thresholds))
    good_flagged = sum(1 for m in good if _flags(m, thresholds))
    recall = bad_flagged / len(bad) if bad else 0.0
    false_positive_rate = good_flagged / len(good) if good else 0.0
    return {
        "pages": len(measurements),
        "bad_pages": len(bad),
        "good_pages": len(good),
        "flagged_bad_pages": bad_flagged,
        "flagged_good_pages": good_flagged,
        "recall_on_bad_pages": round(recall, 4),
        "false_positive_rate_on_good_pages": round(false_positive_rate, 4),
    }


def sweep(measurements: list[Measurement]) -> list[dict[str, object]]:
    """What each blur threshold would do to the numbers.

    The DPI thresholds are left alone: the resolution rule is a physical
    one, and a shop printing at 300 dpi does not care what the Laplacian
    says.
    """
    rows: list[dict[str, object]] = []
    for threshold in BLUR_CANDIDATES:
        result = evaluate(
            measurements,
            QualityThresholds(min_blur_score=threshold),
        )
        rows.append({"min_blur_score": threshold, **result})
    return rows


def choose_blur_threshold(calibration: list[Measurement]) -> float:
    """The threshold to use, chosen on the calibration half alone.

    Every candidate is tried on the calibration pages, and the one that
    meets both targets there with the most distance from the nearest
    measured score is taken. A threshold sitting on top of a measurement
    would stop working the moment a page changed a little.
    """
    best: tuple[float, float] | None = None
    for candidate in BLUR_CANDIDATES:
        thresholds = QualityThresholds(min_blur_score=candidate)
        result = evaluate(calibration, thresholds)
        if result["recall_on_bad_pages"] < TARGET_RECALL:
            continue
        if result["false_positive_rate_on_good_pages"] > TARGET_FALSE_POSITIVE_RATE:
            continue
        margin = _margin(calibration, thresholds)
        if best is None or margin > best[1]:
            best = (candidate, margin)
    if best is None:
        raise SystemExit("No blur threshold meets the targets on the calibration half")
    return best[0]


def _margin(measurements: list[Measurement], thresholds: QualityThresholds) -> float:
    """How far the threshold is from the nearest page it would misjudge.

    A large margin means the threshold is not sitting on top of a
    measurement, so a page that is a little different does not flip the
    answer.
    """
    scores = [m.blur_score for m in measurements if m.blur_score is not None]
    if not scores:
        return 0.0
    margins = [abs(score - thresholds.min_blur_score) for score in scores]
    return round(min(margins), 4)


def main() -> int:
    fixtures = all_fixtures()
    measurements = measure(fixtures)
    calibration = [m for m in measurements if m.split == "calibration"]
    holdout = [m for m in measurements if m.split == "holdout"]

    chosen = choose_blur_threshold(calibration)
    thresholds = QualityThresholds(min_blur_score=chosen)

    calibration_report = evaluate(calibration, thresholds)
    holdout_report = evaluate(holdout, thresholds)
    rows = sweep(measurements)

    print(f"Pages measured: {len(measurements)}")
    print(f"Blur threshold chosen on the calibration half: {chosen}")
    print()
    print("split    | pages | recall | false positive rate")
    for name, report in (
        ("calibration", calibration_report),
        ("holdout    ", holdout_report),
    ):
        print(
            f"{name} | {report['pages']:>5} | {report['recall_on_bad_pages']:>6} | "
            f"{report['false_positive_rate_on_good_pages']:>6}"
        )
    print()
    print("blur threshold | recall | false positive rate")
    for row in rows:
        print(
            f"{row['min_blur_score']:>15} | {row['recall_on_bad_pages']:>6} | "
            f"{row['false_positive_rate_on_good_pages']:>6}"
        )

    OUTPUT_PATH.write_text(
        json.dumps(
            {
                "targets": {
                    "recall_on_bad_pages": TARGET_RECALL,
                    "false_positive_rate_on_good_pages": TARGET_FALSE_POSITIVE_RATE,
                },
                "chosen_blur_threshold": chosen,
                "calibration": calibration_report,
                "holdout": holdout_report,
                "sweep": rows,
                "measurements": [
                    {
                        "fixture": m.fixture,
                        "kind": m.kind,
                        "split": m.split,
                        "expected_flags": list(m.expected_flags),
                        "min_effective_dpi": m.min_effective_dpi,
                        "blur_score": m.blur_score,
                        "flags": list(_flags(m, thresholds)),
                    }
                    for m in measurements
                ],
            },
            indent=2,
        )
        + "\n"
    )
    LABELS_PATH.write_text(labels_csv())
    print()
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Wrote {LABELS_PATH}")

    recall = holdout_report["recall_on_bad_pages"]
    false_positive_rate = holdout_report["false_positive_rate_on_good_pages"]
    if recall < TARGET_RECALL or false_positive_rate > TARGET_FALSE_POSITIVE_RATE:
        print("The held out half does not meet the targets.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
