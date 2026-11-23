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


def normalize_rubric(r: str | None) -> str:
    if not r:
        return ""
    r = str(r).strip()
    return r[1:] if r.startswith(("v", "V")) else r


def evaluate(
    milestones: list[dict[str, Any]],
    snapshot: Snapshot,
    *,
    expected_scope: str,
    expected_rubric: str,
    expected_period: str,
) -> list[dict[str, Any]]:
    snap_rubric = normalize_rubric(snapshot.rubric)
    exp_rubric = normalize_rubric(expected_rubric)
    if not snapshot.valid or (snapshot.scope, snap_rubric, snapshot.period) != (
        expected_scope,
        exp_rubric,
        expected_period,
    ):
        raise IncomparableSnapshot(
            "Snapshot is invalid or scope/rubric/period mismatch"
        )
    # GitHub skills and roadmap milestones can differ in capitalization
    # (e.g. "Python" vs "python"); compare keys without weakening verification.
    normalized_skills: dict[str, list[dict[str, Any]]] = {}
    for skill_key, items in snapshot.skills.items():
        normalized_key = str(skill_key).strip().casefold()
        normalized_skills.setdefault(normalized_key, []).extend(items)

    result = []
    for m in milestones:
        if m["status"] == "completed":
            continue
        required = m.get("required_skills", [])
        if not required:
            continue
        evidence = []
        for skill in required:
            items = normalized_skills.get(str(skill).strip().casefold(), [])
            target = m.get("target_score")
            verified = [
                e
                for e in items
                if e.get("verified") is True
                and e.get("ref")
                and (
                    target is None
                    or (e.get("score") is not None and e["score"] >= target)
                )
            ]
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
