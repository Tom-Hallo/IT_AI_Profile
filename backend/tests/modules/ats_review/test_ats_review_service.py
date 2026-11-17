import pytest

from app.modules.ats_review.service import analyze, keyword_matches

CV = """Skills
Python, FastAPI, PostgreSQL
Projects
Built a REST API using Python.
Education
Bachelor of Computer Science
Experience
Backend development project.
"""


def test_keyword_coverage():
    result = analyze(CV, "Requires Python, FastAPI, Docker, AWS")
    assert result["keyword_coverage"] == 50.0
    assert result["missing_keywords"] == ["Docker", "AWS"]


def test_no_jd():
    result = analyze(CV)
    assert result["keyword_coverage"] is None
    assert result["keyword_matches"] == []


def test_empty_cv():
    with pytest.raises(ValueError, match="CV_EMPTY"):
        analyze("  ")


def test_no_invented_experience():
    result = analyze(CV, "Requires Kubernetes")
    assert "Kubernetes" in result["missing_keywords"]
    assert all(
        "Chỉ bổ sung" in item["message"]
        for item in result["suggestions"]
        if item["type"] == "keyword"
    )


def test_java_not_javascript():
    matches, missing, coverage = keyword_matches(
        "JavaScript developer", "Java developer"
    )
    assert coverage == 0.0
    assert missing == ["Java"]
    assert matches[0]["found"] is False


def test_no_jd_dictionary_match():
    assert analyze(CV, "Strong communication required")["keyword_coverage"] is None


def test_file_checks_not_falsely_completed():
    assert analyze(CV)["checks"]["fonts"] == "not_checked"
