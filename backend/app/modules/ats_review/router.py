"""MVP preview endpoint: authenticated, CSRF-protected and owner-scoped."""

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from app.modules.ats_review.service import analyze
from app.modules.consent.router import csrf
from app.modules.cvs.router import DB, NO_STORE, CurrentUser, error, owned_upload

router = APIRouter(prefix="/ats-reviews", tags=["ATS Resume Feedback"])


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cv_id: int | None = Field(default=None, gt=0)
    text: str | None = Field(default=None, max_length=50_000)
    jd_text: str | None = Field(default=None, max_length=20_000)


@router.post("/preview", dependencies=[Depends(csrf)])
def preview_review(
    body: ReviewRequest, response: Response, user: CurrentUser, db: DB
) -> dict:
    response.headers.update(NO_STORE)
    cv_text = None
    cv_id = body.cv_id
    cv_version = None
    if body.cv_id:
        cv = owned_upload(db, user.id, body.cv_id)
        content = cv.content
        cv_text = content.get("text")
        cv_version = content.get("version")
    elif body.text and body.text.strip():
        cv_text = body.text.strip()
    else:
        raise error(422, "Cần cung cấp cv_id hoặc nội dung văn bản CV.")

    if not isinstance(cv_text, str) or not cv_text.strip():
        raise error(422, "CV không có văn bản hợp lệ.")
    try:
        result = analyze(cv_text, body.jd_text)
    except ValueError:
        raise error(422, "Nội dung CV hoặc JD không hợp lệ.") from None
    return {"cv_id": cv_id, "cv_version": cv_version, **result}
