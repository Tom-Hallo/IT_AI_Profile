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

from dataclasses import dataclass, field
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.scoring import (
    ArchitectureEvidenceSet,
    EvidenceRef,
    RoleRubric,
    RoleScoringEngine,
    RoleScoringInput,
    ScoreStatus,
    SkillSnapshotInput,
)
from app.ai.scoring.schemas import Limitation
from app.modules.analysis.models import AnalysisReport
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
        engine: RoleScoringEngine,
        architecture_provider: ArchitectureEvidencePort,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._guard = guard
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

        combined_result.limitations.extend(
            [
                *public_result.limitations,
                *private_result.limitations,
            ]
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
                .where(AnalysisReport.repository_id == Repository.id)
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
                    code="SCOPE_REPOSITORY_ACCESS_EXCLUDED",
                    message="Repo thiếu quyền hoặc consent đã được loại.",
                )
            )
        if len(allowed) > MAX_REPOSITORIES:
            limitations.append(
                Limitation(
                    code="SCOPE_REPOSITORY_LIMIT",
                    message=f"Tối đa {MAX_REPOSITORIES} repository mỗi scope.",
                )
            )
            allowed = allowed[:MAX_REPOSITORIES]
        if not allowed:
            limitations.append(
                Limitation(
                    code=f"SCOPE_{scope.upper()}_INSUFFICIENT",
                    message="Chưa có repository được phép với đủ bằng chứng.",
                )
            )
            return ScopeResult(scope, False, None, limitations)

        service = RoleScoringService(
            user_id=self._user_id,
            engine=self._engine,
            skill_adapter=SkillSnapshotAdapter(
                DatabaseSkillSnapshotSource(self._db, repo_id_filter=frozenset(allowed))
            ),
            architecture_provider=self._arch_provider,
            guard=self._guard,
        )
        outcome = service.score(
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
        by_key: dict[str, EvidenceRef] = {}
        for ref in pub_refs + priv_refs:
            previous = by_key.get(ref.dedup_key)
            if previous is None or (
                (not ref.verified, ref.confidence_score)
                < (not previous.verified, previous.confidence_score)
            ):
                by_key[ref.dedup_key] = ref
        combined_arch_refs = list(by_key.values())

        total_before = len(pub_refs) + len(priv_refs)
        duplicates_removed = total_before - len(combined_arch_refs)

        dedup_summary = DedupSummary(
            total_public_refs=len(pub_refs),
            total_private_refs=len(priv_refs),
            deduped_combined_refs=len(combined_arch_refs),
            duplicates_removed=duplicates_removed,
        )

        # Giữ các điểm có bộ bằng chứng khác nhau để engine áp dụng rubric.
        combined_skill = self._merge_skill_snapshots(pub_skill, priv_skill)

        if public_outcome is None and private_outcome is None:
            return (
                ScopeResult(
                    "combined",
                    False,
                    None,
                    [
                        Limitation(
                            code="SCOPE_COMBINED_NO_DATA",
                            message="Không có dữ liệu được phép để tính điểm Combined.",
                        )
                    ],
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

        rubric = self._engine.registry.get(role_key, rubric_version)
        result = self._engine.score(
            RoleScoringInput(
                role_key=rubric.role_key,
                skill_snapshot=combined_skill,
                architecture=arch_set,
            ),
            rubric_version=rubric.rubric_version,
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
                    message="Combined chỉ dùng phạm vi Riêng tư đang khả dụng.",
                )
            )
        elif private_outcome is None and public_outcome is not None:
            limitations.append(
                Limitation(
                    code="COMBINED_PRIVATE_SCOPE_UNAVAILABLE",
                    message="Combined chỉ dùng phạm vi Công khai đang khả dụng.",
                )
            )
        seen = {(item.code, item.message) for item in result.limitations}
        for item in [
            *limitations,
            *(
                item
                for outcome in (public_outcome, private_outcome)
                if outcome
                for item in outcome.result.limitations
            ),
        ]:
            key = (item.code, item.message)
            if key not in seen:
                result.limitations.append(item)
                seen.add(key)

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
        """Deduplicate identical inputs and retain distinct evidence."""
        snapshots = [snapshot for snapshot in (pub, priv) if snapshot is not None]
        if not snapshots:
            return None

        items = []
        seen = set()
        for snapshot in snapshots:
            for item in snapshot.items:
                evidence = frozenset(ref.dedup_key for ref in item.evidence_refs)
                key = (item.skill_key, evidence)
                if evidence and key in seen:
                    continue
                seen.add(key)
                items.append(item)

        refs = "|".join(snapshot.snapshot_ref for snapshot in snapshots)
        return SkillSnapshotInput(
            snapshot_ref="combined_" + sha256(refs.encode()).hexdigest()[:24],
            status=snapshots[0].status,
            repository_ids=sorted(
                {repo for snapshot in snapshots for repo in snapshot.repository_ids}
            ),
            items=items,
        )
