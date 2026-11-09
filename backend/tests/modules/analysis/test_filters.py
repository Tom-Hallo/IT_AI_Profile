"""Tests for file filtering, path traversal prevention, and exclusion rules (PBI-012).
"""

from app.modules.analysis.filters import (
    is_ignored_path,
    is_manifest_file,
    is_safe_path,
    normalize_posix_path,
)


def test_path_traversal_prevention():
    """Requirement 5.11: Path traversal and symlink abuse prevention."""
    malicious_paths = [
        "../etc/passwd",
        "../../shadow",
        "foo/../../bar/secret.env",
        "/etc/nginx/nginx.conf",
        "\\Windows\\System32\\cmd.exe",
        "C:\\Users\\secret.txt",
        "D:/projects/repo",
        "safe_dir/../secret.pem",
        "file\x00with_null.py",
        "/root/.ssh/id_rsa",
    ]
    for path in malicious_paths:
        assert not is_safe_path(path), f"Path should be rejected as unsafe: {path}"

    safe_paths = [
        "src/main.py",
        "app/controllers/user_controller.ts",
        "package.json",
        "backend/pyproject.toml",
        "frontend/src/App.tsx",
        ".github/workflows/ci.yml",
    ]
    for path in safe_paths:
        assert is_safe_path(path), f"Path should be accepted as safe: {path}"


def test_generated_vendor_and_binary_exclusion():
    """Requirement 5.6: Generated/vendor/binary exclusion."""
    excluded_paths = [
        # Vendor & dependency directories
        "node_modules/react/index.js",
        "frontend/node_modules/axios/index.js",
        "vendor/bundle/gems/rails.rb",
        "backend/.venv/lib/python3.12/site-packages/fastapi/main.py",
        ".venv/bin/activate",
        "venv/Scripts/python.exe",
        "packages/external/lib.js",
        # Build outputs & caches
        "dist/bundle.js",
        "build/static/js/main.chunk.js",
        "target/classes/App.class",
        "bin/Debug/net8.0/app.dll",
        "obj/Debug/net8.0/app.pdb",
        ".next/server/pages/index.js",
        "__pycache__/service.cpython-312.pyc",
        ".pytest_cache/v/cache/nodeids",
        ".ruff_cache/content/hash",
        # Binaries & media
        "assets/logo.png",
        "public/hero.jpg",
        "docs/architecture.pdf",
        "releases/app.zip",
        "drivers/driver.exe",
        "native/libhelper.so",
        # Minified code
        "static/js/app.min.js",
        "styles/bundle.min.css",
        "frontend/src/client.generated.ts",
    ]
    for path in excluded_paths:
        assert is_ignored_path(path), f"Path should be ignored: {path}"

    included_paths = [
        "app/main.py",
        "src/components/Header.tsx",
        "package.json",
        "pyproject.toml",
        "backend/alembic.ini",
        "migrations/versions/001_init.py",
        "pom.xml",
        "Cargo.toml",
        "go.mod",
        ".github/workflows/ci.yml",
    ]
    for path in included_paths:
        assert not is_ignored_path(path), f"Path should not be ignored: {path}"


def test_manifest_identification():
    assert is_manifest_file("package.json")
    assert is_manifest_file("backend/pyproject.toml")
    assert is_manifest_file("requirements.txt")
    assert is_manifest_file("requirements-dev.txt")
    assert is_manifest_file("pom.xml")
    assert is_manifest_file("app.csproj")
    assert is_manifest_file("go.mod")
    assert is_manifest_file("Cargo.toml")
    assert not is_manifest_file("src/main.py")
    assert not is_manifest_file("README.md")


def test_normalize_posix_path():
    assert normalize_posix_path("backend\\app\\main.py") == "backend/app/main.py"
    assert normalize_posix_path("/frontend/src/App.tsx") == "frontend/src/App.tsx"
