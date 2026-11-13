import os
from typing import Protocol

from .contracts import AnalysisResult, ReanalysisRequest


class AnalysisAdapter(Protocol):
    def analyze(self, owner_id: int, request: ReanalysisRequest) -> AnalysisResult: ...


class FakeAnalysisAdapter:
    """Deterministic fixture ONLY for test/development; never production."""

    def analyze(self, owner_id: int, request: ReanalysisRequest) -> AnalysisResult:
        return AnalysisResult(
            score=74,
            skills={"python": 82.0, "testing": 66.0},
            evidence_summary={"fixture": True},
            source_fingerprint="fixture-only",
        )


def get_analysis_adapter() -> AnalysisAdapter:
    mode = os.getenv("PBI030_ANALYSIS_MODE", "real")
    if mode == "fake":
        if os.getenv("APP_ENV", "production").lower() not in {"development", "test"}:
            raise RuntimeError("Fake analysis is prohibited outside development/test")
        return FakeAnalysisAdapter()
    # PBI-018 integration point: import and instantiate the real analysis service here.
    raise RuntimeError("PBI-018 real analysis adapter is not connected")
