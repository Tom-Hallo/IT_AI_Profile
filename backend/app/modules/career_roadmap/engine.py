"""Pure, deterministic roadmap engine; unknown evidence never means low proficiency."""

from __future__ import annotations

from typing import Any

GOALS: dict[str, dict[str, int]] = {
    "backend": {
        "python": 75,
        "fastapi": 75,
        "postgresql": 70,
        "testing": 70,
        "docker": 60,
    },
    "frontend": {"javascript": 75, "typescript": 70, "react": 75, "testing": 65},
    "fullstack": {
        "python": 65,
        "fastapi": 65,
        "postgresql": 60,
        "typescript": 65,
        "react": 65,
    },
    "devops": {"docker": 80, "ci/cd": 75, "linux": 75, "python": 60},
}


def generate(goal: str, assessments: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate ordered milestones from user-specific verified assessments."""
    if goal not in GOALS:
        raise ValueError("Unsupported goal")
    latest: dict[str, dict[str, Any]] = {}
    for a in assessments:
        skill = str(a.get("skill", "")).strip().lower()
        if skill not in GOALS[goal]:
            continue
        # Provider must return newest records first; do not replace newer snapshots.
        latest.setdefault(skill, a)
    milestones = []
    for skill, target in GOALS[goal].items():
        a = latest.get(skill)
        score = a.get("score") if a else None
        evidence = a.get("evidence", []) if a else []
        confidence = a.get("confidence", "unknown") if a else "unknown"
        verified = (
            bool(evidence)
            and confidence in {"high", "medium"}
            and score is not None
        )
        if not verified:
            gap_type, priority, action = (
                "missing_evidence",
                1,
                f"Create and document a {skill} project with reviewable commits and tests",
            )
            gap = None
        else:
            gap = max(0, target - int(score))
            if gap == 0:
                continue
            gap_type, priority = (
                "skill_gap",
                (1 if gap >= 30 else 2 if gap >= 15 else 3),
            )
            action = (
                f"Create and document a {skill} project "
                "with reviewable commits and tests"
            )
        milestones.append(
            {
                "skill": skill,
                "target_score": target,
                "current_score": int(score) if verified else None,
                "gap": gap,
                "gap_type": gap_type,
                "priority": priority,
                "objective": action,
                "metric": f"Reach verified {skill} assessment >= {target}/100 with at least one accessible evidence reference",
                "evidence": evidence if verified else [],
                "confidence": confidence if verified else "unknown",
                "status": "todo",
            }
        )
    milestones.sort(key=lambda m: (m["priority"], -(m["gap"] or 0), m["skill"]))
    for i, m in enumerate(milestones, 1):
        m["order"] = i
    return {
        "version": "pbi023-v1",
        "goal": goal,
        "milestones": milestones,
        "evidence_gaps": [
            m["skill"] for m in milestones if m["gap_type"] == "missing_evidence"
        ],
        "total": len(milestones),
    }
