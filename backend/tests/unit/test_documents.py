"""Working out what a file is, and what to say about it.

A student who uploads the wrong file should be told how to fix it, not
told that their file is wrong.
"""

from app.domain.documents import DocumentType, describe, detect
from tests.office_fixtures import docx_bytes, png_bytes, xlsx_bytes


def test_a_pdf_is_a_pdf() -> None:
    assert detect(b"%PDF-1.7\n...") is DocumentType.PDF


def test_a_word_document_is_recognised() -> None:
    assert detect(docx_bytes(), filename="report.docx") is DocumentType.DOCX


def test_a_spreadsheet_is_recognised() -> None:
    assert detect(xlsx_bytes(), filename="marks.xlsx") is DocumentType.XLSX


def test_the_bytes_decide_not_the_extension() -> None:
    """A Word document called report.pdf is still a Word document."""
    assert detect(docx_bytes(), filename="report.pdf") is DocumentType.DOCX


def test_the_old_binary_office_formats_are_recognised() -> None:
    assert detect(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1...") is DocumentType.LEGACY_OFFICE


def test_an_rtf_file_is_recognised() -> None:
    assert detect(b"{\\rtf1\\ansi") is DocumentType.RTF


def test_an_image_is_recognised() -> None:
    assert detect(png_bytes()) is DocumentType.IMAGE
    assert detect(b"\xff\xd8\xff\xe0...") is DocumentType.IMAGE
    assert detect(b"GIF89a...") is DocumentType.IMAGE


def test_plain_text_is_recognised() -> None:
    assert detect(b"just some words\nand more\n") is DocumentType.TEXT


def test_something_unrecognisable_is_unknown() -> None:
    assert detect(b"\x00\x01\x02\x03\x04") is DocumentType.UNKNOWN


def test_a_pdf_is_printable_as_it_is() -> None:
    info = describe(DocumentType.PDF)

    assert info.printable is True
    assert info.converted is False
    assert info.message is None


def test_an_office_document_is_printable_after_a_conversion() -> None:
    info = describe(DocumentType.DOCX)

    assert info.printable is True
    assert info.converted is True
    assert info.message is None


def test_an_old_office_file_says_how_to_save_it() -> None:
    info = describe(DocumentType.LEGACY_OFFICE)

    assert info.printable is False
    assert info.message is not None
    assert "Save As" in info.message


def test_an_image_says_how_to_make_a_pdf() -> None:
    info = describe(DocumentType.IMAGE)

    assert info.printable is False
    assert info.message is not None
    assert "Download as PDF" in info.message


def test_every_kind_that_cannot_be_printed_explains_the_fix() -> None:
    """A dead end is a message that does not say what to do."""
    for kind in DocumentType:
        info = describe(kind)
        if info.printable:
            assert info.message is None
        else:
            assert info.message
            assert len(info.message) > 20, kind


def test_the_extension_is_used_when_the_bytes_say_nothing() -> None:
    """A file that is not recognisable is taken at its word."""
    unknown = b"\x00\x01\x02\x03"

    assert detect(unknown, filename="report.pdf") is DocumentType.PDF
    assert detect(unknown, filename="report.docx") is DocumentType.DOCX
    assert detect(unknown, filename="marks.xlsx") is DocumentType.XLSX
    assert detect(unknown, filename="deck.pptx") is DocumentType.PPTX


def test_an_empty_file_is_empty() -> None:
    """There is nothing in it, so it is not a PDF whatever it is called."""
    assert detect(b"", filename="report.pdf") is DocumentType.EMPTY


def test_the_empty_file_message_says_what_to_do() -> None:
    info = describe(DocumentType.EMPTY)

    assert info.printable is False
    assert info.message is not None
    assert "empty" in info.message.lower()
