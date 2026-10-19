from pathlib import Path

import pymupdf


def make_pdf(path: Path, *, pages: int = 1) -> Path:
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"Page {index + 1}")
    document.save(str(path))
    document.close()
    return path


def make_encrypted_pdf(path: Path) -> Path:
    document = pymupdf.open()
    document.new_page()
    document.save(
        str(path),
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="secret",
    )
    document.close()
    return path


def make_corrupt_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.7\nthis is not really a pdf body")
    return path


def make_empty_pdf(path: Path) -> Path:
    path.write_bytes(b"")
    return path


def make_text_file(path: Path) -> Path:
    path.write_text("not a pdf at all")
    return path
