"""Reading the contents of an Office file.

A Word document, a spreadsheet and a presentation are all zip archives of
XML. The standard library can open them, so the platform can print a
student's .docx without adding a package and without a converter the size
of a word processor.

What comes out is a list of blocks: text, an image, a table, or a page
break. The renderer turns those into a PDF.

The limits are honest ones. The text and the pictures survive. The
layout does not: fonts are substituted, tables are laid out by the
renderer, and headers, footers and columns are dropped. A student gets
their content printed, not their exact page breaks.

Everything here is pure: bytes in, blocks out.
"""

import io
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PRESENTATION_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

#: How much a single archive may expand to. A small upload can be a zip
#: bomb, and printing one would fill the disk.
MAX_EXPANDED_BYTES = 200 * 1024 * 1024
#: How much one archive member may expand to. A member is bounded on its own
#: as well as by the document budget, so one picture cannot take the whole
#: allowance.
MAX_MEMBER_BYTES = 32 * 1024 * 1024
#: How many pictures one document may hold.
MAX_IMAGES = 200
#: How many rows one sheet may hold.
MAX_ROWS = 2000
#: How many columns one sheet may hold.
MAX_COLUMNS = 60
#: How many characters one cell may hold.
MAX_CELL_LENGTH = 500


class _Budget:
    """What one document may still expand to.

    The limit is a property of the document, not of the member: a document
    made of many small members can expand just as far as one made of a
    single large member, so the bytes are counted across the whole read.
    """

    def __init__(self, total: int = MAX_EXPANDED_BYTES) -> None:
        self.remaining = total
        self.images_left = MAX_IMAGES

    def take(self, size: int) -> None:
        """Charge the budget, and refuse the document when it is spent."""
        self.remaining -= size
        if self.remaining < 0:
            raise OfficeReadError("The archive is too large once expanded")

    def take_image(self) -> None:
        """Charge one picture, and refuse the document when there are too many."""
        self.images_left -= 1
        if self.images_left < 0:
            raise OfficeReadError("The document has too many pictures")


class OfficeReadError(ValueError):
    """The archive is not something we can read."""


@dataclass(frozen=True)
class TextBlock:
    """A run of text. `heading` is 0 for body text and 1 to 6 for a heading."""

    text: str
    heading: int = 0
    bold: bool = False


@dataclass(frozen=True)
class ImageBlock:
    """A picture, with the bytes and a name to refer to it by."""

    data: bytes
    name: str


@dataclass(frozen=True)
class TableBlock:
    """A grid of cells. The first row is the header."""

    rows: list[list[str]] = field(default_factory=list)


@dataclass(frozen=True)
class PageBreak:
    """The next content starts on a new page."""


Block = TextBlock | ImageBlock | TableBlock | PageBreak


def extract_docx(data: bytes) -> list[Block]:
    """Read a Word document: its paragraphs, its headings and its pictures."""
    budget = _Budget()
    with _open(data) as archive:
        document = _read_xml(archive, "word/document.xml", budget)
        relations = _read_relations(archive, "word/_rels/document.xml.rels", "word/", budget)

        blocks: list[Block] = []
        for paragraph in document.iter(f"{{{WORD_NS}}}p"):
            blocks.extend(_docx_paragraph(paragraph, relations, archive, budget))
    return blocks


def _docx_paragraph(
    paragraph: ElementTree.Element,
    relations: dict[str, str],
    archive: zipfile.ZipFile,
    budget: _Budget,
) -> list[Block]:
    style = paragraph.find(f"{{{WORD_NS}}}pPr/{{{WORD_NS}}}pStyle")
    heading = 0
    if style is not None:
        value = style.get(f"{{{WORD_NS}}}val") or ""
        if value.lower().startswith("heading"):
            digits = value[len("heading") :]
            heading = int(digits) if digits.isdigit() else 1
    bold = False
    parts: list[str] = []
    for run in paragraph.findall(f"{{{WORD_NS}}}r"):
        properties = run.find(f"{{{WORD_NS}}}rPr")
        if properties is not None and properties.find(f"{{{WORD_NS}}}b") is not None:
            bold = True
        for node in run.findall(f"{{{WORD_NS}}}t"):
            parts.append(node.text or "")
    blocks: list[Block] = []
    text = "".join(parts).strip()
    if text:
        blocks.append(TextBlock(text=text, heading=heading, bold=bold))
    for blip in paragraph.iter(f"{{{DRAWING_NS}}}blip"):
        image = _image_for(blip, relations, archive, budget)
        if image is not None:
            blocks.append(image)
    return blocks


def extract_xlsx(data: bytes) -> list[Block]:
    """Read a spreadsheet: one table per sheet, in the order of the tabs."""
    budget = _Budget()
    with _open(data) as archive:
        workbook = _read_xml(archive, "xl/workbook.xml", budget)
        relations = _read_relations(archive, "xl/_rels/workbook.xml.rels", "xl/", budget)
        shared = _shared_strings(archive, budget)

    blocks: list[Block] = []
    sheets = workbook.find(f"{{{SHEET_NS}}}sheets")
    if sheets is None:
        return blocks
    for sheet in sheets.findall(f"{{{SHEET_NS}}}sheet"):
        target = relations.get(sheet.get(f"{{{REL_NS}}}id") or "")
        if target is None:
            continue
        name = sheet.get("name") or "Sheet"
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            sheet_xml = _read_xml(archive, target, budget)
        rows = _sheet_rows(sheet_xml, shared)
        if not rows:
            continue
        blocks.append(TextBlock(text=name, heading=2))
        blocks.append(TableBlock(rows=rows))
    return blocks


def extract_pptx(data: bytes) -> list[Block]:
    """Read a presentation: one page per slide."""
    budget = _Budget()
    with _open(data) as archive:
        presentation = _read_xml(archive, "ppt/presentation.xml", budget)
        relations = _read_relations(archive, "ppt/_rels/presentation.xml.rels", "ppt/", budget)
        slide_ids = [
            node.get(f"{{{REL_NS}}}id") or ""
            for node in presentation.iter(f"{{{PRESENTATION_NS}}}sldId")
        ]
        slides = [relations[slide_id] for slide_id in slide_ids if slide_id in relations]

    blocks: list[Block] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for index, slide in enumerate(slides):
            slide_xml = _read_xml(archive, slide, budget)
            slide_relations = _read_relations(archive, _rels_path(slide), _folder(slide), budget)
            if index > 0:
                blocks.append(PageBreak())
            blocks.extend(_pptx_slide(slide_xml, slide_relations, archive, budget))
    return blocks


def _pptx_slide(
    slide: ElementTree.Element,
    relations: dict[str, str],
    archive: zipfile.ZipFile,
    budget: _Budget,
) -> list[Block]:
    blocks: list[Block] = []
    for shape in slide.iter(f"{{{PRESENTATION_NS}}}sp"):
        parts: list[str] = []
        for node in shape.iter(f"{{{DRAWING_NS}}}t"):
            parts.append(node.text or "")
        text = " ".join(part for part in parts if part).strip()
        if text:
            blocks.append(TextBlock(text=text))
    for blip in slide.iter(f"{{{DRAWING_NS}}}blip"):
        image = _image_for(blip, relations, archive, budget)
        if image is not None:
            blocks.append(image)
    return blocks


def _shared_strings(archive: zipfile.ZipFile, budget: _Budget) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = _read_xml(archive, "xl/sharedStrings.xml", budget)
    strings: list[str] = []
    for item in root.findall(f"{{{SHEET_NS}}}si"):
        parts = [node.text or "" for node in item.iter(f"{{{SHEET_NS}}}t")]
        text = "".join(parts)
        # The shared string table is held in memory all at once, so it is
        # charged against the document budget like any other expansion.
        budget.take(len(text.encode("utf-8")))
        strings.append(text)
    return strings


def _sheet_rows(sheet: ElementTree.Element, shared: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    data = sheet.find(f"{{{SHEET_NS}}}sheetData")
    if data is None:
        return rows
    for row in data.findall(f"{{{SHEET_NS}}}row")[:MAX_ROWS]:
        cells: list[str] = []
        for cell in row.findall(f"{{{SHEET_NS}}}c")[:MAX_COLUMNS]:
            cells.append(_cell_text(cell, shared))
        if any(cell.strip() for cell in cells):
            rows.append(cells)
    return rows


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "s":
        value = cell.find(f"{{{SHEET_NS}}}v")
        if value is None or not value.text:
            return ""
        try:
            return shared[int(value.text)][:MAX_CELL_LENGTH]
        except (ValueError, IndexError):
            return ""
    if kind == "inlineStr":
        node = cell.find(f"{{{SHEET_NS}}}is")
        if node is None:
            return ""
        text = "".join(part.text or "" for part in node.iter(f"{{{SHEET_NS}}}t"))
        return text[:MAX_CELL_LENGTH]
    value = cell.find(f"{{{SHEET_NS}}}v")
    if value is None or not value.text:
        return ""
    return value.text[:MAX_CELL_LENGTH]


def _image_for(
    blip: ElementTree.Element,
    relations: dict[str, str],
    archive: zipfile.ZipFile,
    budget: _Budget,
) -> ImageBlock | None:
    relation_id = blip.get(f"{{{REL_NS}}}embed")
    if relation_id is None:
        return None
    target = relations.get(relation_id)
    if target is None or target not in archive.namelist():
        return None
    # Every picture that is read is a copy that is held in memory, so every
    # one of them is counted and charged, whether or not the same member has
    # been read before.
    budget.take_image()
    try:
        with archive.open(target) as handle:
            data = handle.read(min(MAX_MEMBER_BYTES, max(budget.remaining, 0)) + 1)
    except (KeyError, RuntimeError, zipfile.BadZipFile):
        return None
    if len(data) > MAX_MEMBER_BYTES:
        raise OfficeReadError("The archive is too large once expanded")
    budget.take(len(data))
    return ImageBlock(data=data, name=target.rpartition("/")[2])


def _open(data: bytes) -> zipfile.ZipFile:
    """Open an archive, turning anything that is not one into our own error."""
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, OSError) as exc:
        raise OfficeReadError("The archive could not be opened") from exc


def _read_xml(archive: zipfile.ZipFile, name: str, budget: _Budget) -> ElementTree.Element:
    try:
        with archive.open(name) as handle:
            data = handle.read(MAX_EXPANDED_BYTES + 1)
    except KeyError as exc:
        raise OfficeReadError(f"{name} is missing from the archive") from exc
    except (zipfile.BadZipFile, RuntimeError) as exc:
        raise OfficeReadError("The archive could not be opened") from exc
    if len(data) > MAX_EXPANDED_BYTES:
        raise OfficeReadError("The archive is too large once expanded")
    budget.take(len(data))
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise OfficeReadError("The document could not be read") from exc


def _read_relations(
    archive: zipfile.ZipFile, path: str, folder: str, budget: _Budget
) -> dict[str, str]:
    """Map a relationship id to the name of the file it points at."""
    if path not in archive.namelist():
        return {}
    try:
        root = _read_xml(archive, path, budget)
    except OfficeReadError:
        # A file with no relationships has nothing in it, which is not an
        # error: the document simply has no pictures.
        return {}
    relations: dict[str, str] = {}
    for node in root:
        relation_id = node.get("Id")
        target = node.get("Target")
        if relation_id is None or target is None:
            continue
        relations[relation_id] = _resolve(folder, target)
    return relations


def _resolve(folder: str, target: str) -> str:
    """Resolve a relationship target against the folder it sits in.

    A target is either absolute, or relative to the folder of the file
    that refers to it, and it may step up with "..". A slide in
    "ppt/slides" refers to a picture in "ppt/media", so the resolution
    has to walk the path rather than just join two strings.
    """
    if target.startswith("/"):
        return target.lstrip("/")
    parts = [part for part in folder.split("/") if part]
    for segment in target.split("/"):
        if segment == "..":
            if parts:
                parts.pop()
        elif segment and segment != ".":
            parts.append(segment)
    return "/".join(parts)


def _folder(path: str) -> str:
    """The folder a file lives in, with a trailing slash."""
    head, _, _tail = path.rpartition("/")
    return f"{head}/" if head else ""


def _rels_path(path: str) -> str:
    """The relationships file that belongs to a file."""
    folder = _folder(path)
    name = path.rpartition("/")[2]
    return f"{folder}_rels/{name}.rels"
