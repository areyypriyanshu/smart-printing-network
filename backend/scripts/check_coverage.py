"""Fail the build when coverage drops below the documented floors.

The floors come from `AGENTS.md`:

- at least 90% on `domain` and on `services`
- at least 80% overall

`domain` and `services` are checked separately because they carry the
business rules. A good total can hide a layer that is barely tested.

Run it after pytest with `--cov-append` so the numbers cover every test
step:

    uv run pytest tests --cov=app --cov-append
    uv run python scripts/check_coverage.py
"""

import os
import sys
from pathlib import Path

from coverage import Coverage


def _floor(name: str, default: float) -> float:
    """The floor for a group. Overridable so the gate can be tested."""
    return float(os.environ.get(name, str(default)))


DOMAIN_FLOOR = _floor("SPN_DOMAIN_COVERAGE_FLOOR", 90.0)
SERVICES_FLOOR = _floor("SPN_SERVICES_COVERAGE_FLOOR", 90.0)
OVERALL_FLOOR = _floor("SPN_OVERALL_COVERAGE_FLOOR", 80.0)

DATA_FILE = Path(".coverage")


def percentage(covered: int, total: int) -> float:
    if total == 0:
        return 100.0
    return 100.0 * covered / total


def group_coverage(coverage: Coverage, prefix: str) -> tuple[int, int]:
    """Covered and total statements for the files under `prefix`.

    The paths in the coverage data are absolute, so they are made relative
    to the working directory before they are compared with the prefix.
    """
    root = Path.cwd().resolve()
    covered = 0
    total = 0
    for filename in coverage.get_data().measured_files():
        path = Path(filename).resolve()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if not relative.startswith(prefix):
            continue
        # analysis2 returns (filename, statements, excluded, missing, text)
        _filename, statements, _excluded, missing, _text = coverage.analysis2(str(path))
        total += len(statements)
        covered += len(statements) - len(missing)
    return covered, total


def main() -> int:
    if not DATA_FILE.exists():
        print(f"check_coverage: {DATA_FILE} not found. Run pytest with --cov first.")
        return 1

    coverage = Coverage(data_file=str(DATA_FILE))
    coverage.load()

    results: list[tuple[str, float, float, bool]] = []

    for label, prefix, floor in (
        ("domain", "app/domain", DOMAIN_FLOOR),
        ("services", "app/services", SERVICES_FLOOR),
    ):
        covered, total = group_coverage(coverage, prefix)
        actual = percentage(covered, total)
        results.append((label, actual, floor, actual >= floor))

    covered, total = group_coverage(coverage, "app/")
    overall = percentage(covered, total)
    results.append(("overall", overall, OVERALL_FLOOR, overall >= OVERALL_FLOOR))

    failures = 0
    for label, actual, floor, passed in results:
        mark = "ok  " if passed else "FAIL"
        print(f"check_coverage: {mark} {label:9} {actual:5.1f}%  (floor {floor:.0f}%)")
        if not passed:
            failures += 1

    if failures:
        print(f"check_coverage: {failures} floor(s) not met")
        return 1
    print("check_coverage: every floor is met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
