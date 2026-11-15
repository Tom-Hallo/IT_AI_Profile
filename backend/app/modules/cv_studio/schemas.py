"""Separate user input, source citations and model selection."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)

from app.modules.cvs.parser import CONTROL_CHARS

Template = Literal["classic", "technical"]
Identifier = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]


def document_text(text: str) -> str:
    text.encode("utf-8")
    if CONTROL_CHARS.search(text) or "\ufffe" in text or "\uffff" in text:
        raise ValueError("Invalid document text")
    return text.replace("\r\n", "\n").replace("\r", "\n")


Title = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=120, pattern=r"^[^\r\n]+$"
    ),
    AfterValidator(document_text),
]
JobText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=12_000),
    AfterValidator(document_text),
]


def limit_lines(text: str) -> str:
    if text.count("\n") >= 500:
        raise ValueError("Too many lines")
    return text


BodyText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000),
    AfterValidator(document_text),
    AfterValidator(limit_lines),
]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


def confirm_ai(value: object) -> object:
    if value is not True:
        raise ValueError("Explicit AI consent is required")
    return value


class GenerateCV(RequestModel):
    title: Title
    jd: JobText
    cv_id: Identifier | None = None
    use_github: bool = True
    allow_ai: Annotated[Literal[True], BeforeValidator(confirm_ai)]
    template: Template = "classic"


class SaveVersion(RequestModel):
    title: Title
    text: BodyText
    previous_version: Annotated[int, Field(strict=True, gt=0, le=2**31 - 2)]


class Source(BaseModel):
    type: Literal["cv", "github", "manual", "missing"]
    cv_id: int | None = None
    cv_version: int | None = None
    line_number: int | None = None
    repo_id: int | None = None
    evidence_id: str | None = None
    commit_sha: str | None = None


class DraftLine(BaseModel):
    text: str
    source: Source


class VersionSummary(BaseModel):
    document_id: UUID
    number: int
    title: str
    template: Template
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VersionDetail(VersionSummary):
    lines: list[DraftLine]
    source_unavailable: bool = False


class SelectedFacts(RequestModel):
    ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(
        min_length=1, max_length=30
    )
