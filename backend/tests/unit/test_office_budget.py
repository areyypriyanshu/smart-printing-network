"""How far one Office document may expand.

An Office file is a zip archive, so a small upload can hold a very large
amount of data once it is expanded. The reader is careful about the
individual parts, but a document is made of many parts, and the limit has
to be a property of the document rather than of the part: a document with
four hundred references to one picture holds four hundred pictures in
memory, even though the archive holds only one.

These are the tests for that budget.
"""

import io
import zipfile

import pytest
from app.domain.office import (
    MAX_EXPANDED_BYTES,
    MAX_IMAGES,
    MAX_MEMBER_BYTES,
    OfficeReadError,
    extract_docx,
)
from tests.office_fixtures import A, R, W, _relationships


def _docx_with_many_pictures(count: int, *, picture_bytes: int = 1024) -> bytes:
    """A Word document that refers to the same picture many times.

    The archive holds one picture; the document refers to it once per
    paragraph. Every reference is a copy that is held in memory, which is
    what the budget has to bound.
    """
    body = "".join(
        '<w:p><w:r><w:drawing><a:blip r:embed="rIdImg"/></w:drawing></w:r></w:p>'
        for _ in range(count)
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:a="{A}">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types())
        archive.writestr("word/document.xml", document)
        archive.writestr(
            "word/_rels/document.xml.rels", _relationships({"rIdImg": "media/image1.png"})
        )
        archive.writestr("word/media/image1.png", b"\x00" * picture_bytes)
    return buffer.getvalue()


def _content_types() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )


def test_a_document_with_too_many_pictures_is_refused() -> None:
    """The picture count is a limit, not a suggestion.

    A document with more pictures than the limit is refused rather than
    read into memory and then dropped.
    """
    with pytest.raises(OfficeReadError, match="too many pictures"):
        extract_docx(_docx_with_many_pictures(MAX_IMAGES + 1))


def test_the_same_picture_repeated_is_still_bounded() -> None:
    """One picture, referred to many times, is many copies in memory.

    The archive holds the picture once, so a limit on the archive would
    not catch this. The limit is on the number of pictures the document
    holds, and the repeated reference is counted every time.
    """
    with pytest.raises(OfficeReadError, match="too many pictures"):
        extract_docx(_docx_with_many_pictures(MAX_IMAGES + 1, picture_bytes=64))


def test_a_document_inside_the_limits_is_read() -> None:
    """The budget does not refuse a document that is within it."""
    blocks = extract_docx(_docx_with_many_pictures(3, picture_bytes=64))

    assert len(blocks) == 3


def test_one_member_cannot_be_larger_than_the_member_limit() -> None:
    """A single picture is bounded on its own.

    A member that is larger than the member limit is refused even when
    the document budget would have allowed it.
    """
    assert MAX_MEMBER_BYTES < MAX_EXPANDED_BYTES
    with pytest.raises(OfficeReadError, match="too large once expanded"):
        extract_docx(_docx_with_many_pictures(1, picture_bytes=MAX_MEMBER_BYTES + 1))
