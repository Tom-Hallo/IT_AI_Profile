"""Unit tests cho Resume Pattern Analysis & Anti-Plagiarism (PBI-032)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import create_app
from app.modules.cvs.engine import (
    ResumePatternEngine,
    check_exact_chunk_copy,
    compute_ngram_jaccard_similarity,
)
from app.modules.cvs.schemas import (
    ResumeGenerateRequest,
    TargetRole,
    VerifiedUserFact,
)
from app.modules.users.models import User

SAMPLE_REFERENCE_CV = """
Professional Summary:
Lead Backend Architect with 10 years experience in distributed systems.

Technical Competencies:
- Core: Java, Go, Kubernetes, Kafka, Cassandra, gRPC, Docker, AWS.

Experience:
- Architected enterprise message streaming processing 500k events/sec.
- Mentored junior engineers and maintained 99.99% service availability.
"""


def test_pattern_suggestion_by_role():
    engine = ResumePatternEngine()
    be_pattern = engine.get_pattern_suggestion(TargetRole.BACKEND)
    assert be_pattern.target_role == TargetRole.BACKEND
    assert len(be_pattern.recommended_layout) >= 3
    assert any("Summary" in s.section_name for s in be_pattern.recommended_layout)

    fe_pattern = engine.get_pattern_suggestion(TargetRole.FRONTEND)
    assert fe_pattern.target_role == TargetRole.FRONTEND


def test_extract_layout_from_reference():
    engine = ResumePatternEngine()
    sections = engine.extract_layout_from_reference(SAMPLE_REFERENCE_CV)
    assert len(sections) >= 3


def test_similarity_computation_detects_plagiarism():
    text1 = "Architected enterprise message streaming processing 500k events/sec."
    text2 = "Architected enterprise message streaming processing 500k events/sec."
    assert compute_ngram_jaccard_similarity(text1, text2) == 1.0
    assert check_exact_chunk_copy(text1, text2, min_words=5) is True


def test_generate_resume_original_from_verified_facts():
    engine = ResumePatternEngine()
    req = ResumeGenerateRequest(
        target_role=TargetRole.BACKEND,
        verified_facts=[
            VerifiedUserFact(fact_type="skill", content="Python, FastAPI, PostgreSQL"),
            VerifiedUserFact(
                fact_type="project", content="E-commerce payment gateway microservice"
            ),
            VerifiedUserFact(fact_type="metric", content="Decreased latency by 45%"),
        ],
        reference_template_text=SAMPLE_REFERENCE_CV,
        has_reference_permission=True,
    )
    resp = engine.generate_original_resume(req)
    assert resp.plagiarism_detected is False
    assert resp.similarity_with_reference < 0.20
    assert resp.source_facts_used_count == 3
    assert "chỉ mang tính chất tham khảo" in resp.disclaimer.lower()


def test_generate_resume_blocks_direct_plagiarism():
    engine = ResumePatternEngine()
    req = ResumeGenerateRequest(
        target_role=TargetRole.BACKEND,
        verified_facts=[
            VerifiedUserFact(
                fact_type="project",
                content="Enterprise message streaming processing 500k events/sec",
            )
        ],
        reference_template_text=SAMPLE_REFERENCE_CV,
        has_reference_permission=True,
    )
    with pytest.raises(ValueError, match="(?i)plagiarism"):
        engine.generate_original_resume(req)


def test_generate_resume_rejects_without_permission():
    engine = ResumePatternEngine()
    req = ResumeGenerateRequest(
        target_role=TargetRole.BACKEND,
        verified_facts=[VerifiedUserFact(fact_type="skill", content="Go, Docker")],
        reference_template_text=SAMPLE_REFERENCE_CV,
        has_reference_permission=False,
    )
    with pytest.raises(PermissionError, match="(?i)permission"):
        engine.generate_original_resume(req)


@pytest.fixture
def api_client():
    app = create_app()
    fake_user = User(id=1, email="candidate@test.com", full_name="Candidate")
    app.dependency_overrides[get_current_user] = lambda: fake_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_api_get_patterns(api_client: TestClient):
    resp = api_client.get("/api/v1/resume/patterns/Backend Developer")
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_role"] == "Backend Developer"


def test_api_extract_pattern_without_permission_fails(api_client: TestClient):
    payload = {
        "reference_text": SAMPLE_REFERENCE_CV,
        "has_usage_permission": False,
    }
    resp = api_client.post("/api/v1/resume/patterns/extract", json=payload)
    assert resp.status_code == 403


def test_api_generate_original_resume_success(api_client: TestClient):
    payload = {
        "target_role": "Backend Developer",
        "verified_facts": [
            {"fact_type": "skill", "content": "Python, Docker"},
            {"fact_type": "project", "content": "REST API service"},
        ],
        "has_reference_permission": True,
    }
    resp = api_client.post("/api/v1/resume/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["plagiarism_detected"] is False
    assert len(data["sections"]) >= 1
