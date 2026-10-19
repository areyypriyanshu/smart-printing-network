"""Building Office files to test against.

A .docx, an .xlsx and a .pptx are zip archives of XML. The platform
reads them with the standard library, so the tests build them the same
way: by writing the parts into a zip.

These are fixtures, not samples from Word. They are the smallest files
that exercise the parts the reader looks at.
"""

import io
import struct
import zipfile
import zlib

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"

#: The content type of each part, which is how a reader tells a Word
#: document from a spreadsheet without opening either.
OFFICE = "application/vnd.openxmlformats-officedocument"


def _override(part: str, kind: str) -> str:
    return f'<Override PartName="{part}" ContentType="{OFFICE}.{kind}"/>'


CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Default Extension="png" ContentType="image/png"/>'
    + _override("/word/document.xml", "wordprocessingml.document.main+xml")
    + _override("/xl/workbook.xml", "spreadsheetml.sheet.main+xml")
    + _override("/ppt/presentation.xml", "presentationml.presentation.main+xml")
    + "</Types>"
)


def png_bytes(width: int = 8, height: int = 8, colour: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    """A small solid PNG, so the fixtures can carry a picture."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return (
            struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        )

    raw = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _relationships(entries: dict[str, str]) -> str:
    items = "".join(
        f'<Relationship Id="{key}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/image" Target="{value}"/>'
        for key, value in entries.items()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        f'relationships">{items}</Relationships>'
    )


def docx_bytes(
    paragraphs: list[tuple[str, str]] | None = None,
    *,
    with_image: bool = False,
) -> bytes:
    """A Word document. Each paragraph is (style, text), and the style is
    the paragraph style name, so a heading can be written as `Heading1`."""
    if paragraphs is None:
        paragraphs = [("Heading1", "A heading"), ("", "Some body text.")]
    body = ""
    for style, text in paragraphs:
        properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        body += f"<w:p>{properties}<w:r><w:t>{text}</w:t></w:r></w:p>"
    if with_image:
        body += '<w:p><w:r><w:drawing><a:blip r:embed="rIdImg"/></w:drawing></w:r></w:p>'
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}">'
        f"<w:body>{body}</w:body></w:document>"
    )
    relations = _relationships({"rIdImg": "media/image1.png"}) if with_image else ""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("word/document.xml", document)
        if relations:
            archive.writestr("word/_rels/document.xml.rels", relations)
        if with_image:
            archive.writestr("word/media/image1.png", png_bytes())
    return buffer.getvalue()


def xlsx_bytes(rows: list[list[str]] | None = None) -> bytes:
    """A spreadsheet with one sheet."""
    if rows is None:
        rows = [["Name", "Mark"], ["Asha", "90"]]
    shared = []
    shared_index: dict[str, int] = {}
    for row in rows:
        for cell in row:
            if cell not in shared_index:
                shared_index[cell] = len(shared)
                shared.append(cell)
    shared_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{S}" count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{value}</t></si>" for value in shared)
        + "</sst>"
    )
    row_xml = ""
    for row_number, row in enumerate(rows, start=1):
        cells = ""
        for column_number, cell in enumerate(row):
            reference = f"{chr(ord('A') + column_number)}{row_number}"
            cells += f'<c r="{reference}" t="s"><v>{shared_index[cell]}</v></c>'
        row_xml += f'<row r="{row_number}">{cells}</row>'
    sheet = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{S}"><sheetData>{row_xml}</sheetData></worksheet>'
    )
    workbook = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{S}" xmlns:r="{R}">'
        f'<sheets><sheet name="Marks" sheetId="1" r:id="rIdSheet"/></sheets>'
        "</workbook>"
    )
    workbook_relations = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships">'
        '<Relationship Id="rIdSheet" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_relations)
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


def pptx_bytes(slides: list[str] | None = None) -> bytes:
    """A presentation with one text shape per slide."""
    if slides is None:
        slides = ["First slide", "Second slide"]

    def slide_xml(text: str) -> str:
        return (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:p="{P}" xmlns:a="{A}">'
            "<p:cSld><p:spTree><p:sp><p:txBody>"
            f"<a:p><a:r><a:t>{text}</a:t></a:r></a:p>"
            "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
        )

    presentation = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:presentation xmlns:p="{P}" xmlns:r="{R}">'
        "<p:sldIdLst>"
        + "".join(
            f'<p:sldId id="{256 + index}" r:id="rIdSlide{index + 1}"/>'
            for index in range(len(slides))
        )
        + "</p:sldIdLst></p:presentation>"
    )
    relations = "".join(
        f'<Relationship Id="rIdSlide{index + 1}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
        f'Target="slides/slide{index + 1}.xml"/>'
        for index in range(len(slides))
    )
    presentation_relations = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        f'relationships">{relations}</Relationships>'
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("ppt/presentation.xml", presentation)
        archive.writestr("ppt/_rels/presentation.xml.rels", presentation_relations)
        for index, text in enumerate(slides, start=1):
            archive.writestr(f"ppt/slides/slide{index}.xml", slide_xml(text))
    return buffer.getvalue()
