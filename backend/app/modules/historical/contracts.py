from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ReanalysisRequest(BaseModel):
    scope: dict = Field(min_length=1)
    rubric_version: str = Field(min_length=1, max_length=64)
    window_start: datetime
    window_end: datetime
    visibility: Literal["public", "private"] = "public"

    @model_validator(mode="after")
    def validate_window(self):
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("timezone-aware timestamps required")
        if self.window_start >= self.window_end:
            raise ValueError("window_start must precede window_end")
        return self


class AnalysisResult(BaseModel):
    score: int = Field(ge=0, le=100)
    skills: dict[str, float]
    evidence_summary: dict
    source_fingerprint: str
