from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SnapshotView:
    scope: dict
    rubric_version: str
    window_start: str
    window_end: str
    score: int
    skills: dict[str, float]


def compare_snapshots(old: SnapshotView, new: SnapshotView) -> dict[str, Any]:
    warnings = []
    if old.scope != new.scope:
        warnings.append("SCOPE_CHANGED")
    if old.rubric_version != new.rubric_version:
        warnings.append("RUBRIC_CHANGED")
    if (old.window_start, old.window_end) != (new.window_start, new.window_end):
        warnings.append("TIME_WINDOW_CHANGED")
    comparable = not warnings
    shared = sorted(old.skills.keys() & new.skills.keys())
    return {
        "comparable": comparable,
        "warnings": warnings,
        "score_delta": new.score - old.score if comparable else None,
        "skill_deltas": {k: round(new.skills[k] - old.skills[k], 4) for k in shared} if comparable else {},
        "added_skills": sorted(new.skills.keys() - old.skills.keys()),
        "removed_skills": sorted(old.skills.keys() - new.skills.keys()),
        "interpretation": "Comparable within identical scope/rubric/time window" if comparable else "Comparison limited; raw scores must not be interpreted as progress",
    }
