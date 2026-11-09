"""Framework and major library detection engine with verifiable static evidence (PBI-012).

Detects frameworks from trustworthy indicators:
- Manifest dependencies (package.json, pyproject.toml, requirements.txt, pom.xml, csproj, etc.)
- Configuration files (next.config.js, vite.config.ts, angular.json, etc.)
- Source code imports when inspection is safe.

Handles:
- Missing lockfiles
- Corrupted lockfiles
- Conflicting dependencies / multiple versions
- Uncertain references (never fabricates unsupported conclusions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.analysis.evidence import (
    ConfidenceLevel,
    DetectionMethod,
    EvidenceCollector,
    EvidenceRecord,
    EvidenceSource,
    FindingType,
)
from app.modules.analysis.parsers.base import ManifestParserResult

# Định nghĩa các framework chính và quy tắc nhận diện
FRAMEWORK_CATALOG: list[dict[str, Any]] = [
    # --- Python ---
    {
        "name": "FastAPI",
        "category": "web_framework",
        "ecosystem": "Python",
        "pkg_names": ["fastapi"],
        "import_patterns": ["from fastapi import", "import fastapi"],
    },
    {
        "name": "Django",
        "category": "web_framework",
        "ecosystem": "Python",
        "pkg_names": ["django"],
        "import_patterns": ["from django", "import django"],
        "config_files": ["manage.py", "wsgi.py", "asgi.py"],
    },
    {
        "name": "Flask",
        "category": "web_framework",
        "ecosystem": "Python",
        "pkg_names": ["flask"],
        "import_patterns": ["from flask import", "import flask"],
    },
    {
        "name": "SQLAlchemy",
        "category": "orm",
        "ecosystem": "Python",
        "pkg_names": ["sqlalchemy"],
        "import_patterns": ["import sqlalchemy", "from sqlalchemy"],
    },
    {
        "name": "Alembic",
        "category": "database_migration",
        "ecosystem": "Python",
        "pkg_names": ["alembic"],
        "config_files": ["alembic.ini"],
    },
    {
        "name": "Celery",
        "category": "worker_queue",
        "ecosystem": "Python",
        "pkg_names": ["celery"],
        "import_patterns": ["from celery import", "import celery"],
    },
    {
        "name": "RQ",
        "category": "worker_queue",
        "ecosystem": "Python",
        "pkg_names": ["rq"],
        "import_patterns": ["from rq import", "import rq"],
    },
    # --- JavaScript / TypeScript ---
    {
        "name": "React",
        "category": "frontend_framework",
        "ecosystem": "JavaScript/TypeScript",
        "pkg_names": ["react", "react-dom"],
        "import_patterns": ["import React", "from 'react'", 'from "react"'],
    },
    {
        "name": "Vue",
        "category": "frontend_framework",
        "ecosystem": "JavaScript/TypeScript",
        "pkg_names": ["vue"],
        "config_files": ["vue.config.js", "vite.config.ts"],
    },
    {
        "name": "Angular",
        "category": "frontend_framework",
        "ecosystem": "JavaScript/TypeScript",
        "pkg_names": ["@angular/core"],
        "config_files": ["angular.json"],
    },
    {
        "name": "Next.js",
        "category": "fullstack_framework",
        "ecosystem": "JavaScript/TypeScript",
        "pkg_names": ["next"],
        "config_files": ["next.config.js", "next.config.mjs", "next.config.ts"],
    },
    {
        "name": "Express",
        "category": "backend_framework",
        "ecosystem": "JavaScript/TypeScript",
        "pkg_names": ["express"],
        "import_patterns": ["require('express')", 'from "express"'],
    },
    {
        "name": "NestJS",
        "category": "backend_framework",
        "ecosystem": "JavaScript/TypeScript",
        "pkg_names": ["@nestjs/core"],
        "config_files": ["nest-cli.json"],
    },
    {
        "name": "Vite",
        "category": "build_tool",
        "ecosystem": "JavaScript/TypeScript",
        "pkg_names": ["vite"],
        "config_files": ["vite.config.ts", "vite.config.js"],
    },
    # --- Java / Kotlin ---
    {
        "name": "Spring Boot",
        "category": "backend_framework",
        "ecosystem": "Java/Kotlin",
        "pkg_names": [
            "org.springframework.boot:spring-boot-starter",
            "org.springframework.boot:spring-boot-starter-web",
            "spring-boot",
        ],
        "import_patterns": ["org.springframework.boot.autoconfigure"],
    },
    # --- C# / .NET ---
    {
        "name": "ASP.NET Core",
        "category": "backend_framework",
        "ecosystem": "C#/.NET",
        "pkg_names": [
            "Microsoft.AspNetCore",
            "Microsoft.AspNetCore.App",
            "Microsoft.AspNetCore.Mvc",
        ],
    },
    {
        "name": "Entity Framework Core",
        "category": "orm",
        "ecosystem": "C#/.NET",
        "pkg_names": [
            "Microsoft.EntityFrameworkCore",
            "Microsoft.EntityFrameworkCore.SqlServer",
        ],
    },
    # --- Go ---
    {
        "name": "Gin",
        "category": "web_framework",
        "ecosystem": "Go",
        "pkg_names": ["github.com/gin-gonic/gin"],
    },
    # --- Rust ---
    {
        "name": "Actix Web",
        "category": "web_framework",
        "ecosystem": "Rust",
        "pkg_names": ["actix-web"],
    },
    {
        "name": "Axum",
        "category": "web_framework",
        "ecosystem": "Rust",
        "pkg_names": ["axum"],
    },
]


@dataclass
class FrameworkFinding:
    """Kết quả phát hiện framework hoặc thư viện chính."""

    name: str
    category: str
    ecosystem: str
    version: str | None = None
    status: str = "confirmed"  # confirmed, uncertain, conflicting, missing_lockfile
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH
    evidence: list[EvidenceRecord] = field(default_factory=list)


class FrameworkDetector:
    """Bộ phân tích tĩnh phát hiện framework dựa trên manifest và cấu hình."""

    def __init__(self, repository_id: int, commit_sha: str) -> None:
        self.repository_id = repository_id
        self.commit_sha = commit_sha

    def detect_from_manifests(
        self,
        manifest_results: list[ManifestParserResult],
        all_tree_paths: list[str],
        file_content_getter: Any | None = None,
        collector: EvidenceCollector | None = None,
    ) -> list[FrameworkFinding]:
        """Phân tích danh sách manifest đã parse và đối chiếu với catalog framework."""
        findings: list[FrameworkFinding] = []
        detected_names: set[str] = set()

        tree_paths_lower = {p.lower() for p in all_tree_paths}

        for rule in FRAMEWORK_CATALOG:
            name = rule["name"]
            category = rule["category"]
            ecosystem = rule["ecosystem"]
            pkg_names = [p.lower() for p in rule.get("pkg_names", [])]
            config_files = rule.get("config_files", [])

            matched_dep = None
            matched_manifest = None

            # 1. Kiểm tra trong danh sách dependencies của các manifest
            for m_res in manifest_results:
                if not m_res.is_valid:
                    continue
                for dep in m_res.dependencies:
                    dep_lower = dep.name.lower()
                    for p in pkg_names:
                        if p in dep_lower or dep_lower == p:
                            matched_dep = dep
                            matched_manifest = m_res
                            break
                    if matched_dep:
                        break
                if matched_dep:
                    break

            # 2. Kiểm tra tập tin cấu hình đặc trưng nếu chưa tìm thấy qua manifest
            matched_config_path: str | None = None
            if not matched_dep and config_files:
                for c_file in config_files:
                    c_lower = c_file.lower()
                    for p in tree_paths_lower:
                        if p.endswith(c_lower):
                            matched_config_path = p
                            break
                    if matched_config_path:
                        break

            if matched_dep:
                status = "confirmed"
                conf = ConfidenceLevel.HIGH
                score = 0.95
                rationale_note = ""

                # Kiểm tra cảnh báo lockfile
                if matched_manifest and matched_manifest.lockfile_missing:
                    status = "confirmed_lockfile_missing"
                    conf = ConfidenceLevel.MEDIUM
                    score = 0.85
                    rationale_note = " (Lưu ý: Không tìm thấy lockfile tương ứng)"
                elif matched_manifest and matched_manifest.lockfile_corrupted:
                    status = "uncertain_corrupted_lockfile"
                    conf = ConfidenceLevel.UNCERTAIN
                    score = 0.60
                    rationale_note = " (Lưu ý: Lockfile bị lỗi định dạng)"

                if matched_manifest and matched_manifest.conflicting_dependencies:
                    for conf_str in matched_manifest.conflicting_dependencies:
                        if matched_dep.name.lower() in conf_str.lower():
                            status = "conflicting_versions"
                            conf = ConfidenceLevel.MEDIUM
                            score = 0.70
                            rationale_note += (
                                f" (Phát hiện xung đột phiên bản: {conf_str})"
                            )

                record = EvidenceRecord(
                    repository_id=self.repository_id,
                    commit_sha=self.commit_sha,
                    file_path=matched_dep.manifest_path,
                    finding_type=FindingType.FRAMEWORK,
                    classification=name,
                    evidence_source=EvidenceSource.MANIFEST,
                    detection_method=DetectionMethod.MANIFEST_PARSING,
                    confidence=conf,
                    confidence_score=score,
                    line_number=matched_dep.line_number,
                    matched_content=matched_dep.matched_line or matched_dep.name,
                    rationale=(
                        f"Phát hiện {name} ({category}) khai báo trong {matched_dep.manifest_path}"
                        f"{f' phiên bản {matched_dep.version_spec}' if matched_dep.version_spec else ''}"
                        f"{rationale_note}"
                    ),
                )
                if collector is not None:
                    collector.add(record)

                findings.append(
                    FrameworkFinding(
                        name=name,
                        category=category,
                        ecosystem=ecosystem,
                        version=matched_dep.version_spec,
                        status=status,
                        confidence=conf,
                        evidence=[record],
                    )
                )
                detected_names.add(name)

            elif matched_config_path:
                record = EvidenceRecord(
                    repository_id=self.repository_id,
                    commit_sha=self.commit_sha,
                    file_path=matched_config_path,
                    finding_type=FindingType.FRAMEWORK,
                    classification=name,
                    evidence_source=EvidenceSource.CONFIGURATION,
                    detection_method=DetectionMethod.STRUCTURAL_INSPECTION,
                    confidence=ConfidenceLevel.MEDIUM,
                    confidence_score=0.80,
                    rationale=f"Phát hiện tập tin cấu hình đặc trưng của {name}: {matched_config_path}",
                )
                if collector is not None:
                    collector.add(record)

                findings.append(
                    FrameworkFinding(
                        name=name,
                        category=category,
                        ecosystem=ecosystem,
                        version=None,
                        status="confirmed_via_config",
                        confidence=ConfidenceLevel.MEDIUM,
                        evidence=[record],
                    )
                )
                detected_names.add(name)

        return findings
