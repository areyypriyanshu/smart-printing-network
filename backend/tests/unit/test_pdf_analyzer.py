from pathlib import Path

import pymupdf
from app.quality.analyzer import analyze_pdf


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
