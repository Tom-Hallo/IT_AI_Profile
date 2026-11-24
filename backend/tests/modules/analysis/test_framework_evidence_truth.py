"""Regression coverage for framework detection versus verified skill attribution."""

import pytest

from app.modules.analysis.inspector import InMemoryContentSource, RepositoryInspector


@pytest.mark.anyio
async def test_fastapi_source_import_is_reported_without_claiming_authorship():
    source = InMemoryContentSource(
        {
            "backend/requirements.txt": "fastapi==0.162.0\n",
            "backend/app/main.py": ("from fastapi import FastAPI\napp = FastAPI()\n"),
        }
    )
    result = await RepositoryInspector(1, "a" * 40).inspect(source)

    assert "FastAPI" in {item["name"] for item in result["frameworks"]}
    source_evidence = [
        item
        for item in result["evidence"]
        if item["classification"] == "FastAPI"
        and item["evidence_source"] == "source_code"
    ]
    assert [item["file_path"] for item in source_evidence] == ["backend/app/main.py"]
    assert source_evidence[0]["line_number"] == 1
    assert source_evidence[0]["matched_content"] is None


@pytest.mark.anyio
async def test_vite_config_is_not_proof_of_vue():
    source = InMemoryContentSource(
        {
            "frontend/package.json": (
                '{"dependencies":{"react":"^19.0.0"},'
                '"devDependencies":{"vite":"^8.0.0"}}'
            ),
            "frontend/vite.config.ts": ("import { defineConfig } from 'vite';\n"),
            "frontend/src/App.tsx": (
                "import React from 'react';\n"
                "export default function App() { return null; }\n"
            ),
        }
    )
    result = await RepositoryInspector(2, "b" * 40).inspect(source)
    names = {item["name"] for item in result["frameworks"]}

    assert {"React", "Vite"} <= names
    assert "Vue" not in names
    assert any(
        item["classification"] == "React"
        and item["file_path"] == "frontend/src/App.tsx"
        and item["evidence_source"] == "source_code"
        for item in result["evidence"]
    )


@pytest.mark.anyio
async def test_comments_and_manifest_do_not_masquerade_as_source_imports():
    source = InMemoryContentSource(
        {
            "requirements.txt": "fastapi==0.162.0\n",
            "app.py": "# from fastapi import FastAPI\nprint('no API import')\n",
        }
    )
    result = await RepositoryInspector(3, "c" * 40).inspect(source)

    assert "FastAPI" in {item["name"] for item in result["frameworks"]}
    assert not [
        item
        for item in result["evidence"]
        if item["classification"] == "FastAPI"
        and item["evidence_source"] == "source_code"
    ]


@pytest.mark.anyio
async def test_verified_priority_selects_framework_and_architecture_samples():
    changed = "backend/app/modules/jobs/router.py"
    files = {
        "backend/requirements.txt": "fastapi==0.162.0\n",
        "backend/app/api/__init__.py": "",
        "backend/app/api/router.py": "from fastapi import APIRouter\n",
        "backend/app/db/session.py": "pass\n",
        "backend/app/workers/README.md": "# Worker",
        "backend/app/workers/worker.py": "pass\n",
        changed: "from fastapi import APIRouter\n",
    }
    files.update({f"a{i:02}.py": "pass\n" for i in range(40)})
    result = await RepositoryInspector(1, "a" * 40).inspect(
        InMemoryContentSource(files), priority_paths=frozenset({changed})
    )
    findings = result["evidence"]
    assert any(
        item["classification"] == "FastAPI"
        and item["evidence_source"] == "source_code"
        and item["file_path"] == changed
        for item in findings
    )
    assert any(
        item["classification"] == "api_service" and item["file_path"] == changed
        for item in findings
    )
    assert any(
        item["classification"] == "background_workers"
        and item["file_path"] == "backend/app/workers/worker.py"
        for item in findings
    )
