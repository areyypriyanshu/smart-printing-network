"""Reading an Office file and turning it into a PDF we can print."""

import io
from pathlib import Path

import pymupdf
import pytest
from app.domain.office import (
    ImageBlock,
    OfficeReadError,
    PageBreak,
    TableBlock,
    TextBlock,
    extract_docx,
    extract_pptx,
    extract_xlsx,
)
from app.services.document_service import ConversionError, convert_to_pdf
from tests.office_fixtures import docx_bytes, png_bytes, pptx_bytes, xlsx_bytes


def _write(data: bytes, name: str = "document.bin") -> Path:
    path = Path("/tmp") / f"spn-test-{name}"
    path.write_bytes(data)
    return path


def test_a_word_document_gives_its_headings_and_text() -> None:
    blocks = extract_docx(docx_bytes([("Heading1", "A heading"), ("", "Some body text.")]))

    texts = [block for block in blocks if isinstance(block, TextBlock)]
    assert texts[0].text == "A heading"
    assert texts[0].heading == 1
    assert texts[1].text == "Some body text."
    assert texts[1].heading == 0


def test_a_word_document_gives_its_pictures() -> None:
    blocks = extract_docx(docx_bytes(with_image=True))

    images = [block for block in blocks if isinstance(block, ImageBlock)]
    assert len(images) == 1
    assert images[0].data.startswith(b"\x89PNG")


def test_a_spreadsheet_gives_a_table() -> None:
    blocks = extract_xlsx(xlsx_bytes([["Name", "Mark"], ["Asha", "90"]]))

    tables = [block for block in blocks if isinstance(block, TableBlock)]
    assert len(tables) == 1
    assert tables[0].rows == [["Name", "Mark"], ["Asha", "90"]]


def test_a_presentation_gives_one_page_per_slide() -> None:
    blocks = extract_pptx(pptx_bytes(["First", "Second"]))

    assert any(isinstance(block, PageBreak) for block in blocks)
    texts = [block.text for block in blocks if isinstance(block, TextBlock)]
    assert texts == ["First", "Second"]


def test_an_archive_that_is_not_an_office_file_cannot_be_read() -> None:
    with pytest.raises(OfficeReadError):
        extract_docx(b"this is not a zip file at all")


def test_an_archive_with_no_document_cannot_be_read() -> None:
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "nothing here")
    with pytest.raises(OfficeReadError):
        extract_docx(buffer.getvalue())


def test_a_word_document_becomes_a_pdf() -> None:
    source = _write(docx_bytes([("", "Hello from a document.")]), "doc.docx")
    target = Path("/tmp/spn-test-out.pdf")

    pages = convert_to_pdf(source, target, kind="docx")

    assert pages == 1
    with pymupdf.open(target) as document:
        assert "Hello from a document." in document[0].get_text()


def test_a_word_document_keeps_its_picture() -> None:
    source = _write(docx_bytes(with_image=True), "image.docx")
    target = Path("/tmp/spn-test-out.pdf")

    convert_to_pdf(source, target, kind="docx")

    with pymupdf.open(target) as document:
        assert len(document[0].get_images()) == 1


def test_a_spreadsheet_becomes_a_pdf_with_its_numbers() -> None:
    source = _write(xlsx_bytes([["Name", "Mark"], ["Asha", "90"]]), "sheet.xlsx")
    target = Path("/tmp/spn-test-out.pdf")

    convert_to_pdf(source, target, kind="xlsx")

    with pymupdf.open(target) as document:
        text = document[0].get_text()
    assert "Asha" in text
    assert "90" in text


def test_a_presentation_becomes_one_page_per_slide() -> None:
    source = _write(pptx_bytes(["First", "Second", "Third"]), "deck.pptx")
    target = Path("/tmp/spn-test-out.pdf")

    pages = convert_to_pdf(source, target, kind="pptx")

    assert pages == 3


def test_a_document_with_nothing_in_it_cannot_be_converted() -> None:
    source = _write(docx_bytes([]), "empty.docx")
    target = Path("/tmp/spn-test-out.pdf")

    with pytest.raises(ConversionError):
        convert_to_pdf(source, target, kind="docx")


def test_a_format_we_cannot_convert_is_refused() -> None:
    source = _write(docx_bytes(), "doc.docx")
    target = Path("/tmp/spn-test-out.pdf")

    with pytest.raises(ConversionError):
        convert_to_pdf(source, target, kind="doc")


def test_a_picture_that_is_not_a_picture_is_skipped() -> None:
    """A broken image in a document must not lose the document."""
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<w:body><w:p><w:r><w:t>Text survives</w:t></w:r></w:p>"
            '<w:p><w:r><w:drawing><a:blip r:embed="rIdImg"/></w:drawing></w:r></w:p>'
            "</w:body></w:document>",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdImg" Type="x" Target="media/image1.png"/>'
            "</Relationships>",
        )
        archive.writestr("word/media/image1.png", b"not really a png")
    source = _write(buffer.getvalue(), "broken.docx")
    target = Path("/tmp/spn-test-out.pdf")

    convert_to_pdf(source, target, kind="docx")

    with pymupdf.open(target) as document:
        assert "Text survives" in document[0].get_text()


def test_the_picture_in_a_fixture_is_a_real_picture() -> None:
    """The fixture is a real PNG, so the test above means something."""
    assert png_bytes().startswith(b"\x89PNG")


def test_a_bold_run_is_marked_as_bold() -> None:
    """A heading in bold in Word is still a heading in the PDF."""
    import io
    import zipfile

    document = (
        '<?xml version="1.0"?><w:document '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Loud</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)

    blocks = extract_docx(buffer.getvalue())

    texts = [block for block in blocks if isinstance(block, TextBlock)]
    assert texts[0].text == "Loud"
    assert texts[0].bold is True


def test_a_workbook_with_no_sheets_gives_nothing() -> None:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0"?><workbook '
            'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>',
        )

    assert extract_xlsx(buffer.getvalue()) == []


def test_a_sheet_with_no_rows_is_left_out() -> None:
    import io
    import zipfile

    sheet = (
        '<?xml version="1.0"?><worksheet '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData/></worksheet>"
    )
    workbook = (
        '<?xml version="1.0"?><workbook '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Marks" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relations = (
        '<?xml version="1.0"?><Relationships '
        'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relations)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)

    assert extract_xlsx(buffer.getvalue()) == []


def test_a_sheet_with_a_number_in_it_keeps_the_number() -> None:
    """A cell that is a number is not a shared string."""
    sheet = (
        '<?xml version="1.0"?><worksheet '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1"><c r="A1"><v>42</v></c></row></sheetData>'
        "</worksheet>"
    )
    workbook = (
        '<?xml version="1.0"?><workbook '
        'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Marks" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relations = (
        '<?xml version="1.0"?><Relationships '
        'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="x" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relations)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)

    tables = [block for block in extract_xlsx(buffer.getvalue()) if isinstance(block, TableBlock)]
    assert tables[0].rows == [["42"]]
