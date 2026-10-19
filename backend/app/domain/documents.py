"""What kind of document a file is, and what to say about it.

A student uploads the wrong file and the old message was "File does not
look like a PDF", which is a dead end. This module knows what the file
actually is, so the error can name the fix.

Everything here is pure: bytes in, an answer out. No file system, no
framework, no I/O.
"""

from dataclasses import dataclass
from enum import StrEnum

PDF = "pdf"
DOCX = "docx"
XLSX = "xlsx"
PPTX = "pptx"
LEGACY_OFFICE = "legacy_office"
RTF = "rtf"
IMAGE = "image"
TEXT = "text"
EMPTY = "empty"
UNKNOWN = "unknown"

#: The formats the platform can print. Everything else is refused with a
#: message that says how to turn it into something we can print.
PRINTABLE = frozenset({PDF, DOCX, XLSX, PPTX})

#: The formats that are turned into a PDF before they are printed. A
#: document in one of these is not printed as it is: it is converted, and
#: the page count and the price come from the converted PDF.
CONVERTED = frozenset({DOCX, XLSX, PPTX})

ZIP_MAGIC = b"PK\x03\x04"
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
RTF_MAGIC = b"{\\rtf"
PDF_MAGIC = b"%PDF-"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
GIF_MAGIC = b"GIF8"


class DocumentType(StrEnum):
    """What the file is."""

    PDF = "pdf"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    LEGACY_OFFICE = "legacy_office"
    RTF = "rtf"
    IMAGE = "image"
    TEXT = "text"
    EMPTY = "empty"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DocumentInfo:
    """What the file is, and what to tell the customer about it."""

    kind: DocumentType
    #: True when the platform can print this file, converting it first if
    #: it has to.
    printable: bool
    #: True when the file has to be converted before it is printed.
    converted: bool
    #: The message to show when the file cannot be printed. None when it
    #: can.
    message: str | None = None


def detect(head: bytes, *, filename: str = "") -> DocumentType:
    """Work out what a file is from its first bytes.

    The extension is a hint and is only used when the bytes are
    ambiguous. A file called `report.pdf` that is really a Word document
    is a Word document.
    """
    if not head:
        # The file has nothing in it. The extension is not evidence.
        return DocumentType.EMPTY
    if head.startswith(PDF_MAGIC):
        return DocumentType.PDF
    if head.startswith(OLE2_MAGIC):
        # The old binary Office formats: .doc, .xls, .ppt.
        return DocumentType.LEGACY_OFFICE
    if head.startswith(RTF_MAGIC):
        return DocumentType.RTF
    if head.startswith(ZIP_MAGIC):
        return _detect_zip(head)
    if head.startswith(PNG_MAGIC) or head.startswith(JPEG_MAGIC):
        return DocumentType.IMAGE
    if head.startswith(GIF_MAGIC):
        return DocumentType.IMAGE
    if _looks_like_text(head):
        return DocumentType.TEXT
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return DocumentType.PDF
    if lowered.endswith(".docx"):
        return DocumentType.DOCX
    if lowered.endswith(".xlsx"):
        return DocumentType.XLSX
    if lowered.endswith(".pptx"):
        return DocumentType.PPTX
    return DocumentType.UNKNOWN


def _detect_zip(head: bytes) -> DocumentType:
    """Tell the OOXML formats apart from a plain zip.

    A Word document, a spreadsheet and a presentation are all zip files.
    The difference is one name inside them, and that name appears near
    the start of the archive, so the first few kilobytes are enough.
    """
    window = head[:8192]
    if b"word/document.xml" in window:
        return DocumentType.DOCX
    if b"xl/workbook.xml" in window:
        return DocumentType.XLSX
    if b"ppt/presentation.xml" in window:
        return DocumentType.PPTX
    return DocumentType.UNKNOWN


def _looks_like_text(head: bytes) -> bool:
    """A file of plain text has no control bytes other than whitespace."""
    if not head:
        return False
    return all(not (byte < 9 or (13 < byte < 32)) for byte in head[:1024])


def describe(kind: DocumentType) -> DocumentInfo:
    """What to do with a file of this kind, and what to say about it."""
    if kind is DocumentType.PDF:
        return DocumentInfo(kind=kind, printable=True, converted=False, message=None)
    if kind in (DocumentType.DOCX, DocumentType.XLSX, DocumentType.PPTX):
        return DocumentInfo(kind=kind, printable=True, converted=True, message=None)
    if kind is DocumentType.LEGACY_OFFICE:
        return DocumentInfo(
            kind=kind,
            printable=False,
            converted=False,
            message=(
                "That is an old Word or Excel file, which we cannot print "
                "directly. Open it in the app, choose Save As, and save it as "
                "a .docx or .xlsx. Or upload a PDF."
            ),
        )
    if kind is DocumentType.RTF:
        return DocumentInfo(
            kind=kind,
            printable=False,
            converted=False,
            message=(
                "We cannot print RTF files. Open it in Word or Google Docs "
                "and download it as a PDF, then upload that."
            ),
        )
    if kind is DocumentType.IMAGE:
        return DocumentInfo(
            kind=kind,
            printable=False,
            converted=False,
            message=(
                "We print PDF files, not images. Open your file in Google Docs "
                "and choose File, Download as PDF, then upload that."
            ),
        )
    if kind is DocumentType.TEXT:
        return DocumentInfo(
            kind=kind,
            printable=False,
            converted=False,
            message=(
                "We print PDF files, not plain text. Open your file in Google "
                "Docs and choose File, Download as PDF, then upload that."
            ),
        )
    if kind is DocumentType.EMPTY:
        return DocumentInfo(
            kind=kind,
            printable=False,
            converted=False,
            message=("That file is empty. Choose it again on your computer and upload it."),
        )
    return DocumentInfo(
        kind=kind,
        printable=False,
        converted=False,
        message=(
            "We print PDF files. Open your file in Google Docs and choose "
            "File, Download as PDF, then upload that. Word, Excel and "
            "PowerPoint files are fine too."
        ),
    )
