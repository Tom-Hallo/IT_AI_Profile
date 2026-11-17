"""FastAPI Router cho Resume Pattern Analysis & Generation (PBI-032)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.dependencies import get_current_user
from app.modules.cvs.engine import ResumePatternEngine
from app.modules.cvs.schemas import (
    PatternExtractRequest,
    PatternExtractResponse,
    ResumeGenerateRequest,
    ResumeGenerateResponse,
    ResumePatternSuggestion,
    TargetRole,
)
from app.modules.users.models import User

router = APIRouter(prefix="/resume", tags=["Resume Intelligence"])


def get_resume_engine() -> ResumePatternEngine:
    return ResumePatternEngine()


@router.get(
    "/patterns/{role}",
    response_model=ResumePatternSuggestion,
    summary="Lấy gợi ý pattern bố cục chuẩn theo vị trí tuyển dụng",
)
def get_role_pattern(
    role: TargetRole,
    engine: Annotated[ResumePatternEngine, Depends(get_resume_engine)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> ResumePatternSuggestion:
    response.headers["Cache-Control"] = "no-store"
    return engine.get_pattern_suggestion(role)


@router.post(
    "/patterns/extract",
    response_model=PatternExtractResponse,
    summary="Trích xuất bố cục cấu trúc từ CV tham khảo",
)
def extract_pattern(
    req: PatternExtractRequest,
    engine: Annotated[ResumePatternEngine, Depends(get_resume_engine)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> PatternExtractResponse:
    response.headers["Cache-Control"] = "no-store"
    if not req.has_usage_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bạn cần xác nhận quyền sử dụng hợp pháp tài liệu tham khảo.",
        )
    sections = engine.extract_layout_from_reference(req.reference_text)
    return PatternExtractResponse(
        sections_detected=sections,
        formatting_insights=[
            f"Phát hiện {len(sections)} phân đoạn chính.",
            "Cấu trúc tập trung vào kết quả định lượng và kỹ năng công nghệ.",
        ],
    )


@router.post(
    "/generate",
    response_model=ResumeGenerateResponse,
    summary="Tạo CV gốc từ dữ kiện đã xác nhận của người dùng và chống đạo văn",
)
def generate_resume(
    req: ResumeGenerateRequest,
    engine: Annotated[ResumePatternEngine, Depends(get_resume_engine)],
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> ResumeGenerateResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        return engine.generate_original_resume(req)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
"""Authenticated CV preview, confirmation and editing."""

import asyncio
import base64
import json
import subprocess
import sys
from datetime import datetime
from hashlib import sha256
from hmac import digest
from threading import BoundedSemaphore
from typing import Annotated
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.db.session import get_session
from app.modules.consent.router import csrf
from app.modules.cvs.models import CV
from app.modules.cvs.parser import (
    CONTROL_CHARS,
    DOCX,
    MAX_FILE_BYTES,
    MAX_TEXT_CHARS,
    PDF,
)
from app.modules.cvs.references import (
    ReferenceQuery,
    ReferenceSearch,
    search_references,
)
from app.modules.cvs.scanner import ScannerUnavailable, UnsafeCV, scan_cv
from app.modules.users.models import User

NO_STORE = {"Cache-Control": "no-store"}
PREVIEW_TTL = 900
UPLOAD_SOURCE = "user_upload"
UPLOAD_SLOTS = BoundedSemaphore(2)
router = APIRouter(prefix="/cvs", tags=["CV"], responses={})
CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_session)]


def error(status: int, detail: str) -> HTTPException:
    return HTTPException(status, detail, headers=NO_STORE)


async def read_limited(request: Request, limit: int) -> bytes:
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or len(length) > 9 or int(length) > limit):
        raise error(413, "Dữ liệu vượt giới hạn kích thước.")
    data = bytearray()
    try:
        async with asyncio.timeout(20):
            async for chunk in request.stream():
                if len(data) + len(chunk) > limit:
                    raise error(413, "Dữ liệu vượt giới hạn kích thước.")
                data.extend(chunk)
    except TimeoutError:
        raise error(408, "Tải dữ liệu quá thời gian chờ.") from None
    return bytes(data)


class CVText(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)

    @field_validator("text")
    @classmethod
    def valid_text(cls, value: str) -> str:
        text = value.strip()
        if not text or CONTROL_CHARS.search(text):
            raise ValueError("Invalid text")
        text.encode("utf-8")
        return text


class ConfirmCV(CVText):
    receipt: str = Field(min_length=1, max_length=1024)


class EditCV(CVText):
    version: int = Field(strict=True, ge=1, le=2**31 - 1)


class CVPreview(BaseModel):
    text: str
    receipt: str


class CVListItem(BaseModel):
    id: int
    uploaded_at: datetime


class CVItem(CVListItem):
    text: str
    version: int


def receipt_codec() -> Fernet:
    key = settings.github_token_encryption_key
    if key is None:
        raise error(503, "Chưa cấu hình khóa xác nhận CV.")
    derived = digest(key.get_secret_value().encode(), b"ita:cv-upload:v1", sha256)
    return Fernet(base64.urlsafe_b64encode(derived))


def parse_upload(data: bytes, media_type: str) -> str:
    try:
        scan_cv(data)
    except UnsafeCV:
        raise error(422, "Tệp CV bị phát hiện không an toàn.") from None
    except ScannerUnavailable:
        raise error(503, "Dịch vụ quét tệp CV chưa sẵn sàng. Hãy thử lại.") from None
    try:
        process = subprocess.run(
            [sys.executable, "-m", "app.modules.cvs.parser", media_type],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=True,
        )
        return CVText(text=json.loads(process.stdout)).text
    except (subprocess.SubprocessError, ValueError):
        raise error(
            422, "Không đọc được văn bản CV. Hãy dùng PDF có chữ hoặc DOCX hợp lệ."
        ) from None
    except OSError:
        raise error(503, "Trình đọc CV chưa sẵn sàng.") from None


@router.post("/preview", dependencies=[Depends(csrf)])
async def preview_cv(
    request: Request, response: Response, user: CurrentUser
) -> CVPreview:
    response.headers.update(NO_STORE)
    media_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    if media_type not in (PDF, DOCX):
        raise error(415, "Chỉ chấp nhận PDF và DOCX.")
    if not UPLOAD_SLOTS.acquire(blocking=False):
        raise error(429, "Đang xử lý nhiều tệp CV. Hãy thử lại.")
    try:
        data = await read_limited(request, MAX_FILE_BYTES)
        magic = b"%PDF-" if media_type == PDF else b"PK\x03\x04"
        if not data.startswith(magic):
            raise error(415, "Nội dung tệp không khớp định dạng PDF hoặc DOCX.")
        codec = receipt_codec()
        text = await run_in_threadpool(parse_upload, data, media_type)
        receipt = codec.encrypt(f"{user.id}:{uuid4().hex}".encode()).decode()
        return CVPreview(text=text, receipt=receipt)
    finally:
        UPLOAD_SLOTS.release()


async def confirm_body(request: Request) -> ConfirmCV:
    try:
        return ConfirmCV.model_validate_json(
            await read_limited(request, MAX_TEXT_CHARS * 12 + 4096)
        )
    except ValidationError:
        raise error(422, "Nội dung hoặc mã xác nhận CV không hợp lệ.") from None


async def edit_body(request: Request) -> EditCV:
    try:
        return EditCV.model_validate_json(
            await read_limited(request, MAX_TEXT_CHARS * 12 + 4096)
        )
    except ValidationError:
        raise error(422, "Nội dung hoặc phiên bản CV không hợp lệ.") from None


def owned_uploads(user_id: int):
    return select(CV).where(
        CV.user_id == user_id, CV.content["source"].as_string() == UPLOAD_SOURCE
    )


def owned_upload(db: Session, user_id: int, cv_id: int, *, lock: bool = False) -> CV:
    query = owned_uploads(user_id).where(CV.id == cv_id)
    cv = db.scalar(query.with_for_update() if lock else query)
    if cv is None:
        raise error(404, "Không tìm thấy CV.")
    return cv


def cv_item(cv: CV) -> CVItem:
    return CVItem(
        id=cv.id,
        uploaded_at=cv.uploaded_at,
        text=cv.content["text"],
        version=cv.content["version"],
    )


@router.post("", status_code=201, dependencies=[Depends(csrf)])
def confirm_cv(
    response: Response,
    user: CurrentUser,
    db: DB,
    body: Annotated[ConfirmCV, Depends(confirm_body)],
) -> CVItem:
    response.headers.update(NO_STORE)
    codec = receipt_codec()
    try:
        owner, upload_id = (
            codec.decrypt(body.receipt.encode(), ttl=PREVIEW_TTL).decode().split(":")
        )
        if owner != str(user.id):
            raise InvalidToken
    except (InvalidToken, ValueError):
        raise error(422, "Mã xác nhận CV không hợp lệ hoặc đã hết hạn.") from None
    # Serialize repeat confirms for the same account even across backend processes.
    db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    cv = db.scalar(
        owned_uploads(user.id).where(CV.content["upload_id"].as_string() == upload_id)
    )
    if cv is not None:
        return cv_item(cv)
    cv = CV(
        user_id=user.id,
        content={
            "source": UPLOAD_SOURCE,
            "upload_id": upload_id,
            "version": 1,
            "text": body.text,
        },
    )
    db.add(cv)
    db.commit()
    db.refresh(cv)
    return cv_item(cv)


@router.get("")
def list_cvs(
    response: Response,
    user: CurrentUser,
    db: DB,
    before_id: Annotated[int | None, Query(gt=0, le=2**63 - 1)] = None,
) -> list[CVListItem]:
    response.headers.update(NO_STORE)
    query = owned_uploads(user.id).with_only_columns(CV.id, CV.uploaded_at)
    if before_id is not None:
        query = query.where(CV.id < before_id)
    rows = db.execute(query.order_by(CV.id.desc()).limit(50))
    return [CVListItem(id=row.id, uploaded_at=row.uploaded_at) for row in rows]


CVId = Annotated[int, Field(gt=0, le=2**63 - 1)]


@router.get("/references")
def list_references(
    query: Annotated[ReferenceQuery, Query()], response: Response, user: CurrentUser
) -> ReferenceSearch:
    response.headers.update(NO_STORE)
    return search_references(query)


@router.get("/{cv_id}")
def get_cv(cv_id: CVId, response: Response, user: CurrentUser, db: DB) -> CVItem:
    response.headers.update(NO_STORE)
    return cv_item(owned_upload(db, user.id, cv_id))


@router.put("/{cv_id}", dependencies=[Depends(csrf)])
def update_cv(
    cv_id: CVId,
    response: Response,
    user: CurrentUser,
    db: DB,
    body: Annotated[EditCV, Depends(edit_body)],
) -> CVItem:
    response.headers.update(NO_STORE)
    cv = owned_upload(db, user.id, cv_id, lock=True)
    if body.version != cv.content["version"]:
        raise error(409, "CV đã thay đổi. Hãy mở lại bản mới nhất.")
    cv.content = {**cv.content, "version": body.version + 1, "text": body.text}
    db.commit()
    return cv_item(cv)


@router.delete("/{cv_id}", status_code=204, dependencies=[Depends(csrf)])
def delete_cv(cv_id: CVId, user: CurrentUser, db: DB) -> Response:
    db.delete(owned_upload(db, user.id, cv_id, lock=True))
    db.commit()
    return Response(status_code=204, headers=NO_STORE)
