"""Strict allowlist for the structured tool proposals returned by the mentor."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
DraftText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)
]
RepositoryId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]
ToolName = Literal["create_cv", "create_roadmap", "reanalyze_repository"]
ActionStatus = Literal[
    "pending", "declined", "expired", "succeeded", "denied", "failed"
]


class CVProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: Literal["create_cv"]
    title: Title
    summary: DraftText
    skills: list[Title] = Field(max_length=20)


class RoadmapProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: Literal["create_roadmap"]
    title: Title
    steps: list[DraftText] = Field(min_length=1, max_length=12)


class ReanalysisProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: Literal["reanalyze_repository"]
    repository_id: RepositoryId


ToolProposal = Annotated[
    CVProposal | RoadmapProposal | ReanalysisProposal, Field(discriminator="tool")
]
tool_proposal_adapter: TypeAdapter[ToolProposal] = TypeAdapter(ToolProposal)


class ActionPreview(BaseModel):
    id: UUID
    tool: ToolName
    sources: list[str]
    impact: str
    proposal: ToolProposal
    expires_at: datetime


class ActionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["confirm", "decline"]


class ActionResult(BaseModel):
    status: ActionStatus
    result_id: str | None = None
