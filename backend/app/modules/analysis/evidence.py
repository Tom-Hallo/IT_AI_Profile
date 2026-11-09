"""Evidence data models, collectors, and storage contracts for PBI-012.

Each meaningful finding produces verifiable evidence preserving repository ID,
commit SHA, file path, finding type, classification, evidence source, scope,
time range, timestamp, detection method, and confidence metrics.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field

UTC = getattr(datetime, "UTC", timezone.utc)  # noqa: UP017


class EvidenceSource(StrEnum):
    """Nguồn gốc của bằng chứng phát hiện được."""

    MANIFEST = "manifest"
    SOURCE_CODE = "source_code"
    DIRECTORY_STRUCTURE = "directory_structure"
    CONFIGURATION = "configuration"
    METADATA = "metadata"


class FindingType(StrEnum):
    """Phân loại hạng mục phát hiện."""

    LANGUAGE = "language"
    FRAMEWORK = "framework"
    ARCHITECTURE = "architecture"
    DEPENDENCY = "dependency"
    STRUCTURE = "structure"


class DetectionMethod(StrEnum):
    """Phương thức phân tích tĩnh được áp dụng."""

    MANIFEST_PARSING = "manifest_parsing"
    CONTENT_INSPECTION = "content_inspection"
    STRUCTURAL_INSPECTION = "structural_inspection"
    EXTENSION_EVIDENCE = "extension_evidence"
    METADATA_EXTRACTION = "metadata_extraction"


class ConfidenceLevel(StrEnum):
    """Mức độ tin cậy của kết luận phân tích."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


class EvidenceRecord(BaseModel):
    """Bằng chứng xác thực gắn với repository path và commit hash (PBI-012)."""

    repository_id: int
    commit_sha: str
    file_path: str
    finding_type: FindingType
    classification: str
    evidence_source: EvidenceSource
    detection_method: DetectionMethod
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    confidence_score: float = Field(ge=0.0, le=1.0, default=1.0)
    rationale: str
    line_number: int | None = None
    matched_content: str | None = None
    scope: str = "all"
    time_range: dict[str, str | None] | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": True}


class EvidenceCollector:
    """Bộ thu thập, loại trùng và tổ chức bằng chứng trong phiên phân tích."""

    def __init__(self) -> None:
        self._records: list[EvidenceRecord] = []
        self._seen_keys: set[tuple[str, str, str, str]] = set()

    def add(self, record: EvidenceRecord) -> bool:
        """Thêm một bản ghi bằng chứng, tránh trùng lặp dữ liệu."""
        key = (
            record.commit_sha,
            record.file_path,
            record.classification,
            record.finding_type.value,
        )
        if key in self._seen_keys:
            return False
        self._seen_keys.add(key)
        self._records.append(record)
        return True

    def get_all(self) -> list[EvidenceRecord]:
        """Lấy toàn bộ danh sách bằng chứng đã thu thập."""
        return list(self._records)

    def filter_by_type(self, finding_type: FindingType) -> list[EvidenceRecord]:
        """Lọc bằng chứng theo loại phát hiện."""
        return [r for r in self._records if r.finding_type == finding_type]

    def filter_by_classification(self, classification: str) -> list[EvidenceRecord]:
        """Lọc bằng chứng theo tên công nghệ hoặc mẫu kiến trúc."""
        return [
            r
            for r in self._records
            if r.classification.lower() == classification.lower()
        ]

    def __len__(self) -> int:
        return len(self._records)


class EvidenceStoreProtocol(Protocol):
    """Giao diện hợp đồng chuẩn bị cho PBI-015 (Evidence Store).

    Hợp đồng trừu tượng này giúp PBI-012 lưu trữ và truy xuất bằng chứng
    mà không cần phát minh trước cấu trúc cơ sở dữ liệu chưa được chuẩn hóa của PBI-015.
    """

    async def save_evidence(
        self,
        repository_id: int,
        commit_sha: str,
        records: list[EvidenceRecord],
    ) -> int:
        """Lưu danh sách bằng chứng vào store."""
        ...

    async def get_evidence_by_commit(
        self,
        repository_id: int,
        commit_sha: str,
        finding_type: FindingType | None = None,
    ) -> list[EvidenceRecord]:
        """Truy xuất bằng chứng theo repository ID và commit SHA chính xác."""
        ...
