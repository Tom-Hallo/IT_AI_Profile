"""PBI-034 — Multi-source extended competency assessment service.

Verified layer: pure RoleScoringService (GitHub contribution-verified only).
Extended layer: verified + self-reported claims (structurally lower confidence).
Self-reported evidence NEVER mutates Verified Score.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ai.scoring.schemas import Limitation
from app.modules.competency_assessment.schemas import (
    AssessmentLayerOut,
    ClaimedSkillOut,
    ClaimEvidenceOut,
    CompetencyAssessmentResponse,
    ConflictItem,
    MissingItem,
    SourceSummary,
)
from app.modules.role_scoring.schemas import RoleScoreResponse
from app.modules.role_scoring.service import (
    RoleScoringOutcome,
    RoleScoringRequest,
    RoleScoringService,
)
from app.modules.self_reported_skills.service import list_skills, serialize_skill

CLAIM_BASE_CONFIDENCE = 0.35
CLAIM_WITH_EVIDENCE_CONFIDENCE = 0.45


class CompetencyAssessmentService:
    def __init__(
        self,
        *,
        user_id: int,
        db: Session,
        role_scoring: RoleScoringService,
    ) -> None:
        self._user_id = user_id
        self._db = db
        self._role_scoring = role_scoring

    def assess(
        self,
        role_key: str,
        *,
        repository_ids: Sequence[int] | None = None,
        snapshot_ref: str | None = None,
        rubric_version: str | None = None,
    ) -> CompetencyAssessmentResponse:
        # 1. Verified Assessment — pure existing Role Scoring (no claims).
        verified_outcome = self._role_scoring.score(
            RoleScoringRequest(
                role_key=role_key,
                repository_ids=repository_ids,
                snapshot_ref=snapshot_ref,
                rubric_version=rubric_version,
            )
        )
        verified_response = RoleScoreResponse.from_outcome(verified_outcome)
        verified_layer = self._build_verified_layer(verified_outcome, verified_response)

        # 2. Load self-reported claims (owner-isolated).
        claimed_skills = self._load_claimed_skills()

        # 3. Extended = verified + claims (never mutates verified score).
        extended_layer = self._build_extended_layer(
            verified_layer=verified_layer,
            claimed_skills=claimed_skills,
        )

        # 4. Detect conflicts / missing.
        conflicts = self._detect_conflicts(verified_layer, claimed_skills)
        missing = self._collect_missing(verified_outcome)

        return CompetencyAssessmentResponse(
            role_key=verified_outcome.rubric.role_key,
            role_name=verified_outcome.rubric.name,
            rubric_version=verified_outcome.rubric.rubric_version,
            verified=verified_layer,
            extended=extended_layer,
            conflicts=conflicts,
            missing=missing,
            generated_at=datetime.now(UTC),
            verified_detail=verified_response,
        )

    def _build_verified_layer(
        self,
        outcome: RoleScoringOutcome,
        response: RoleScoreResponse,
    ) -> AssessmentLayerOut:
        result = outcome.result
        github_count = len(result.evidence_refs) if result.evidence_refs else 0

        sources = [
            SourceSummary(
                source="github",
                evidence_count=github_count,
                confidence_note=(
                    "Only contribution-verified GitHub evidence is included. "
                    "Unverified or private-without-consent repositories are excluded."
                ),
            )
        ]

        status_val = (
            result.status.value
            if hasattr(result.status, "value")
            else str(result.status)
        )

        return AssessmentLayerOut(
            layer="verified",
            status=status_val,
            score=result.role_score,
            confidence=result.confidence,
            coverage=result.coverage,
            rationale=result.rationale,
            sources=sources,
            criteria=response.criteria,
            claimed_skills=[],
            limitations=list(result.limitations),
            evidence_refs=response.evidence_refs,
        )

    def _load_claimed_skills(self) -> list[ClaimedSkillOut]:
        skills = list_skills(self._db, self._user_id)
        out: list[ClaimedSkillOut] = []
        for skill in skills:
            data = serialize_skill(self._db, skill)
            evidence_items = data.get("evidence") or []
            has_evidence = len(evidence_items) > 0
            conf = (
                CLAIM_WITH_EVIDENCE_CONFIDENCE
                if has_evidence
                else CLAIM_BASE_CONFIDENCE
            )
            out.append(
                ClaimedSkillOut(
                    id=data["id"],
                    skill_name=data["skill_name"],
                    description=data.get("description"),
                    source="self_reported",
                    status=data.get("status", "self-reported"),
                    confidence=conf,
                    evidence=[
                        ClaimEvidenceOut(
                            id=ev.get("id"),
                            title=ev.get("title") or "",
                            description=ev.get("description"),
                            url=ev.get("url"),
                            source="self_reported",
                            confidence=conf,
                            created_at=ev.get("created_at"),
                        )
                        for ev in evidence_items
                    ],
                )
            )
        return out

    def _build_extended_layer(
        self,
        *,
        verified_layer: AssessmentLayerOut,
        claimed_skills: list[ClaimedSkillOut],
    ) -> AssessmentLayerOut:
        sources = list(verified_layer.sources)
        claim_count = sum(len(s.evidence) for s in claimed_skills) + len(claimed_skills)
        if claimed_skills:
            sources.append(
                SourceSummary(
                    source="self_reported",
                    evidence_count=claim_count,
                    confidence_note=(
                        "Self-reported skills and evidence are included only in the "
                        "Extended layer. They carry structurally lower confidence and "
                        "do not affect Verified Assessment score."
                    ),
                )
            )

        extra_limitations = list(verified_layer.limitations)
        if claimed_skills:
            extra_limitations.append(
                Limitation(
                    code="SELF_REPORTED_INCLUDED",
                    message=(
                        f"{len(claimed_skills)} self-reported skill(s) are shown in "
                        "Extended Assessment only. They do not change Verified Score."
                    ),
                )
            )
        else:
            extra_limitations.append(
                Limitation(
                    code="NO_SELF_REPORTED",
                    message="No self-reported skills found for this user.",
                )
            )

        extended_confidence = verified_layer.confidence
        if claimed_skills and extended_confidence is not None:
            extended_confidence = round(min(extended_confidence, 70.0) * 0.95, 2)

        return AssessmentLayerOut(
            layer="extended",
            status=verified_layer.status,
            # Intentionally identical — claims do not alter Verified Score
            score=verified_layer.score,
            confidence=extended_confidence,
            coverage=verified_layer.coverage,
            rationale=(
                (verified_layer.rationale or "")
                + (
                    " Extended layer additionally surfaces self-reported claims "
                    "with explicit low confidence; they are never mixed into the "
                    "Verified Score."
                    if claimed_skills
                    else ""
                )
            ).strip()
            or None,
            sources=sources,
            criteria=verified_layer.criteria,
            claimed_skills=claimed_skills,
            limitations=extra_limitations,
            evidence_refs=verified_layer.evidence_refs,
        )

    def _detect_conflicts(
        self,
        verified_layer: AssessmentLayerOut,
        claimed_skills: list[ClaimedSkillOut],
    ) -> list[ConflictItem]:
        conflicts: list[ConflictItem] = []
        if not claimed_skills:
            return conflicts

        low_or_missing = {
            c.key.lower()
            for c in verified_layer.criteria
            if c.status in {"INSUFFICIENT", "UNKNOWN", "CONFLICTING"}
            or (c.score is not None and c.score < 40)
        }
        low_or_missing.update(
            c.name.lower()
            for c in verified_layer.criteria
            if c.status in {"INSUFFICIENT", "UNKNOWN", "CONFLICTING"}
            or (c.score is not None and c.score < 40)
        )

        for claim in claimed_skills:
            name_l = claim.skill_name.lower()
            matched = next(
                (k for k in low_or_missing if name_l in k or k in name_l),
                None,
            )
            if matched:
                conflicts.append(
                    ConflictItem(
                        skill_or_criterion=claim.skill_name,
                        verified_value="low or missing verified evidence",
                        claim_value=f"self-reported (confidence={claim.confidence})",
                        claim_source="self_reported",
                        explanation=(
                            f"User claims '{claim.skill_name}' but verified GitHub "
                            "evidence for related criteria is weak or absent. "
                            "Claim remains visible only in Extended Assessment."
                        ),
                    )
                )
        return conflicts

    def _collect_missing(self, outcome: RoleScoringOutcome) -> list[MissingItem]:
        missing: list[MissingItem] = []
        result = outcome.result
        for crit in result.criteria:
            status = (
                crit.status.value if hasattr(crit.status, "value") else str(crit.status)
            )
            if status in {"INSUFFICIENT", "UNKNOWN"}:
                missing.append(
                    MissingItem(
                        key=crit.key,
                        description=crit.name or crit.key,
                        required=crit.required,
                        suggestion=(
                            "Connect and verify more repositories, or ensure "
                            "contribution verification (PBI-013) has completed."
                            if crit.type and "SKILL" in str(crit.type)
                            else "Run architecture analysis on selected repositories."
                        ),
                    )
                )
        return missing
