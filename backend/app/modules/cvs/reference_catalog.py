"""Reviewed links to public resume templates. No CV content is stored here."""

from dataclasses import dataclass
from datetime import date
from typing import Literal

OutcomeStage = Literal["screen", "interview", "offer"]


@dataclass(frozen=True)
class Source:
    publisher: str
    url: str
    license: Literal["MIT", "CC BY 4.0"]
    rights_url: str
    checked_on: date


@dataclass(frozen=True)
class OutcomeEvidence:
    """Add only public evidence that identifies the same CV, employer and role."""

    company: str
    role: str
    stage: OutcomeStage
    publisher: str
    url: str


@dataclass(frozen=True)
class Reference:
    source: str
    title: str
    roles: tuple[str, ...]
    pattern: str
    company: str | None = None
    evidence: OutcomeEvidence | None = None


REVIEW_DATE = date(2026, 11, 15)

# Each entry lists an exact, reviewed resource, not a domain-wide permission.
APPROVED_SOURCES = {
    "lxlynx-markdown": Source(
        publisher="Alexander Cardoza (lxlynx) · GitHub",
        url="https://github.com/lxlynx/resume",
        license="MIT",
        rights_url="https://github.com/lxlynx/resume/blob/main/LICENSE",
        checked_on=REVIEW_DATE,
    ),
    "david-typst": Source(
        publisher="David Sasson · GitHub",
        url="https://github.com/DavidSasson22/david-resume-template#canonical-example",
        license="MIT",
        rights_url="https://github.com/DavidSasson22/david-resume-template/blob/main/LICENSE",
        checked_on=REVIEW_DATE,
    ),
    "milan-junior": Source(
        publisher="Milan Milanović · GitHub",
        url="https://github.com/milanm/Milanovic-Resume",
        license="MIT",
        rights_url="https://github.com/milanm/Milanovic-Resume/blob/main/LICENSE",
        checked_on=REVIEW_DATE,
    ),
    "jake-latex": Source(
        publisher="Jake Gutierrez · Overleaf",
        url="https://www.overleaf.com/latex/templates/jakes-resume/syzfjbzwjncs",
        license="MIT",
        rights_url="https://github.com/jakegut/resume/blob/master/LICENSE",
        checked_on=REVIEW_DATE,
    ),
    "timmy-data": Source(
        publisher="Timmy Chan · Overleaf",
        url="https://www.overleaf.com/latex/templates/data-science-tech-resume-template/zcdmpfxrzjhv",
        license="CC BY 4.0",
        rights_url="https://www.overleaf.com/latex/templates/data-science-tech-resume-template/zcdmpfxrzjhv",
        checked_on=REVIEW_DATE,
    ),
}

CATALOG = (
    Reference(
        source="lxlynx-markdown",
        title="Mẫu Markdown cho kỹ sư phần mềm",
        roles=("backend", "platform", "fullstack"),
        pattern="Nêu kết quả của từng công việc rồi chọn dự án và công nghệ liên quan.",
    ),
    Reference(
        source="david-typst",
        title="Mẫu Typst cho kỹ sư full-stack",
        roles=("backend", "frontend", "fullstack"),
        pattern=(
            "Nhóm kỹ năng theo lĩnh vực, trình bày kinh nghiệm theo thứ tự gần nhất."
        ),
    ),
    Reference(
        source="milan-junior",
        title="Mẫu kỹ sư phần mềm mới vào nghề",
        roles=("junior",),
        pattern="Đặt dự án nổi bật lên trước nếu kinh nghiệm làm việc còn ít.",
    ),
    Reference(
        source="jake-latex",
        title="Jake’s Resume",
        roles=("software", "frontend", "fullstack", "mobile"),
        pattern="Tách rõ học vấn, kinh nghiệm, dự án và kỹ năng trong bố cục một cột.",
    ),
    Reference(
        source="timmy-data",
        title="Mẫu CV Data Science",
        roles=("data",),
        pattern="Tách kỹ năng kỹ thuật khỏi kinh nghiệm và các hoạt động liên quan.",
    ),
)
