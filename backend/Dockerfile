# Backend + Worker IT Talent AI Profile — image cho môi trường PHÁT TRIỂN (Technical Blueprint, mục 3).
# Không dùng cho production. Một image dùng cho cả `backend` và `worker` (quyết định D02):
# chỉ khác lệnh khởi động do docker-compose.yml đặt.
#   backend: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
#   worker : python -m app.workers.worker
#
# Build context: thư mục backend/ (Compose khai báo `build: ./backend`).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Compose bind-mount ./backend vào /app; PYTHONPATH để mã trong /app luôn được ưu tiên.
    PYTHONPATH=/app

WORKDIR /app

# Chạy bằng user không phải root.
RUN useradd --create-home --uid 1000 appuser \
    && install -d -o appuser -g appuser -m 0700 /tmp/ita-private-code \
    && chown appuser:appuser /app

# Cài dependency (kể cả dev: pytest, ruff) theo pyproject.toml, đặt trước COPY mã nguồn
# để Docker cache lại khi chỉ sửa code. Trên image dev, bộ công cụ test nằm sẵn để chạy
# `docker compose exec backend pytest`.
COPY --chown=appuser:appuser pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install ".[dev]" \
    && pip uninstall -y it-ai-profile-backend \
    && rm -rf app

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

# Healthcheck do Compose khai báo (không cài thêm curl):
#   python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=5).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
