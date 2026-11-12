"""Dependency wiring cho Role Scoring (PBI-017 / PBI-018).

``get_skill_snapshot_source`` là ĐIỂM NỐI DUY NHẤT với PBI-016. Khi PBI-016 được push,
trả về một đối tượng thoả ``SkillSnapshotSource`` ở đây (hoặc dùng
``app.dependency_overrides`` trong test). Mặc định: chưa cấu hình → skill criteria
UNKNOWN, không có dữ liệu giả.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.scoring import RoleScoringEngine
from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.role_scoring.access import DbRepositoryAccessGuard
from app.modules.role_scoring.architecture_provider import (
    DbArchitectureEvidenceProvider,
)
from app.modules.role_scoring.scoped_service import ScopedRoleScoringService
from app.modules.role_scoring.service import RoleScoringService
from app.modules.role_scoring.skill_adapter import (
    DatabaseSkillSnapshotSource,
    SkillSnapshotAdapter,
    SkillSnapshotSource,
)
from app.modules.users.models import User


@lru_cache(maxsize=1)
def get_role_scoring_engine() -> RoleScoringEngine:
    return RoleScoringEngine()


def get_skill_snapshot_source(
    db: Annotated[Session, Depends(get_session)],
) -> SkillSnapshotSource:
    return DatabaseSkillSnapshotSource(db)


def get_role_scoring_service(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    engine: Annotated[RoleScoringEngine, Depends(get_role_scoring_engine)],
    source: Annotated[SkillSnapshotSource, Depends(get_skill_snapshot_source)],
) -> RoleScoringService:
    guard = DbRepositoryAccessGuard(db, user)
    return RoleScoringService(
        user_id=user.id,
        engine=engine,
        skill_adapter=SkillSnapshotAdapter(source),
        architecture_provider=DbArchitectureEvidenceProvider(db, user.id, guard),
        guard=guard,
    )


def get_scoped_role_scoring_service(
    db: Annotated[Session, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    engine: Annotated[RoleScoringEngine, Depends(get_role_scoring_engine)],
) -> ScopedRoleScoringService:
    """Dependency cho endpoint /score/scoped (PBI-018)."""
    guard = DbRepositoryAccessGuard(db, user)
    arch_provider = DbArchitectureEvidenceProvider(db, user.id, guard)
    base_source = DatabaseSkillSnapshotSource(db)
    base_service = RoleScoringService(
        user_id=user.id,
        engine=engine,
        skill_adapter=SkillSnapshotAdapter(base_source),
        architecture_provider=arch_provider,
        guard=guard,
    )
    return ScopedRoleScoringService(
        db=db,
        user_id=user.id,
        base_service=base_service,
        engine=engine,
        architecture_provider=arch_provider,
    )
