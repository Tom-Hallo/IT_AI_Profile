"""Business logic for owner-isolated self-reported skills."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.self_reported_skills.models import (
    SelfReportedSkill,
    SelfReportedSkillEvidence,
)


def get_owned_skill(db: Session, user_id: int, skill_id: int) -> SelfReportedSkill:
    skill = db.scalar(
        select(SelfReportedSkill).where(
            SelfReportedSkill.id == skill_id,
            SelfReportedSkill.user_id == user_id,
        )
    )
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


def get_owned_evidence(
    db: Session,
    user_id: int,
    skill_id: int,
    evidence_id: int,
) -> SelfReportedSkillEvidence:
    evidence = db.scalar(
        select(SelfReportedSkillEvidence).where(
            SelfReportedSkillEvidence.id == evidence_id,
            SelfReportedSkillEvidence.skill_id == skill_id,
            SelfReportedSkillEvidence.user_id == user_id,
        )
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence


def list_skills(db: Session, user_id: int) -> list[SelfReportedSkill]:
    return list(
        db.scalars(
            select(SelfReportedSkill)
            .where(SelfReportedSkill.user_id == user_id)
            .order_by(SelfReportedSkill.created_at.desc())
        ).all()
    )


def serialize_skill(db: Session, skill: SelfReportedSkill) -> dict:
    evidence_items = db.scalars(
        select(SelfReportedSkillEvidence)
        .where(
            SelfReportedSkillEvidence.skill_id == skill.id,
            SelfReportedSkillEvidence.user_id == skill.user_id,
        )
        .order_by(SelfReportedSkillEvidence.created_at)
    ).all()

    return {
        "id": skill.id,
        "skill_name": skill.skill_name,
        "description": skill.description,
        "source": skill.source,
        "status": skill.status,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
        "evidence": [
            {
                "id": item.id,
                "skill_id": item.skill_id,
                "title": item.title,
                "description": item.description,
                "url": item.url,
                "source": item.source,
                "status": item.status,
                "created_at": item.created_at,
                "updated_at": item.updated_at,
            }
            for item in evidence_items
        ],
    }


def commit_or_rollback(db: Session) -> None:
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
