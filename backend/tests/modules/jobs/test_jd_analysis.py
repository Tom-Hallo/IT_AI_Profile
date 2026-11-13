"""Unit and Security Tests cho Job Description Analysis (PBI-025)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import create_app
from app.modules.jobs.extractor import JDSkillExtractor
from app.modules.jobs.schemas import (
    ExtractedSkill,
    JDAnalysisRequest,
    JDPreviewUpdateRequest,
    SkillRequirementLevel,
)
from app.modules.jobs.service import JDAnalysisService
from app.modules.jobs.url_fetcher import (
    SSRFBlockedError,
    URLFetchError,
    fetch_jd_from_url,
    validate_url_security,
)
from app.modules.users.models import User

SAMPLE_JD_TEXT = """
Backend Engineer (Python / FastAPI)
Northstar Labs - Remote

Mô tả công việc:
Chúng tôi tìm kiếm lập trình viên Backend xây dựng hệ sinh thái microservices.

Yêu cầu bắt buộc:
- Có ít nhất 3 năm kinh nghiệm với Python và framework FastAPI.
- Thành thạo thiết kế RESTful API và làm việc với cơ sở dữ liệu PostgreSQL.
- Kinh nghiệm thực tế với Docker và Linux.

Điểm cộng (Ưu tiên):
- Hiểu biết về Redis caching và message queue.
- Có kinh nghiệm triển khai Kubernetes trên AWS.
- Biết lập trình frontend cơ bản với React hoặc TypeScript.
"""


def test_extractor_detects_job_title():
    extractor = JDSkillExtractor()
    title = extractor.extract_title(SAMPLE_JD_TEXT)
    assert title is not None
    assert "Backend Engineer" in title


def test_extractor_separates_required_and_preferred_skills():
    extractor = JDSkillExtractor()
    required, preferred = extractor.extract_skills(SAMPLE_JD_TEXT)

    req_keys = {s.skill_key for s in required}
    pref_keys = {s.skill_key for s in preferred}

    assert "python" in req_keys
    assert "fastapi" in req_keys
    assert "postgresql" in req_keys
    assert "docker" in req_keys
    assert "linux" in req_keys

    assert "redis" in pref_keys
    assert "kubernetes" in pref_keys
    assert "aws" in pref_keys
    assert "react" in pref_keys or "typescript" in pref_keys

    fastapi_skill = next(s for s in required if s.skill_key == "fastapi")
    assert fastapi_skill.level == SkillRequirementLevel.REQUIRED
    assert fastapi_skill.confidence >= 0.9
    assert "FastAPI" in (fastapi_skill.context_snippet or "")

    redis_skill = next(s for s in preferred if s.skill_key == "redis")
    assert redis_skill.level == SkillRequirementLevel.PREFERRED
    assert redis_skill.confidence >= 0.9


@pytest.mark.parametrize(
    "forbidden_url",
    [
        "http://localhost:8000/internal",
        "http://127.0.0.1:8080/metrics",
        "http://127.0.0.10/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/secrets",
        "http://172.16.1.1/internal",
        "http://192.168.1.100/router",
        "ftp://example.com/job.txt",
        "file:///etc/passwd",
    ],
)
def test_ssrf_blocked_on_internal_urls(forbidden_url: str):
    with pytest.raises(SSRFBlockedError):
        validate_url_security(forbidden_url)


def test_fetch_jd_fallback_on_network_error():
    with patch("httpx.Client.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        with pytest.raises(URLFetchError):
            fetch_jd_from_url("https://careers.google.com/jobs/123")


def test_service_analyze_text_success():
    service = JDAnalysisService()
    req = JDAnalysisRequest(text=SAMPLE_JD_TEXT)
    resp = service.analyze(req)

    assert resp.source_type.value == "raw_text"
    assert resp.total_skills_count > 0
    assert len(resp.required_skills) > 0
    assert len(resp.preferred_skills) > 0
    assert resp.fallback is None


def test_service_empty_text_and_no_url_raises_value_error():
    service = JDAnalysisService()
    req = JDAnalysisRequest(text="   ")
    with pytest.raises(ValueError, match="Vui lòng cung cấp"):
        service.analyze(req)


def test_service_url_error_provides_fallback_suggestion():
    service = JDAnalysisService()
    req = JDAnalysisRequest(url="http://127.0.0.1/private-job")

    resp = service.analyze(req)
    assert resp.total_skills_count == 0
    assert resp.fallback is not None
    assert resp.fallback.fallback_mode == "paste_text"
    assert "chặn" in resp.fallback.message or "bảo vệ" in resp.fallback.message


def test_service_preview_update():
    service = JDAnalysisService()
    req = JDPreviewUpdateRequest(
        required_skills=[
            ExtractedSkill(
                skill_key="python",
                raw_name="Python 3.12",
                level=SkillRequirementLevel.REQUIRED,
                confidence=1.0,
            )
        ],
        preferred_skills=[
            ExtractedSkill(
                skill_key="docker",
                raw_name="Docker container",
                level=SkillRequirementLevel.PREFERRED,
                confidence=0.9,
            )
        ],
    )
    resp = service.update_preview(req)
    assert resp.updated is True
    assert resp.total_skills_count == 2
    assert resp.required_skills[0].skill_key == "python"
    assert resp.preferred_skills[0].skill_key == "docker"


@pytest.fixture
def api_client():
    app = create_app()
    fake_user = User(id=1, email="candidate@test.com", full_name="Candidate")
    app.dependency_overrides[get_current_user] = lambda: fake_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_api_analyze_job_text(api_client: TestClient):
    payload = {"text": SAMPLE_JD_TEXT}
    resp = api_client.post("/api/v1/jobs/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "raw_text"
    assert data["total_skills_count"] > 0
    assert any(s["skill_key"] == "fastapi" for s in data["required_skills"])


def test_api_analyze_ssrf_url_returns_fallback_gracefully(api_client: TestClient):
    payload = {"url": "http://127.0.0.1:9000/jd"}
    resp = api_client.post("/api/v1/jobs/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["fallback"] is not None
    assert data["fallback"]["fallback_mode"] == "paste_text"


def test_api_analyze_empty_payload_returns_422(api_client: TestClient):
    resp = api_client.post("/api/v1/jobs/analyze", json={})
    assert resp.status_code == 422


def test_api_update_preview(api_client: TestClient):
    payload = {
        "required_skills": [
            {
                "skill_key": "golang",
                "raw_name": "Go",
                "level": "required",
                "confidence": 1.0,
            }
        ],
        "preferred_skills": [],
    }
    resp = api_client.post("/api/v1/jobs/preview/update", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_skills_count"] == 1
    assert data["required_skills"][0]["skill_key"] == "golang"
