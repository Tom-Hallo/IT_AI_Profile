"""Cấu hình ứng dụng (Blueprint mục 1.4 và 5).

Quy tắc:
- Đây là NƠI DUY NHẤT đọc biến môi trường. Module khác chỉ `from app.core.config import settings`.
- Biến bắt buộc không có giá trị mặc định: thiếu thì dừng ngay khi import.
- Thông báo lỗi chỉ nêu TÊN biến, không bao giờ nêu giá trị.
"""

from typing import Annotated, Literal

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.core.exceptions import ConfigurationError

APP_NAME = "backend"
APP_VERSION = "0.1.0"


def _split_csv(value: object) -> object:
    """Chuyển "a, b,c" thành ["a", "b", "c"]; giá trị khác giữ nguyên."""
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Chạy ngoài Docker: đọc backend/.env. Trong Docker, Compose truyền biến trực tiếp
        # và biến của tiến trình luôn được ưu tiên hơn file.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Không đưa giá trị đầu vào vào thông báo ValidationError (Blueprint R12).
        hide_input_in_errors=True,
    )

    # --- Bắt buộc (không có mặc định) ---
    app_env: Literal["development", "test", "production"]
    # SecretStr: không bị in ra khi repr/log. URL chứa mật khẩu.
    database_url: SecretStr
    redis_url: SecretStr

    # --- Tùy chọn ---
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # GitHub OAuth: để trống khi chưa cấu hình OAuth App.
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None
    github_redirect_uri: str = "http://localhost:8000/api/v1/auth/github/callback"
    github_token_encryption_key: SecretStr | None = None
    frontend_url: str = "http://localhost:5173"
    ita_analysis_tmp_root: str = "/var/lib/ita/analysis-tmp"

    @field_validator(
        "github_client_id",
        "github_client_secret",
        "github_token_encryption_key",
        mode="before",
    )
    @classmethod
    def _empty_github_credentials_as_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("github_token_encryption_key")
    @classmethod
    def _validate_encryption_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        import base64
        import binascii

        raw = value.get_secret_value()
        try:
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) != 32:
                raise ValueError("khóa mã hóa phải gồm đúng 32 bytes (base64 urlsafe)")
        except (ValueError, TypeError, binascii.Error):
            raise ValueError(
                "khóa mã hóa không hợp lệ (phải là 32 bytes base64 urlsafe)"
            ) from None
        return value

    # NoDecode: nhận chuỗi phân tách bằng dấu phẩy thay vì JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    worker_queues: Annotated[list[str], NoDecode] = ["default"]

    @field_validator("cors_origins", "worker_queues", mode="before")
    @classmethod
    def _parse_csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("cors_origins")
    @classmethod
    def _no_wildcard_origin(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("không được dùng '*'")
        return value

    @field_validator("database_url")
    @classmethod
    def _database_driver(cls, value: SecretStr) -> SecretStr:
        # Blueprint D07/R6: bắt buộc driver psycopg v3 (đồng bộ).
        if not value.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("phải bắt đầu bằng 'postgresql+psycopg://'")
        return value

    @field_validator("redis_url")
    @classmethod
    def _redis_scheme(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("phải bắt đầu bằng 'redis://' hoặc 'rediss://'")
        return value

    @field_validator("worker_queues")
    @classmethod
    def _queues_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("không được rỗng")
        return value

    @property
    def github_oauth_enabled(self) -> bool:
        """Chỉ bật GitHub OAuth khi đã có đủ Client ID và Client Secret."""
        return bool(
            self.github_client_id
            and self.github_client_secret
            and self.github_client_secret.get_secret_value()
        )

    @property
    def docs_enabled(self) -> bool:
        """Swagger/OpenAPI chỉ bật ở development (Blueprint mục 7.2, S4)."""
        return self.app_env == "development"


def load_settings() -> Settings:
    """Đọc cấu hình; nếu sai thì ném ConfigurationError chỉ nêu TÊN biến."""
    try:
        # type: ignore[call-arg]  # giá trị lấy từ môi trường
        return Settings()
    except ValidationError as exc:
        problems: list[str] = []
        for err in exc.errors(include_input=False, include_url=False):
            name = ".".join(str(part) for part in err["loc"]).upper()
            kind = "thiếu" if err["type"] == "missing" else "không hợp lệ"
            problems.append(f"{name} ({kind})")
        raise ConfigurationError(
            "Cấu hình môi trường chưa đúng, kiểm tra các biến: "
            + ", ".join(problems)
            + ". Xem .env.example."
        ) from None  # `from None`: không kéo theo ngữ cảnh lỗi gốc


settings = load_settings()
