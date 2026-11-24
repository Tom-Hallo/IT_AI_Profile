"""Fail-closed evidence checks shared by roadmap reads and submissions."""

from copy import deepcopy

from .evidence_urls import GitHubEvidenceLink, parse_github_evidence_url


def link_key(url: str) -> tuple[str, str, str] | None:
    try:
        link = parse_github_evidence_url(url)
    except (ValueError, AttributeError):
        return None
    return (link.repo_name.casefold(), link.evidence_type, link.identifier)


def matching_evidence(
    link: GitHubEvidenceLink,
    repository_id: int,
    required_skills: list[str],
    target_score: int | None,
    assessments: list[dict],
) -> bool:
    """Require exact, score-attributed contribution for every required skill."""
    if not required_skills or target_score is None:
        return False
    for skill in required_skills:
        assessment = next(
            (
                a
                for a in assessments
                if str(a.get("skill", "")).strip().casefold()
                == str(skill).strip().casefold()
            ),
            None,
        )
        if (
            not assessment
            or assessment.get("confidence") not in {"high", "medium"}
            or assessment.get("score") is None
            or assessment["score"] < target_score
        ):
            return False
        if not any(
            ref.get("repository_id") == repository_id
            and ref.get("finding_type") == link.evidence_type
            and (
                str(ref.get("commit_sha", "")).lower() == link.identifier
                if link.evidence_type == "commit"
                else str(ref.get("pr_number")) == link.identifier
            )
            for ref in assessment.get("evidence", [])
        ):
            return False
    return True


def visible_milestone(
    original: dict,
    permitted: set[int],
    assessments: list[dict],
    required_skills: list[str] | None = None,
) -> dict:
    """Do not expose revoked references or keep obsolete verification badges."""
    item = deepcopy(original)
    required = required_skills or item.get("required_skills") or [item.get("skill")]
    target = item.get("target_score")
    entries = item.get("evidence", [])
    entries = entries if isinstance(entries, list) else []
    visible = []
    for entry in entries:
        if not isinstance(entry, dict):
            if isinstance(entry, str):
                visible.append(entry)
            continue
        repository_id = entry.get("repository_id")
        if repository_id is not None and repository_id not in permitted:
            continue
        if entry.get("source") == "submission" or entry.get("url"):
            try:
                link = parse_github_evidence_url(entry.get("url", ""))
            except (ValueError, AttributeError):
                link = None
            verified = bool(
                entry.get("verified") is True
                and repository_id in permitted
                and link
                and matching_evidence(
                    link, repository_id, required, target, assessments
                )
            )
            entry["verified"] = verified
            entry["verification_status"] = "verified" if verified else "self_reported"
        visible.append(entry)
    item["evidence"] = visible

    valid_refs = {
        (str(a.get("skill", "")).strip().casefold(), str(ref["id"]))
        for a in assessments
        if a.get("confidence") in {"high", "medium"}
        and a.get("score") is not None
        and (target is None or a["score"] >= target)
        for ref in a.get("evidence", [])
        if ref.get("repository_id") in permitted and ref.get("id") is not None
    }
    evaluation = item.get("evaluation_evidence", [])
    evaluation = evaluation if isinstance(evaluation, list) else []
    safe_evaluation = [
        ref
        for ref in evaluation
        if isinstance(ref, dict)
        and (str(ref.get("skill", "")).strip().casefold(), str(ref.get("ref")))
        in valid_refs
    ]
    if evaluation or item.get("verification_status") == "verified":
        item["evaluation_evidence"] = safe_evaluation
        if (
            not all(
                any(
                    str(ref.get("skill", "")).strip().casefold()
                    == str(skill).strip().casefold()
                    for ref in safe_evaluation
                )
                for skill in required
            )
            or not safe_evaluation
        ):
            item["verification_status"] = "pending"
    if len(visible) != len(entries) or (
        item.get("gap_type") == "skill_gap"
        and not any(
            isinstance(ref, dict)
            and ref.get("source") != "submission"
            and not ref.get("url")
            for ref in visible
        )
    ):
        item.update(
            current_score=None,
            confidence="unknown",
            gap_type="missing_evidence",
            gap=None,
        )
    return item
