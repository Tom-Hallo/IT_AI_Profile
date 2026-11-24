"""Assessment adapters: fixtures are explicit and NEVER silently used in production."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.scoring.evidence_catalog import is_forbidden_evidence_type
from app.ai.scoring.schemas import ScoreStatus, SkillSnapshotInput
from app.modules.github.models import Repository, user_repository
from app.modules.role_scoring.skill_adapter import DatabaseSkillSnapshotSource
from app.modules.scoring.snapshots import VERSION


class AssessmentProvider(Protocol):
    def load(self, db: Session, user_id: int) -> list[dict[str, Any]]: ...


class RealAssessmentProvider:
    """Read report-bound public skills from the same evidence source as scoring."""

    def load(self, db: Session, user_id: int) -> list[dict[str, Any]]:
        repo_ids = public_repo_ids(db, user_id)
        if not repo_ids:
            return []
        raw = DatabaseSkillSnapshotSource(
            db,
            repo_id_filter=frozenset(repo_ids),
            report_scope=("public",),
            rubric_version=VERSION,
        ).fetch(user_id)
        if raw is None or not isinstance(raw.payload, SkillSnapshotInput):
            return []
        results = []
        for item in raw.payload.items:
            evidence = [
                {
                    "id": ref.evidence_id or ref.dedup_key,
                    "repository_id": ref.repository_id,
                    "commit_sha": ref.commit_sha,
                    "pr_number": ref.pr_number,
                    "finding_type": ref.finding_type,
                    "file_path": ref.file_path,
                }
                for ref in item.evidence_refs
                if ref.repository_id in repo_ids
                and ref.verified
                and ref.confidence_score > 0
                and not is_forbidden_evidence_type(ref.finding_type, ref.classification)
            ]
            confidence = item.confidence or 0
            results.append(
                {
                    "skill": item.skill_key,
                    "score": item.score if item.status == ScoreStatus.SCORED else None,
                    "confidence": (
                        "high"
                        if evidence and confidence >= 80
                        else "medium"
                        if evidence and confidence >= 60
                        else "unknown"
                    ),
                    "evidence": evidence,
                }
            )
        return results


def public_repo_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(
            select(Repository.id)
            .join(user_repository, user_repository.c.repository_id == Repository.id)
            .where(user_repository.c.user_id == user_id, Repository.private.is_(False))
        )
    )


class FixtureAssessmentProvider:
    """For tests/local development only; never expose via public API flag."""

    def __init__(self, path: Path):
        self.path = path

    def load(self, db: Session, user_id: int) -> list[dict[str, Any]]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data["assessments"]
