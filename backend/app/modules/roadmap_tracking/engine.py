"""Pure comparison engine; no database, network or untrusted code execution."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Snapshot:
    key: str
    user_id: int
    scope: str
    rubric: str
    period: str
    skills: dict[str, list[dict[str, Any]]]
    valid: bool = True


class IncomparableSnapshot(ValueError):
    pass


def evaluate(
    milestones: list[dict[str, Any]],
    snapshot: Snapshot,
    *,
    expected_scope: str,
    expected_rubric: str,
    expected_period: str,
) -> list[dict[str, Any]]:
    if not snapshot.valid or (snapshot.scope, snapshot.rubric, snapshot.period) != (
        expected_scope,
        expected_rubric,
        expected_period,
    ):
        raise IncomparableSnapshot(
            "Snapshot is invalid or scope/rubric/period mismatch"
        )
    result = []
    for m in milestones:
        if m["status"] == "completed":
            continue
        required = m.get("required_skills", [])
        if not required:
            continue
        evidence = []
        for skill in required:
            items = snapshot.skills.get(skill, [])
            verified = [e for e in items if e.get("verified") is True and e.get("ref")]
            if not verified:
                break
            evidence.extend({"skill": skill, "ref": e["ref"]} for e in verified)
        else:
            result.append(
                {
                    "milestone_id": m["id"],
                    "action": "complete",
                    "evidence": evidence,
                    "explanation": "Verified evidence found for all required skills: "
                    + ", ".join(required),
                }
            )
    return result
