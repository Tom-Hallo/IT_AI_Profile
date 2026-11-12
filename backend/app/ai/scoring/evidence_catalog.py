"""Danh mục loại evidence mà hệ thống hiện tại thực sự cung cấp (PBI-017).

Chỉ liệt kê những gì có căn cứ trong source:
- ``SUPPORTED_ARCHITECTURE_PATTERNS``: các ``classification`` mà
  ``app.modules.analysis.architecture.ArchitectureAnalyzer`` phát ra với
  ``finding_type = "architecture"``. Test ``test_role_scoring_catalog`` đối chiếu
  danh sách này với mã nguồn analyzer để tránh lệch khi analyzer thay đổi.
- ``FORBIDDEN_EVIDENCE_TYPES``: các số liệu hoạt động KHÔNG được dùng làm bằng chứng
  trực tiếp cho năng lực (SRS FR-010/FR-012, AC PBI-017).
"""

from __future__ import annotations

import re

ARCHITECTURE_FINDING_TYPE = "architecture"

SUPPORTED_ARCHITECTURE_PATTERNS: frozenset[str] = frozenset(
    {
        "frontend_backend_separation",
        "layered_architecture",
        "mvc_architecture",
        "api_service",
        "background_workers",
        "database_integration",
        "monorepo",
    }
)

FORBIDDEN_EVIDENCE_TYPES: frozenset[str] = frozenset(
    {
        "commit_count",
        "commits",
        "lines_of_code",
        "loc",
        "repository_count",
        "repo_count",
        "repositories",
        "stars",
        "stargazers",
        "star_count",
        "forks",
        "fork_count",
    }
)


def normalize_key(value: str) -> str:
    """Chuẩn hoá khoá (skill/pattern/finding type) về dạng so khớp ổn định."""
    return re.sub(r"[^a-z0-9#+]+", "_", value.strip().lower()).strip("_")


def is_forbidden_evidence_type(*values: str | None) -> bool:
    """True nếu bất kỳ giá trị nào thuộc nhóm số liệu bị cấm làm evidence."""
    return any(v and normalize_key(v) in FORBIDDEN_EVIDENCE_TYPES for v in values)
