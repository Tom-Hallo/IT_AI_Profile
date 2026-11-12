"""Provider đọc architecture evidence từ hệ thống phân tích hiện có (PBI-012/015).

Tái sử dụng bảng ``ita.analysis_reports`` / ``ita.analysis_evidence`` (không tạo store
thứ hai) và guard authorization/consent hiện có. Quy tắc:

* Quyền: mỗi repository phải qua ``RepositoryAccessGuard`` (sở hữu + private access +
  consent ACCESS còn hiệu lực). Repository được chỉ định rõ mà không đạt → lỗi
  fail-closed; khi không chỉ định (``None``) thì repo không đạt bị BỎ QUA và ghi nhận.
  Lưu ý: ``get_latest_analysis`` hiện có chỉ kiểm tra sở hữu, không kiểm tra consent
  repo private, nên provider này tự áp consent và KHÔNG dùng cache trong bộ nhớ.
* Riêng tư: chỉ SELECT các cột cần cho tham chiếu (id, repo, commit, file_path, loại,
  nguồn, confidence). KHÔNG đọc ``matched_content``, ``line_number`` hay ``rationale``.
* Không suy diễn chất lượng: chỉ giữ ``finding_type = architecture`` với pattern mà
  analyzer thật sự phát ra. Evidence suy ra CHỈ từ tên thư mục (``directory_structure``)
  bị loại theo mặc định; số file/commit/LOC không bao giờ được đưa vào.
* ``verified``: evidence chỉ được coi là đã kiểm chứng khi PBI-013 xác nhận đóng góp
  thực tế của người dùng ở repository đó (``verification_status == "verified"``).
  Thiếu bản xác minh → ``verified=False`` và engine loại evidence (reason UNVERIFIED).
* Thiếu dữ liệu: không có report → ``evidence_set=None`` (engine: UNKNOWN); có report
  nhưng không có evidence phù hợp → tập rỗng (engine: UNKNOWN/NO_MATCHING_EVIDENCE).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai.scoring import ArchitectureEvidenceSet, EvidenceRef, TimeRange
from app.ai.scoring.evidence_catalog import (
    ARCHITECTURE_FINDING_TYPE,
    SUPPORTED_ARCHITECTURE_PATTERNS,
    normalize_key,
)
from app.ai.scoring.schemas import Limitation
from app.modules.analysis.models import (
    AnalysisEvidence,
    AnalysisReport,
    RepositoryVerification,
)
from app.modules.github.models import user_repository
from app.modules.role_scoring.access import AccessDecision, RepositoryAccessGuard
from app.modules.role_scoring.errors import (
    PrivateConsentRequiredError,
    RepositoryNotFoundError,
)

logger = logging.getLogger(__name__)

DIRECTORY_STRUCTURE_SOURCE = "directory_structure"
MAX_REPOSITORIES = 50


@dataclass(frozen=True)
class ArchitectureEvidencePolicy:
    # Nguồn evidence KHÔNG được dùng làm bằng chứng (suy ra từ tên thư mục).
    excluded_evidence_sources: frozenset[str] = frozenset({DIRECTORY_STRUCTURE_SOURCE})
    # Chỉ coi evidence là verified khi PBI-013 xác nhận đóng góp thực tế.
    require_verified_contribution: bool = True
    max_evidence_rows_per_report: int = 2000


class ArchitectureStatus(StrEnum):
    AVAILABLE = "AVAILABLE"  # có ít nhất một report dùng được
    NOT_ANALYZED = "NOT_ANALYZED"  # repo hợp lệ nhưng chưa có report
    NO_ACCESSIBLE_REPOSITORY = "NO_ACCESSIBLE_REPOSITORY"


class RepositoryEvidenceStatus(StrEnum):
    USED = "USED"
    NO_ANALYSIS = "NO_ANALYSIS"
    SKIPPED_PRIVATE_CONSENT_REQUIRED = "SKIPPED_PRIVATE_CONSENT_REQUIRED"


@dataclass(frozen=True)
class RepositoryEvidenceInfo:
    repository_id: int
    status: RepositoryEvidenceStatus
    report_id: int | None = None
    commit_sha: str | None = None
    evidence_used: int = 0
    excluded_by_source: dict[str, int] = field(default_factory=dict)
    contribution_verified: bool = False


@dataclass(frozen=True)
class ArchitectureEvidenceResult:
    status: ArchitectureStatus
    evidence_set: ArchitectureEvidenceSet | None = None
    repositories: list[RepositoryEvidenceInfo] = field(default_factory=list)
    limitations: list[Limitation] = field(default_factory=list)

    @property
    def repository_ids(self) -> set[int]:
        return {
            r.repository_id
            for r in self.repositories
            if r.status != RepositoryEvidenceStatus.SKIPPED_PRIVATE_CONSENT_REQUIRED
        }


class ArchitectureEvidencePort(Protocol):
    def get(
        self, repository_ids: Sequence[int] | None = None
    ) -> ArchitectureEvidenceResult: ...


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _time_range(raw: dict | None) -> TimeRange | None:
    if not raw:
        return None
    start, end = _parse_dt(raw.get("start_utc")), _parse_dt(raw.get("end_utc"))
    if start is None and end is None:
        return None
    try:
        return TimeRange(from_at=start, to_at=end)
    except ValidationError:
        return None


class DbArchitectureEvidenceProvider:
    def __init__(
        self,
        db: Session,
        user_id: int,
        guard: RepositoryAccessGuard,
        policy: ArchitectureEvidencePolicy | None = None,
    ) -> None:
        self._db = db
        self._user_id = user_id
        self._guard = guard
        self._policy = policy or ArchitectureEvidencePolicy()

    # ------------------------------------------------------------------ public

    def get(
        self, repository_ids: Sequence[int] | None = None
    ) -> ArchitectureEvidenceResult:
        explicit = repository_ids is not None
        if explicit:
            ids = sorted(set(repository_ids or ()))
            if len(ids) > MAX_REPOSITORIES:
                raise ValueError(f"at most {MAX_REPOSITORIES} repositories")
        else:
            ids = self._linked_repository_ids()

        limitations: list[Limitation] = []
        infos: list[RepositoryEvidenceInfo] = []
        allowed: list[int] = []
        skipped: list[int] = []

        for repo_id in ids:
            decision = self._guard.check(repo_id)
            if decision == AccessDecision.ALLOWED:
                allowed.append(repo_id)
            elif decision == AccessDecision.NOT_FOUND:
                if explicit:
                    raise RepositoryNotFoundError(str(repo_id))
            elif explicit:
                raise PrivateConsentRequiredError(str(repo_id))
            else:
                skipped.append(repo_id)
                infos.append(
                    RepositoryEvidenceInfo(
                        repo_id,
                        RepositoryEvidenceStatus.SKIPPED_PRIVATE_CONSENT_REQUIRED,
                    )
                )
        if skipped:
            limitations.append(
                Limitation(
                    code="PRIVATE_REPOSITORY_SKIPPED",
                    message=(
                        f"{len(skipped)} repository private bị bỏ qua vì thiếu hoặc "
                        "đã thu hồi consent."
                    ),
                )
            )

        refs: list[EvidenceRef] = []
        reports: list[AnalysisReport] = []
        unanalyzed: list[int] = []
        unverified_repos: list[int] = []

        for repo_id in allowed:
            report = self._latest_report(repo_id)
            if report is None:
                unanalyzed.append(repo_id)
                infos.append(
                    RepositoryEvidenceInfo(
                        repo_id, RepositoryEvidenceStatus.NO_ANALYSIS
                    )
                )
                continue
            verified = self._contribution_verified(repo_id)
            if self._policy.require_verified_contribution and not verified:
                unverified_repos.append(repo_id)
            repo_refs, excluded, truncated, invalid = self._load_evidence(
                report, verified or not self._policy.require_verified_contribution
            )
            if truncated:
                limitations.append(
                    Limitation(
                        code="ARCHITECTURE_EVIDENCE_TRUNCATED",
                        message=(
                            f"Report {report.id} vượt giới hạn "
                            f"{self._policy.max_evidence_rows_per_report} evidence; "
                            "phần vượt không được dùng."
                        ),
                    )
                )
            if invalid:
                limitations.append(
                    Limitation(
                        code="ARCHITECTURE_EVIDENCE_INVALID_ROWS_SKIPPED",
                        message=(
                            f"Bỏ qua {invalid} evidence không hợp lệ "
                            f"ở report {report.id}."
                        ),
                    )
                )
            refs.extend(repo_refs)
            reports.append(report)
            infos.append(
                RepositoryEvidenceInfo(
                    repo_id,
                    RepositoryEvidenceStatus.USED,
                    report_id=report.id,
                    commit_sha=report.commit_sha,
                    evidence_used=len(repo_refs),
                    excluded_by_source=dict(excluded),
                    contribution_verified=verified,
                )
            )

        excluded_total: Counter[str] = Counter()
        for info in infos:
            excluded_total.update(info.excluded_by_source)
        for source, count in sorted(excluded_total.items()):
            limitations.append(
                Limitation(
                    code="EVIDENCE_SOURCE_EXCLUDED",
                    message=(
                        f"Đã loại {count} evidence có nguồn '{source}': suy ra từ tên "
                        "thư mục, không phải bằng chứng chất lượng kiến trúc."
                    ),
                )
            )
        if unanalyzed:
            limitations.append(
                Limitation(
                    code="REPOSITORY_NOT_ANALYZED",
                    message=f"{len(unanalyzed)} repository chưa có kết quả phân tích.",
                )
            )
        if unverified_repos:
            limitations.append(
                Limitation(
                    code="CONTRIBUTION_NOT_VERIFIED",
                    message=(
                        f"{len(unverified_repos)} repository chưa được PBI-013 xác "
                        "nhận đóng góp thực tế; evidence của chúng không được tính."
                    ),
                )
            )

        infos.sort(key=lambda i: i.repository_id)
        if not reports:
            status = (
                ArchitectureStatus.NOT_ANALYZED
                if allowed
                else ArchitectureStatus.NO_ACCESSIBLE_REPOSITORY
            )
            return ArchitectureEvidenceResult(status, None, infos, limitations)

        return ArchitectureEvidenceResult(
            ArchitectureStatus.AVAILABLE,
            self._build_set(reports, refs),
            infos,
            limitations,
        )

    # --------------------------------------------------------------- internals

    def _linked_repository_ids(self) -> list[int]:
        rows = self._db.scalars(
            select(user_repository.c.repository_id)
            .where(user_repository.c.user_id == self._user_id)
            .order_by(user_repository.c.repository_id)
            .limit(MAX_REPOSITORIES)
        ).all()
        return [int(r) for r in rows]

    def _latest_report(self, repository_id: int) -> AnalysisReport | None:
        return self._db.scalar(
            select(AnalysisReport)
            .where(AnalysisReport.repository_id == repository_id)
            .order_by(desc(AnalysisReport.analyzed_at), desc(AnalysisReport.id))
            .limit(1)
        )

    def _contribution_verified(self, repository_id: int) -> bool:
        status = self._db.scalar(
            select(RepositoryVerification.verification_status)
            .where(
                RepositoryVerification.repository_id == repository_id,
                RepositoryVerification.user_id == self._user_id,
            )
            .order_by(
                desc(RepositoryVerification.verified_at),
                desc(RepositoryVerification.id),
            )
            .limit(1)
        )
        return status == "verified"

    def _load_evidence(
        self, report: AnalysisReport, verified: bool
    ) -> tuple[list[EvidenceRef], Counter[str], bool, int]:
        limit = self._policy.max_evidence_rows_per_report
        rows = self._db.execute(
            select(
                AnalysisEvidence.id,
                AnalysisEvidence.repository_id,
                AnalysisEvidence.commit_sha,
                AnalysisEvidence.file_path,
                AnalysisEvidence.finding_type,
                AnalysisEvidence.classification,
                AnalysisEvidence.evidence_source,
                AnalysisEvidence.confidence_score,
            )
            .where(
                AnalysisEvidence.report_id == report.id,
                AnalysisEvidence.repository_id == report.repository_id,
                AnalysisEvidence.finding_type == ARCHITECTURE_FINDING_TYPE,
            )
            .order_by(AnalysisEvidence.id)
            .limit(limit + 1)
        ).all()
        truncated = len(rows) > limit
        refs: list[EvidenceRef] = []
        excluded: Counter[str] = Counter()
        invalid = 0
        for row in rows[:limit]:
            if normalize_key(row.classification) not in SUPPORTED_ARCHITECTURE_PATTERNS:
                continue
            source = normalize_key(row.evidence_source or "")
            if source in self._policy.excluded_evidence_sources:
                excluded[source] += 1
                continue
            try:
                refs.append(
                    EvidenceRef(
                        evidence_id=row.id,
                        repository_id=row.repository_id,
                        commit_sha=row.commit_sha,
                        file_path=row.file_path,
                        finding_type=row.finding_type,
                        classification=row.classification,
                        confidence_score=row.confidence_score,
                        verified=verified,
                    )
                )
            except ValidationError:
                invalid += 1
        return refs, excluded, truncated, invalid

    @staticmethod
    def _build_set(
        reports: list[AnalysisReport], refs: list[EvidenceRef]
    ) -> ArchitectureEvidenceSet:
        reports = sorted(reports, key=lambda r: r.repository_id)
        ranges = {repr(r.time_range) for r in reports}
        analyzed = [r.analyzed_at for r in reports if r.analyzed_at is not None]
        return ArchitectureEvidenceSet(
            report_ref="analysis_report:" + ",".join(str(r.id) for r in reports),
            commit_sha=reports[0].commit_sha if len(reports) == 1 else None,
            # report.scope là phạm vi phân tích, không cùng từ vựng với repository_scope
            # của PBI-016 → để None để engine không báo SOURCE_MISMATCH giả.
            repository_scope=None,
            repository_ids=[str(r.repository_id) for r in reports],
            time_range=_time_range(reports[0].time_range) if len(ranges) == 1 else None,
            analyzed_at=max(analyzed) if analyzed else None,
            evidence=refs,
        )
