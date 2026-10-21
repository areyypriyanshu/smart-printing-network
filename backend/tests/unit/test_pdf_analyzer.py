import time
from pathlib import Path

import pymupdf
import pytest
from app.quality.analyzer import MAX_IMAGES_PER_PAGE, AnalysisTimeout, analyze_pdf
from tests.fixtures.pdf_files import make_encrypted_pdf, make_pdf


def _pdf_with_image(path: Path, *, width: int, height: int) -> None:
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    pix = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, width, height), False)
    pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    document.save(path)
    document.close()


def test_analyzer_reports_image_dpi_and_blur_score(tmp_path: Path) -> None:
    path = tmp_path / "image.pdf"
    _pdf_with_image(path, width=300, height=300)
    result = analyze_pdf(path)
    assert len(result.pages) == 1
    assert result.pages[0].min_effective_dpi is not None
    assert result.pages[0].min_effective_dpi < 150
    assert result.pages[0].blur_score is not None


def test_analyzer_reports_vector_page_without_image_dpi(tmp_path: Path) -> None:
    path = tmp_path / "text.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Hello")
    document.save(path)
    document.close()
    result = analyze_pdf(path)
    # A page with no raster content has nothing to measure: vector text is
    # sharp by definition, so there is no resolution and no blur score.
    assert result.pages[0].min_effective_dpi is None
    assert result.pages[0].blur_score is None


def test_a_file_that_takes_too_long_is_stopped(tmp_path: Path) -> None:
    """The timeout is the bound on a file that is slow.

    The deadline is in the past, so the check trips on the first page.
    A file that is merely long is stopped by the same check, and a file
    that is slow to parse at one point is stopped after that point.
    """
    path = make_pdf(tmp_path / "slow.pdf", pages=2)

    with pytest.raises(AnalysisTimeout):
        analyze_pdf(path, timeout_seconds=-1.0)


def test_the_timeout_is_checked_between_pages(tmp_path: Path) -> None:
    path = make_pdf(tmp_path / "long.pdf", pages=3)
    deadline = time.monotonic() + 30.0

    result = analyze_pdf(path, timeout_seconds=30.0)

    assert len(result.pages) == 3
    assert deadline > 0.0


def test_a_password_protected_file_is_refused(tmp_path: Path) -> None:
    path = make_encrypted_pdf(tmp_path / "locked.pdf")

    with pytest.raises(ValueError, match="password protected"):
        analyze_pdf(path)


def test_a_file_with_too_many_pages_is_refused(tmp_path: Path) -> None:
    path = make_pdf(tmp_path / "many.pdf", pages=3)

    with pytest.raises(ValueError, match="too many pages"):
        analyze_pdf(path, max_pages=2)


def test_a_page_with_too_many_images_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "crowded.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    pix = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 4, 4), False)
    pix.clear_with(255)
    for index in range(MAX_IMAGES_PER_PAGE + 1):
        rect = pymupdf.Rect(index * 4, 0, index * 4 + 4, 4)
        page.insert_image(rect, pixmap=pix)
    document.save(path)
    document.close()

    with pytest.raises(ValueError, match="too many images"):
        analyze_pdf(path)


def test_a_placement_with_no_area_is_ignored(tmp_path: Path, monkeypatch) -> None:
    """A picture placed with no width or no height is skipped.

    The PDF library refuses to write such a placement, so it can only
    come from a file that was written by something else. The guard is
    there so that one such placement does not divide by zero and take
    the whole report down.
    """
    path = tmp_path / "image.pdf"
    _pdf_with_image(path, width=300, height=300)
    empty = pymupdf.Rect(10, 10, 10, 10)
    monkeypatch.setattr(pymupdf.Page, "get_image_rects", lambda _self, _xref: [empty])

    result = analyze_pdf(path)

    assert result.pages[0].min_effective_dpi is None
    assert result.pages[0].blur_score is None


def test_an_unknown_fixture_kind_is_refused() -> None:
    from app.quality.fixtures import Fixture

    with pytest.raises(ValueError, match="Unknown fixture kind"):
        Fixture(
            name="odd",
            kind="not_a_kind",
            expected_flags=(),
            note="",
            split="calibration",
            seed=1,
        ).render()


def test_a_picture_that_cannot_be_encoded_is_refused(monkeypatch) -> None:
    """The generator refuses to build a page it cannot encode.

    A page that is half written would be a fixture that lies about what
    it is, so the generator stops instead.
    """
    from app.quality import fixtures

    def cannot_encode(_image, _extension: str) -> tuple[bool, bytes]:
        return False, b""

    monkeypatch.setattr(fixtures.cv2, "imencode", cannot_encode)

    with pytest.raises(ValueError, match="could not be encoded"):
        fixtures._png(fixtures._noise_image(10, 10, 1))


def test_a_very_tall_picture_is_rendered_within_the_memory_cap(tmp_path: Path) -> None:
    """A picture placed in a very tall box is scaled down, not rendered whole.

    Rendering it at the full width would use more memory than the worker
    should spend on one page, so the rendering is cut down to the cap.
    """
    path = tmp_path / "tall.pdf"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    pix = pymupdf.Pixmap(pymupdf.csRGB, (0, 0, 20, 400), False)
    pix.clear_with(255)
    page.insert_image(pymupdf.Rect(0, 0, 20, 792), pixmap=pix)
    document.save(path)
    document.close()

    result = analyze_pdf(path)

    assert len(result.pages) == 1
    assert result.pages[0].blur_score is not None
