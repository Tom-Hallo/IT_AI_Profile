"""Pydantic request & response schemas for repository analysis API (PBI-012)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.modules.analysis.evidence import EvidenceRecord


class RepositoryAnalysisRequest(BaseModel):
    """Tham số yêu cầu phân tích repository tĩnh."""

    branch: str | None = Field(
        default=None,
        description="Tên nhánh Git cần phân tích (mặc định: default_branch)",
    )
    mode: Literal["preset", "month", "year", "custom"] | None = Field(
        default=None, description="Chế độ chọn khoảng thời gian (PBI-010)"
    )
    preset: Literal["1m", "3m", "6m", "1y", "all"] | None = Field(
        default=None, description="Khoảng thời gian mẫu"
    )
    month: str | None = Field(default=None, description="Tháng dạng YYYY-MM")
    year: int | str | None = Field(default=None, description="Năm dạng YYYY")
    start_date: date | None = Field(default=None, description="Ngày bắt đầu")
    end_date: date | None = Field(default=None, description="Ngày kết thúc")
    timezone: str = Field(default="UTC", description="Múi giờ IANA")
    scope: Literal["all", "public", "private", "full"] = Field(
        default="all", description="Phạm vi phân tích repository"
    )

    @field_validator("scope", mode="before")
    @classmethod
    def normalize_scope(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().lower()
            if clean in ("all", "all code in repo"):
                return "all"
            if clean in ("full", "public", "private"):
                return clean
        return v


class LanguageSummary(BaseModel):
    name: str
    primary: bool
    bytes_count: int | None = None
    percentage: float | None = None
    file_count: int
    evidence_count: int


class FrameworkSummary(BaseModel):
    name: str
    category: str
    ecosystem: str
    version: str | None = None
    status: str
    confidence: str
    evidence_count: int


class ArchitectureSummary(BaseModel):
    pattern: str
    name: str
    description: str
    confidence: str
    evidence_count: int


class StructureSummary(BaseModel):
    total_files: int
    inspected_files: int
    ignored_files: int


class RepositoryAnalysisResponse(BaseModel):
    """Kết quả phân tích toàn diện repository."""

    report_id: int | None = None
    repository_id: int
    commit_sha: str
    analyzed_at: str
    scope: str
    time_range: dict[str, str | None] | None = None
    structure: StructureSummary
    languages: list[LanguageSummary]
    frameworks: list[FrameworkSummary]
    architecture: list[ArchitectureSummary]
    evidence_count: int
    budget: dict[str, Any]
    verification: RepositoryVerificationSummary | None = None


class EvidenceListResponse(BaseModel):
    """Danh sách các bản ghi bằng chứng có thể kiểm chứng độc lập."""

    report_id: int | None = None
    repository_id: int
    commit_sha: str
    total: int
    items: list[EvidenceRecord]


class VerificationRequest(BaseModel):
    """Tham số yêu cầu xác minh fork, ownership và đóng góp (PBI-013)."""

    scope: Literal["all", "public", "private"] = Field(
        default="all",
        description="Phạm vi dữ liệu được phép xác minh",
    )

    branch: str | None = Field(default=None, description="Tên nhánh Git cần xác minh")
    mode: Literal["preset", "month", "year", "custom"] | None = Field(
        default=None, description="Chế độ chọn khoảng thời gian"
    )
    preset: Literal["1m", "3m", "6m", "1y", "all"] | None = Field(
        default=None, description="Khoảng thời gian mẫu"
    )
    month: str | None = Field(default=None, description="Tháng dạng YYYY-MM")
    year: int | str | None = Field(default=None, description="Năm dạng YYYY")
    start_date: date | None = Field(default=None, description="Ngày bắt đầu")
    end_date: date | None = Field(default=None, description="Ngày kết thúc")
    timezone: str = Field(default="UTC", description="Múi giờ IANA")
    force_refresh: bool = Field(
        default=False, description="Bắt buộc làm mới dữ liệu từ GitHub API"
    )


class VerificationEvidenceItem(BaseModel):
    """Bản ghi bằng chứng xác minh commit / PR / provenance (PBI-013)."""

    id: int | None = None
    evidence_type: str = Field(
        description="Loại bằng chứng: commit, pull_request, provenance, ownership"
    )
    target_identifier: str = Field(
        description="Định danh: Commit SHA, số PR, hoặc tên repository"
    )
    verification_status: Literal["verified", "unverified", "unknown"] = Field(
        description="Trạng thái xác minh"
    )
    actor_login: str | None = None
    actor_id: str | None = None
    actor_type: str | None = None
    html_url: str | None = None
    title_or_message: str | None = None
    is_merge: bool = False
    is_bot: bool = False
    is_fork_inherited: bool = False
    additions: int | None = None
    deletions: int | None = None
    pr_state: str | None = None
    pr_merged: bool | None = None
    source_repo: str | None = None
    target_repo: str | None = None
    recorded_at: str | datetime | None = None
    rationale: str
    metadata: dict[str, Any] | None = None

    @field_serializer("recorded_at", when_used="json")
    def serialize_recorded_at(self, v: str | datetime | None) -> str | None:
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class RepositoryVerificationSummary(BaseModel):
    """Tóm tắt trạng thái xác minh fork và quyền sở hữu (PBI-013)."""

    provenance_type: str
    ownership_status: str
    is_fork: bool
    parent_repo_name: str | None = None
    parent_repo_url: str | None = None
    parent_metadata_status: str
    verification_status: str
    coverage_status: str
    confidence: str
    verified_commits_count: int
    unverified_commits_count: int
    verified_prs_count: int
    unverified_prs_count: int
    verified_additions: int
    verified_deletions: int
    anti_inflation_flag: bool = False
    rationale: str | None = None
    verified_at: str | datetime = Field(description="Thời điểm thực hiện xác minh")

    @field_serializer("verified_at", when_used="json")
    def serialize_verified_at(self, v: str | datetime) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class RepositoryVerificationResponse(BaseModel):
    """Kết quả xác minh toàn diện fork, ownership và đóng góp thực tế (PBI-013)."""

    id: int | None = None
    repository_id: int
    repository_name: str
    repository_full_name: str
    user_id: int
    job_id: str | None = None
    report_id: int | None = None
    provenance_type: str
    ownership_status: str
    is_fork: bool
    parent_repo_name: str | None = None
    parent_repo_url: str | None = None
    parent_metadata_status: str
    verification_status: str
    coverage_status: str
    confidence: str
    verified_commits_count: int
    unverified_commits_count: int
    verified_prs_count: int
    unverified_prs_count: int
    verified_additions: int
    verified_deletions: int
    anti_inflation_flag: bool = False
    time_range: dict[str, str | None] | None = None
    limitations: list[str] = Field(default_factory=list)
    summary_data: dict[str, Any] = Field(default_factory=dict)
    verified_at: str | datetime
    evidence: list[VerificationEvidenceItem] = Field(default_factory=list)

    @field_serializer("verified_at", when_used="json")
    def serialize_verified_at(self, v: str | datetime) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class VerificationEvidenceListResponse(BaseModel):
    """Danh sách bằng chứng xác minh phân trang (PBI-013)."""

    repository_id: int
    total: int
    page: int = 1
    per_page: int = 50
    items: list[VerificationEvidenceItem]


# ============================================================================
# PBI-014: Pull Request, Review, CI & Problem-Solving Schemas
# ============================================================================


class CollaborationAnalysisRequest(BaseModel):
    """Tham số yêu cầu phân tích Pull Request, Review, CI & xử lý lỗi (PBI-014)."""

    branch: str | None = Field(
        default=None,
        description="Tên nhánh Git cần phân tích (mặc định: default_branch)",
    )
    mode: Literal["preset", "month", "year", "custom"] | None = Field(
        default=None, description="Chế độ chọn khoảng thời gian"
    )
    preset: Literal["1m", "3m", "6m", "1y", "all"] | None = Field(
        default=None, description="Khoảng thời gian mẫu"
    )
    month: str | None = Field(default=None, description="Tháng dạng YYYY-MM")
    year: int | str | None = Field(default=None, description="Năm dạng YYYY")
    start_date: date | None = Field(default=None, description="Ngày bắt đầu")
    end_date: date | None = Field(default=None, description="Ngày kết thúc")
    timezone: str = Field(default="UTC", description="Múi giờ IANA")
    force_refresh: bool = Field(
        default=False, description="Bắt buộc quét lại dữ liệu mới từ GitHub API"
    )


class CollaborationEvidenceItem(BaseModel):
    """Bằng chứng chi tiết cho PR, Review, CI check hoặc chu kỳ xử lý lỗi (PBI-014)."""

    id: int | None = None
    evidence_type: str = Field(
        description=(
            "Loại bằng chứng: pull_request, review, check_run, "
            "commit_status, problem_solving_sequence"
        )
    )
    target_identifier: str = Field(
        description="Định danh đối tượng (PR #1, Review #101, CheckRun #202)"
    )
    pr_number: int | None = None
    commit_sha: str | None = None
    check_name: str | None = None
    state: str | None = None
    conclusion: str | None = None
    actor_login: str | None = None
    actor_id: str | None = None
    actor_type: str | None = None
    is_profile_owner: bool = False
    html_url: str | None = None
    title_or_message: str | None = None
    recorded_at: str | datetime | None = None
    rationale: str
    metadata: dict[str, Any] | None = None

    @field_serializer("recorded_at", when_used="json")
    def serialize_recorded_at(self, v: str | datetime | None) -> str | None:
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class CollaborationObservation(BaseModel):
    """Quan sát hợp tác/phản biện dựa trên bằng chứng khách quan (PBI-014)."""

    category: str = Field(
        description="Danh mục quan sát: pull_request, review, ci_check, problem_solving"
    )
    title: str
    description: str
    evidence_level: str = Field(
        default="observed_event",
        description=(
            "Mức độ chứng minh: observed_event, evidence_backed_relationship, "
            "contextual_explanation"
        ),
    )
    confidence: str = Field(default="high")
    related_identifiers: list[str] = Field(default_factory=list)


class ProblemSolvingSequence(BaseModel):
    """Chuỗi sự kiện xử lý vấn đề / chu kỳ phản hồi lặp (PBI-014)."""

    sequence_id: str
    pr_number: int | None = None
    trigger_event: dict[str, Any] = Field(
        description="Sự kiện khởi phát (yêu cầu thay đổi, CI fail)"
    )
    iteration_events: list[dict[str, Any]] = Field(
        default_factory=list, description="Các bước điều chỉnh tiếp sau (commit mới)"
    )
    resolution_or_outcome: dict[str, Any] = Field(
        description="Kết quả chu kỳ (CI pass, review approved, PR merged/closed)"
    )
    cycle_duration_seconds: float | None = None
    explanation: str
    limitations: list[str] = Field(default_factory=list)


class CollaborationAnalysisResponse(BaseModel):
    """Kết quả phân tích toàn diện PR, Review, CI & xử lý lỗi (PBI-014)."""

    id: int | None = None
    repository_id: int
    repository_name: str
    repository_full_name: str
    user_id: int
    job_id: str | None = None
    report_id: int | None = None

    # PR Metrics
    total_prs_analyzed: int = 0
    merged_prs_count: int = 0
    closed_unmerged_prs_count: int = 0
    open_prs_count: int = 0
    user_prs_count: int = 0
    external_prs_count: int = 0

    # Review Metrics
    total_reviews_analyzed: int = 0
    approved_reviews_count: int = 0
    changes_requested_count: int = 0
    commented_reviews_count: int = 0
    dismissed_reviews_count: int = 0
    user_reviews_conducted_count: int = 0
    user_reviews_received_count: int = 0

    # CI Checks Metrics
    total_checks_analyzed: int = 0
    successful_checks_count: int = 0
    failed_checks_count: int = 0
    pending_checks_count: int = 0
    other_checks_count: int = 0
    problem_solving_sequences_count: int = 0

    # Quality and Uncertainty Gates
    coverage_status: str = "complete"  # complete, partial, insufficient
    confidence: str = "high"  # high, medium, uncertain
    time_range: dict[str, str | None] | None = None
    limitations: list[str] = Field(default_factory=list)
    collaboration_observations: list[CollaborationObservation] = Field(
        default_factory=list
    )
    problem_solving_sequences: list[ProblemSolvingSequence] = Field(
        default_factory=list
    )
    summary_data: dict[str, Any] = Field(default_factory=dict)
    analyzed_at: str | datetime
    evidence: list[CollaborationEvidenceItem] = Field(default_factory=list)

    @field_serializer("analyzed_at", when_used="json")
    def serialize_analyzed_at(self, v: str | datetime) -> str:
        if isinstance(v, datetime):
            return v.isoformat()
        return v


class CollaborationEvidenceListResponse(BaseModel):
    """Danh sách bằng chứng cộng tác/CI phân trang (PBI-014)."""

    repository_id: int
    total: int
    page: int = 1
    per_page: int = 50
    items: list[CollaborationEvidenceItem]
