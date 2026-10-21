from app.domain.pdf_rules import PageMeasurements, QualityThresholds, assess_document, assess_page


def test_low_dpi_and_blur_flags_are_reported() -> None:
    result = assess_page(PageMeasurements(1, 120.0, 20.0))
    assert result.flags == ("LOW_RESOLUTION", "BLURRY")


def test_measurements_at_threshold_are_not_flagged() -> None:
    limits = QualityThresholds()
    result = assess_page(PageMeasurements(1, limits.min_dpi, limits.min_blur_score))
    assert result.flags == ()


def test_vector_page_has_no_quality_measurement_or_warning() -> None:
    result = assess_page(PageMeasurements(1, None, None))
    assert result.min_effective_dpi is None
    assert result.blur_score is None
    assert not result.flagged


def test_document_preserves_page_order() -> None:
    result = assess_document(
        [
            PageMeasurements(2, 90.0, None),
            PageMeasurements(1, None, 100.0),
        ],
        QualityThresholds(),
    )
    assert [page.page_number for page in result] == [2, 1]
    assert result[0].flags == ("VERY_LOW_RESOLUTION",)
