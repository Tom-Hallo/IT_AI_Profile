"""Cấu hình test chung. Đặt biến môi trường trước khi import app.

Khi chạy integration test, sử dụng DATABASE_URL thật từ file .env.
Khi chạy unit test, sử dụng DATABASE_URL giả.
"""

import os

from cryptography.fernet import Fernet

os.environ.setdefault("APP_ENV", "test")

if os.environ.get("RUN_INTEGRATION") != "1":
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://test:test-pass@127.0.0.1:5432/test_db",
    )

os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault(
    "GITHUB_TOKEN_ENCRYPTION_KEY",
    Fernet.generate_key().decode(),
)
