"""Bounded text-only extraction executed in a child process."""

import io
import json
import logging
import re
import sys
from pathlib import PurePosixPath
from zipfile import ZipFile

from defusedxml.ElementTree import fromstring
from pypdf import PdfReader

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_TEXT_CHARS = 50_000
XML = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
PACKAGE_XML = "{http://schemas.openxmlformats.org/package/2006/content-types}"
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class InvalidCV(Exception):
    """The document is unsupported, exceeds a parsing limit or has no text."""


def _pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise InvalidCV
    pdf = PdfReader(io.BytesIO(data), strict=True)
    if pdf.is_encrypted or not 1 <= len(pdf.pages) <= 30:
        raise InvalidCV
    root = pdf.root_object
    if any(key in root for key in ("/OpenAction", "/AA", "/AcroForm")):
        raise InvalidCV
    names = root.get("/Names")
    if names and any(
        key in names.get_object() for key in ("/JavaScript", "/EmbeddedFiles")
    ):
        raise InvalidCV
    # Only extract page text. Never resolve annotations, links or launch actions.
    parts = []
    size = 0
    for page in pdf.pages:
        part = page.extract_text()
        size += len(part) + 1
        if size > MAX_TEXT_CHARS:
            raise InvalidCV
        parts.append(part)
    return "\n".join(parts)


def _docx_text(data: bytes) -> str:
    if not data.startswith(b"PK\x03\x04"):
        raise InvalidCV
    with ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = {item.filename for item in entries}
        if (
            len(entries) > 256
            or len(names) != len(entries)
            or sum(item.file_size for item in entries) > 25 * 1024 * 1024
        ):
            raise InvalidCV
        for item in entries:
            path = PurePosixPath(item.filename)
            name = item.filename.lower()
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in name
                or item.flag_bits & 1
                or any(
                    part in name for part in ("vbaproject", "/embeddings/", "/activex/")
                )
            ):
                raise InvalidCV
        types = fromstring(archive.read("[Content_Types].xml"))
        main_type = (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document.main+xml"
        )
        if not any(
            node.get("PartName") == "/word/document.xml"
            and node.get("ContentType") == main_type
            for node in types.findall(f"{PACKAGE_XML}Override")
        ):
            raise InvalidCV
        root = fromstring(archive.read("word/document.xml"))
    body = root.find(f"{XML}body")
    if body is None:
        raise InvalidCV
    paragraphs = []
    size = 0
    for paragraph in body.iter(f"{XML}p"):
        text = "".join(
            node.text or ""
            if node.tag == f"{XML}t"
            else "\t"
            if node.tag == f"{XML}tab"
            else "\n"
            if node.tag in {f"{XML}br", f"{XML}cr"}
            else ""
            for node in paragraph.iter()
        )
        size += len(text) + 1
        if size > MAX_TEXT_CHARS:
            raise InvalidCV
        paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_text(data: bytes, media_type: str) -> str:
    if media_type not in (PDF, DOCX):
        raise InvalidCV
    try:
        text = _pdf_text(data) if media_type == PDF else _docx_text(data)
    except Exception:
        # Parser errors can include raw PDF/XML data.
        raise InvalidCV from None
    text = CONTROL_CHARS.sub("", text).strip()
    if not text:
        raise InvalidCV
    return text


def main() -> None:
    logging.disable(logging.CRITICAL)
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
    try:
        payload = sys.stdin.buffer.read(MAX_FILE_BYTES + 1)
        if len(payload) > MAX_FILE_BYTES:
            raise InvalidCV
        text = extract_text(payload, sys.argv[1])
        sys.stdout.write(json.dumps(text))
    except InvalidCV:
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
