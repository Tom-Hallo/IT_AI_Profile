"""Programming language detection engine.

Multi-source verifiable evidence (PBI-012).

Detects languages combining:
1. Dependency manifests (pyproject.toml, package.json, pom.xml, go.mod, etc.)
2. Project configuration files (tsconfig.json, etc.)
3. GitHub language byte-count metadata
4. Source file extensions across non-ignored files

Does not rely solely on extensions when stronger evidence is present.
Handles empty repositories gracefully without crashing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.analysis.evidence import (
    ConfidenceLevel,
    DetectionMethod,
    EvidenceCollector,
    EvidenceRecord,
    EvidenceSource,
    FindingType,
)

# Bản đồ ánh xạ phần mở rộng file sang ngôn ngữ lập trình chuẩn
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".pyi": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".php": "PHP",
    ".rb": "Ruby",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sass": "CSS",
    ".less": "CSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".swift": "Swift",
    ".dart": "Dart",
    ".scala": "Scala",
}

# Bản đồ các manifest/config đặc trưng cho ngôn ngữ (bằng chứng mạnh hơn extension)
MANIFEST_TO_LANGUAGE: dict[str, str] = {
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "pipfile": "Python",
    "setup.py": "Python",
    "setup.cfg": "Python",
    "tsconfig.json": "TypeScript",
    "pom.xml": "Java",
    "build.gradle": "Java/Kotlin",
    "build.gradle.kts": "Kotlin",
    "go.mod": "Go",
    "cargo.toml": "Rust",
    "composer.json": "PHP",
    "gemfile": "Ruby",
}


@dataclass
class LanguageFinding:
    """Kết quả phát hiện ngôn ngữ lập trình với số liệu và bằng chứng đi kèm."""

    name: str
    primary: bool = False
    bytes_count: int | None = None
    percentage: float | None = None
    file_count: int = 0
    evidence: list[EvidenceRecord] = field(default_factory=list)


class LanguageDetector:
    """Bộ nhận diện ngôn ngữ dựa trên bằng chứng đa nguồn."""

    def __init__(self, repository_id: int, commit_sha: str) -> None:
        self.repository_id = repository_id
        self.commit_sha = commit_sha

    def detect(
        self,
        tree_paths: list[str],
        file_sizes: dict[str, int],
        github_languages: dict[str, int] | None = None,
        manifest_paths: set[str] | None = None,
        collector: EvidenceCollector | None = None,
    ) -> list[LanguageFinding]:
        """Phát hiện các ngôn ngữ lập trình trong repository."""
        if not tree_paths:
            # Xử lý an toàn cho empty repository
            return []

        lang_file_counts: dict[str, int] = {}
        lang_bytes: dict[str, int] = {}
        manifest_paths = manifest_paths or set()

        # 1. Thu thập bằng chứng từ cấu hình và manifest (Bằng chứng có độ tin cậy cao
        # nhất)
        for m_path in manifest_paths:
            fname = m_path.lower().split("/")[-1]
            if fname in MANIFEST_TO_LANGUAGE:
                lang = MANIFEST_TO_LANGUAGE[fname]
                if collector is not None:
                    record = EvidenceRecord(
                        repository_id=self.repository_id,
                        commit_sha=self.commit_sha,
                        file_path=m_path,
                        finding_type=FindingType.LANGUAGE,
                        classification=lang,
                        evidence_source=(
                            EvidenceSource.MANIFEST
                            if "config" not in fname
                            else EvidenceSource.CONFIGURATION
                        ),
                        detection_method=DetectionMethod.MANIFEST_PARSING,
                        confidence=ConfidenceLevel.HIGH,
                        confidence_score=1.0,
                        rationale=(
                            f"Phát hiện ngôn ngữ {lang} thông qua tập tin "
                            f"cấu hình/manifest: {m_path}"
                        ),
                    )
                    collector.add(record)

        # 2. Duyệt qua danh sách file trong tree
        for path in tree_paths:
            lower_path = path.lower()
            dot_idx = lower_path.rfind(".")
            if dot_idx != -1:
                ext = lower_path[dot_idx:]
                if ext in EXTENSION_TO_LANGUAGE:
                    lang = EXTENSION_TO_LANGUAGE[ext]
                    lang_file_counts[lang] = lang_file_counts.get(lang, 0) + 1
                    fsize = file_sizes.get(path, 0)
                    lang_bytes[lang] = lang_bytes.get(lang, 0) + fsize

                    if collector is not None and lang_file_counts[lang] <= 3:
                        # Ghi nhận bằng chứng mẫu (tối đa 3 file đầu tiên cho mỗi ngôn
                        # ngữ)
                        record = EvidenceRecord(
                            repository_id=self.repository_id,
                            commit_sha=self.commit_sha,
                            file_path=path,
                            finding_type=FindingType.LANGUAGE,
                            classification=lang,
                            evidence_source=EvidenceSource.SOURCE_CODE,
                            detection_method=DetectionMethod.EXTENSION_EVIDENCE,
                            confidence=ConfidenceLevel.HIGH,
                            confidence_score=0.9,
                            rationale=f"Tập tin mã nguồn phần mở rộng '{ext}': {path}",
                        )
                        collector.add(record)

        # 3. Kết hợp với metadata GitHub languages nếu có
        if github_languages:
            for g_lang, g_bytes in github_languages.items():
                if g_bytes > 0:
                    lang_bytes[g_lang] = max(lang_bytes.get(g_lang, 0), g_bytes)
                    if g_lang not in lang_file_counts:
                        lang_file_counts[g_lang] = 1

                    if collector is not None:
                        record = EvidenceRecord(
                            repository_id=self.repository_id,
                            commit_sha=self.commit_sha,
                            file_path="github_api:languages",
                            finding_type=FindingType.LANGUAGE,
                            classification=g_lang,
                            evidence_source=EvidenceSource.METADATA,
                            detection_method=DetectionMethod.METADATA_EXTRACTION,
                            confidence=ConfidenceLevel.HIGH,
                            confidence_score=0.95,
                            rationale=(
                                "Metadata thống kê dung lượng ngôn ngữ "
                                f"từ GitHub: {g_bytes} bytes"
                            ),
                        )
                        collector.add(record)

        if not lang_file_counts:
            return []

        # 4. Tính toán tỷ lệ phần trăm và xác định primary language
        total_bytes = sum(lang_bytes.values())
        max_bytes = -1
        primary_lang = ""

        # Xác định ngôn ngữ chính dựa theo dung lượng hoặc số lượng file
        for lang, b_count in lang_bytes.items():
            if b_count > max_bytes:
                max_bytes = b_count
                primary_lang = lang

        if not primary_lang and lang_file_counts:
            primary_lang = max(lang_file_counts.items(), key=lambda item: item[1])[0]

        findings: list[LanguageFinding] = []
        for lang in sorted(
            lang_file_counts.keys(),
            key=lambda language: lang_bytes.get(language, 0),
            reverse=True,
        ):
            b_count = lang_bytes.get(lang, 0)
            percentage = (
                round((b_count / total_bytes) * 100.0, 2) if total_bytes > 0 else None
            )
            ev = (
                collector.filter_by_classification(lang)
                if collector is not None
                else []
            )
            findings.append(
                LanguageFinding(
                    name=lang,
                    primary=(lang == primary_lang),
                    bytes_count=b_count if b_count > 0 else None,
                    percentage=percentage,
                    file_count=lang_file_counts[lang],
                    evidence=ev,
                )
            )

        return findings
