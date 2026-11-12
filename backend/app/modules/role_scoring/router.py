"""API Role-based Scoring (PBI-017 / PBI-018).

* ``GET /role-scoring/roles`` — rubric khả dụng (role mở rộng bằng cách thêm rubric).
* ``GET /role-scoring/roles/{role_key}/score`` — chấm role cho CHÍNH người dùng
  đăng nhập.
* ``GET /role-scoring/roles/{role_key}/score/scoped`` — chấm role với 3 scope độc lập:
  Public / Private / Combined (PBI-018). Combined tự dedup evidence, không cộng điểm.

Chỉ đọc, không ghi DB (persistence chờ contract snapshot PBI-016), nên dùng GET và
không cần CSRF. Phản hồi ``Cache-Control: no-store``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import Field

from app.ai.scoring import RubricNotFoundError
from app.modules.role_scoring.dependencies import (
    get_role_scoring_service,
    get_scoped_role_scoring_service,
)
from app.modules.role_scoring.errors import (
    PrivateConsentRequiredError,
    RepositoryNotFoundError,
    SkillSnapshotSourceError,
)
from app.modules.role_scoring.schemas import (
    RoleListResponse,
    RoleScoreResponse,
    RoleSummary,
    ScopedRoleScoreResponse,
)
from app.modules.role_scoring.scoped_service import ScopedRoleScoringService
from app.modules.role_scoring.service import RoleScoringRequest, RoleScoringService

router = APIRouter(prefix="/role-scoring", tags=["Role Scoring"])

ServiceDep = Annotated[RoleScoringService, Depends(get_role_scoring_service)]
ScopedServiceDep = Annotated[
    ScopedRoleScoringService, Depends(get_scoped_role_scoring_service)
]
RepositoryId = Annotated[int, Field(gt=0)]


@router.get("/roles", response_model=RoleListResponse)
def list_roles(service: ServiceDep, response: Response) -> RoleListResponse:
    response.headers["Cache-Control"] = "no-store"
    return RoleListResponse(
        roles=[RoleSummary.from_rubric(r) for r in service.list_rubrics()]
    )


@router.get("/roles/{role_key}/score", response_model=RoleScoreResponse)
def score_role(
    role_key: str,
    service: ServiceDep,
    response: Response,
    repository_id: Annotated[
        list[RepositoryId] | None,
        Query(
            max_length=50,
            description="Giới hạn repository dùng làm bằng chứng; bỏ trống = tất cả "
            "repository hợp lệ của bạn (repo private thiếu consent bị bỏ qua).",
        ),
    ] = None,
    snapshot_ref: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    rubric_version: Annotated[
        str | None, Query(pattern=r"^\d+\.\d+\.\d+$", max_length=20)
    ] = None,
) -> RoleScoreResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        outcome = service.score(
            RoleScoringRequest(
                role_key=role_key,
                repository_ids=repository_id,
                snapshot_ref=snapshot_ref,
                rubric_version=rubric_version,
            )
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
    return RoleScoreResponse.from_outcome(outcome)


@router.get(
    "/roles/{role_key}/score/scoped",
    response_model=ScopedRoleScoreResponse,
    summary="Tính điểm role theo 3 scope: Public / Private / Combined",
    description=(
        "Trả về điểm role độc lập cho từng scope. Combined được tính bằng engine "
        "riêng với evidence đã dedup — không phải trung bình hay tổng công của "
        "Public + Private. Evidence trùng lặp (cùng commit/file) chỉ được tính 1 lần."
    ),
)
def score_role_scoped(
    role_key: str,
    service: ScopedServiceDep,
    response: Response,
    rubric_version: Annotated[
        str | None, Query(pattern=r"^\d+\.\d+\.\d+$", max_length=20)
    ] = None,
) -> ScopedRoleScoreResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        outcome = service.score_all_scopes(
            role_key,
            rubric_version=rubric_version,
        )
    except RubricNotFoundError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Role or rubric not found"
        ) from exc
    except (RepositoryNotFoundError, PrivateConsentRequiredError) as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Repository access changed; refresh the scoped score.",
            headers={"Cache-Control": "no-store"},
        ) from exc
    except SkillSnapshotSourceError as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Skill snapshot source temporarily unavailable.",
        ) from exc
    return ScopedRoleScoreResponse.from_scoped_outcome(outcome)
