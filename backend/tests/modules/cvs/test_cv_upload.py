"""PBI-028 tests cover binary parsing, fail-closed scanning and the owner lifecycle."""

from io import BytesIO
from time import time
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
from pypdf import PdfWriter
from pypdf.actions import JavaScript
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import func, select

from app.core.config import settings
from app.modules.cvs import router as cv_routes
from app.modules.cvs import scanner
from app.modules.cvs.models import CV
from app.modules.cvs.parser import DOCX, PDF, InvalidCV, extract_text
from tests.modules.role_scoring import conftest as role_fixtures
from tests.modules.role_scoring import test_scoped_postgres as pg_fixtures

db = pg_fixtures.db
world = role_fixtures.world
make_client = role_fixtures.make_client
ORIGIN = {"Origin": settings.frontend_url}
CV_ROOT = "/api/v1/cvs"
PREVIEW_PATH = f"{CV_ROOT}/preview"
CV_TEXT = "Nguyễn Văn An — Python"


def make_docx(*, entity=False, macro=False) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        prefix = '<!DOCTYPE w:document [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
        document = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body><w:p><w:r>'
            f"<w:t>{'&e;' if entity else CV_TEXT}</w:t><w:br/><w:t>PostgreSQL</w:t>"
            "</w:r></w:p></w:body></w:document>"
        )
        archive.writestr("word/document.xml", (prefix if entity else "") + document)
        if macro:
            archive.writestr("word/vbaProject.bin", "test")
    return stream.getvalue()


def make_pdf(*, active=False, encrypted=False) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    name = NameObject
    page[name("/Resources")] = DictionaryObject(
        {
            name("/Font"): DictionaryObject(
                {
                    name("/F1"): DictionaryObject(
                        {
                            name("/Type"): name("/Font"),
                            name("/Subtype"): name("/Type1"),
                            name("/BaseFont"): name("/Helvetica"),
                        }
                    ),
                }
            ),
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 30 150 Td (Python developer) Tj ET")
    page.replace_contents(stream)
    if active:
        writer.add_open_action(JavaScript("void(0)"))
    if encrypted:
        writer.encrypt("test-only")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_extracts_actual_text_from_both_formats():
    assert extract_text(make_pdf(), PDF) == "Python developer"
    assert extract_text(make_docx(), DOCX) == f"{CV_TEXT}\nPostgreSQL"


@pytest.mark.parametrize(
    "create,media",
    [
        (lambda: make_pdf(active=True), PDF),
        (lambda: make_pdf(encrypted=True), PDF),
        (lambda: make_docx(entity=True), DOCX),
        (lambda: make_docx(macro=True), DOCX),
        (lambda: make_docx(), PDF),
        (lambda: b"%PDF-damaged content", PDF),
    ],
)
def test_invalid_or_active_documents_are_rejected(create, media):
    with pytest.raises(InvalidCV):
        extract_text(create(), media)


@pytest.mark.parametrize(
    "verdict,error",
    [
        (b"stream: OK\0", None),
        (b"stream: Eicar-Test-Signature FOUND\0", scanner.UnsafeCV),
        (b"INSTREAM size limit exceeded. ERROR\0", scanner.ScannerUnavailable),
        (b"stream: OK", scanner.ScannerUnavailable),
    ],
)
def test_clamd_requires_a_complete_verdict(monkeypatch, verdict, error):
    context = Mock()
    socket = context.__enter__ = Mock()
    connection = socket.return_value
    context.__exit__ = Mock(return_value=False)
    connection.recv.side_effect = [verdict, b""]
    monkeypatch.setattr(scanner.socket, "create_connection", lambda *_a, **_kw: context)
    if error is None:
        scanner.scan_cv(b"data")
    else:
        with pytest.raises(error):
            scanner.scan_cv(b"data")
    assert [call.args[0] for call in connection.sendall.call_args_list] == [
        b"zINSTREAM\0",
        b"\0\0\0\x04data",
        b"\0" * 4,
    ]


def test_full_cv_lifecycle_is_owner_only_and_preview_is_ephemeral(
    db, world, make_client, monkeypatch
):
    owner = world.user("cv-owner@example.test")
    stranger = world.user("cv-stranger@example.test")
    client = make_client(owner)
    other = make_client(stranger)
    upload_headers = {**ORIGIN, "Content-Type": DOCX}
    docs = make_docx()
    malware_scan = Mock()
    monkeypatch.setattr(cv_routes, "scan_cv", malware_scan)

    assert (
        make_client()
        .post(PREVIEW_PATH, content=docs, headers=upload_headers)
        .status_code
        == 401
    )
    assert (
        client.post(
            PREVIEW_PATH, content=docs, headers={"Content-Type": DOCX}
        ).status_code
        == 403
    )
    assert (
        client.post(
            PREVIEW_PATH, content=docs, headers={**ORIGIN, "Content-Type": PDF}
        ).status_code
        == 415
    )
    assert (
        client.post(
            PREVIEW_PATH,
            content=docs,
            headers={**upload_headers, "Content-Length": "5242881"},
        ).status_code
        == 413
    )
    malware_scan.assert_not_called()

    preview = client.post(PREVIEW_PATH, content=docs, headers=upload_headers)
    assert preview.status_code == 200, preview.text
    assert preview.headers["Cache-Control"] == "no-store"
    assert preview.json()["text"] == f"{CV_TEXT}\nPostgreSQL"
    assert db.scalar(select(func.count(CV.id))) == 0

    edited = {"receipt": preview.json()["receipt"], "text": CV_TEXT + " · Rust"}
    assert other.post(CV_ROOT, json=edited, headers=ORIGIN).status_code == 422
    invalid = client.post(
        CV_ROOT, json={**edited, "user_id": stranger.id}, headers=ORIGIN
    )
    assert invalid.status_code == 422
    assert CV_TEXT not in invalid.text and edited["receipt"] not in invalid.text
    old_receipt = (
        cv_routes.receipt_codec()
        .encrypt_at_time(
            f"{owner.id}:expired".encode(), int(time()) - cv_routes.PREVIEW_TTL - 2
        )
        .decode()
    )
    assert (
        client.post(
            CV_ROOT, json={**edited, "receipt": old_receipt}, headers=ORIGIN
        ).status_code
        == 422
    )

    saved = client.post(CV_ROOT, json=edited, headers=ORIGIN)
    assert saved.status_code == 201, saved.text
    assert saved.json()["text"] == edited["text"]
    assert client.post(CV_ROOT, json=edited, headers=ORIGIN).json() == saved.json()
    cv_id = saved.json()["id"]
    path = f"{CV_ROOT}/{cv_id}"
    assert client.get(CV_ROOT).json() == [
        {"id": cv_id, "uploaded_at": saved.json()["uploaded_at"]}
    ]
    assert other.get(CV_ROOT).json() == []
    assert other.get(path).status_code == 404
    assert other.delete(path, headers=ORIGIN).status_code == 404

    update = {"text": "Updated CV", "version": 1}
    assert other.put(path, json=update, headers=ORIGIN).status_code == 404
    assert client.put(path, json=update, headers=ORIGIN).json()["version"] == 2
    assert client.put(path, json=update, headers=ORIGIN).status_code == 409
    assert client.get(path).json()["text"] == "Updated CV"
    mentor = client.get("/api/v1/mentor/sources")
    assert mentor.status_code == 200
    assert cv_id in {item["id"] for item in mentor.json()["cvs"]}
    assert client.delete(path, headers=ORIGIN).status_code == 204
    assert client.get(path).status_code == 404
    assert db.scalar(select(func.count(CV.id))) == 0


def test_upload_fails_closed_with_no_scanner_or_threat(
    db, world, make_client, monkeypatch
):
    owner = world.user("cv-scan-owner@example.test")
    client = make_client(owner)
    parse = Mock()
    monkeypatch.setattr(cv_routes.subprocess, "run", parse)
    for failure, status in ((scanner.UnsafeCV, 422), (scanner.ScannerUnavailable, 503)):
        monkeypatch.setattr(cv_routes, "scan_cv", Mock(side_effect=failure))
        response = client.post(
            PREVIEW_PATH, content=make_docx(), headers={**ORIGIN, "Content-Type": DOCX}
        )
        assert response.status_code == status
        assert CV_TEXT not in response.text
    parse.assert_not_called()
