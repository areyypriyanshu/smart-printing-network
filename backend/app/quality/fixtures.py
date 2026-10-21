"""The labelled fixture set the quality rules are calibrated against.

Each fixture is a page: a known-good one (text, vector art, a sharp photo,
a clean scan) or a known-bad one (a thumbnail stretched across the page, a
blurred scan, a tiny image blown up). The labels live here rather than in
a committed CSV of binary files, so the set is reproducible, small and
reviewable.

The generator is deterministic: the same seed gives the same pixels, so a
calibration run is comparable with the one before it.

The set is split in two. A whole kind goes to one half or the other, never
both, so the same source image cannot appear in the calibration half and
in the held out half. The threshold is chosen on the calibration half and
reported on the held out half.
"""

from dataclasses import dataclass

import cv2
import numpy as np
import pymupdf

#: The page size every fixture is drawn on, in PostScript points (A4).
PAGE_WIDTH = 595
PAGE_HEIGHT = 842

#: The seed every random image starts from. Fixed, so the set never
#: changes under the feet of a calibration run.
SEED = 20261021

#: The width of the box every fixture image is printed into, in points.
#: The image keeps its own pixel count, so the effective resolution is
#: decided by how many pixels there are to fill that box. A 1600 pixel
#: image in this box is sharp, and a 120 pixel image in the same box is
#: the pixelated page a customer complains about.
PLACED_WIDTH_POINTS = 297.0


@dataclass(frozen=True)
class Fixture:
    """One labelled page."""

    name: str
    kind: str
    #: The flags the page is expected to raise. An empty tuple means the
    #: page is expected to be clean.
    expected_flags: tuple[str, ...]
    #: A short note about what makes the page good or bad.
    note: str
    #: Which half of the set the page belongs to: "calibration" or
    #: "holdout". A whole kind belongs to one half only.
    split: str
    #: A number that makes this page's pixels different from every other
    #: page's pixels.
    seed: int

    @property
    def expected_bad(self) -> bool:
        """Does the page carry a warning the customer should see?"""
        return bool(self.expected_flags)

    def render(self) -> bytes:
        return _render(self)


def _noise_image(width: int, height: int, seed: int) -> np.ndarray:
    """A deterministic, detailed image.

    Random noise has a lot of high frequency detail in every direction,
    so a sharp version of it and a blurred version of it are easy to tell
    apart, and the picture of it does not depend on what was drawn.
    """
    generator = np.random.default_rng(SEED + seed + width + height)
    noise = generator.integers(0, 256, size=(height, width, 3), dtype=np.uint8)
    blurred = cv2.GaussianBlur(noise, (0, 0), 3)
    return cv2.addWeighted(noise, 0.5, blurred, 0.5, 0)


def _blurred_image(width: int, height: int, kernel: int, seed: int) -> np.ndarray:
    return cv2.GaussianBlur(_noise_image(width, height, seed), (0, 0), kernel)


def _motion_blurred_image(width: int, height: int, size: int, seed: int) -> np.ndarray:
    image = _noise_image(width, height, seed)
    kernel = np.zeros((size, size), dtype=np.float32)
    kernel[size // 2, :] = 1.0 / size
    return cv2.filter2D(image, -1, kernel)


def _png(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise ValueError("The fixture image could not be encoded")
    return encoded.tobytes()


def _pdf_with_image(image: np.ndarray) -> bytes:
    """A one page PDF holding the image in the fixed placement box."""
    height, width = image.shape[:2]
    document = pymupdf.open()
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    placed_height = PLACED_WIDTH_POINTS * height / width
    rect = pymupdf.Rect(0, 0, PLACED_WIDTH_POINTS, placed_height)
    page.insert_image(rect, stream=_png(image))
    output: bytes = document.tobytes()
    document.close()
    return output


def _pdf_with_text() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_text((60, 100), "Smart Printing Network quality fixture", fontsize=18)
    for line in range(20):
        page.insert_text((60, 140 + line * 22), f"Line {line + 1} of vector text.", fontsize=11)
    output: bytes = document.tobytes()
    document.close()
    return output


def _pdf_with_vector() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    shape = page.new_shape()
    shape.draw_circle((300, 400), 120)
    shape.finish(color=(0.1, 0.3, 0.6), fill=(0.8, 0.9, 1.0), width=3)
    shape.commit()
    output: bytes = document.tobytes()
    document.close()
    return output


def _pdf_with_text_and_image(image: np.ndarray) -> bytes:
    height, width = image.shape[:2]
    document = pymupdf.open()
    page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    page.insert_text((60, 60), "A page with text and a picture.", fontsize=14)
    placed_height = PLACED_WIDTH_POINTS * height / width
    rect = pymupdf.Rect(60, 100, 60 + PLACED_WIDTH_POINTS, 100 + placed_height)
    page.insert_image(rect, stream=_png(image))
    output: bytes = document.tobytes()
    document.close()
    return output


def _render(fixture: Fixture) -> bytes:
    kind = fixture.kind
    seed = fixture.seed
    if kind == "vector_text":
        return _pdf_with_text()
    if kind == "vector_art":
        return _pdf_with_vector()
    if kind == "sharp_photo":
        return _pdf_with_image(_noise_image(1600, 1200, seed))
    if kind == "good_scan":
        return _pdf_with_image(_noise_image(1400, 1000, seed))
    if kind == "low_resolution":
        return _pdf_with_image(_noise_image(120, 90, seed))
    if kind == "upscaled_thumbnail":
        return _pdf_with_image(_noise_image(60, 45, seed))
    if kind == "tiny_image":
        return _pdf_with_image(_noise_image(20, 15, seed))
    if kind == "blurred_scan":
        return _pdf_with_image(_blurred_image(1400, 1000, 9, seed))
    if kind == "very_blurred_scan":
        return _pdf_with_image(_blurred_image(1400, 1000, 21, seed))
    if kind == "motion_blurred_scan":
        return _pdf_with_image(_motion_blurred_image(1400, 1000, 41, seed))
    if kind == "text_with_low_resolution_image":
        return _pdf_with_text_and_image(_noise_image(120, 90, seed))
    if kind == "text_with_sharp_image":
        return _pdf_with_text_and_image(_noise_image(1600, 1200, seed))
    raise ValueError(f"Unknown fixture kind: {kind}")


#: Every kind, how many pages it has, the flags those pages are expected
#: to raise, which half of the set the kind belongs to, and how to
#: describe it. The half is part of the kind, so a kind never appears in
#: both halves.
_KINDS: list[tuple[str, int, tuple[str, ...], str, str]] = [
    ("vector_text", 4, (), "calibration", "vector text is sharp by definition"),
    ("sharp_photo", 6, (), "calibration", "a sharp photograph printed large"),
    ("good_scan", 5, (), "calibration", "a clean scan printed large"),
    (
        "text_with_sharp_image",
        3,
        (),
        "calibration",
        "a page with text and a sharp picture",
    ),
    (
        "low_resolution",
        5,
        ("VERY_LOW_RESOLUTION",),
        "calibration",
        "a 120 pixel image printed large",
    ),
    (
        "tiny_image",
        3,
        ("VERY_LOW_RESOLUTION",),
        "calibration",
        "a 20 pixel image blown up to fill the page",
    ),
    ("blurred_scan", 4, ("BLURRY",), "calibration", "a scan blurred with a wide kernel"),
    ("vector_art", 3, (), "holdout", "vector art has no resolution limit"),
    (
        "text_with_low_resolution_image",
        3,
        ("VERY_LOW_RESOLUTION",),
        "holdout",
        "readable text with a pixelated picture",
    ),
    (
        "upscaled_thumbnail",
        4,
        ("VERY_LOW_RESOLUTION",),
        "holdout",
        "a 60 pixel thumbnail stretched across the page",
    ),
    (
        "very_blurred_scan",
        3,
        ("BLURRY",),
        "holdout",
        "a scan blurred past the point of detail",
    ),
    (
        "motion_blurred_scan",
        3,
        ("BLURRY",),
        "holdout",
        "a scan blurred by camera movement",
    ),
]


def all_fixtures() -> list[Fixture]:
    """Every fixture page, in a stable order.

    There are more than thirty pages, and both kinds are represented: a
    checker that only ever saw bad pages would flag everything and look
    perfect.
    """
    fixtures: list[Fixture] = []
    for kind, count, expected_flags, split, note in _KINDS:
        for index in range(count):
            fixtures.append(
                Fixture(
                    name=f"{'bad' if expected_flags else 'good'}-{kind}-{index}",
                    kind=kind,
                    expected_flags=expected_flags,
                    note=note,
                    split=split,
                    # Every page has its own pixels, so two pages of the
                    # same kind are not the same page twice.
                    seed=len(fixtures) * 7919,
                )
            )
    return fixtures


def calibration_fixtures() -> list[Fixture]:
    return [f for f in all_fixtures() if f.split == "calibration"]


def holdout_fixtures() -> list[Fixture]:
    return [f for f in all_fixtures() if f.split == "holdout"]


def labels_csv() -> str:
    """The labels as CSV, the way the plan asks for them."""
    lines = ["fixture,kind,split,expected_flags,note"]
    for fixture in all_fixtures():
        flags = "|".join(fixture.expected_flags) if fixture.expected_flags else "none"
        lines.append(f"{fixture.name},{fixture.kind},{fixture.split},{flags},{fixture.note}")
    return "\n".join(lines) + "\n"
