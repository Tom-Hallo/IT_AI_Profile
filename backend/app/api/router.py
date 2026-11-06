"""Router gốc của API. Mọi endpoint nằm dưới tiền tố /api/v1 (Blueprint mục 7.3)."""

from fastapi import APIRouter

from app.api import health

API_PREFIX = "/api/v1"

api_router = APIRouter()
api_router.include_router(health.router)
# Router của các module nghiệp vụ sẽ được gắn ở đây trong các PBI sau (KHÔNG thêm trong PBI-001).
