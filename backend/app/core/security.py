"""Bảo mật và mã hóa dữ liệu nhạy cảm (PBI-009).

Quy tắc:
- Token GitHub OAuth được mã hóa trước khi lưu vào DB bằng cryptography.fernet
  (AES-128-CBC + HMAC-SHA256).
- Khóa mã hóa đọc từ settings.github_token_encryption_key.
- Không có fallback plaintext nếu thiếu khóa (ném ConfigurationError).
- Không bao giờ log token thô hoặc đưa token vào exception hay API response.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.core.exceptions import ConfigurationError


def _get_fernet() -> Fernet:
    """Khởi tạo Fernet cipher từ cấu hình.

    Ném ConfigurationError nếu chưa cấu hình GITHUB_TOKEN_ENCRYPTION_KEY.
    """
    if not settings.github_token_encryption_key:
        raise ConfigurationError("Chưa cấu hình GITHUB_TOKEN_ENCRYPTION_KEY để mã hóa token.")
    try:
        key_bytes = settings.github_token_encryption_key.get_secret_value().encode("utf-8")
        return Fernet(key_bytes)
    except Exception as exc:
        raise ConfigurationError("GITHUB_TOKEN_ENCRYPTION_KEY không hợp lệ.") from exc


def encrypt_token(plain_token: str) -> str:
    """Mã hóa token truy cập trước khi lưu vào cơ sở dữ liệu."""
    if not plain_token or not isinstance(plain_token, str):
        raise ValueError("Token không hợp lệ để mã hóa.")
    fernet = _get_fernet()
    encrypted_bytes = fernet.encrypt(plain_token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Giải mã token truy cập từ cơ sở dữ liệu."""
    if not encrypted_token or not isinstance(encrypted_token, str):
        raise ValueError("Dữ liệu mã hóa không hợp lệ.")
    fernet = _get_fernet()
    try:
        decrypted_bytes = fernet.decrypt(encrypted_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except InvalidToken:
        raise ValueError("Không thể giải mã token (token bị hỏng hoặc sai khóa).") from None


def mask_token(token: str | None) -> str:
    """Tạo chuỗi che giấu an toàn cho mục đích hiển thị/log (không lộ token)."""
    if not token:
        return "(none)"
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"
