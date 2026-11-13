"""Assessment adapters: fixtures are explicit and NEVER silently used in production."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.analysis.models import AnalysisEvidence
from app.modules.github.models import Repository
from app.modules.scoring.models import ScoreEvidenceLink, SkillScore


class AssessmentProvider(Protocol):
    def load(self, db: Session, user_id: int) -> list[dict[str, Any]]: ...


class RealAssessmentProvider:
    """Adapter for PBI-016 scores.

    Private scope is excluded until consent integration.
    """

    def load(self, db: Session, user_id: int) -> list[dict[str, Any]]:
        rows = db.execute(
            select(SkillScore, Repository)
            .join(Repository, Repository.id == SkillScore.repository_id)
            .where(SkillScore.user_id == user_id, Repository.owner_id == user_id)
            .order_by(SkillScore.created_at.desc(), SkillScore.id.desc())
        ).all()
        results = []
        for score, repo in rows:
            # Fail closed: only public repositories, even when historical scores exist.
            if repo.private:
                continue
            links = (
                db.execute(
                    select(AnalysisEvidence)
                    .join(
                        ScoreEvidenceLink,
                        ScoreEvidenceLink.evidence_id == AnalysisEvidence.id,
                    )
                    .where(
                        ScoreEvidenceLink.score_id == score.id,
                        AnalysisEvidence.repository_id == score.repository_id,
                        AnalysisEvidence.report_id == score.report_id,
                        AnalysisEvidence.commit_sha == score.commit_sha,
                        AnalysisEvidence.scope.in_(["public", "all"]),
                    )
                )
                .scalars()
                .all()
            )
            evidence = [
                {
                    "id": e.id,
                    "repository_id": e.repository_id,
                    "commit_sha": e.commit_sha,
                    "file_path": e.file_path,
                }
                for e in links
            ]
            results.append(
                {
                    "skill": score.technology.lower(),
                    "score": score.score if score.status == "scored" else None,
                    "confidence": "medium" if evidence else "unknown",
                    "evidence": evidence,
                }
            )
        return results


class FixtureAssessmentProvider:
    """For tests/local development only; never expose via public API flag."""

    def __init__(self, path: Path):
        self.path = path

    def load(self, db: Session, user_id: int) -> list[dict[str, Any]]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data["assessments"]
