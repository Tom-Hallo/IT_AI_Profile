from fastapi import APIRouter

from app.api import health
from app.api.activity import router as activity_router
from app.modules.ai_mentor.router import actions_router
from app.modules.ai_mentor.router import router as mentor_router
from app.modules.analysis.router import router as analysis_router
from app.modules.auth.router import router as auth_router
from app.modules.career_roadmap.router import (
    router as career_roadmap_router,
)
from app.modules.consent.router import router as consent_router
from app.modules.github.router import router as github_router
from app.modules.github.selection_router import router as selection_router
from app.modules.jobs.router import router as jobs_router
from app.modules.roadmap_tracking.router import router as roadmap_tracking_router
from app.modules.role_scoring.router import router as role_scoring_router
from app.modules.scoring.router import router as scoring_router

API_PREFIX = "/api/v1"

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth_router)
api_router.include_router(github_router)
api_router.include_router(activity_router)
api_router.include_router(selection_router)
api_router.include_router(analysis_router)
api_router.include_router(consent_router)
api_router.include_router(role_scoring_router)
api_router.include_router(scoring_router)
api_router.include_router(mentor_router)
api_router.include_router(actions_router)
api_router.include_router(career_roadmap_router)
api_router.include_router(jobs_router)
api_router.include_router(roadmap_tracking_router)
