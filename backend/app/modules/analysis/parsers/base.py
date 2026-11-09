"""Base interfaces and data structures for static manifest parsers (PBI-012)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParsedDependency:
    """Thông tin một thư viện / dependency bóc tách từ manifest."""

    name: str
    version_spec: str | None = None
    is_dev: bool = False
    manifest_path: str = ""
    line_number: int | None = None
    matched_line: str | None = None


@dataclass
class ManifestParserResult:
    """Kết quả phân tích một manifest của dự án."""

    manifest_path: str
    ecosystem: str
    dependencies: list[ParsedDependency] = field(default_factory=list)
    is_valid: bool = True
    error_message: str | None = None
    lockfile_missing: bool = False
    lockfile_corrupted: bool = False
    conflicting_dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def find_dependency(self, name: str) -> ParsedDependency | None:
        """Tìm kiếm dependency theo tên không phân biệt hoa thường."""
        target = name.lower()
        for dep in self.dependencies:
            if dep.name.lower() == target:
                return dep
        return None
