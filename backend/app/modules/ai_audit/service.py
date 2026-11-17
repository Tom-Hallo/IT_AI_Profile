"""Append trace events without accepting prompts, payloads or resource identifiers."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.ai_audit.models import (
    AIUsageEvent,
    Consent,
    Feature,
    Phase,
    Provider,
    Source,
    Status,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trace:
    user_id: int
    feature: Feature
    provider: Provider
    operation_id: UUID = field(default_factory=uuid4)

    def write(
        self,
        db: Session,
        phase: Phase,
        sources: Iterable[tuple[Source, Consent]],
        status: Status,
        *,
        required: bool = True,
    ) -> None:
        events = [
            AIUsageEvent(
                user_id=self.user_id,
                operation_id=self.operation_id,
                feature=self.feature,
                provider=self.provider,
                phase=phase,
                source=source,
                consent=consent,
                status=status,
            )
            for source, consent in dict.fromkeys(sources)
        ]
        if not events:
            return
        try:
            with Session(bind=db.get_bind()) as audit_db, audit_db.begin():
                audit_db.add_all(events)
        except SQLAlchemyError as exc:
            logger.error("Unable to persist AI audit event: %s", type(exc).__name__)
            if required:
                raise HTTPException(
                    503, "Không thể ghi lịch sử sử dụng AI. Hãy thử lại."
                ) from None
