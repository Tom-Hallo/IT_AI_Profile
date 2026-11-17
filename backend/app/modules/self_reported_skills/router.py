"""Owner-only CRUD API for self-reported skills and evidence."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.modules.self_reported_skills.models import (
    SelfReportedSkill,
    SelfReportedSkillEvidence,
)
from app.modules.self_reported_skills.schemas import (
    EvidenceCreate,
    EvidenceOut,
    EvidenceUpdate,
    SkillCreate,
    SkillOut,
    SkillUpdate,
)
from app.modules.self_reported_skills.service import (
    commit_or_rollback,
    get_owned_evidence,
    get_owned_skill,
    list_skills,
    serialize_skill,
)
from app.modules.users.models import User

router = APIRouter(prefix="/self-reported-skills", tags=["Self-reported Skills"])

Db = Annotated[Session, Depends(get_session)]
Owner = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=list[SkillOut])
def get_my_skills(db: Db, user: Owner) -> list[dict]:
    return [serialize_skill(db, skill) for skill in list_skills(db, user.id)]


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill(body: SkillCreate, db: Db, user: Owner) -> dict:
    skill = SelfReportedSkill(
        user_id=user.id,
        skill_name=body.skill_name.strip(),
        description=body.description,
        source="self-reported",
        status="self-reported",
    )
    if not skill.skill_name:
        raise HTTPException(status_code=422, detail="Skill name cannot be empty")

    db.add(skill)
    commit_or_rollback(db)
    db.refresh(skill)
    return serialize_skill(db, skill)


@router.get("/{skill_id}", response_model=SkillOut)
def get_skill(skill_id: int, db: Db, user: Owner) -> dict:
    skill = get_owned_skill(db, user.id, skill_id)
    return serialize_skill(db, skill)


@router.patch("/{skill_id}", response_model=SkillOut)
def update_skill(skill_id: int, body: SkillUpdate, db: Db, user: Owner) -> dict:
    skill = get_owned_skill(db, user.id, skill_id)
    changes = body.model_dump(exclude_unset=True)

    if "skill_name" in changes:
        if changes["skill_name"] is None or not changes["skill_name"].strip():
            raise HTTPException(status_code=422, detail="Skill name cannot be empty")
        changes["skill_name"] = changes["skill_name"].strip()

    for field, value in changes.items():
        setattr(skill, field, value)

    commit_or_rollback(db)
    db.refresh(skill)
    return serialize_skill(db, skill)


@router.delete("/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, db: Db, user: Owner) -> Response:
    skill = get_owned_skill(db, user.id, skill_id)
    db.delete(skill)
    commit_or_rollback(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{skill_id}/evidence",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence(
    skill_id: int, body: EvidenceCreate, db: Db, user: Owner
) -> SelfReportedSkillEvidence:
    get_owned_skill(db, user.id, skill_id)

    evidence = SelfReportedSkillEvidence(
        skill_id=skill_id,
        user_id=user.id,
        title=body.title.strip(),
        description=body.description,
        url=str(body.url) if body.url is not None else None,
        source="self-reported",
        status="self-reported",
    )
    if not evidence.title:
        raise HTTPException(status_code=422, detail="Evidence title cannot be empty")

    db.add(evidence)
    commit_or_rollback(db)
    db.refresh(evidence)
    return evidence


@router.patch(
    "/{skill_id}/evidence/{evidence_id}",
    response_model=EvidenceOut,
)
def update_evidence(
    skill_id: int,
    evidence_id: int,
    body: EvidenceUpdate,
    db: Db,
    user: Owner,
) -> SelfReportedSkillEvidence:
    get_owned_skill(db, user.id, skill_id)
    evidence = get_owned_evidence(db, user.id, skill_id, evidence_id)
    changes = body.model_dump(exclude_unset=True)

    if "title" in changes:
        if changes["title"] is None or not changes["title"].strip():
            raise HTTPException(
                status_code=422, detail="Evidence title cannot be empty"
            )
        changes["title"] = changes["title"].strip()

    if "url" in changes:
        changes["url"] = str(changes["url"]) if changes["url"] is not None else None

    for field, value in changes.items():
        setattr(evidence, field, value)

    commit_or_rollback(db)
    db.refresh(evidence)
    return evidence


@router.delete(
    "/{skill_id}/evidence/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_evidence(
    skill_id: int,
    evidence_id: int,
    db: Db,
    user: Owner,
) -> Response:
    get_owned_skill(db, user.id, skill_id)
    evidence = get_owned_evidence(db, user.id, skill_id, evidence_id)
    db.delete(evidence)
    commit_or_rollback(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
