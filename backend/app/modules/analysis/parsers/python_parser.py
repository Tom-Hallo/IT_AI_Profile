"""Safe static parser for Python dependency manifests (PBI-012).

Parses requirements.txt, pyproject.toml, Pipfile, setup.cfg, and setup.py without
ever executing untrusted code or invoking setup scripts.
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.analysis.parsers.base import ManifestParserResult, ParsedDependency

# Thư viện tomllib tích hợp sẵn từ Python 3.11, dự phòng tomli cho phiên bản thấp hơn
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ImportError:
        tomllib = None  # type: ignore[assignment]


def parse_requirements_txt(
    content: str, path: str = "requirements.txt"
) -> ManifestParserResult:
    """Phân tích tập tin requirements.txt chuẩn theo quy chuẩn pip."""
    deps: list[ParsedDependency] = []
    lines = content.splitlines()

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        # Bỏ qua các cờ pip như -r, -i, --extra-index-url, -f
        if line.startswith(("-", "--")):
            continue

        # Cắt bỏ comment inline
        if " #" in line:
            line = line.split(" #", 1)[0].strip()

        # Tách environment markers (vd: fastapi>=0.100 ; python_version >= '3.8')
        if ";" in line:
            line = line.split(";", 1)[0].strip()

        # Bóc tách tên package (có thể kèm extras như [standard]) và phiên bản
        match = re.match(r"^([a-zA-Z0-9_\-\.]+)(?:\[[^\]]+\])?\s*([~=><!^].*)?$", line)
        if match:
            pkg_name = match.group(1).strip()
            version_spec = match.group(2).strip() if match.group(2) else None
            deps.append(
                ParsedDependency(
                    name=pkg_name,
                    version_spec=version_spec,
                    manifest_path=path,
                    line_number=idx,
                    matched_line=raw_line.strip(),
                )
            )

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="Python",
        dependencies=deps,
        is_valid=True,
    )


def parse_pyproject_toml(
    content: str, path: str = "pyproject.toml"
) -> ManifestParserResult:
    """Phân tích pyproject.toml tĩnh qua tomllib/regex mà không thực thi mã."""
    deps: list[ParsedDependency] = []
    metadata: dict[str, Any] = {}

    if tomllib is not None:
        try:
            data = tomllib.loads(content)
            # 1. PEP 621: [project.dependencies]
            project = data.get("project", {})
            if isinstance(project, dict):
                raw_deps = project.get("dependencies", [])
                if isinstance(raw_deps, list):
                    for item in raw_deps:
                        if isinstance(item, str):
                            m = re.match(
                                r"^([a-zA-Z0-9_\-\.]+)\s*([~=><!^].*)?$", item.strip()
                            )
                            if m:
                                deps.append(
                                    ParsedDependency(
                                        name=m.group(1).strip(),
                                        version_spec=m.group(2).strip()
                                        if m.group(2)
                                        else None,
                                        manifest_path=path,
                                    )
                                )
                # Optional dependencies
                opt_deps = project.get("optional-dependencies", {})
                if isinstance(opt_deps, dict):
                    for group_deps in opt_deps.values():
                        if isinstance(group_deps, list):
                            for item in group_deps:
                                if isinstance(item, str):
                                    m = re.match(
                                        r"^([a-zA-Z0-9_\-\.]+)\s*([~=><!^].*)?$",
                                        item.strip(),
                                    )
                                    if m:
                                        deps.append(
                                            ParsedDependency(
                                                name=m.group(1).strip(),
                                                version_spec=m.group(2).strip()
                                                if m.group(2)
                                                else None,
                                                is_dev=True,
                                                manifest_path=path,
                                            )
                                        )

            # 2. Poetry: [tool.poetry.dependencies]
            tool = data.get("tool", {})
            if isinstance(tool, dict):
                poetry = tool.get("poetry", {})
                if isinstance(poetry, dict):
                    p_deps = poetry.get("dependencies", {})
                    if isinstance(p_deps, dict):
                        for k, v in p_deps.items():
                            if k.lower() != "python":
                                ver = v if isinstance(v, str) else None
                                deps.append(
                                    ParsedDependency(
                                        name=k,
                                        version_spec=ver,
                                        manifest_path=path,
                                    )
                                )

            return ManifestParserResult(
                manifest_path=path,
                ecosystem="Python",
                dependencies=deps,
                is_valid=True,
                metadata=metadata,
            )
        except (ValueError, TypeError) as exc:
            return ManifestParserResult(
                manifest_path=path,
                ecosystem="Python",
                dependencies=[],
                is_valid=False,
                error_message=f"Lỗi cú pháp TOML: {exc}",
            )

    # Dự phòng bóc tách bằng regex dòng lệnh an toàn nếu không có thư viện toml
    lines = content.splitlines()
    in_deps = False
    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_deps = "dependencies" in line.lower()
            continue
        if in_deps:
            m = re.match(
                (
                    r'^["\']?([a-zA-Z0-9_\-\.]+)["\']?'
                    r'\s*(=|~=|>=|<=|>|<)?'
                    r'\s*["\']?([^"\']*)?["\']?,?$'
                ),
                line,
            )
            if m:
                deps.append(
                    ParsedDependency(
                        name=m.group(1),
                        version_spec=m.group(3) if m.group(3) else None,
                        manifest_path=path,
                        line_number=idx,
                    )
                )

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="Python",
        dependencies=deps,
        is_valid=True,
    )


def parse_pipfile(content: str, path: str = "Pipfile") -> ManifestParserResult:
    """Phân tích Pipfile bằng quy tắc tĩnh an toàn."""
    deps: list[ParsedDependency] = []
    current_section: str | None = None

    for idx, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip().lower()
            continue

        if current_section in ("packages", "dev-packages"):
            parts = line.split("=", 1)
            pkg_name = parts[0].strip().strip('"').strip("'")
            ver = parts[1].strip().strip('"').strip("'") if len(parts) > 1 else None
            deps.append(
                ParsedDependency(
                    name=pkg_name,
                    version_spec=ver if ver != "*" else None,
                    is_dev=(current_section == "dev-packages"),
                    manifest_path=path,
                    line_number=idx,
                    matched_line=line,
                )
            )

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="Python",
        dependencies=deps,
        is_valid=True,
    )


def parse_setup_cfg_or_py(content: str, path: str) -> ManifestParserResult:
    """Phân tích tĩnh setup.cfg hoặc setup.py mà KHÔNG chạy setup.py."""
    deps: list[ParsedDependency] = []
    # Tìm install_requires = [...] bằng regex an toàn
    match = re.search(r"install_requires\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if match:
        block = match.group(1)
        for line in block.splitlines():
            pkg = line.strip().strip(",").strip('"').strip("'")
            if pkg and not pkg.startswith("#"):
                m = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*([~=><!^].*)?$", pkg)
                if m:
                    deps.append(
                        ParsedDependency(
                            name=m.group(1).strip(),
                            version_spec=m.group(2).strip() if m.group(2) else None,
                            manifest_path=path,
                        )
                    )

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="Python",
        dependencies=deps,
        is_valid=True,
    )
