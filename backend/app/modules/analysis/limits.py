"""Resource limits and budget tracking for repository analysis."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AnalysisLimits:
    """Các giới hạn tài nguyên có thể tùy biến khi phân tích repository."""

    max_inspected_files: int = 1000
    max_file_size_bytes: int = 512 * 1024  # 512 KB
    max_total_analysis_bytes: int = 10 * 1024 * 1024  # 10 MB
    analysis_timeout_seconds: float = 30.0


@dataclass
class AnalysisBudgetTracker:
    """Theo dõi mức sử dụng tài nguyên trong suốt tiến trình phân tích."""

    limits: AnalysisLimits = field(default_factory=AnalysisLimits)
    start_time: float = field(default_factory=time.monotonic)
    inspected_files_count: int = 0
    inspected_bytes_total: int = 0
    skipped_oversized_files: int = 0
    limit_reached: bool = False
    limit_reason: str | None = None

    def check_can_inspect_file(self, file_size: int = 0) -> bool:
        """Kiểm tra xem còn hạn mức để phân tích thêm một file hay không."""
        # 1. Kiểm tra timeout
        elapsed = time.monotonic() - self.start_time
        if elapsed > self.limits.analysis_timeout_seconds:
            self.limit_reached = True
            self.limit_reason = (
                f"Quá thời gian tối đa ({self.limits.analysis_timeout_seconds:.1f}s)"
            )
            return False

        # 2. Kiểm tra số lượng tập tin tối đa
        if self.inspected_files_count >= self.limits.max_inspected_files:
            self.limit_reached = True
            self.limit_reason = (
                "Đã đạt số lượng tập tin tối đa "
                f"({self.limits.max_inspected_files} files)"
            )
            return False

        # 3. Kiểm tra tổng dung lượng tối đa
        if (
            self.inspected_bytes_total + file_size
            > self.limits.max_total_analysis_bytes
        ):
            self.limit_reached = True
            max_mb = self.limits.max_total_analysis_bytes // (1024 * 1024)
            self.limit_reason = f"Đã đạt tổng dung lượng phân tích tối đa ({max_mb} MB)"
            return False

        return True

    def record_file_inspected(self, file_size: int) -> None:
        """Ghi nhận một tập tin đã được duyệt qua và phân tích nội dung."""
        self.inspected_files_count += 1
        self.inspected_bytes_total += max(0, file_size)

    def record_oversized_skipped(self) -> None:
        """Ghi nhận một tập tin bị bỏ qua vì vượt quá kích thước đơn lẻ."""
        self.skipped_oversized_files += 1

    def summary(self) -> dict[str, Any]:
        """Tóm tắt mức tiêu hao tài nguyên phân tích."""
        return {
            "inspected_files": self.inspected_files_count,
            "inspected_bytes": self.inspected_bytes_total,
            "skipped_oversized_files": self.skipped_oversized_files,
            "limit_reached": self.limit_reached,
            "limit_reason": self.limit_reason,
            "elapsed_seconds": round(time.monotonic() - self.start_time, 3),
        }
