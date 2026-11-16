"""API for PBI-034 Multi-source Extended Competency Assessment.

GET /assessments/competency/{role_key}
  → returns verified + extended layers clearly separated.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import Field

from app.ai.scoring import RubricNotFoundError
from app.modules.competency_assessment.dependencies import (
    get_competency_assessment_service,
)
from app.modules.competency_assessment.schemas import CompetencyAssessmentResponse
from app.modules.competency_assessment.service import CompetencyAssessmentService
from app.modules.role_scoring.errors import (
    PrivateConsentRequiredError,
    RepositoryNotFoundError,
    SkillSnapshotSourceError,
)

router = APIRouter(prefix="/assessments", tags=["Competency Assessment"])

ServiceDep = Annotated[
    CompetencyAssessmentService, Depends(get_competency_assessment_service)
]
RepositoryId = Annotated[int, Field(gt=0)]


@router.get(
    "/competency/{role_key}",
    response_model=CompetencyAssessmentResponse,
    summary="Multi-source competency assessment (Verified + Extended)",
)
def assess_competency(
    role_key: str,
    service: ServiceDep,
    response: Response,
    repository_id: Annotated[
        list[RepositoryId] | None,
        Query(
            max_length=50,
            description=(
                "Limit repositories used as evidence. Empty = all accessible "
                "repositories of the current user (private without consent skipped)."
            ),
        ),
    ] = None,
    snapshot_ref: Annotated[
        str | None,
        Query(max_length=200, description="Optional skill snapshot reference"),
    ] = None,
    rubric_version: Annotated[
        str | None,
        Query(pattern=r"^\d+\.\d+\.\d+$", max_length=20),
    ] = None,
) -> CompetencyAssessmentResponse:
    """Trả về hai lớp đánh giá tách biệt.

    - **verified**: chỉ evidence GitHub đã contribution-verified.
    - **extended**: verified + self-reported claims (confidence thấp hơn).

    Self-reported / claims **không bao giờ** thay đổi Verified Score.
    """
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.assess(
            role_key,
            repository_ids=repository_id,
            snapshot_ref=snapshot_ref,
            rubric_version=rubric_version,
        )
    except RubricNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Role or rubric not found"
        ) from exc
    except RepositoryNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Không tìm thấy repository hoặc bạn không có quyền truy cập.",
        ) from exc
    except PrivateConsentRequiredError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Private repository consent required"
        ) from exc
    except SkillSnapshotSourceError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Skill snapshot source temporarily unavailable.",
        ) from exc
