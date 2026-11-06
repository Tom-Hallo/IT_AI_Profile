"""Cấu hình test chung. Đặt biến môi trường GIẢ trước khi import `app`.

Dùng setdefault để khi chạy test tích hợp (RUN_INTEGRATION=1) có thể truyền URL thật.
"""

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test-pass@127.0.0.1:5432/test_db")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")
