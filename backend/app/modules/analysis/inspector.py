"""Repository Inspector engine orchestrating static analysis.

Evidence generation (PBI-012).

Orchestrates:
1. Tree traversal and path safety verification (prevents traversal attacks).
2. Resource limiting & file filtering (exclusions, budget tracking).
3. Manifest parsing across ecosystems (Python, JS/TS, Java, Go, Rust, C#).
4. Multi-language detection.
5. Framework and major library detection with lockfile health verification.
6. Architecture pattern analysis supported by verifiable evidence.
7. Graceful empty repository handling.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.modules.analysis.architecture import ArchitectureAnalyzer, ArchitectureFinding
from app.modules.analysis.evidence import (
    UTC,
    EvidenceCollector,
)
from app.modules.analysis.filters import (
    is_ignored_path,
    is_manifest_file,
    is_safe_path,
    normalize_posix_path,
)
from app.modules.analysis.frameworks import FrameworkDetector, FrameworkFinding
from app.modules.analysis.languages import LanguageDetector, LanguageFinding
from app.modules.analysis.limits import AnalysisBudgetTracker, AnalysisLimits
from app.modules.analysis.parsers import (
    ManifestParserResult,
    parse_build_gradle,
    parse_cargo_toml,
    parse_dotnet_csproj,
    parse_go_mod,
    parse_package_json,
    parse_pipfile,
    parse_pom_xml,
    parse_pyproject_toml,
    parse_requirements_txt,
    parse_setup_cfg_or_py,
)

logger = logging.getLogger(__name__)


class RepositoryContentSource(ABC):
    """Giao diện nguồn cung cấp nội dung cây thư mục và tập tin."""

    @abstractmethod
    async def get_tree_items(self) -> list[dict[str, Any]]:
        """Trả về danh sách các mục trong Git Tree: [{'path': ..., 'size': ..., 'type':
        'blob'|'tree'}]
        """
        ...

    @abstractmethod
    async def get_file_content(self, path: str, max_bytes: int) -> str | None:
        """Đọc nội dung văn bản UTF-8 của một tập tin an toàn."""
        ...


class InMemoryContentSource(RepositoryContentSource):
    """Nguồn nội dung trong bộ nhớ dùng cho kiểm thử tự động deterministic."""

    def __init__(self, files: dict[str, str | bytes]) -> None:
        self.files = files

    async def get_tree_items(self) -> list[dict[str, Any]]:
        items = []
        for path, content in self.files.items():
            size = len(content.encode("utf-8") if isinstance(content, str) else content)
            items.append({"path": path, "size": size, "type": "blob"})
        return items

    async def get_file_content(self, path: str, max_bytes: int) -> str | None:
        normalized = normalize_posix_path(path)
        content = self.files.get(normalized)
        if content is None:
            return None
        raw = content.encode("utf-8") if isinstance(content, str) else content
        if len(raw) > max_bytes:
            return None
        return raw.decode("utf-8", errors="replace")


class RepositoryInspector:
    """Bộ kiểm tra và phân tích tĩnh toàn diện repository mã nguồn."""

    def __init__(
        self,
        repository_id: int,
        commit_sha: str,
        limits: AnalysisLimits | None = None,
        scope: str = "all",
        time_range: dict[str, str | None] | None = None,
    ) -> None:
        self.repository_id = repository_id
        self.commit_sha = commit_sha
        self.limits = limits or AnalysisLimits()
        self.scope = scope
        self.time_range = time_range
        self.budget = AnalysisBudgetTracker(limits=self.limits)
        self.collector = EvidenceCollector()

    async def inspect(
        self,
        source: RepositoryContentSource,
        github_languages: dict[str, int] | None = None,
        on_progress: Callable[[str, int], None] | None = None,
    ) -> dict[str, Any]:
        """Thực thi toàn bộ quy trình kiểm tra và phân tích tĩnh repository."""
        # 1. Lấy toàn bộ cây tập tin
        raw_tree = await source.get_tree_items()

        # Xử lý Empty Repository
        if not raw_tree:
            logger.info(
                (
                    f"Repository id={self.repository_id} rỗng (0 tập tin), "
                    "trả về kết quả an toàn."
                )
            )
            if on_progress:
                on_progress("empty_repository", 90)
            return self._build_result(
                total_files=0,
                inspected_files=0,
                ignored_files=0,
                languages=[],
                frameworks=[],
                architecture=[],
                manifest_results=[],
            )

        if on_progress:
            on_progress("tree_loaded", 30)

        valid_tree_paths: list[str] = []
        file_sizes: dict[str, int] = {}
        manifest_paths: set[str] = set()
        lockfile_paths: set[str] = set()
        ignored_count = 0

        # 2. Lọc và kiểm tra an toàn đường dẫn (Chống Path Traversal & loại bỏ
        # vendor/binaries)
        for item in raw_tree:
            path = item.get("path", "")
            if not is_safe_path(path):
                logger.warning(
                    (
                        "Bỏ qua đường dẫn không an toàn hoặc cố tình "
                        f"path traversal: {path!r}"
                    )
                )
                continue

            norm_path = normalize_posix_path(path)
            size = int(item.get("size") or 0)

            if is_ignored_path(norm_path):
                ignored_count += 1
                continue

            valid_tree_paths.append(norm_path)
            file_sizes[norm_path] = size

            if is_manifest_file(norm_path):
                manifest_paths.add(norm_path)
            if "lock" in norm_path.lower():
                lockfile_paths.add(norm_path)

        if on_progress:
            on_progress("filtering_paths", 35)

        # 3. Phân tích các tập tin manifest để bóc tách dependencies
        manifest_results: list[ManifestParserResult] = []
        total_m = len(manifest_paths)
        for idx, m_path in enumerate(manifest_paths, 1):
            fsize = file_sizes.get(m_path, 0)
            if fsize > self.limits.max_file_size_bytes:
                self.budget.record_oversized_skipped()
                continue

            if not self.budget.check_can_inspect_file(fsize):
                break

            content = await source.get_file_content(
                m_path, max_bytes=self.limits.max_file_size_bytes
            )
            if content is None:
                continue

            self.budget.record_file_inspected(len(content.encode("utf-8")))
            res = self._parse_manifest_content(m_path, content, lockfile_paths)
            if res:
                manifest_results.append(res)

            if on_progress and total_m > 0:
                pct = 35 + int((idx / total_m) * 25)
                on_progress(f"parsing_manifests ({idx}/{total_m})", pct)

        # 4. Phát hiện ngôn ngữ lập trình
        if on_progress:
            on_progress("detecting_languages", 65)
        lang_detector = LanguageDetector(self.repository_id, self.commit_sha)
        languages = lang_detector.detect(
            tree_paths=valid_tree_paths,
            file_sizes=file_sizes,
            github_languages=github_languages,
            manifest_paths=manifest_paths,
            collector=self.collector,
        )

        # 5. Phát hiện frameworks và thư viện chính
        if on_progress:
            on_progress("detecting_frameworks", 75)
        framework_detector = FrameworkDetector(self.repository_id, self.commit_sha)
        frameworks = framework_detector.detect_from_manifests(
            manifest_results=manifest_results,
            all_tree_paths=valid_tree_paths,
            collector=self.collector,
        )

        # 6. Phân tích đặc trưng kiến trúc phần mềm
        if on_progress:
            on_progress("analyzing_architecture", 82)
        arch_analyzer = ArchitectureAnalyzer(self.repository_id, self.commit_sha)
        architecture = arch_analyzer.analyze(
            tree_paths=valid_tree_paths,
            manifest_results=manifest_results,
            collector=self.collector,
        )

        return self._build_result(
            total_files=len(raw_tree),
            inspected_files=self.budget.inspected_files_count,
            ignored_files=ignored_count,
            languages=languages,
            frameworks=frameworks,
            architecture=architecture,
            manifest_results=manifest_results,
        )

    def _parse_manifest_content(
        self,
        path: str,
        content: str,
        known_lockfiles: set[str],
    ) -> ManifestParserResult | None:
        """Chuyển tiếp tới parser chuyên biệt tùy theo loại manifest."""
        lower = path.lower()
        filename = lower.split("/")[-1]

        # 1. Python
        if filename == "requirements.txt" or (
            filename.startswith("requirements") and filename.endswith(".txt")
        ):
            return parse_requirements_txt(content, path)
        if filename == "pyproject.toml":
            return parse_pyproject_toml(content, path)
        if filename == "pipfile":
            res = parse_pipfile(content, path)
            # Kiểm tra xem Pipfile.lock có tồn tại không
            lock_candidate = path + ".lock"
            if lock_candidate.lower() not in known_lockfiles:
                res.lockfile_missing = True
            return res
        if filename in ("setup.py", "setup.cfg"):
            return parse_setup_cfg_or_py(content, path)

        # 2. JavaScript / TypeScript
        if filename == "package.json":
            res = parse_package_json(content, path)
            # Kiểm tra lockfile tương ứng (package-lock.json, yarn.lock, pnpm-lock.yaml)
            parent_dir = path.rsplit("/", 1)[0] if "/" in path else ""
            has_lock = False
            for lock_name in ("package-lock.json", "yarn.lock", "pnpm-lock.yaml"):
                candidate = (
                    f"{parent_dir}/{lock_name}".lstrip("/") if parent_dir else lock_name
                )
                if candidate.lower() in known_lockfiles:
                    has_lock = True
                    break
            if not has_lock:
                res.lockfile_missing = True
            return res

        # 3. Java / Kotlin
        if filename == "pom.xml":
            return parse_pom_xml(content, path)
        if filename in ("build.gradle", "build.gradle.kts"):
            return parse_build_gradle(content, path)

        # 4. C# / .NET
        if filename.endswith(".csproj") or filename == "packages.config":
            return parse_dotnet_csproj(content, path)

        # 5. Go
        if filename == "go.mod":
            res = parse_go_mod(content, path)
            sum_candidate = path.replace("go.mod", "go.sum")
            if sum_candidate.lower() not in known_lockfiles:
                res.lockfile_missing = True
            return res

        # 6. Rust
        if filename == "cargo.toml":
            res = parse_cargo_toml(content, path)
            lock_candidate = path.replace("cargo.toml", "cargo.lock")
            if lock_candidate.lower() not in known_lockfiles:
                res.lockfile_missing = True
            return res

        return None

    def _build_result(
        self,
        total_files: int,
        inspected_files: int,
        ignored_files: int,
        languages: list[LanguageFinding],
        frameworks: list[FrameworkFinding],
        architecture: list[ArchitectureFinding],
        manifest_results: list[ManifestParserResult],
    ) -> dict[str, Any]:
        """Tổng hợp kết quả phân tích theo schema chuẩn."""
        all_records = self.collector.get_all()

        return {
            "repository_id": self.repository_id,
            "commit_sha": self.commit_sha,
            "analyzed_at": datetime.now(UTC).isoformat(),
            "scope": self.scope,
            "time_range": self.time_range,
            "structure": {
                "total_files": total_files,
                "inspected_files": inspected_files,
                "ignored_files": ignored_files,
            },
            "languages": [
                {
                    "name": language.name,
                    "primary": language.primary,
                    "bytes_count": language.bytes_count,
                    "percentage": language.percentage,
                    "file_count": language.file_count,
                    "evidence_count": len(language.evidence),
                }
                for language in languages
            ],
            "frameworks": [
                {
                    "name": f.name,
                    "category": f.category,
                    "ecosystem": f.ecosystem,
                    "version": f.version,
                    "status": f.status,
                    "confidence": f.confidence.value,
                    "evidence_count": len(f.evidence),
                }
                for f in frameworks
            ],
            "architecture": [
                {
                    "pattern": a.pattern,
                    "name": a.name,
                    "description": a.description,
                    "confidence": a.confidence.value,
                    "evidence_count": len(a.evidence),
                }
                for a in architecture
            ],
            "evidence": [record.model_dump(mode="json") for record in all_records],
            "budget": self.budget.summary(),
        }
