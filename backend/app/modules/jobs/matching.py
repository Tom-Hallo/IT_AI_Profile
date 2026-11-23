"""Match confirmed JD requirements against the PBI-018 scoped skill source."""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.scoring.evidence_catalog import is_forbidden_evidence_type, normalize_key
from app.ai.scoring.schemas import EvidenceRef, ScoreStatus, SkillScoreItem
from app.modules.analysis.models import AnalysisReport
from app.modules.analysis.report_window import ReportWindow
from app.modules.github.models import Repository, user_repository
from app.modules.jobs.schemas import SkillRequirementLevel
from app.modules.role_scoring.access import AccessDecision, DbRepositoryAccessGuard
from app.modules.role_scoring.architecture_provider import MAX_REPOSITORIES
from app.modules.role_scoring.skill_adapter import (
    MAX_SNAPSHOT_ITEMS,
    DatabaseSkillSnapshotSource,
    SkillSnapshotAdapter,
)
from app.modules.users.models import User

Scope = Literal["public", "private", "combined"]
MatchStatus = Literal["matched", "partial", "unknown"]
SkillKey = Annotated[str, StringConstraints(min_length=1, max_length=100)]
MATCH_SCORE = 70
MATCH_CONFIDENCE = 60
STALE_AFTER = timedelta(days=90)
SKILL_ALIASES = {
    "c#": "csharp",
    "c++": "cpp",
    "go": "golang",
    "node_js": "nodejs",
    "next_js": "nextjs",
    "nest_js": "nestjs",
    "spring_boot": "springboot",
    "tailwindcss": "tailwind",
    "postgres": "postgresql",
    "ci_cd": "cicd",
    "net": "csharp",
    "dotnet": "csharp",
}


def _skill_key(value: str) -> str:
    key = normalize_key(value)
    return SKILL_ALIASES.get(key, key)


class JobRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skill_key: SkillKey
    level: SkillRequirementLevel

    @field_validator("skill_key")
    @classmethod
    def normalize_skill(cls, value: str) -> str:
        normalized = _skill_key(value)
        if not normalized:
            raise ValueError("Skill key must contain a supported character")
        return normalized


class JobMatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Scope = "public"
    skills: list[JobRequirement] = Field(min_length=1, max_length=80)


class MatchEvidence(BaseModel):
    evidence_id: str | None
    repository_id: int
    commit_sha: str | None
    file_path: str | None
    source_scope: Literal["public", "private"]
    repository_name: str | None = None
    repository_full_name: str | None = None
    commit_url: str | None = None


class JobSkillMatch(JobRequirement):
    status: MatchStatus
    reason: str
    score: float | None = None
    confidence: float | None = None
    evidence: list[MatchEvidence] = Field(default_factory=list)


class JobMatchResponse(BaseModel):
    scope: Scope
    skills: list[JobSkillMatch]
    required_matched_percent: int | None
    snapshot_refs: list[str]
    stale_snapshot: bool
    limitations: list[str]
    disclaimer: str = (
        "Tỷ lệ chỉ phản ánh kỹ năng bắt buộc có bằng chứng đạt ngưỡng. "
        "Tỷ lệ này không phải xác suất trúng tuyển."
    )


def _rank(item: SkillScoreItem) -> tuple[bool, float, float]:
    score = item.score or 0
    confidence = item.confidence or 0
    return score >= MATCH_SCORE and confidence >= MATCH_CONFIDENCE, confidence, score


def _usable(item: SkillScoreItem, allowed: set[int]) -> bool:
    return item.status == ScoreStatus.SCORED and any(
        _usable_ref(ref, allowed) for ref in item.evidence_refs
    )


def _usable_ref(ref: EvidenceRef, allowed: set[int]) -> bool:
    return (
        ref.repository_id in allowed
        and ref.verified
        and ref.confidence_score > 0
        and not is_forbidden_evidence_type(ref.finding_type, ref.classification)
    )


def _match_skill(
    requirement: JobRequirement,
    candidates: list[tuple[SkillScoreItem, Literal["public", "private"]]],
    allowed: set[int],
    repos_map: dict[int, Repository] | None = None,
) -> JobSkillMatch:
    fields = requirement.model_dump()
    if not candidates:
        return JobSkillMatch(
            **fields, status="unknown", reason="Chưa có assessment kèm bằng chứng."
        )
    best, scope = max(candidates, key=lambda candidate: _rank(candidate[0]))
    meets_threshold, confidence, score = _rank(best)
    refs: dict[str, MatchEvidence] = {}
    for ref in sorted(
        best.evidence_refs, key=lambda ref: (ref.dedup_key, ref.evidence_id or "")
    ):
        if _usable_ref(ref, allowed) and ref.repository_id is not None:
            repo = (repos_map or {}).get(ref.repository_id)
            repo_full_name = repo.full_name or repo.name if repo else None
            repo_name = repo.name if repo else None
            commit_url = None
            if repo and ref.commit_sha:
                if getattr(repo, "html_url", None):
                    commit_url = f"{repo.html_url.rstrip('/')}/commit/{ref.commit_sha}"
                elif repo_full_name:
                    commit_url = (
                        f"https://github.com/{repo_full_name}/commit/{ref.commit_sha}"
                    )
            refs.setdefault(
                ref.dedup_key,
                MatchEvidence(
                    evidence_id=ref.evidence_id,
                    repository_id=ref.repository_id,
                    commit_sha=ref.commit_sha,
                    file_path=ref.file_path,
                    source_scope=scope,
                    repository_name=repo_name,
                    repository_full_name=repo_full_name,
                    commit_url=commit_url,
                ),
            )
    if meets_threshold:
        reason = "Điểm kỹ năng và độ tin cậy đạt ngưỡng đối chiếu."
    elif score < MATCH_SCORE and confidence < MATCH_CONFIDENCE:
        reason = "Điểm kỹ năng và độ tin cậy đều dưới ngưỡng đối chiếu."
    elif score < MATCH_SCORE:
        reason = "Có bằng chứng, nhưng điểm kỹ năng dưới ngưỡng đối chiếu."
    else:
        reason = "Có điểm kỹ năng, nhưng độ tin cậy dưới ngưỡng đối chiếu."
    return JobSkillMatch(
        **fields,
        status="matched" if meets_threshold else "partial",
        reason=reason,
        score=best.score,
        confidence=best.confidence,
        evidence=list(refs.values())[:5],
    )


def match_job(db: Session, user: User, request: JobMatchRequest) -> JobMatchResponse:
    guard = DbRepositoryAccessGuard(db, user)
    candidates = defaultdict(list)
    snapshots: list[str] = []
    limitations: list[str] = []
    stale = False
    allowed: set[int] = set()
    scopes: tuple[Literal["public", "private"], ...] = (
        ("public", "private") if request.scope == "combined" else (request.scope,)
    )
    for scope in scopes:
        # Legacy all/full reports cannot establish public provenance.
        report_scopes = ("public",) if scope == "public" else ("private", "all", "full")
        recent_report = (
            select(AnalysisReport.analyzed_at)
            .where(
                AnalysisReport.repository_id == Repository.id,
                AnalysisReport.scope.in_(report_scopes),
            )
            .order_by(AnalysisReport.analyzed_at.desc())
            .limit(1)
            .scalar_subquery()
        )
        repo_ids = db.scalars(
            select(Repository.id)
            .join(user_repository, Repository.id == user_repository.c.repository_id)
            .where(
                user_repository.c.user_id == user.id,
                Repository.private.is_(scope == "private"),
                recent_report.is_not(None),
            )
            .order_by(recent_report.desc(), Repository.id)
            .limit(MAX_REPOSITORIES + 1)
        ).all()
        if len(repo_ids) > MAX_REPOSITORIES:
            limitations.append(f"Chỉ đọc tối đa {MAX_REPOSITORIES} repo mỗi phạm vi.")
        repo_filter = {
            repo_id
            for repo_id in repo_ids[:MAX_REPOSITORIES]
            if guard.check(repo_id) == AccessDecision.ALLOWED
        }
        if not repo_filter:
            continue
        loaded = SkillSnapshotAdapter(
            DatabaseSkillSnapshotSource(
                db,
                repo_id_filter=frozenset(repo_filter),
                window=ReportWindow(),
                report_scope=report_scopes,
            )
        ).load(user.id, guard=guard)
        snapshot = loaded.snapshot
        if snapshot is None:
            continue
        current_ids = set(
            db.scalars(
                select(Repository.id).where(
                    Repository.id.in_(repo_filter),
                    Repository.private.is_(scope == "private"),
                )
            )
        )
        if not {int(repo_id) for repo_id in snapshot.repository_ids} <= current_ids:
            limitations.append("Quyền hoặc phạm vi repository đã thay đổi.")
            continue
        allowed.update(repo_filter)
        snapshots.append(snapshot.snapshot_ref)
        if len(snapshot.items) >= MAX_SNAPSHOT_ITEMS:
            limitations.append("Snapshot đạt giới hạn số bản ghi kỹ năng.")
        evidence_repos: set[int] = set()
        for item in snapshot.items:
            if _usable(item, repo_filter):
                candidates[_skill_key(item.skill_key)].append((item, scope))
                evidence_repos.update(
                    ref.repository_id
                    for ref in item.evidence_refs
                    if ref.repository_id is not None and _usable_ref(ref, repo_filter)
                )
        latest_by_repo = db.scalars(
            select(func.max(AnalysisReport.analyzed_at))
            .where(
                AnalysisReport.repository_id.in_(evidence_repos),
                AnalysisReport.scope.in_(report_scopes),
            )
            .group_by(AnalysisReport.repository_id)
        )
        cutoff = datetime.now(UTC) - STALE_AFTER
        stale |= any(timestamp < cutoff for timestamp in latest_by_repo)

    repos_map: dict[int, Repository] = {}
    if allowed:
        repos = db.scalars(select(Repository).where(Repository.id.in_(allowed))).all()
        repos_map = {r.id: r for r in repos}

    unique: dict[str, JobRequirement] = {}
    for item in request.skills:
        if item.skill_key not in unique or item.level == SkillRequirementLevel.REQUIRED:
            unique[item.skill_key] = item
    matches = [
        _match_skill(item, candidates[key], allowed, repos_map)
        for key, item in unique.items()
    ]
    required = [
        item for item in matches if item.level == SkillRequirementLevel.REQUIRED
    ]
    percent = None
    if required and any(item.status != "unknown" for item in required):
        percent = round(
            100 * sum(item.status == "matched" for item in required) / len(required)
        )
    if not snapshots:
        limitations.append("Chưa có snapshot phù hợp hoặc được phép sử dụng.")
    if "public" in scopes:
        limitations.append("Phạm vi công khai chỉ dùng báo cáo được ghi rõ là public.")
    return JobMatchResponse(
        scope=request.scope,
        skills=matches,
        required_matched_percent=percent,
        snapshot_refs=snapshots,
        stale_snapshot=stale,
        limitations=limitations,
    )
