"""Evidence-based, text-only ATS review. Does not inspect original file layout."""

import re

VERSION = "1.0.0"
SKILLS = (
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "React",
    "FastAPI",
    "Django",
    "Node.js",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Docker",
    "Kubernetes",
    "AWS",
    "Azure",
    "Git",
    "GitHub Actions",
    "CI/CD",
    "REST API",
    "GraphQL",
    "SQL",
    "Machine Learning",
    "TensorFlow",
    "PyTorch",
    "HTML",
    "CSS",
    "C#",
    ".NET",
    "Spring Boot",
)
HEADINGS = {
    "experience": (
        "experience",
        "work experience",
        "kinh nghiệm",
        "kinh nghiệm làm việc",
    ),
    "education": ("education", "học vấn", "giáo dục"),
    "skills": ("skills", "technical skills", "kỹ năng"),
    "projects": ("projects", "dự án"),
}


def occurrences(text: str, term: str) -> list[tuple[int, int]]:
    pattern = rf"(?<!\w){re.escape(term)}(?!\w)"
    return [m.span() for m in re.finditer(pattern, text, flags=re.IGNORECASE)]


def extract_keywords(jd: str) -> list[str]:
    return [term for term in SKILLS if occurrences(jd, term)]


def keyword_matches(cv: str, jd: str) -> tuple[list[dict], list[str], float | None]:
    terms = extract_keywords(jd)
    if not terms:
        return [], [], None
    matches, missing = [], []
    for term in terms:
        spans = occurrences(cv, term)
        if not spans:
            missing.append(term)
        evidence = None
        if spans:
            start, end = spans[0]
            evidence = cv[max(0, start - 60) : min(len(cv), end + 60)].strip()
        matches.append({"keyword": term, "found": bool(spans), "evidence": evidence})
    return matches, missing, round(100 * (len(terms) - len(missing)) / len(terms), 2)


def analyze(cv: str, jd: str | None = None) -> dict:
    if not cv or not cv.strip():
        raise ValueError("CV_EMPTY")
    if len(cv) > 50_000:
        raise ValueError("CV_TOO_LARGE")
    jd = (jd or "").strip()
    if len(jd) > 20_000:
        raise ValueError("JD_TOO_LARGE")
    lines = {
        line.strip().rstrip(":").casefold() for line in cv.splitlines() if line.strip()
    }
    issues = [
        {
            "code": "MISSING_HEADING",
            "severity": "warning",
            "section": section,
            "message": f"Không tìm thấy heading: {section}",
        }
        for section, aliases in HEADINGS.items()
        if not any(alias in lines for alias in aliases)
    ]
    matches, missing, coverage = keyword_matches(cv, jd)
    suggestions = [
        {
            "type": "structure",
            "message": f"Nếu có nội dung tương ứng, thêm heading '{issue['section']}'.",
            "evidence": issue["code"],
        }
        for issue in issues
    ]
    suggestions += [
        {
            "type": "keyword",
            "message": f"JD đề cập {term}. Chỉ bổ sung nếu có kinh nghiệm thực tế.",
            "evidence": f"JD_KEYWORD:{term}",
        }
        for term in missing
    ]
    return {
        "analyzer_version": VERSION,
        "readability_score": round(100 * (len(HEADINGS) - len(issues)) / len(HEADINGS)),
        "keyword_coverage": coverage,
        "keyword_matches": matches,
        "missing_keywords": missing,
        "layout_issues": issues,
        "parsing_issues": [],
        "suggestions": suggestions,
        "checks": {
            "text_structure": "completed",
            "file_layout": "not_checked",
            "embedded_images": "not_checked",
            "fonts": "not_checked",
        },
        "disclaimer": (
            "Đây là đánh giá tham khảo, không phải kết quả ATS thực tế "
            "và không đảm bảo vượt qua vòng tuyển dụng."
        ),
    }
