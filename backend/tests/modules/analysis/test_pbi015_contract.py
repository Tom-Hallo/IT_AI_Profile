"""Fast unit contract; add PostgreSQL integration tests before merge."""

from app.modules.analysis.finding_router import EvidenceOut


def test_private_snippet_is_not_serialized():
    data = {
        "id": 1,
        "commit_sha": "a" * 40,
        "file_path": "src/app.py",
        "line_number": 4,
        "pr_number": None,
        "evidence_source": "source_code",
        "detection_method": "content_inspection",
        "confidence_score": 0.9,
        "matched_content": "SENSITIVE_PRIVATE_SNIPPET",
    }
    result = EvidenceOut.model_validate(data, extra="ignore").model_dump_json()
    assert "SENSITIVE_PRIVATE_SNIPPET" not in result
    assert "matched_content" not in result


def test_finding_response_does_not_expose_snippet():
    from app.modules.analysis.finding_router import FindingOut

    response = FindingOut(
        id=1,
        report_id=2,
        repository_id=3,
        commit_sha="a" * 40,
        finding_type="language",
        classification="Python",
        rationale="Python source",
        confidence_score=0.9,
        analyzer_version="pbi012-legacy",
        scope="public",
        time_range=None,
        evidence=[
            EvidenceOut(
                id=4,
                commit_sha="a" * 40,
                file_path="src/main.py",
                line_number=2,
                evidence_source="source_code",
                detection_method="content_inspection",
                confidence_score=0.9,
            )
        ],
    )
    assert "matched_content" not in response.model_dump_json()
    assert response.evidence[0].id == 4


def test_finding_model_has_same_report_foreign_keys():
    from app.modules.analysis.finding_models import FindingEvidenceLink

    foreign_keys = [
        set(str(x) for x in fk.column_keys)
        for fk in FindingEvidenceLink.__table__.foreign_key_constraints
    ]
    assert {"finding_id", "report_id"} in foreign_keys
    assert {"evidence_id", "report_id"} in foreign_keys
