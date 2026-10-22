"""The measurements a quality report is built from.

This module reads a PDF and measures two things per page: the effective
resolution of the images on the page, and how sharp they are. It does no
database or storage work, and it does not decide anything: the flags come
from the pure rules in `app.domain.pdf_rules`.

The two measurements are taken differently on purpose.

The resolution is the pixel count of the image divided by the size it is
printed at, so it is a property of the file and does not depend on how
the page is drawn.

The blur score is taken from the picture as it will be printed: the region
of the page the image occupies is rendered at a fixed width, and the
variance of the Laplacian of that grey rendering is the score. Rendering
the region rather than the image file keeps a picture that is low
resolution and a picture that is blurred two different problems, and
keeps text on the page out of the measurement.

The work is bounded. The number of pages, the number of pictures on a
page, the size of every rendered region and the time the whole analysis
may take are all capped, because the file comes from a stranger.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pymupdf

from app.domain import limits
from app.domain.pdf_rules import PageMeasurements

#: The width every picture region is rendered at, in pixels. The score
#: only means something against a fixed width, because a bigger picture
#: has more detail in it.
RENDER_WIDTH = 1000

#: The most pictures one page may have. A page with thousands of them is
#: not a document anybody is going to print, and the work has to be
#: bounded.
MAX_IMAGES_PER_PAGE = 50

#: The most pixels a rendered region may have. A very large picture would
#: use more memory than the worker should spend on one page.
MAX_RENDER_PIXELS = 8_000_000

#: The most pages one file may have. It is the same number the upload
#: limit uses, so a file that was accepted can be analysed. The
#: analyzer is still called with its own bound, so that it is safe on
#: its own.
MAX_PAGES = limits.MAX_PAGES


class AnalysisTimeout(Exception):
    """The analysis took longer than it was allowed to."""


@dataclass(frozen=True)
class AnalysisResult:
    pages: list[PageMeasurements]


def _blur_score(image: np.ndarray) -> float:
    """How sharp the picture is.

    The variance of the Laplacian is the standard measure: a sharp
    picture has many strong edges, so the variance is high, and a blurred
    one has soft edges, so the variance is low.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _region_blur(
    page: pymupdf.Page, rect: pymupdf.Rect, *, render_width: int = RENDER_WIDTH
) -> float:
    """The blur score of the part of the page the image occupies."""
    width = max(rect.width, 1.0)
    height = max(rect.height, 1.0)
    scale = render_width / width
    if width * scale * height * scale > MAX_RENDER_PIXELS:
        scale = (MAX_RENDER_PIXELS / (width * height)) ** 0.5
    matrix = pymupdf.Matrix(scale, scale)
    pixmap = page.get_pixmap(
        matrix=matrix,
        clip=rect,
        colorspace=pymupdf.csGRAY,
        alpha=False,
    )
    array = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width)
    return _blur_score(array)


def analyze_pdf(
    path: Path,
    *,
    max_pages: int = MAX_PAGES,
    timeout_seconds: float | None = None,
) -> AnalysisResult:
    """Measure every page of the PDF.

    The timeout is checked between pages and between pictures, so a file
    that is merely long is stopped, and a file that is slow at one point
    is stopped after that point.
    """
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    document = pymupdf.open(str(path))
    try:
        if document.needs_pass:
            raise ValueError("The PDF is password protected")
        if document.page_count > max_pages:
            raise ValueError("The PDF has too many pages")
        pages: list[PageMeasurements] = []
        for index, page in enumerate(document, start=1):
            _check_deadline(deadline)
            pages.append(PageMeasurements(index, *_measure_page(page, deadline)))
        return AnalysisResult(pages)
    finally:
        document.close()


def _check_deadline(deadline: float | None) -> None:
    if deadline is not None and time.monotonic() > deadline:
        raise AnalysisTimeout("The quality check took too long and was stopped")


def _measure_page(
    page: pymupdf.Page, deadline: float | None = None
) -> tuple[float | None, float | None]:
    """The resolution and the blur score of one page.

    A page with no picture on it has neither: vector text and vector art
    are as sharp as they can be, and a number for them would be a
    measurement of nothing.
    """
    images = page.get_images(full=True)
    if len(images) > MAX_IMAGES_PER_PAGE:
        raise ValueError("The page has too many images on it")
    dpis: list[float] = []
    blurs: list[float] = []
    for image in images:
        _check_deadline(deadline)
        xref = image[0]
        pixel_width = image[2]
        pixel_height = image[3]
        for rect in page.get_image_rects(xref):
            if rect.width <= 0 or rect.height <= 0:
                continue
            dpis.append(
                min(
                    pixel_width * 72.0 / rect.width,
                    pixel_height * 72.0 / rect.height,
                )
            )
            blurs.append(_region_blur(page, rect))
    if not dpis:
        return None, None
    # The worst picture on the page is the one that decides the answer.
    return min(dpis), min(blurs)
