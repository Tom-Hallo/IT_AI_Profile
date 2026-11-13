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
from hashlib import sha256
from statistics import fmean
from typing import Any, Protocol

from pydantic import ValidationError
from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.ai.scoring import (
    EvidenceRef,
    ScoreStatus,
    SkillScoreItem,
    SkillSnapshotInput,
    SnapshotStatus,
)
from app.ai.scoring.evidence_catalog import normalize_key
from app.ai.scoring.schemas import Limitation
from app.modules.analysis.models import (
    AnalysisEvidence,
    AnalysisReport,
    RepositoryVerification,
    VerificationEvidence,
)
from app.modules.analysis.report_window import ReportWindow
from app.modules.role_scoring.access import AccessDecision, RepositoryAccessGuard
from app.modules.role_scoring.errors import (
    SkillSnapshotSourceError,
    SkillSnapshotSourceNotConfigured,
)
from app.modules.scoring.models import ScoreEvidenceLink, SkillScore

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


class DatabaseSkillSnapshotSource:
    """Nguồn đọc Skill Scores thực tế từ bảng ita.skill_scores của PBI-016.

    ``repo_id_filter``: nếu được cung cấp, chỉ lấy scores từ các repository có
    id trong tập này (dùng cho scope public/private của PBI-018). ``None`` = không lọc.
    """

    def __init__(
        self,
        db: Session,
        *,
        repo_id_filter: frozenset[int] | None = None,
        window: ReportWindow | None = None,
    ) -> None:
        self._db = db
        self._repo_id_filter = repo_id_filter
        self._window = window

    def fetch(
        self, user_id: int, *, snapshot_ref: str | None = None
    ) -> RawSkillSnapshot | None:
        try:
            query = (
                select(SkillScore)
                .where(SkillScore.user_id == user_id)
                .order_by(desc(SkillScore.created_at), desc(SkillScore.id))
                .limit(MAX_SNAPSHOT_ITEMS)
            )
            if self._repo_id_filter is not None:
                query = query.where(SkillScore.repository_id.in_(self._repo_id_filter))
            if self._window is not None:
                latest_report_id = (
                    select(AnalysisReport.id)
                    .where(
                        AnalysisReport.repository_id == SkillScore.repository_id,
                        *self._window.conditions(AnalysisReport.analyzed_at),
                    )
                    .order_by(
                        AnalysisReport.analyzed_at.desc(), AnalysisReport.id.desc()
                    )
                    .limit(1)
                    .correlate(SkillScore)
                    .scalar_subquery()
                )
                query = query.where(SkillScore.report_id == latest_report_id)
            scores = self._db.scalars(query).all()
            if not scores:
                return None

            score_ids = [s.id for s in scores]
            evidence_by_score: dict[int, list[EvidenceRef]] = {}
            if score_ids:
                links = (
                    select(ScoreEvidenceLink.score_id, AnalysisEvidence)
                    .join(
                        AnalysisEvidence,
                        ScoreEvidenceLink.evidence_id == AnalysisEvidence.id,
                    )
                    .where(ScoreEvidenceLink.score_id.in_(score_ids))
                )
                if self._repo_id_filter is not None:
                    links = links.join(
                        SkillScore,
                        and_(
                            SkillScore.id == ScoreEvidenceLink.score_id,
                            SkillScore.repository_id == AnalysisEvidence.repository_id,
                            SkillScore.report_id == AnalysisEvidence.report_id,
                            SkillScore.commit_sha == AnalysisEvidence.commit_sha,
                        ),
                    )
                for sid, ev in self._db.execute(links).all():
                    evidence_by_score.setdefault(sid, []).append(
                        EvidenceRef.from_record(ev)
                    )

            contributions = (
                self._verification_refs(scores, user_id)
                if self._repo_id_filter is not None
                else {}
            )
            items: list[SkillScoreItem] = []
            repo_ids: set[str] = set()

            for s in scores:
                if s.repository_id:
                    repo_ids.add(str(s.repository_id))

                raw_status = (s.status or "").strip().lower()
                if raw_status == "scored" and s.score is not None:
                    status = ScoreStatus.SCORED
                    score_val = float(s.score)
                    confidence_val = float(s.score)
                elif raw_status == "insufficient":
                    status = ScoreStatus.INSUFFICIENT
                    score_val = None
                    confidence_val = None
                else:
                    status = ScoreStatus.UNKNOWN
                    score_val = None
                    confidence_val = None

                refs = evidence_by_score.get(s.id, [])
                if self._repo_id_filter is not None and status == ScoreStatus.SCORED:
                    verified_refs, verified_confidence = contributions.get(
                        s.id, ([], None)
                    )
                    refs = [*refs, *verified_refs]
                    # Derive confidence from distinct evidence references.
                    confidence_by_ref: dict[str, float] = {}
                    for ref in refs:
                        key = ref.dedup_key
                        confidence_by_ref[key] = min(
                            confidence_by_ref.get(key, 1.0), ref.confidence_score
                        )
                    confidence_val = (
                        100 * fmean(confidence_by_ref.values())
                        if confidence_by_ref
                        else None
                    )
                    if verified_confidence is not None:
                        confidence_val = verified_confidence
                    if not refs:
                        status = ScoreStatus.INSUFFICIENT
                        score_val = None
                elif not refs and status == ScoreStatus.SCORED:
                    refs = [
                        EvidenceRef(
                            evidence_id=f"skill_score_{s.id}",
                            repository_id=s.repository_id,
                            commit_sha=s.commit_sha,
                            file_path=f"skills/{s.technology}",
                            finding_type="skill",
                            classification=s.technology,
                            confidence_score=1.0,
                            verified=True,
                            rationale=s.explanation,
                        )
                    ]

                items.append(
                    SkillScoreItem(
                        skill_key=normalize_key(s.technology),
                        score=score_val,
                        confidence=confidence_val,
                        status=status,
                        evidence_refs=refs,
                        rationale=s.explanation,
                    )
                )

            actual_ref = snapshot_ref or f"pbi016_user_{user_id}"
            if self._repo_id_filter is not None:
                source = "|".join(
                    f"{row.report_id}:{row.rubric_id}:{row.id}" for row in scores
                )
                actual_ref = "pbi016_" + sha256(source.encode()).hexdigest()[:24]
            snapshot = SkillSnapshotInput(
                snapshot_ref=actual_ref,
                status=SnapshotStatus.COMPLETE,
                repository_ids=sorted(repo_ids),
                items=items,
            )
            return RawSkillSnapshot(owner_user_id=user_id, payload=snapshot)
        except Exception as exc:
            logger.error("Không thể đọc skill scores: %s", type(exc).__name__)
            raise SkillSnapshotSourceError(
                "Không thể truy vấn skill scores từ database"
            ) from exc

    def _verification_refs(
        self, scores: list[SkillScore], user_id: int
    ) -> dict[int, tuple[list[EvidenceRef], float | None]]:
        ids_by_score: dict[int, set[int]] = {}
        for score in scores:
            ids = {
                ref
                for part in score.breakdown or []
                if part.get("evidence_kind") == "verification"
                for ref in part.get("evidence_ids", [])
                if type(ref) is int and ref > 0
            }
            if ids:
                ids_by_score[score.id] = ids
        if not ids_by_score:
            return {}

        rows = self._db.execute(
            select(
                VerificationEvidence.id,
                VerificationEvidence.repository_id,
                VerificationEvidence.evidence_type,
                VerificationEvidence.target_identifier,
                RepositoryVerification.report_id,
            )
            .join(
                RepositoryVerification,
                RepositoryVerification.id == VerificationEvidence.verification_id,
            )
            .where(
                VerificationEvidence.id.in_(set().union(*ids_by_score.values())),
                VerificationEvidence.user_id == user_id,
                VerificationEvidence.verification_status == "verified",
                VerificationEvidence.is_bot.is_(False),
                VerificationEvidence.is_fork_inherited.is_(False),
                VerificationEvidence.evidence_type.in_(("commit", "pull_request")),
                RepositoryVerification.user_id == user_id,
                RepositoryVerification.repository_id
                == VerificationEvidence.repository_id,
            )
        ).all()
        by_id = {row.id: row for row in rows}
        result = {}
        for score in scores:
            ids = ids_by_score.get(score.id)
            if not ids:
                continue
            refs = []
            for identifier in sorted(ids):
                row = by_id.get(identifier)
                if (
                    row is None
                    or row.repository_id != score.repository_id
                    or row.report_id != score.report_id
                ):
                    continue
                sha = row.target_identifier if row.evidence_type == "commit" else None
                refs.append(
                    EvidenceRef(
                        evidence_id=f"verification-commit:{sha}"
                        if sha
                        else f"verification:{row.id}",
                        repository_id=row.repository_id,
                        commit_sha=sha,
                        finding_type=row.evidence_type,
                        classification=score.technology,
                    )
                )
            if len(refs) != len(ids):
                continue
            confidence = next(
                (
                    part.get("normalized_value")
                    for part in score.breakdown
                    if part.get("criterion") == "confidence"
                    and part.get("evidence_kind") == "verification"
                ),
                None,
            )
            if not isinstance(confidence, (float, int)) or not 0 <= confidence <= 1:
                continue
            result[score.id] = (refs, float(confidence) * 100)
        return result


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
