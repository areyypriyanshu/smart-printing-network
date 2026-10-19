"""Turning an Office document into a PDF we can print.

The student uploads a .docx. The shop prints a PDF. This service reads
the document and writes the PDF, and the price, the page count and the
file the shop downloads are all about the converted PDF.

The limits are worth being clear about, and they are in
[ADR 015](../../docs/adr/015-office-file-upload.md). The text and the
pictures survive. The layout does not: fonts are substituted, the
renderer decides where the tables break, and headers, footers and
columns are dropped. A student gets their content printed, not their
exact page breaks.
"""

import html as html_escape
import logging
from collections.abc import Sequence
from pathlib import Path

import pymupdf

from app.domain.office import (
    Block,
    ImageBlock,
    OfficeReadError,
    PageBreak,
    TableBlock,
    TextBlock,
    extract_docx,
    extract_pptx,
    extract_xlsx,
)

logger = logging.getLogger(__name__)

A4 = pymupdf.paper_rect("a4")
MARGIN = 56

USER_CSS = """
* { font-family: sans-serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 18pt; margin-bottom: 6pt; }
h2 { font-size: 14pt; margin-top: 10pt; margin-bottom: 4pt; }
h3 { font-size: 12pt; margin-top: 8pt; margin-bottom: 3pt; }
h4, h5, h6 { font-size: 11pt; margin-top: 6pt; margin-bottom: 2pt; }
p { margin-bottom: 6pt; }
b, strong { font-weight: bold; }
table { border-collapse: collapse; margin-bottom: 8pt; }
td, th { border: 0.5pt solid #999; padding: 2pt 4pt; vertical-align: top; }
th { background-color: #eee; }
img { max-width: 100%; margin-bottom: 6pt; }
"""


class ConversionError(RuntimeError):
    """The document could not be turned into a PDF."""


def convert_to_pdf(source: Path, target: Path, *, kind: str) -> int:
    """Convert an Office file to a PDF and return the page count."""
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise ConversionError("The document could not be read") from exc

    try:
        if kind == "docx":
            blocks = extract_docx(data)
        elif kind == "xlsx":
            blocks = extract_xlsx(data)
        elif kind == "pptx":
            blocks = extract_pptx(data)
        else:
            raise ConversionError(f"Cannot convert a {kind} file")
    except OfficeReadError as exc:
        raise ConversionError(str(exc)) from exc

    if not blocks:
        raise ConversionError("The document has nothing in it to print")

    document_html, archive = _to_html(blocks)
    try:
        story = pymupdf.Story(html=document_html, user_css=USER_CSS, archive=archive)
        writer = pymupdf.DocumentWriter(str(target))
        try:
            more = 1
            while more:
                device = writer.begin_page(A4)
                more, _ = story.place(A4)
                story.draw(device)
                writer.end_page()
        finally:
            writer.close()
    except (RuntimeError, ValueError) as exc:
        raise ConversionError("The document could not be laid out") from exc

    try:
        with pymupdf.open(target) as document:
            pages = int(document.page_count)
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise ConversionError("The converted document could not be read") from exc
    if pages == 0:
        raise ConversionError("The converted document has no pages")
    return pages


def _to_html(blocks: Sequence[Block]) -> tuple[str, pymupdf.Archive]:
    """Build the HTML the renderer lays out, and the pictures it refers to."""
    archive = pymupdf.Archive()
    added: set[str] = set()
    parts: list[str] = ["<html><body>"]
    for block in blocks:
        if isinstance(block, TextBlock):
            parts.append(_text_html(block))
        elif isinstance(block, ImageBlock):
            parts.append(_image_html(block, archive, added))
        elif isinstance(block, TableBlock):
            parts.append(_table_html(block))
        elif isinstance(block, PageBreak):
            parts.append('<div style="page-break-after: always"></div>')
    parts.append("</body></html>")
    return "".join(parts), archive


def _text_html(block: TextBlock) -> str:
    text = html_escape.escape(block.text)
    if block.bold:
        text = f"<b>{text}</b>"
    if block.heading:
        level = min(block.heading, 6)
        return f"<h{level}>{text}</h{level}>"
    return f"<p>{text}</p>"


def _image_html(block: ImageBlock, archive: pymupdf.Archive, added: set[str]) -> str:
    if block.name in added:
        return ""
    try:
        archive.add(block.data, block.name)
    except (RuntimeError, ValueError):
        return ""
    added.add(block.name)
    return f'<p><img src="{html_escape.escape(block.name)}"></p>'


def _table_html(block: TableBlock) -> str:
    if not block.rows:
        return ""
    parts = ["<table>"]
    for index, row in enumerate(block.rows):
        tag = "th" if index == 0 else "td"
        cells = "".join(f"<{tag}>{html_escape.escape(cell)}</{tag}>" for cell in row)
        parts.append(f"<tr>{cells}</tr>")
    parts.append("</table>")
    return "".join(parts)
