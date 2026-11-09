from fastapi import APIRouter

from app.api import health
from app.api.activity import router as activity_router
from app.modules.analysis.router import router as analysis_router
from app.modules.auth.router import router as auth_router
from app.modules.github.router import router as github_router
from app.modules.github.selection_router import router as selection_router

API_PREFIX = "/api/v1"

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(github_router)
api_router.include_router(activity_router)
api_router.include_router(selection_router)
