"""Adapter nhận Skill Score từ PBI-016 (PBI-017).

PBI-016 chưa xác nhận contract, nên module này KHÔNG import model/bảng/service nào của
PBI-016 và KHÔNG tự tính điểm kỹ năng. Nó chỉ định nghĩa:

* ``SkillSnapshotSource`` — cổng (Protocol) mà PBI-016 sẽ hiện thực. Trả về
  ``RawSkillSnapshot`` (chủ sở hữu + payload) hoặc ``None`` nếu chưa có snapshot.
* ``SkillSnapshotAdapter`` — gọi nguồn, kiểm tra chủ sở hữu, validate payload sang
  ``SkillSnapshotInput`` của engine, kiểm tra phạm vi repository qua guard
  authorization/consent, rồi trả ``SkillSnapshotResult`` với trạng thái rõ ràng.

Khi PBI-016 được push: chỉ cần viết một lớp thoả ``SkillSnapshotSource`` (hoặc truyền
``mapper`` để đổi payload của 016 sang dict của ``SkillSnapshotInput``) và đổi
dependency ``get_skill_snapshot_source`` — engine và service không đổi.

Không bao giờ giả lập snapshot: thiếu/không hợp lệ/không được phép → ``snapshot=None``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from pydantic import ValidationError

from app.ai.scoring import ScoreStatus, SkillSnapshotInput
from app.ai.scoring.schemas import Limitation
from app.modules.role_scoring.access import AccessDecision, RepositoryAccessGuard
from app.modules.role_scoring.errors import (
    SkillSnapshotSourceError,
    SkillSnapshotSourceNotConfigured,
)

logger = logging.getLogger(__name__)

MAX_SNAPSHOT_ITEMS = 500
MAX_REPOSITORIES_PER_SNAPSHOT = 200


class SkillSnapshotStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"  # PBI-016 chưa có snapshot cho người dùng
    NOT_CONFIGURED = "NOT_CONFIGURED"  # PBI-016 chưa được nối
    INVALID = "INVALID"  # payload sai contract
    FORBIDDEN = "FORBIDDEN"  # sai chủ sở hữu / tham chiếu repo không được phép


@dataclass(frozen=True)
class RawSkillSnapshot:
    """Gói do nguồn PBI-016 trả về.

    ``owner_user_id`` bắt buộc để adapter xác nhận data isolation (defense in depth,
    ngoài việc nguồn đã lọc theo ``user_id``).
    ``payload`` là ``SkillSnapshotInput`` hoặc mapping có đúng trường của nó.
    """

    owner_user_id: int
    payload: SkillSnapshotInput | Mapping[str, Any]


class SkillSnapshotSource(Protocol):
    """Cổng PBI-016 sẽ hiện thực. Phải lọc theo ``user_id``."""

    def fetch(
        self, user_id: int, *, snapshot_ref: str | None = None
    ) -> RawSkillSnapshot | None:
        """Snapshot mới nhất (hoặc đúng ``snapshot_ref``); None nếu chưa có."""
        ...


class UnconfiguredSkillSnapshotSource:
    """Mặc định khi PBI-016 chưa nối: báo NOT_CONFIGURED, không bịa dữ liệu."""

    def fetch(
        self, user_id: int, *, snapshot_ref: str | None = None
    ) -> RawSkillSnapshot | None:
        raise SkillSnapshotSourceNotConfigured("PBI-016 skill source not configured")


@dataclass(frozen=True)
class SkillSnapshotResult:
    status: SkillSnapshotStatus
    snapshot: SkillSnapshotInput | None = None
    issues: list[Limitation] = field(default_factory=list)


Mapper = Callable[[Any], SkillSnapshotInput | Mapping[str, Any]]


def _issue(code: str, message: str) -> Limitation:
    return Limitation(code=code, message=message)


def _safe_validation_summary(exc: ValidationError) -> str:
    """Chỉ nêu vị trí/loại lỗi, KHÔNG chép giá trị đầu vào (tránh lộ dữ liệu)."""
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or '<root>'}: {err['type']}"
        for err in exc.errors(include_input=False, include_url=False)[:10]
    ]
    return "; ".join(parts)


class SkillSnapshotAdapter:
    def __init__(
        self,
        source: SkillSnapshotSource,
        *,
        mapper: Mapper | None = None,
    ) -> None:
        self._source = source
        self._mapper = mapper

    def load(
        self,
        user_id: int,
        *,
        snapshot_ref: str | None = None,
        guard: RepositoryAccessGuard | None = None,
    ) -> SkillSnapshotResult:
        try:
            raw = self._source.fetch(user_id, snapshot_ref=snapshot_ref)
        except SkillSnapshotSourceNotConfigured:
            return SkillSnapshotResult(
                SkillSnapshotStatus.NOT_CONFIGURED,
                issues=[
                    _issue(
                        "SKILL_SNAPSHOT_SOURCE_NOT_CONFIGURED",
                        "Nguồn skill snapshot (PBI-016) chưa được cấu hình.",
                    )
                ],
            )
        except Exception as exc:  # lỗi hạ tầng ≠ thiếu dữ liệu: không che giấu
            logger.error("Skill snapshot source failed: %s", type(exc).__name__)
            raise SkillSnapshotSourceError("skill snapshot source failed") from exc

        if raw is None:
            return SkillSnapshotResult(
                SkillSnapshotStatus.MISSING,
                issues=[
                    _issue(
                        "SKILL_SNAPSHOT_MISSING",
                        "Chưa có skill snapshot từ PBI-016 cho người dùng.",
                    )
                ],
            )

        if raw.owner_user_id != user_id:
            logger.warning("Skill snapshot owner mismatch rejected")
            return SkillSnapshotResult(
                SkillSnapshotStatus.FORBIDDEN,
                issues=[
                    _issue(
                        "SKILL_SNAPSHOT_OWNER_MISMATCH",
                        "Skill snapshot không thuộc người dùng hiện tại; đã bỏ qua.",
                    )
                ],
            )

        snapshot, error = self._validate(raw.payload)
        if snapshot is None:
            return SkillSnapshotResult(
                SkillSnapshotStatus.INVALID,
                issues=[_issue("SKILL_SNAPSHOT_INVALID", error or "payload invalid")],
            )

        if snapshot_ref and snapshot.snapshot_ref != snapshot_ref:
            return SkillSnapshotResult(
                SkillSnapshotStatus.INVALID,
                issues=[
                    _issue(
                        "SKILL_SNAPSHOT_REF_MISMATCH",
                        "snapshot_ref trả về khác snapshot_ref được yêu cầu.",
                    )
                ],
            )

        scope_result = self._check_scope(snapshot, guard)
        if scope_result is not None:
            return scope_result

        return SkillSnapshotResult(
            SkillSnapshotStatus.AVAILABLE, snapshot, self._warnings(snapshot)
        )

    # ------------------------------------------------------------------ internals

    def _validate(
        self, payload: SkillSnapshotInput | Mapping[str, Any]
    ) -> tuple[SkillSnapshotInput | None, str | None]:
        try:
            data = self._mapper(payload) if self._mapper else payload
            if isinstance(data, SkillSnapshotInput):
                # Dựng lại để chạy validator, kể cả khi model được tạo bằng construct().
                data = data.model_dump()
            snapshot = SkillSnapshotInput.model_validate(data)
        except ValidationError as exc:
            return None, _safe_validation_summary(exc)
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            return None, f"mapper/payload error: {type(exc).__name__}"
        if len(snapshot.items) > MAX_SNAPSHOT_ITEMS:
            return None, f"items exceeds {MAX_SNAPSHOT_ITEMS}"
        if len(snapshot.repository_ids) > MAX_REPOSITORIES_PER_SNAPSHOT:
            return None, f"repository_ids exceeds {MAX_REPOSITORIES_PER_SNAPSHOT}"
        return snapshot, None

    @staticmethod
    def _referenced_repository_ids(
        snapshot: SkillSnapshotInput,
    ) -> tuple[set[int], bool]:
        """Trả (tập repo id, có id không phân giải được)."""
        ids: set[int] = set()
        unresolvable = False
        for raw_id in snapshot.repository_ids:
            try:
                ids.add(int(raw_id))
            except (TypeError, ValueError):
                unresolvable = True
        for item in snapshot.items:
            for ref in item.evidence_refs:
                if ref.repository_id is not None:
                    ids.add(ref.repository_id)
        return ids, unresolvable

    def _check_scope(
        self, snapshot: SkillSnapshotInput, guard: RepositoryAccessGuard | None
    ) -> SkillSnapshotResult | None:
        repo_ids, unresolvable = self._referenced_repository_ids(snapshot)
        if unresolvable:
            return SkillSnapshotResult(
                SkillSnapshotStatus.INVALID,
                issues=[
                    _issue(
                        "SKILL_SNAPSHOT_REPOSITORY_ID_UNRESOLVABLE",
                        "repository_ids của snapshot phải là số nguyên.",
                    )
                ],
            )
        if repo_ids and guard is None:
            # Fail-closed: có tham chiếu repo mà không có guard để kiểm tra.
            return SkillSnapshotResult(
                SkillSnapshotStatus.FORBIDDEN,
                issues=[
                    _issue(
                        "SKILL_SNAPSHOT_SCOPE_UNVERIFIABLE",
                        "Không thể xác minh quyền truy cập repository của snapshot.",
                    )
                ],
            )
        for repo_id in sorted(repo_ids):
            if guard is None or guard.check(repo_id) != AccessDecision.ALLOWED:
                return SkillSnapshotResult(
                    SkillSnapshotStatus.FORBIDDEN,
                    issues=[
                        _issue(
                            "SKILL_SNAPSHOT_REFERENCES_INACCESSIBLE_REPOSITORY",
                            "Snapshot tham chiếu repository không còn được phép dùng "
                            "(không thuộc người dùng hoặc thiếu/thu hồi consent); "
                            "toàn bộ snapshot bị loại.",
                        )
                    ],
                )
        return None

    @staticmethod
    def _warnings(snapshot: SkillSnapshotInput) -> list[Limitation]:
        warnings: list[Limitation] = []
        if not snapshot.items:
            warnings.append(
                _issue(
                    "SKILL_SNAPSHOT_HAS_NO_ITEMS", "Skill snapshot không có item nào."
                )
            )
        no_evidence = sorted(
            {
                item.skill_key
                for item in snapshot.items
                if item.status == ScoreStatus.SCORED and not item.evidence_refs
            }
        )
        if no_evidence:
            warnings.append(
                _issue(
                    "SKILL_ITEM_WITHOUT_EVIDENCE",
                    "Skill có điểm nhưng thiếu evidence reference "
                    f"(không đủ để chấm tiêu chí): {', '.join(no_evidence)}.",
                )
            )
        return warnings
