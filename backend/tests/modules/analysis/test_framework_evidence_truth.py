"""Regression coverage for framework detection versus verified skill attribution."""

import pytest

from app.modules.analysis.inspector import InMemoryContentSource, RepositoryInspector


@pytest.mark.anyio
async def test_fastapi_source_import_is_reported_without_claiming_authorship():
    source = InMemoryContentSource(
        {
            "backend/requirements.txt": "fastapi==0.162.0\n",
            "backend/app/main.py": (
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
            ),
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
            "frontend/vite.config.ts": (
                "import { defineConfig } from 'vite';\n"
            ),
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
