"""Request and response schemas for self-reported skills."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SkillCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)


class SkillUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=5000)


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    url: HttpUrl | None = None


class EvidenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    url: HttpUrl | None = None


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_id: int
    title: str
    description: str | None
    url: str | None
    source: str
    status: str
    created_at: datetime
    updated_at: datetime


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_name: str
    description: str | None
    source: str
    status: str
    created_at: datetime
    updated_at: datetime
    evidence: list[EvidenceOut] = Field(default_factory=list)
