"""Pydantic schemas for Operator Telemetry & Redacted Logging (PBI-039)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class TelemetryEventCategory(StrEnum):
    API = "api"
    WORKER = "worker"
    AI_PROVIDER = "ai_provider"
    GITHUB = "github"
    SYSTEM = "system"


class TelemetrySeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class TelemetryReasonCode(StrEnum):
    SUCCESS = "SUCCESS"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    JOB_EXECUTION_FAILED = "JOB_EXECUTION_FAILED"
    AI_PROVIDER_ERROR = "AI_PROVIDER_ERROR"
    AI_QUOTA_EXHAUSTED = "AI_QUOTA_EXHAUSTED"
    SSRF_BLOCKED = "SSRF_BLOCKED"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class TelemetryEventCreate(BaseModel):
    """Payload to record a telemetry event."""

    category: TelemetryEventCategory
    severity: TelemetrySeverity = TelemetrySeverity.INFO
    reason_code: TelemetryReasonCode = TelemetryReasonCode.SUCCESS
    correlation_id: str = Field(..., description="Request or Job correlation ID")
    job_id: str | None = None
    user_id: int | None = None
    event_name: str = Field(..., max_length=150)
    status: str = Field("ok", description="Status e.g. ok, failure, degraded")
    payload: dict[str, Any] = Field(default_factory=dict)


class TelemetryEventItem(BaseModel):
    """Redacted telemetry event returned to operator."""

    id: str
    timestamp: datetime
    correlation_id: str
    job_id: str | None = None
    category: TelemetryEventCategory
    severity: TelemetrySeverity
    reason_code: TelemetryReasonCode
    event_name: str
    status: str
    redacted_payload: dict[str, Any]
    user_id: int | None = None


class TelemetryQueryResponse(BaseModel):
    """List of telemetry events for diagnostics."""

    total: int
    correlation_id_filter: str | None = None
    events: list[TelemetryEventItem]
