"""Dependency wiring for PBI-034 Competency Assessment."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.competency_assessment.service import CompetencyAssessmentService
from app.modules.role_scoring.dependencies import get_role_scoring_service
from app.modules.role_scoring.service import RoleScoringService
from app.modules.users.models import User


def get_competency_assessment_service(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    role_scoring: Annotated[RoleScoringService, Depends(get_role_scoring_service)],
) -> CompetencyAssessmentService:
    return CompetencyAssessmentService(
        user_id=user.id,
        db=db,
        role_scoring=role_scoring,
    )