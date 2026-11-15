"""Search reviewed public references without reading user CVs or fetching URLs."""

import re
from datetime import date
from typing import Annotated, Literal
from unicodedata import combining, normalize
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.modules.cvs.reference_catalog import (
    APPROVED_SOURCES,
    CATALOG,
    OutcomeEvidence,
    OutcomeStage,
)

SearchText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]

ROLE_ALIASES = {
    "backend": ("backend", "back end", "server side"),
    "frontend": ("frontend", "front end", "ui engineer", "lập trình giao diện"),
    "fullstack": ("fullstack", "full stack"),
    "platform": (
        "devops",
        "dev ops",
        "sre",
        "site reliability",
        "platform",
        "cloud engineer",
        "security engineer",
        "devsecops",
    ),
    "software": (
        "software",
        "developer",
        "programmer",
        "swe",
        "sde",
        "web",
        "lập trình viên",
        "kỹ sư phần mềm",
    ),
    "junior": (
        "junior",
        "intern",
        "internship",
        "fresher",
        "entry level",
        "new grad",
        "thực tập",
    ),
    "data": (
        "data",
        "database",
        "analytics",
        "machine learning",
        "ml engineer",
        "ai engineer",
        "dữ liệu",
        "khoa học dữ liệu",
    ),
    "mobile": ("mobile", "android", "ios", "flutter", "react native", "di động"),
}

DISCLAIMER = (
    "Chỉ tham khảo cách trình bày. Hãy viết CV bằng dữ kiện của bạn "
    "và tránh sao chép mẫu."
)


class ReferenceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: SearchText
    role: SearchText


class ReferenceResult(BaseModel):
    id: str
    title: str
    source: str
    source_url: str
    license: str
    rights_url: str
    rights_checked_on: date
    pattern: str
    outcome_status: Literal["verified", "unverified"]
    outcome_stage: OutcomeStage | Literal["unknown"] = "unknown"
    outcome_evidence_url: str | None = None
    outcome_evidence_publisher: str | None = None


class ReferenceSearch(BaseModel):
    mode: Literal["verified", "general", "empty"]
    references: list[ReferenceResult]
    disclaimer: str = DISCLAIMER


def _normalize(text: str) -> str:
    folded = normalize("NFKD", text.casefold()).replace("đ", "d")
    letters = "".join(char for char in folded if not combining(char))
    return " ".join(re.findall(r"[^\W_]+", letters))


def _role_scores(text: str) -> dict[str, int]:
    words = f" {_normalize(text)} "
    return {
        role: 2 if role != "software" else 1
        for role, aliases in ROLE_ALIASES.items()
        if any(f" {_normalize(alias)} " in words for alias in aliases)
    }


def _approved_outcome(
    company: str | None,
    evidence: OutcomeEvidence | None,
    target_company: str,
    target_role: str,
) -> OutcomeEvidence | None:
    if not company or not evidence or not target_company:
        return None
    if (
        _normalize(company) != target_company
        or _normalize(evidence.company) != target_company
        or _normalize(evidence.role) != target_role
    ):
        return None
    if evidence.stage not in ("screen", "interview", "offer") or not evidence.publisher:
        return None
    try:
        url = urlsplit(evidence.url)
        if url.scheme != "https" or not url.hostname or url.port not in (None, 443):
            return None
    except ValueError:
        return None
    if url.username or url.password or re.search(r"[\\\s]", evidence.url):
        return None
    return evidence


def search_references(query: ReferenceQuery) -> ReferenceSearch:
    target_company = _normalize(query.company)
    target_role = _normalize(query.role)
    scores = _role_scores(query.role)
    exact: list[tuple[int, ReferenceResult]] = []
    general: list[tuple[int, ReferenceResult]] = []

    for entry in CATALOG:
        source = APPROVED_SOURCES.get(entry.source)
        score = max((scores.get(role, 0) for role in entry.roles), default=0)
        if source is None or not score:
            continue

        evidence = _approved_outcome(
            entry.company, entry.evidence, target_company, target_role
        )
        # Company-specific claims stay hidden without matching public evidence.
        if entry.company and evidence is None:
            continue
        result = ReferenceResult(
            id=entry.source,
            title=entry.title,
            source=source.publisher,
            source_url=source.url,
            license=source.license,
            rights_url=source.rights_url,
            rights_checked_on=source.checked_on,
            pattern=entry.pattern,
            outcome_status="verified" if evidence else "unverified",
            outcome_stage=evidence.stage if evidence else "unknown",
            outcome_evidence_url=evidence.url if evidence else None,
            outcome_evidence_publisher=evidence.publisher if evidence else None,
        )
        (exact if evidence else general).append((score, result))

    selected = sorted(exact or general, key=lambda item: -item[0])
    mode = "verified" if exact else "general" if general else "empty"
    return ReferenceSearch(mode=mode, references=[row for _, row in selected])
