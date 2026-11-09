"""Safe static parsers for JVM, .NET, Go, and Rust manifests (PBI-012)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from app.modules.analysis.parsers.base import ManifestParserResult, ParsedDependency


def parse_pom_xml(content: str, path: str = "pom.xml") -> ManifestParserResult:
    """Phân tích tập tin Maven pom.xml một cách an toàn (không expand XML entities)."""
    deps: list[ParsedDependency] = []
    try:
        root = ET.fromstring(content)
        # Bỏ qua XML namespace nếu có
        for elem in root.iter():
            if elem.tag.endswith("dependency"):
                group_id = ""
                artifact_id = ""
                version = None
                scope = ""
                for child in elem:
                    tag_clean = (
                        child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    )
                    text = (child.text or "").strip()
                    if tag_clean == "groupId":
                        group_id = text
                    elif tag_clean == "artifactId":
                        artifact_id = text
                    elif tag_clean == "version":
                        version = text
                    elif tag_clean == "scope":
                        scope = text

                if artifact_id:
                    full_name = f"{group_id}:{artifact_id}" if group_id else artifact_id
                    deps.append(
                        ParsedDependency(
                            name=full_name,
                            version_spec=version,
                            is_dev=(scope in ("test", "provided")),
                            manifest_path=path,
                        )
                    )

        return ManifestParserResult(
            manifest_path=path,
            ecosystem="Java/Kotlin",
            dependencies=deps,
            is_valid=True,
        )
    except (ET.ParseError, ValueError, TypeError) as exc:
        return ManifestParserResult(
            manifest_path=path,
            ecosystem="Java/Kotlin",
            dependencies=[],
            is_valid=False,
            error_message=f"Lỗi cú pháp XML trong pom.xml: {exc}",
        )


def parse_build_gradle(
    content: str, path: str = "build.gradle"
) -> ManifestParserResult:
    """Phân tích tĩnh tập tin Gradle build.gradle hoặc build.gradle.kts."""
    deps: list[ParsedDependency] = []
    # Tìm implementation("org.springframework.boot:spring-boot-starter-web:3.0.0") hoặc
    # '...'
    pattern = re.compile(
        r"(?:implementation|api|compileOnly|testImplementation)"
        r"""\s*\(?['"]([^'"]+)['"]\)?"""
    )
    for idx, line in enumerate(content.splitlines(), start=1):
        m = pattern.search(line)
        if m:
            dep_str = m.group(1).strip()
            parts = dep_str.split(":")
            if len(parts) >= 2:
                name = f"{parts[0]}:{parts[1]}"
                ver = parts[2] if len(parts) > 2 else None
                is_dev = "test" in line.lower()
                deps.append(
                    ParsedDependency(
                        name=name,
                        version_spec=ver,
                        is_dev=is_dev,
                        manifest_path=path,
                        line_number=idx,
                    )
                )

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="Java/Kotlin",
        dependencies=deps,
        is_valid=True,
    )


def parse_dotnet_csproj(content: str, path: str) -> ManifestParserResult:
    """Phân tích tập tin C# .csproj bằng XML parser an toàn."""
    deps: list[ParsedDependency] = []
    try:
        root = ET.fromstring(content)
        for elem in root.iter():
            tag_clean = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag_clean == "PackageReference":
                pkg_name = elem.attrib.get("Include") or elem.attrib.get("Update")
                ver = elem.attrib.get("Version")
                if pkg_name:
                    deps.append(
                        ParsedDependency(
                            name=pkg_name,
                            version_spec=ver,
                            manifest_path=path,
                        )
                    )

        return ManifestParserResult(
            manifest_path=path,
            ecosystem="C#/.NET",
            dependencies=deps,
            is_valid=True,
        )
    except (ET.ParseError, ValueError, TypeError) as exc:
        return ManifestParserResult(
            manifest_path=path,
            ecosystem="C#/.NET",
            dependencies=[],
            is_valid=False,
            error_message=f"Lỗi XML trong {path}: {exc}",
        )


def parse_go_mod(content: str, path: str = "go.mod") -> ManifestParserResult:
    """Phân tích tĩnh go.mod."""
    deps: list[ParsedDependency] = []
    in_require_block = False

    for idx, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue

        if line == "require (" or line.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block and line == ")":
            in_require_block = False
            continue

        if in_require_block or line.startswith("require "):
            cleaned = line.removeprefix("require ").strip()
            parts = cleaned.split()
            if len(parts) >= 2:
                deps.append(
                    ParsedDependency(
                        name=parts[0],
                        version_spec=parts[1],
                        manifest_path=path,
                        line_number=idx,
                    )
                )

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="Go",
        dependencies=deps,
        is_valid=True,
    )


def parse_cargo_toml(content: str, path: str = "Cargo.toml") -> ManifestParserResult:
    """Phân tích tĩnh Cargo.toml cho ngôn ngữ Rust."""
    deps: list[ParsedDependency] = []
    in_deps = False

    for idx, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_deps = line.lower() in (
                "[dependencies]",
                "[dev-dependencies]",
                "[workspace.dependencies]",
            )
            continue
        if in_deps and "=" in line:
            parts = line.split("=", 1)
            pkg_name = parts[0].strip().strip('"').strip("'")
            ver = parts[1].strip().strip('"').strip("'")
            deps.append(
                ParsedDependency(
                    name=pkg_name,
                    version_spec=ver,
                    manifest_path=path,
                    line_number=idx,
                )
            )

    return ManifestParserResult(
        manifest_path=path,
        ecosystem="Rust",
        dependencies=deps,
        is_valid=True,
    )
