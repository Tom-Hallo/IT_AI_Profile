"""Repository static code, language, framework & architecture analysis module (PBI-012)."""

from typing import Any

from app.modules.analysis.evidence import (
    ConfidenceLevel,
    DetectionMethod,
    EvidenceCollector,
    EvidenceRecord,
    EvidenceSource,
    EvidenceStoreProtocol,
    FindingType,
)
from app.modules.analysis.inspector import (
    InMemoryContentSource,
    RepositoryContentSource,
    RepositoryInspector,
)
from app.modules.analysis.limits import AnalysisBudgetTracker, AnalysisLimits

__all__ = [
    "AnalysisBudgetTracker",
    "AnalysisLimits",
    "ConfidenceLevel",
    "DetectionMethod",
    "EvidenceCollector",
    "EvidenceRecord",
    "EvidenceSource",
    "EvidenceStoreProtocol",
    "FindingType",
    "InMemoryContentSource",
    "RepositoryContentSource",
    "RepositoryInspector",
    "analyze_repository",
    "router",
]


def __getattr__(name: str) -> Any:
    if name == "router":
        from app.modules.analysis.router import router

        return router
    if name == "analyze_repository":
        from app.modules.analysis.service import analyze_repository

        return analyze_repository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
