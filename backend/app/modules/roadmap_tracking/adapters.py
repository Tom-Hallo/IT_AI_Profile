"""Build a roadmap snapshot from public assessments owned by the requester."""

import json
from hashlib import sha256

from sqlalchemy.orm import Session

from app.modules.career_roadmap.provider import RealAssessmentProvider
from app.modules.scoring.snapshots import VERSION

from .engine import Snapshot


def current_snapshot(db: Session, user_id: int) -> Snapshot:
    skills: dict[str, list[dict]] = {}
    for assessment in RealAssessmentProvider().load(db, user_id):
        skill = assessment["skill"]
        if skill in skills:
            continue
        score = assessment["score"]
        skills[skill] = [
            {"verified": True, "ref": str(item["id"]), "score": score}
            for item in sorted(assessment["evidence"], key=lambda item: item["id"])
            if score is not None and assessment["confidence"] in {"high", "medium"}
        ]
    fingerprint = sha256(json.dumps(skills, sort_keys=True).encode()).hexdigest()
    return Snapshot(fingerprint, user_id, "public", VERSION, "all_time", skills)
