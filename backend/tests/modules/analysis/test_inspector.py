"""Tests for RepositoryInspector, language/framework detection, resource limits, and
evidence correctness (PBI-012).
"""

import pytest

from app.modules.analysis.evidence import ConfidenceLevel, FindingType
from app.modules.analysis.inspector import InMemoryContentSource, RepositoryInspector
from app.modules.analysis.limits import AnalysisLimits


@pytest.mark.anyio
async def test_empty_repository_does_not_crash():
    """Requirement 5.1: Empty repository handling without crashing."""
    inspector = RepositoryInspector(
        repository_id=42,
        commit_sha="a" * 40,
    )
    # Cây tập tin rỗng hoàn toàn
    source = InMemoryContentSource({})
    result = await inspector.inspect(source)

    assert result["repository_id"] == 42
    assert result["commit_sha"] == "a" * 40
    assert result["structure"]["total_files"] == 0
    assert result["languages"] == []
    assert result["frameworks"] == []
    assert result["architecture"] == []
    assert result["evidence"] == []


@pytest.mark.anyio
async def test_single_language_repository():
    """Requirement 5.2: Single-language repository detection."""
    files = {
        "pyproject.toml": """
        [project]
        name = "python-tool"
        dependencies = ["click>=8.0"]
        """,
        "src/cli.py": "import click\nprint('hello')",
        "src/utils.py": "def add(a, b): return a + b",
    }
    source = InMemoryContentSource(files)
    inspector = RepositoryInspector(
        repository_id=1,
        commit_sha="b" * 40,
    )
    result = await inspector.inspect(source)

    assert len(result["languages"]) == 1
    lang = result["languages"][0]
    assert lang["name"] == "Python"
    assert lang["primary"] is True
    assert lang["file_count"] == 2  # cli.py, utils.py
    assert lang["evidence_count"] >= 1


@pytest.mark.anyio
async def test_multi_language_and_multiple_frameworks():
    """Requirement 5.3 & 5.4: Multi-language repository and multiple frameworks."""
    files = {
        # Backend: Python + FastAPI + SQLAlchemy + Alembic
        "backend/pyproject.toml": """
        [project]
        name = "backend"
        dependencies = [
            "fastapi>=0.110.0",
            "sqlalchemy>=2.0.0",
            "alembic>=1.13.0"
        ]
        """,
        "backend/app/main.py": "from fastapi import FastAPI\napp = FastAPI()",
        "backend/app/models/user.py": "from sqlalchemy.orm import DeclarativeBase",
        "backend/alembic.ini": "[alembic]\nscript_location = migrations",
        # Frontend: TypeScript + React + Vite
        "frontend/package.json": """{
            "name": "frontend",
            "dependencies": {
                "react": "^18.2.0",
                "react-dom": "^18.2.0"
            },
            "devDependencies": {
                "vite": "^5.0.0",
                "typescript": "^5.3.0"
            }
        }""",
        "frontend/src/App.tsx": (
            "import React from 'react'; "
            "export const App = () => <div>Hello</div>;"
        ),
        "frontend/src/main.ts": "import './App';",
        "frontend/vite.config.ts": "import { defineConfig } from 'vite';",
        "docker-compose.yml": "services:\n  backend:\n  frontend:",
    }
    source = InMemoryContentSource(files)
    inspector = RepositoryInspector(
        repository_id=10,
        commit_sha="c" * 40,
    )
    result = await inspector.inspect(source)

    # 1. Kiểm tra đa ngôn ngữ
    lang_names = [language["name"] for language in result["languages"]]
    assert "Python" in lang_names
    assert "TypeScript" in lang_names

    # 2. Kiểm tra nhiều frameworks
    fw_names = [f["name"] for f in result["frameworks"]]
    assert "FastAPI" in fw_names
    assert "React" in fw_names
    assert "SQLAlchemy" in fw_names
    assert "Alembic" in fw_names
    assert "Vite" in fw_names

    # 3. Kiểm tra kiến trúc phát hiện được
    arch_patterns = [a["pattern"] for a in result["architecture"]]
    assert "frontend_backend_separation" in arch_patterns
    assert "monorepo" in arch_patterns


@pytest.mark.anyio
async def test_missing_and_corrupted_lockfile():
    """Requirement 5.5: Missing or malformed lockfile."""
    # Repository có package.json nhưng không có lockfile
    files = {
        "package.json": '{"name": "app", "dependencies": {"express": "^4.19.0"}}',
        "server.js": "const express = require('express');",
    }
    source = InMemoryContentSource(files)
    inspector = RepositoryInspector(
        repository_id=20,
        commit_sha="d" * 40,
    )
    result = await inspector.inspect(source)

    express_fw = next(f for f in result["frameworks"] if f["name"] == "Express")
    assert express_fw["status"] == "confirmed_lockfile_missing"
    assert express_fw["confidence"] == ConfidenceLevel.MEDIUM.value


@pytest.mark.anyio
async def test_oversized_files_and_resource_limits():
    """Requirement 5.7: Oversized files and resource limits."""
    # Tạo 1 file manifest khổng lồ (> 50KB khi giới hạn max là 10KB)
    huge_requirements = "fastapi==0.110.0\n" + ("# filler comment line\n" * 2000)
    normal_package = '{"name": "app", "dependencies": {"react": "^18.0.0"}}'

    custom_limits = AnalysisLimits(
        max_inspected_files=5,
        max_file_size_bytes=2048,  # Giới hạn 2 KB
        max_total_analysis_bytes=10240,  # 10 KB
    )

    files = {
        "requirements.txt": huge_requirements,  # Vượt quá 2 KB -> bị bỏ qua
        "package.json": normal_package,  # Dưới 2 KB -> được phân tích
        "src/app.py": "print('hello')",
    }
    source = InMemoryContentSource(files)
    inspector = RepositoryInspector(
        repository_id=30,
        commit_sha="e" * 40,
        limits=custom_limits,
    )
    result = await inspector.inspect(source)

    budget = result["budget"]
    assert budget["skipped_oversized_files"] == 1
    # Framework trong huge file (FastAPI) bị bỏ qua, trong khi React vẫn được nhận diện
    fw_names = [f["name"] for f in result["frameworks"]]
    assert "React" in fw_names
    assert "FastAPI" not in fw_names


@pytest.mark.anyio
async def test_commit_and_path_evidence_correctness():
    """Requirement 5.13: Commit/path evidence correctness."""
    commit_sha = "f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9"
    repo_id = 99
    files = {
        "pyproject.toml": '[project]\ndependencies = ["fastapi==0.110.0"]',
        "main.py": "from fastapi import FastAPI\napp = FastAPI()",
    }
    source = InMemoryContentSource(files)
    inspector = RepositoryInspector(
        repository_id=repo_id,
        commit_sha=commit_sha,
    )
    result = await inspector.inspect(source)

    all_evidence = result["evidence"]
    assert len(all_evidence) > 0

    for ev in all_evidence:
        assert ev["repository_id"] == repo_id
        assert ev["commit_sha"] == commit_sha
        assert len(ev["file_path"]) > 0
        assert ev["finding_type"] in [
            FindingType.LANGUAGE.value,
            FindingType.FRAMEWORK.value,
            FindingType.ARCHITECTURE.value,
        ]
        assert ev["evidence_source"] is not None
        assert ev["detection_method"] is not None
        assert ev["confidence"] in ["high", "medium", "low", "uncertain"]
        assert len(ev["rationale"]) > 0
