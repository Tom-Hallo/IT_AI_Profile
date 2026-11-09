"""File filtering, ignore patterns, and security path validation (PBI-012).

Rules:
- Strictly prevent path traversal (reject '..', absolute paths, Windows drive prefixes).
- Exclude generated code, vendor directories, dependency installations, binaries, build
outputs.
- Never execute untrusted repository code.
"""

from __future__ import annotations

import os
from pathlib import PurePosixPath

# Thư mục phụ thuộc bên thứ ba và cài đặt vendor
IGNORED_DIR_NAMES: set[str] = {
    # Node / JS
    "node_modules",
    "bower_components",
    ".pnpm-store",
    # Python
    ".venv",
    "venv",
    "env",
    ".env",
    "site-packages",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    # Build outputs & Binaries
    "dist",
    "build",
    "out",
    "target",
    "bin",
    "obj",
    ".next",
    ".nuxt",
    ".turbo",
    ".parcel-cache",
    # Java / Kotlin
    ".gradle",
    # Mobile / iOS / Android
    "pods",
    ".bundle",
    # VCS & IDE internals
    ".git",
    ".svn",
    ".hg",
    ".idea",
    ".vscode",
    # Vendor / third party
    "vendor",
    "packages",
}

# Phần mở rộng nhị phân và tài nguyên không phân tích mã nguồn
IGNORED_EXTENSIONS: set[str] = {
    # Executable & libraries
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".pyc",
    ".pyo",
    ".o",
    ".obj",
    ".a",
    ".lib",
    ".jar",
    ".war",
    ".ear",
    # Archives
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".7z",
    ".rar",
    ".bz2",
    # Media & images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".webp",
    ".bmp",
    ".tiff",
    ".mp3",
    ".mp4",
    ".wav",
    ".avi",
    ".mov",
    ".pdf",
    ".psd",
    # Fonts
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
    # Minified & maps
    ".min.js",
    ".min.css",
    ".map",
}

# Các file manifest và cấu hình công nghệ cần ưu tiên kiểm tra
MANIFEST_FILENAMES: set[str] = {
    # Python
    "requirements.txt",
    "pyproject.toml",
    "pipfile",
    "pipfile.lock",
    "setup.py",
    "setup.cfg",
    "poetry.lock",
    # JavaScript / TypeScript
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
    # Java / Kotlin / JVM
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
    # C# / .NET
    "packages.config",
    "directory.build.props",
    # Go
    "go.mod",
    "go.sum",
    # Rust
    "cargo.toml",
    "cargo.lock",
    # PHP
    "composer.json",
    "composer.lock",
    # Ruby
    "gemfile",
    "gemfile.lock",
    # Container & CI/CD
    "dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}


def normalize_posix_path(raw_path: str) -> str:
    """Chuẩn hóa đường dẫn thành dạng PurePosixPath phân cách bởi '/'."""
    return raw_path.replace("\\", "/").strip().lstrip("/")


def is_safe_path(path: str) -> bool:
    """Xác thực đường dẫn an toàn, ngăn chặn tấn công Path Traversal.

    Không cho phép đường dẫn chứa '..', ký tự null, ký tự ổ đĩa Windows (C:),
    hoặc đường dẫn tuyệt đối nhằm thoát ra khỏi phạm vi repository.
    """
    if not path or "\x00" in path:
        return False

    norm = normalize_posix_path(path)

    # Ngăn chặn ổ đĩa Windows như C: hoặc D:
    if len(norm) >= 2 and norm[1] == ":":
        return False

    # Không cho phép đường dẫn bắt đầu bằng '/'
    if path.startswith(("/", "\\")):
        return False

    # Phân tích các thành phần đường dẫn POSIX
    try:
        parts = PurePosixPath(norm).parts
    except (ValueError, TypeError):
        return False

    for part in parts:
        if part in ("..", ".", ""):
            return False

    # Kiểm tra os.path.isabs
    return not os.path.isabs(path)


def is_ignored_path(path: str) -> bool:
    """Kiểm tra tập tin/thư mục có nằm trong danh mục bị loại bỏ không.

    Loại bỏ vendor, thư viện ngoài, tệp sinh tự động, thư mục cache, tệp nhị phân.
    """
    norm = normalize_posix_path(path).lower()
    parts = norm.split("/")

    # 1. Kiểm tra bất kỳ thư mục con nào nằm trong IGNORED_DIR_NAMES
    for part in parts[:-1]:
        if (part in IGNORED_DIR_NAMES or part.startswith(".")) and part not in (
            ".github",
        ):
            return True

    # 2. Kiểm tra nếu chính thư mục hiện tại là thư mục bị bỏ qua
    if len(parts) > 0 and parts[-1] in IGNORED_DIR_NAMES:
        return True

    filename = parts[-1] if parts else ""

    # 3. Kiểm tra các phần mở rộng bị bỏ qua (vd: .min.js, .exe, .png)
    for ext in IGNORED_EXTENSIONS:
        if filename.endswith(ext):
            return True

    # 4. Kiểm tra tệp sinh tự động
    return bool(filename.endswith((".generated.cs", ".generated.ts")))


def is_manifest_file(path: str) -> bool:
    """Xác định tập tin có phải là manifest hoặc file cấu hình công nghệ."""
    norm = normalize_posix_path(path).lower()
    filename = norm.split("/")[-1]
    if filename in MANIFEST_FILENAMES:
        return True
    if filename.endswith((".csproj", ".fsproj")):
        return True
    return bool(filename.startswith("requirements") and filename.endswith(".txt"))
