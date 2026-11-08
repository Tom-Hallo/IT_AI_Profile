from fastapi import APIRouter

from app.api import health
from app.modules.auth.router import router as auth_router

API_PREFIX = "/api/v1"

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth_router)
