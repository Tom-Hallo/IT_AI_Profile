import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[2]
SECRET_PASSWORD = "S3cr3t-Pa55word"


# Các biến mà app đọc. Xóa khỏi môi trường tiến trình con để test không phụ thuộc máy chạy.
APP_VARS = (
    "APP_ENV",
    "DATABASE_URL",
    "REDIS_URL",
    "LOG_LEVEL",
    "CORS_ORIGINS",
    "WORKER_QUEUES",
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "GITHUB_REDIRECT_URI",
)


def _import_app_in_clean_env(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Import app.core.config trong tiến trình riêng, môi trường app do test chỉ định.

    Giữ lại biến của hệ điều hành (trên Windows cần SYSTEMROOT để Python khởi tạo mạng),
    chỉ loại bỏ các biến mà app đọc.
    """
    base = {k: v for k, v in os.environ.items() if k not in APP_VARS}
    base["PYTHONPATH"] = str(BACKEND_DIR)
    # Windows mặc định dùng bảng mã cp1252 khi ghi ra pipe, làm tiếng Việt thành mã \\uXXXX.
    base["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, "-c", "import app.core.config"],
        check=False,
        env={**base, **env},
        # thư mục không có .env để không đọc nhầm file
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


GOOD_ENV = {
    "APP_ENV": "development",
    "DATABASE_URL": f"postgresql+psycopg://u:{SECRET_PASSWORD}@127.0.0.1:5432/d",
    "REDIS_URL": "redis://127.0.0.1:6379/0",
}


def test_good_environment_loads():
    result = _import_app_in_clean_env(GOOD_ENV)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("missing", ["APP_ENV", "DATABASE_URL", "REDIS_URL"])
def test_missing_required_variable_names_the_variable(missing):
    env = {k: v for k, v in GOOD_ENV.items() if k != missing}
    result = _import_app_in_clean_env(env)

    assert result.returncode != 0
    assert missing in result.stderr
    assert "thiếu" in result.stderr
    assert SECRET_PASSWORD not in result.stderr


def test_invalid_value_error_never_contains_the_value():
    env = {**GOOD_ENV, "DATABASE_URL": f"postgresql://u:{SECRET_PASSWORD}@127.0.0.1/d"}
    result = _import_app_in_clean_env(env)

    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr
    assert SECRET_PASSWORD not in result.stderr
    assert "postgresql://u" not in result.stderr


def test_invalid_app_env_is_rejected_without_echoing_value():
    result = _import_app_in_clean_env({**GOOD_ENV, "APP_ENV": "staging-xyz"})
    assert result.returncode != 0
    assert "APP_ENV" in result.stderr
    assert "staging-xyz" not in result.stderr


def _make(**overrides) -> Settings:
    values = {
        "app_env": "test",
        "database_url": "postgresql+psycopg://u:p@h/d",
        "redis_url": "redis://h:6379/0",
        "github_client_id": None,
        "github_client_secret": None,
    }
    values.update(overrides)
    return Settings(**values)


def test_cors_wildcard_is_rejected():
    with pytest.raises(ValidationError):
        _make(cors_origins="*")
    with pytest.raises(ValidationError):
        _make(cors_origins="http://localhost:5173,*")


def test_cors_origins_are_split_by_comma():
    assert _make(cors_origins=" http://a.test , http://b.test ").cors_origins == [
        "http://a.test",
        "http://b.test",
    ]


def test_defaults():
    s = _make()
    assert s.cors_origins == ["http://localhost:5173"]
    assert s.worker_queues == ["default"]
    assert s.log_level == "INFO"


def test_secret_is_hidden_in_repr():
    assert "p@h" not in repr(_make())


def test_github_oauth_disabled_without_credentials():
    s = _make()

    assert s.github_client_id is None
    assert s.github_client_secret is None
    assert s.github_oauth_enabled is False


def test_github_oauth_enabled_with_credentials():
    s = _make(
        github_client_id="test-client-id",
        github_client_secret="test-client-secret",
    )

    assert s.github_oauth_enabled is True
    assert s.github_client_id == "test-client-id"


def test_github_client_secret_is_hidden_in_repr():
    secret = "github-super-secret"
    s = _make(
        github_client_id="test-client-id",
        github_client_secret=secret,
    )

    assert secret not in repr(s)
