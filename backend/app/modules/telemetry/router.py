"""Operator Telemetry Diagnostics API Router (PBI-039)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_current_user
from app.modules.telemetry.schemas import (
    TelemetryEventCreate,
    TelemetryEventItem,
    TelemetryQueryResponse,
    TelemetryReasonCode,
)
from app.modules.telemetry.service import (
    TelemetryService,
    get_telemetry_service,
)
from app.modules.users.models import User

router = APIRouter(prefix="/telemetry", tags=["Operator Telemetry & Diagnostics"])


@router.post(
    "/events",
    response_model=TelemetryEventItem,
    status_code=status.HTTP_201_CREATED,
    summary="Record a telemetry event with automatic secret & CV redaction",
)
def record_telemetry_event(
    event_in: TelemetryEventCreate,
    service: Annotated[TelemetryService, Depends(get_telemetry_service)],
    user: Annotated[User, Depends(get_current_user)],
) -> TelemetryEventItem:
    """Record telemetry event; sensitive fields are masked before storing."""
    if event_in.user_id is None:
        event_in.user_id = user.id
    return service.record_event(event_in)


@router.get(
    "/diagnostics",
    response_model=TelemetryQueryResponse,
    summary="Query operator telemetry diagnostics without sensitive leakage",
)
def get_diagnostics(
    service: Annotated[TelemetryService, Depends(get_telemetry_service)],
    user: Annotated[User, Depends(get_current_user)],
    correlation_id: Annotated[str | None, Query(max_length=100)] = None,
    job_id: Annotated[str | None, Query(max_length=100)] = None,
    reason_code: Annotated[TelemetryReasonCode | None, Query()] = None,
) -> TelemetryQueryResponse:
    """Query telemetry diagnostics by correlation_id or job_id."""
    _ = user
    events = service.query_diagnostics(
        correlation_id=correlation_id,
        job_id=job_id,
        reason_code=reason_code,
    )
    return TelemetryQueryResponse(
        total=len(events),
        correlation_id_filter=correlation_id,
        events=events,
    )
