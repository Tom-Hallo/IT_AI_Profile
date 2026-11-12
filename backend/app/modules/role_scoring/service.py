"""Application service điều phối Role Scoring (PBI-017).

Thứ tự (có chủ đích):
1. Kiểm tra rubric/role.
2. Lấy architecture evidence — bước này xác thực quyền + consent các repository được
   chỉ định, nên request không được phép dừng TRƯỚC khi chạm tới nguồn PBI-016.
3. Lấy skill snapshot qua adapter (có kiểm tra chủ sở hữu + phạm vi repository).
4. Gọi ``RoleScoringEngine`` (không sao chép logic chấm điểm).
5. Gắn thêm giới hạn nguồn dữ liệu vào kết quả, giữ nguyên reference/metadata.

Service không ghi DB: persistence bị tách riêng vì schema snapshot PBI-016 chưa
xác nhận.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.ai.scoring import (
    RoleRubric,
    RoleScoreResult,
    RoleScoringEngine,
    RoleScoringInput,
)
from app.ai.scoring.schemas import Limitation
from app.modules.role_scoring.access import RepositoryAccessGuard
from app.modules.role_scoring.architecture_provider import (
    ArchitectureEvidencePort,
    ArchitectureEvidenceResult,
)
from app.modules.role_scoring.skill_adapter import (
    SkillSnapshotAdapter,
    SkillSnapshotResult,
)


@dataclass(frozen=True)
class RoleScoringRequest:
    role_key: str
    repository_ids: Sequence[int] | None = None
    snapshot_ref: str | None = None
    rubric_version: str | None = None


@dataclass(frozen=True)
class RoleScoringOutcome:
    result: RoleScoreResult
    rubric: RoleRubric
    skill: SkillSnapshotResult
    architecture: ArchitectureEvidenceResult


class RoleScoringService:
    def __init__(
        self,
        *,
        user_id: int,
        engine: RoleScoringEngine,
        skill_adapter: SkillSnapshotAdapter,
        architecture_provider: ArchitectureEvidencePort,
        guard: RepositoryAccessGuard,
    ) -> None:
        self._user_id = user_id
        self._engine = engine
        self._skills = skill_adapter
        self._architecture = architecture_provider
        self._guard = guard

    def list_rubrics(self) -> list[RoleRubric]:
        registry = self._engine.registry
        return [registry.get(role) for role in registry.roles()]

    def score(self, request: RoleScoringRequest) -> RoleScoringOutcome:
        rubric = self._engine.registry.get(request.role_key, request.rubric_version)

        architecture = self._architecture.get(request.repository_ids)
        skill = self._skills.load(
            self._user_id,
            snapshot_ref=request.snapshot_ref,
            guard=self._guard,
        )

        result = self._engine.score(
            RoleScoringInput(
                role_key=rubric.role_key,
                skill_snapshot=skill.snapshot,
                architecture=architecture.evidence_set,
            ),
            rubric_version=rubric.rubric_version,
        )
        self._merge_limitations(result, skill, architecture, request)
        return RoleScoringOutcome(result, rubric, skill, architecture)

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _merge_limitations(
        result: RoleScoreResult,
        skill: SkillSnapshotResult,
        architecture: ArchitectureEvidenceResult,
        request: RoleScoringRequest,
    ) -> None:
        extra: list[Limitation] = [*skill.issues, *architecture.limitations]

        snapshot = skill.snapshot
        if snapshot is not None and snapshot.repository_ids:
            skill_repos = set()
            for raw in snapshot.repository_ids:
                try:
                    skill_repos.add(int(raw))
                except (TypeError, ValueError):
                    continue
            arch_repos = architecture.repository_ids
            if skill_repos and arch_repos and skill_repos != arch_repos:
                extra.append(
                    Limitation(
                        code="REPOSITORY_SET_MISMATCH",
                        message=(
                            "Tập repository của skill snapshot khác tập repository "
                            "dùng cho bằng chứng kiến trúc; kết quả có thể không "
                            "đồng nhất."
                        ),
                    )
                )

        seen = {(item.code, item.message) for item in result.limitations}
        for item in extra:
            if (item.code, item.message) not in seen:
                result.limitations.append(item)
                seen.add((item.code, item.message))
