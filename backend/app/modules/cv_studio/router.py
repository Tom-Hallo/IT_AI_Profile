"""Owner-scoped CV Studio endpoints."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import and_, func, select

from app.modules.consent.router import csrf
from app.modules.cv_studio.export import PDFCharacterError, export_cv
from app.modules.cv_studio.models import CVStudioVersion
from app.modules.cv_studio.schemas import (
    GenerateCV,
    SaveVersion,
    VersionDetail,
    VersionSummary,
)
from app.modules.cv_studio.service import (
    append_version,
    compose,
    get_version,
    version_detail,
    versions_for,
)
from app.modules.cvs.router import DB, NO_STORE, CurrentUser, error, read_limited

router = APIRouter(prefix="/cv-studio", tags=["CV Studio"])
Number = Annotated[int, Path(gt=0, le=2**31 - 1)]
Offset = Annotated[int, Query(ge=0, le=2**31 - 1)]
PAGE_SIZE = 50


async def read_json[T: (GenerateCV, SaveVersion)](
    request: Request, schema: type[T]
) -> T:
    if (
        request.headers.get("content-type", "").split(";", 1)[0].strip()
        != "application/json"
    ):
        raise error(415, "Dữ liệu cần đúng định dạng JSON.")
    raw = await read_limited(request, 256_000)
    try:
        return schema.model_validate_json(raw)
    except ValidationError:
        raise error(
            422, "Thông tin CV không hợp lệ hoặc chưa xác nhận sử dụng AI."
        ) from None


async def generation_body(request: Request) -> GenerateCV:
    return await read_json(request, GenerateCV)


async def version_body(request: Request) -> SaveVersion:
    return await read_json(request, SaveVersion)


@router.post("/generate", status_code=201, dependencies=[Depends(csrf)])
async def generate(
    response: Response,
    user: CurrentUser,
    db: DB,
    body: Annotated[GenerateCV, Depends(generation_body)],
) -> VersionDetail:
    response.headers.update(NO_STORE)
    return await compose(db, user, body)


@router.get("")
def list_documents(
    response: Response, user: CurrentUser, db: DB, offset: Offset = 0
) -> list[VersionSummary]:
    response.headers.update(NO_STORE)
    latest = (
        select(
            CVStudioVersion.document_id,
            func.max(CVStudioVersion.number).label("number"),
        )
        .where(CVStudioVersion.user_id == user.id)
        .group_by(CVStudioVersion.document_id)
        .subquery()
    )
    query = (
        select(CVStudioVersion)
        .join(
            latest,
            and_(
                CVStudioVersion.document_id == latest.c.document_id,
                CVStudioVersion.number == latest.c.number,
            ),
        )
        .where(CVStudioVersion.user_id == user.id)
        .order_by(CVStudioVersion.created_at.desc(), CVStudioVersion.document_id)
        .offset(offset)
        .limit(PAGE_SIZE)
    )
    return [VersionSummary.model_validate(row) for row in db.scalars(query)]


@router.get("/{document_id}/versions")
def list_versions(
    document_id: UUID, response: Response, user: CurrentUser, db: DB, offset: Offset = 0
) -> list[VersionSummary]:
    response.headers.update(NO_STORE)
    query = versions_for(user.id, document_id).order_by(CVStudioVersion.number.desc())
    rows = db.scalars(query.offset(offset).limit(PAGE_SIZE)).all()
    if not rows and not offset:
        raise error(404, "Không tìm thấy tài liệu CV.")
    return [VersionSummary.model_validate(row) for row in rows]


@router.get("/{document_id}/versions/{number}")
def read_version(
    document_id: UUID, number: Number, response: Response, user: CurrentUser, db: DB
) -> VersionDetail:
    response.headers.update(NO_STORE)
    return version_detail(db, get_version(db, user.id, document_id, number))


@router.post("/{document_id}/versions", status_code=201, dependencies=[Depends(csrf)])
def save_version(
    document_id: UUID,
    response: Response,
    user: CurrentUser,
    db: DB,
    body: Annotated[SaveVersion, Depends(version_body)],
) -> VersionDetail:
    response.headers.update(NO_STORE)
    return append_version(db, user.id, document_id, body)


@router.get("/{document_id}/versions/{number}/export")
def download(
    document_id: UUID,
    number: Number,
    user: CurrentUser,
    db: DB,
    format: Literal["pdf", "docx"],
) -> Response:
    detail = version_detail(db, get_version(db, user.id, document_id, number))
    if detail.source_unavailable:
        raise error(
            409,
            "Nguồn GitHub đã thay đổi. Hãy tạo bản nháp từ nguồn còn truy cập được.",
        )
    try:
        data, media_type = export_cv(detail, format)
    except PDFCharacterError:
        raise error(
            422, "PDF chưa hỗ trợ một số ký tự trong CV. Bạn có thể chọn DOCX."
        ) from None
    return Response(
        data,
        media_type=media_type,
        headers={
            **NO_STORE,
            "Content-Disposition": f'attachment; filename="cv-v{number}.{format}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
