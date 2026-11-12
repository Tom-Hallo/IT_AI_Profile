"""Service tính điểm role theo 3 scope: Public / Private / Combined (PBI-018).

Mỗi scope được tính độc lập bằng ``RoleScoringService.score()`` với bộ
repository được lọc theo ``Repository.private``.

**Dedup combined**: combined KHÔNG cộng điểm public + private. Engine chạy lại
từ đầu với bộ evidence đã dedup bằng ``EvidenceRef.dedup_key`` — bảo đảm rằng
cùng một file/commit không được đếm 2 lần dù xuất hiện ở cả public lẫn private
(ví dụ: fork hoặc mirror).

Quy tắc consent:
- Public scope: chỉ repo ``private=False``.
- Private scope: chỉ repo ``private=True``.
- Combined: tất cả repo hợp lệ; dedup evidence sau đó chạy engine một lần.
- Repo private thiếu consent → bị bỏ qua (``PRIVATE_REPOSITORY_SKIPPED`` ở
  architecture provider), không làm fail toàn request.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.scoring import (
    ArchitectureEvidenceSet,
    EvidenceRef,
    RoleRubric,
    RoleScoreResult,
    RoleScoringEngine,
    RoleScoringInput,
    ScoreStatus,
    SkillSnapshotInput,
)
from app.ai.scoring.schemas import Limitation
from app.modules.analysis.models import AnalysisReport
from app.modules.analysis.report_window import ReportWindow
from app.modules.github.models import Repository, user_repository
from app.modules.role_scoring.access import AccessDecision, RepositoryAccessGuard
from app.modules.role_scoring.architecture_provider import (
    MAX_REPOSITORIES,
    ArchitectureEvidencePort,
    ArchitectureEvidenceResult,
    ArchitectureStatus,
)
from app.modules.role_scoring.service import (
    RoleScoringOutcome,
    RoleScoringRequest,
    RoleScoringService,
)
from app.modules.role_scoring.skill_adapter import (
    DatabaseSkillSnapshotSource,
    SkillSnapshotAdapter,
    SkillSnapshotResult,
    SkillSnapshotStatus,
)

logger = logging.getLogger(__name__)

Scope = str  # "public" | "private" | "combined"


@dataclass(frozen=True)
class DedupSummary:
    total_public_refs: int
    total_private_refs: int
    deduped_combined_refs: int
    duplicates_removed: int


@dataclass(frozen=True)
class ScopeResult:
    """Kết quả của một scope đơn.

    ``available=False``: scope này không có repo nào (ví dụ user không có
    private repo) → ``outcome=None``.
    """

    scope: Scope
    available: bool
    outcome: RoleScoringOutcome | None
    limitations: list[Limitation] = field(default_factory=list)


@dataclass(frozen=True)
class ScopedScoringOutcome:
    rubric: RoleRubric
    public: ScopeResult
    private: ScopeResult
    combined: ScopeResult
    dedup_summary: DedupSummary


class ScopedRoleScoringService:
    """Tính điểm role cho 3 scope Public / Private / Combined.

    Khởi tạo với cùng ``db``, ``user_id`` và các dependency như
    ``RoleScoringService``, nhưng tự resolve repo IDs theo scope.
    """

    def __init__(
        self,
        *,
        db: Session,
        user_id: int,
        guard: RepositoryAccessGuard,
        window: ReportWindow,
        engine: RoleScoringEngine,
        architecture_provider: ArchitectureEvidencePort,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._guard = guard
        self._window = window
        self._engine = engine
        self._arch_provider = architecture_provider

    # ------------------------------------------------------------------ public

    def score_all_scopes(
        self,
        role_key: str,
        *,
        rubric_version: str | None = None,
    ) -> ScopedScoringOutcome:
        rubric = self._engine.registry.get(role_key, rubric_version)

        public_ids = self._repo_ids_by_visibility(private=False)
        private_ids = self._repo_ids_by_visibility(private=True)

        public_result = self._score_scope(
            "public",
            role_key=role_key,
            rubric_version=rubric_version,
            repo_ids=public_ids,
        )
        private_result = self._score_scope(
            "private",
            role_key=role_key,
            rubric_version=rubric_version,
            repo_ids=private_ids,
        )
        combined_result, dedup = self._score_combined(
            role_key=role_key,
            rubric_version=rubric_version,
            public_outcome=public_result.outcome,
            private_outcome=private_result.outcome,
        )

        return ScopedScoringOutcome(
            rubric=rubric,
            public=public_result,
            private=private_result,
            combined=combined_result,
            dedup_summary=dedup,
        )

    # --------------------------------------------------------------- internals

    def _repo_ids_by_visibility(self, *, private: bool) -> list[int]:
        """Trả danh sách repository_id của user theo visibility."""
        rows = self._db.scalars(
            select(user_repository.c.repository_id)
            .join(
                Repository,
                Repository.id == user_repository.c.repository_id,
            )
            .where(
                user_repository.c.user_id == self._user_id,
                Repository.private == private,
            )
            .order_by(
                select(AnalysisReport.analyzed_at)
                .where(
                    AnalysisReport.repository_id == Repository.id,
                    *self._window.conditions(AnalysisReport.analyzed_at),
                )
                .order_by(AnalysisReport.analyzed_at.desc())
                .limit(1)
                .scalar_subquery()
                .desc()
                .nulls_last(),
                user_repository.c.repository_id,
            )
        ).all()
        return [int(r) for r in rows]

    def _score_scope(
        self,
        scope: Scope,
        *,
        role_key: str,
        rubric_version: str | None,
        repo_ids: list[int],
    ) -> ScopeResult:
        allowed = [
            repo_id
            for repo_id in repo_ids
            if self._guard.check(repo_id) == AccessDecision.ALLOWED
        ]
        limitations = []
        if len(allowed) < len(repo_ids):
            limitations.append(
                Limitation(
                    code="SCOPE_ACCESS_FILTERED",
                    message="Đã loại repository thiếu quyền hoặc consent.",
                )
            )
        if len(allowed) > MAX_REPOSITORIES:
            limitations.append(
                Limitation(
                    code="SCOPE_REPOSITORY_LIMIT",
                    message=f"Tối đa {MAX_REPOSITORIES} repository mỗi phạm vi.",
                )
            )
            allowed = allowed[:MAX_REPOSITORIES]
        if not allowed:
            return ScopeResult(
                scope=scope,
                available=False,
                outcome=None,
                limitations=[
                    *limitations,
                    Limitation(
                        code=f"SCOPE_{scope.upper()}_NO_REPOSITORIES",
                        message=(
                            f"Không có repository {scope} nào thuộc người dùng "
                            "này; scope không khả dụng."
                        ),
                    ),
                ],
            )

        # DatabaseSkillSnapshotSource với filter repo
        scoped_source = DatabaseSkillSnapshotSource(
            self._db,
            repo_id_filter=frozenset(allowed),
            window=self._window,
        )
        adapter = SkillSnapshotAdapter(scoped_source)

        scoped_service = RoleScoringService(
            user_id=self._user_id,
            engine=self._engine,
            skill_adapter=adapter,
            architecture_provider=self._arch_provider,
            guard=self._guard,
        )

        outcome = scoped_service.score(
            RoleScoringRequest(
                role_key=role_key,
                repository_ids=allowed,
                rubric_version=rubric_version,
            )
        )
        if outcome.result.status == ScoreStatus.UNKNOWN:
            outcome.result.status = ScoreStatus.INSUFFICIENT
        return ScopeResult(scope, True, outcome, limitations)

    def _score_combined(
        self,
        *,
        role_key: str,
        rubric_version: str | None,
        public_outcome: RoleScoringOutcome | None,
        private_outcome: RoleScoringOutcome | None,
    ) -> tuple[ScopeResult, DedupSummary]:
        """Tính combined bằng cách dedup evidence từ cả 2 scope rồi chạy engine."""
        pub_refs: list[EvidenceRef] = []
        priv_refs: list[EvidenceRef] = []
        pub_skill: SkillSnapshotInput | None = None
        priv_skill: SkillSnapshotInput | None = None

        if public_outcome is not None:
            arch_set = public_outcome.architecture.evidence_set
            if arch_set:
                pub_refs = list(arch_set.evidence)
            snap = public_outcome.skill.snapshot
            if snap:
                pub_skill = snap

        if private_outcome is not None:
            arch_set = private_outcome.architecture.evidence_set
            if arch_set:
                priv_refs = list(arch_set.evidence)
            snap = private_outcome.skill.snapshot
            if snap:
                priv_skill = snap

        # Dedup architecture evidence
        seen_keys: set[str] = set()
        combined_arch_refs: list[EvidenceRef] = []
        for ref in pub_refs + priv_refs:
            k = ref.dedup_key
            if k not in seen_keys:
                seen_keys.add(k)
                combined_arch_refs.append(ref)

        total_before = len(pub_refs) + len(priv_refs)
        duplicates_removed = total_before - len(combined_arch_refs)

        dedup_summary = DedupSummary(
            total_public_refs=len(pub_refs),
            total_private_refs=len(priv_refs),
            deduped_combined_refs=len(combined_arch_refs),
            duplicates_removed=duplicates_removed,
        )

        # Merge skill snapshot (dedup theo skill_key: giữ item có score cao hơn)
        combined_skill = self._merge_skill_snapshots(pub_skill, priv_skill)

        # Nếu không có dữ liệu gì → không khả dụng
        if combined_skill is None and not combined_arch_refs:
            limitations = [
                Limitation(
                    code="SCOPE_COMBINED_NO_DATA",
                    message="Không có dữ liệu nào để tính combined score.",
                )
            ]
            if public_outcome is None and private_outcome is None:
                return (
                    ScopeResult(
                        scope="combined",
                        available=False,
                        outcome=None,
                        limitations=limitations,
                    ),
                    dedup_summary,
                )

        # Xây ArchitectureEvidenceSet tổng hợp
        arch_set: ArchitectureEvidenceSet | None = None
        if combined_arch_refs:
            # Dùng report_ref tổng hợp từ cả 2 scope
            pub_ref = (
                public_outcome.architecture.evidence_set.report_ref
                if public_outcome and public_outcome.architecture.evidence_set
                else None
            )
            priv_ref = (
                private_outcome.architecture.evidence_set.report_ref
                if private_outcome and private_outcome.architecture.evidence_set
                else None
            )
            refs_parts = [r for r in [pub_ref, priv_ref] if r]
            combined_report_ref = (
                "combined:" + "|".join(refs_parts) if refs_parts else "combined"
            )

            # Repository IDs từ cả 2 scope
            all_repo_ids: list[str] = []
            seen_repo: set[str] = set()
            for outcome in [public_outcome, private_outcome]:
                if outcome and outcome.architecture.evidence_set:
                    for rid in outcome.architecture.evidence_set.repository_ids:
                        if rid not in seen_repo:
                            seen_repo.add(rid)
                            all_repo_ids.append(rid)

            arch_set = ArchitectureEvidenceSet(
                report_ref=combined_report_ref,
                repository_scope="combined",
                repository_ids=all_repo_ids,
                evidence=combined_arch_refs,
            )

        # Chạy engine với data đã dedup
        try:
            rubric = self._engine.registry.get(role_key, rubric_version)
            scoring_input = RoleScoringInput(
                role_key=rubric.role_key,
                skill_snapshot=combined_skill,
                architecture=arch_set,
            )
            result: RoleScoreResult = self._engine.score(
                scoring_input,
                rubric_version=rubric.rubric_version,
            )
        except Exception:
            logger.exception("Lỗi khi tính combined score")
            return (
                ScopeResult(
                    scope="combined",
                    available=False,
                    outcome=None,
                    limitations=[
                        Limitation(
                            code="SCOPE_COMBINED_SCORING_FAILED",
                            message="Tính điểm combined thất bại.",
                        )
                    ],
                ),
                dedup_summary,
            )

        if result.status == ScoreStatus.UNKNOWN:
            result.status = ScoreStatus.INSUFFICIENT

        # Thêm limitation nếu chỉ 1 scope khả dụng
        limitations: list[Limitation] = []
        if duplicates_removed > 0:
            limitations.append(
                Limitation(
                    code="COMBINED_DEDUP_APPLIED",
                    message=(
                        f"Đã loại {duplicates_removed} evidence trùng lặp giữa "
                        "public và private scope (cùng commit/file)."
                    ),
                )
            )
        if public_outcome is None and private_outcome is not None:
            limitations.append(
                Limitation(
                    code="COMBINED_PUBLIC_SCOPE_UNAVAILABLE",
                    message="Combined chỉ dùng private scope (không có public repo).",
                )
            )
        elif private_outcome is None and public_outcome is not None:
            limitations.append(
                Limitation(
                    code="COMBINED_PRIVATE_SCOPE_UNAVAILABLE",
                    message="Combined chỉ dùng public scope (không có private repo).",
                )
            )
        result.limitations.extend(limitations)

        # Dựng ArchitectureEvidenceResult tổng hợp cho outcome

        combined_arch_result = ArchitectureEvidenceResult(
            status=(
                ArchitectureStatus.AVAILABLE
                if arch_set
                else ArchitectureStatus.NOT_ANALYZED
            ),
            evidence_set=arch_set,
        )

        # SkillSnapshotResult tổng hợp
        combined_skill_result = SkillSnapshotResult(
            status=(
                SkillSnapshotStatus.AVAILABLE
                if combined_skill
                else SkillSnapshotStatus.MISSING
            ),
            snapshot=combined_skill,
        )

        combined_outcome = RoleScoringOutcome(
            result=result,
            rubric=rubric,
            skill=combined_skill_result,
            architecture=combined_arch_result,
        )

        return (
            ScopeResult(scope="combined", available=True, outcome=combined_outcome),
            dedup_summary,
        )

    @staticmethod
    def _merge_skill_snapshots(
        pub: SkillSnapshotInput | None,
        priv: SkillSnapshotInput | None,
    ) -> SkillSnapshotInput | None:
        """Gộp 2 skill snapshots; với cùng skill_key, giữ item có score cao hơn."""
        if pub is None and priv is None:
            return None

        from app.ai.scoring.schemas import SkillScoreItem

        all_items: dict[str, SkillScoreItem] = {}

        for snap in [pub, priv]:
            if snap is None:
                continue
            for item in snap.items:
                existing = all_items.get(item.skill_key)
                if existing is None:
                    all_items[item.skill_key] = item
                else:
                    # Giữ item có điểm cao hơn; nếu bằng thì giữ item đã có
                    new_score = item.score if item.score is not None else -1.0
                    old_score = existing.score if existing.score is not None else -1.0
                    if new_score > old_score:
                        all_items[item.skill_key] = item

        if not all_items:
            return None

        # Gộp repository_ids từ cả 2 snapshot
        repo_ids: list[str] = []
        seen: set[str] = set()
        for snap in [pub, priv]:
            if snap is None:
                continue
            for rid in snap.repository_ids:
                if rid not in seen:
                    seen.add(rid)
                    repo_ids.append(rid)

        # Lấy context từ snap nào có dữ liệu
        base = pub or priv
        assert base is not None

        return SkillSnapshotInput(
            snapshot_ref=f"combined_{base.snapshot_ref}",
            status=base.status,
            repository_ids=repo_ids,
            items=list(all_items.values()),
        )
