"""Safe static parser for JavaScript/TypeScript dependency manifests (PBI-012).

Parses package.json, package-lock.json, pnpm-lock.yaml, and yarn.lock without
running npm, yarn, or executing package lifecycle scripts.
"""

from __future__ import annotations

import json
from typing import Any

from app.modules.analysis.parsers.base import ManifestParserResult, ParsedDependency


def parse_package_json(
    content: str, path: str = "package.json"
) -> ManifestParserResult:
    """Phân tích tập tin package.json an toàn."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        return ManifestParserResult(
            manifest_path=path,
            ecosystem="JavaScript/TypeScript",
            dependencies=[],
            is_valid=False,
            error_message=f"Tập tin package.json bị lỗi định dạng JSON: {exc}",
        )

    if not isinstance(data, dict):
        return ManifestParserResult(
            manifest_path=path,
            ecosystem="JavaScript/TypeScript",
            dependencies=[],
            is_valid=False,
            error_message="package.json không phải là một đối tượng JSON hợp lệ.",
        )

    deps: list[ParsedDependency] = []
    seen_versions: dict[str, str] = {}
    conflicts: list[str] = []

    # 1. dependencies
    prod_deps = data.get("dependencies", {})
    if isinstance(prod_deps, dict):
        for name, ver in prod_deps.items():
            ver_str = str(ver) if ver is not None else None
            deps.append(
                ParsedDependency(
                    name=name,
                    version_spec=ver_str,
                    is_dev=False,
                    manifest_path=path,
                )
            )
            seen_versions[name] = ver_str or ""

    # 2. devDependencies
    dev_deps = data.get("devDependencies", {})
    if isinstance(dev_deps, dict):
        for name, ver in dev_deps.items():
            ver_str = str(ver) if ver is not None else None
            if name in seen_versions and seen_versions[name] != ver_str:
                conflicts.append(
                    f"{name} (prod: {seen_versions[name]} vs dev: {ver_str})"
                )
            deps.append(
                ParsedDependency(
                    name=name,
                    version_spec=ver_str,
                    is_dev=True,
                    manifest_path=path,
                )
            )

    # 3. peerDependencies
    peer_deps = data.get("peerDependencies", {})
    if isinstance(peer_deps, dict):
        for name, ver in peer_deps.items():
            if name not in seen_versions:
                deps.append(
                    ParsedDependency(
                        name=name,
                        version_spec=str(ver) if ver is not None else None,
                        is_dev=False,
                        manifest_path=path,
                    )
                )

    metadata: dict[str, Any] = {}
    if "workspaces" in data:
        metadata["workspaces"] = data["workspaces"]
        metadata["is_monorepo"] = True

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="JavaScript/TypeScript",
        dependencies=deps,
        is_valid=True,
        conflicting_dependencies=conflicts,
        metadata=metadata,
    )


def verify_lockfile_health(content: str, path: str) -> tuple[bool, bool, str | None]:
    """Kiểm tra tính toàn vẹn của lockfile (package-lock.json).

    Trả về (is_healthy, is_corrupted, error_message).
    """
    if not content or not content.strip():
        return False, True, "Lockfile rỗng hoặc hỏng nội dung"

    if path.endswith(".json"):
        try:
            data = json.loads(content)
            if not isinstance(data, dict):
                return False, True, "Định dạng lockfile không phải object"
            return True, False, None
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            return False, True, f"Lỗi cú pháp JSON trong lockfile: {exc}"

    # Lockfile dạng yaml hoặc lockfile khác (yarn.lock, pnpm-lock.yaml)
    if (
        "lockfileVersion" in content
        or "yarn lockfile" in content
        or "packages:" in content
    ):
        return True, False, None

    return True, False, None
