"""Exercise the full CV Studio contract with isolated PostgreSQL."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import BytesIO
from uuid import UUID

import httpx
import pytest
from docx import Document
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.ai_mentor import usage_service
from app.modules.ai_mentor.usage_models import AIUsageLog
from app.modules.auth.service import disconnect_github
from app.modules.cv_studio.models import CVStudioVersion
from app.modules.cv_studio.schemas import GenerateCV, SaveVersion
from app.modules.cv_studio.service import append_version
from app.modules.cvs.models import CV
from tests.modules.jobs.test_job_matching import seed
from tests.modules.role_scoring import conftest as fixtures
from tests.modules.role_scoring import test_scoped_postgres as pg_fixtures

db = pg_fixtures.db
world = fixtures.world
make_client = fixtures.make_client
PATH = "/api/v1/cv-studio"
HEADERS = {"Origin": settings.frontend_url}
TITLE = "Hồ sơ kỹ sư phần mềm"
EXPERIENCE = "Phát triển dịch vụ Python tại Đà Nẵng & kiểm thử."
JD_MARKER = "This JD text must stay on the server."
CV_MARKER = "Private source information must stay on the server."


@pytest.fixture
def provider(db, monkeypatch):
    @contextmanager
    def isolated_usage():
        with Session(db.get_bind()) as session:
            yield session
            session.commit()

    monkeypatch.setattr(usage_service, "session_scope", isolated_usage)
    monkeypatch.setattr(settings, "ai_provider", "ollama")
    monkeypatch.setattr(settings, "ai_model", "test-model")
    calls = []
    state = {"reply": '{"ids":[1,3,1]}', "on_send": None}

    def respond(request):
        assert request.url.path == "/api/chat"
        wire = json.loads(request.content)
        content = wire["messages"][1]["content"]
        for secret in (EXPERIENCE, CV_MARKER, JD_MARKER):
            assert secret not in content
        calls.append(json.loads(json.loads(content.split("\n", 1)[1])))
        if state["on_send"]:
            state["on_send"]()
        return httpx.Response(
            200, json={"message": {"content": state["reply"]}, "eval_count": 10}
        )

    class MockTransportClient(httpx.AsyncClient):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(
        "app.ai.providers.ollama_provider.httpx.AsyncClient", MockTransportClient
    )
    return calls, state


@pytest.fixture
def setup(db, world, make_client):
    owner = world.user("studio-owner@example.test", private_enabled=True)
    other = world.user("studio-foreign@example.test")
    public = world.repo(owner)
    private = world.repo(owner, private=True)
    world.consent(owner, private)
    report = seed(db, world, owner, public, scope="public", score=85)
    seed(db, world, owner, private, scope="private", score=100, suffix="b")
    cv = CV(
        user_id=owner.id,
        content={
            "source": "user_upload",
            "text": f"{EXPERIENCE}\n{CV_MARKER}",
            "version": 1,
        },
    )
    db.add(cv)
    db.commit()
    payload = {
        "title": TITLE,
        "jd": f"Requirements: Python, Kubernetes. {JD_MARKER}",
        "cv_id": cv.id,
        "use_github": True,
        "template": "technical",
        "allow_ai": True,
    }
    return owner, public, report, payload, make_client(owner), make_client(other)


def generate(client, body):
    result = client.post(f"{PATH}/generate", json=body, headers=HEADERS)
    assert result.status_code == 201, result.text
    return result.json()


def read_export(client, path, version, format_):
    result = client.get(f"{path}/{version}/export?format={format_}")
    assert result.status_code == 200, result.text[:300]
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["content-disposition"] == (
        f'attachment; filename="cv-v{version}.{format_}"'
    )
    if format_ == "pdf":
        assert result.headers["content-type"] == "application/pdf"
        return "\n".join(
            page.extract_text() for page in PdfReader(BytesIO(result.content)).pages
        )
    assert "wordprocessingml.document" in result.headers["content-type"]
    return "\n".join(item.text for item in Document(BytesIO(result.content)).paragraphs)


def test_generate_version_and_export_exact_snapshot(db, setup, provider):
    _, repo, report, payload, client, other = setup
    first = generate(client, payload)
    calls, _ = provider
    assert calls[0]["job"] == [
        {"skill": "python", "level": "required"},
        {"skill": "kubernetes", "level": "required"},
    ]
    assert [item["source"] for item in calls[0]["candidates"]] == ["cv", "cv", "github"]
    assert first["title"] == TITLE
    assert first["number"] == 1
    cv_line, github, missing = first["lines"]
    assert cv_line["text"] == EXPERIENCE
    assert cv_line["source"]["cv_id"] == payload["cv_id"]
    assert cv_line["source"]["cv_version"] == 1
    assert cv_line["source"]["line_number"] == 1
    assert github["source"]["repo_id"] == repo.id
    assert github["source"]["commit_sha"] == report.commit_sha
    assert github["source"]["evidence_id"]
    assert missing["source"]["type"] == "missing"
    assert "kubernetes" in missing["text"]
    assert CV_MARKER not in str(first)

    document = f"{PATH}/{first['document_id']}/versions"
    edited = "Đã cập nhật <b>văn bản</b> & ký hiệu."
    version_body = {
        "title": "Hồ sơ mới",
        "text": f"{EXPERIENCE}\r\n{edited}",
        "previous_version": 1,
    }
    response = client.post(document, json=version_body, headers=HEADERS)
    assert response.status_code == 201, response.text
    second = response.json()
    assert second["number"] == 2
    assert [line["source"]["type"] for line in second["lines"]] == [
        "cv",
        "manual",
        "missing",
    ]
    assert client.post(document, json=version_body, headers=HEADERS).status_code == 409
    assert client.get(f"{document}/1").json() == first
    assert client.get(f"{document}/2").json() == second
    assert [row["number"] for row in client.get(document).json()] == [2, 1]
    assert client.get(PATH).json()[0]["title"] == "Hồ sơ mới"
    for format_ in ("pdf", "docx"):
        before = read_export(client, document, 1, format_)
        after = read_export(client, document, 2, format_)
        assert TITLE in before
        assert EXPERIENCE in before and EXPERIENCE in after
        assert "Bằng chứng kỹ thuật" in before and "Bằng chứng kỹ thuật" not in after
        assert edited not in before and edited in after
        assert "kubernetes" not in before and "kubernetes" not in after
        assert other.get(f"{document}/1/export?format={format_}").status_code == 404

    assert other.get(PATH).json() == []
    assert other.get(document).status_code == 404
    assert other.get(f"{document}/1").status_code == 404
    assert other.post(document, json=version_body, headers=HEADERS).status_code == 404
    assert db.scalar(select(AIUsageLog.status)) == "ok"


def test_refuse_unconsented_forged_or_missing_sources(db, setup, make_client, provider):
    _, _, _, payload, client, other = setup
    uri = f"{PATH}/generate"
    assert make_client().post(uri, json=payload, headers=HEADERS).status_code == 401
    assert client.post(uri, json=payload).status_code == 403
    assert other.post(uri, json=payload, headers=HEADERS).status_code == 404
    for invalid in (False, "true", 1, None):
        response = client.post(
            uri, json={**payload, "allow_ai": invalid}, headers=HEADERS
        )
        assert response.status_code == 422
        assert JD_MARKER not in response.text
    response = other.post(uri, json={**payload, "cv_id": None}, headers=HEADERS)
    assert response.status_code == 422
    assert not provider[0]
    provider[1]["reply"] = '{"ids":[1,123456]}'
    response = client.post(uri, json=payload, headers=HEADERS)
    assert response.status_code == 502
    assert db.scalar(select(func.count()).select_from(CVStudioVersion)) == 0
    assert db.scalar(select(AIUsageLog.status)) == "error"
    assert client.get(PATH).json() == []


@pytest.mark.parametrize("change", ["private", "disconnected"])
def test_revalidate_public_sources_after_save(db, setup, provider, change):
    user, repo, _, payload, client, _ = setup
    first = generate(client, payload)
    if change == "private":
        repo.private = True
        db.commit()
    else:
        assert disconnect_github(db, user.id)
    path = f"{PATH}/{first['document_id']}/versions/1"
    current = client.get(path).json()
    assert current["source_unavailable"]
    assert all(line["source"]["type"] != "github" for line in current["lines"])
    assert client.get(f"{path}/export?format=pdf").status_code == 409
    assert db.scalar(select(func.count()).select_from(CVStudioVersion)) == 1


def test_revalidate_sources_after_ai_response(db, setup, provider):
    _, repo, _, payload, client, _ = setup

    def privatize():
        repo.private = True
        db.commit()

    provider[1]["on_send"] = privatize
    response = client.post(f"{PATH}/generate", json=payload, headers=HEADERS)
    assert response.status_code == 409
    assert client.get(PATH).json() == []


def test_request_unicode_and_formats_validate():
    request = SaveVersion(title=" Tiêu đề ", text="line\r\nnext", previous_version=1)
    assert request.title == "Tiêu đề"
    assert request.text == "line\nnext"
    with pytest.raises(ValueError):
        SaveVersion(title="title", text="word\u0000", previous_version=1)
    with pytest.raises(ValueError):
        GenerateCV(title="title", jd="python", allow_ai=True, template="made-up")


def test_parallel_saves_create_one_version(db, setup, provider):
    owner, _, _, payload, client, _ = setup
    first = generate(client, payload)
    owner_id = owner.id
    engine = db.get_bind()
    document = UUID(first["document_id"])
    body = SaveVersion(title=TITLE, text=EXPERIENCE, previous_version=1)

    def save():
        with Session(engine) as session:
            try:
                return append_version(session, owner_id, document, body).number
            except HTTPException as exc:
                return exc.status_code

    db.rollback()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_save = pool.submit(save)
        second_save = pool.submit(save)
        assert sorted([first_save.result(), second_save.result()]) == [2, 409]
    assert db.scalar(select(func.count()).select_from(CVStudioVersion)) == 2


def test_pdf_reports_unsupported_glyph_and_docx_preserves_it(setup, provider):
    _, _, _, payload, client, _ = setup
    first = generate(client, payload)
    document = f"{PATH}/{first['document_id']}/versions"
    text = "開発者"
    response = client.post(
        document,
        json={"title": TITLE, "text": text, "previous_version": 1},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    assert client.get(f"{document}/2/export?format=pdf").status_code == 422
    assert text in read_export(client, document, 2, "docx")
