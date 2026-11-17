"""Telemetry redaction engine & service for Operator Diagnostics (PBI-039).

Ensures sensitive details (tokens, secrets, private repo snippets, CV text)
are rigorously redacted before persisting or logging telemetry events.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from app.modules.telemetry.schemas import (
    TelemetryEventCreate,
    TelemetryEventItem,
    TelemetryReasonCode,
    TelemetrySeverity,
)

# Common secret regex patterns (tokens, keys, bearer headers)
_PATTERNS = [
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{16,255}"),  # GitHub tokens
    re.compile(r"sk-[A-Za-z0-9-_]{20,255}"),  # OpenAI keys
    re.compile(r"AIza[0-9A-Za-z-_]{35}"),  # Google API keys
    re.compile(r"bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(
        r"(?i)(password|secret|token|api_key|access_token|private_key)"
        r"(\s*[:=]\s*)([^\s,;'\"]+)"
    ),
]

SENSITIVE_FIELD_NAMES = {
    "token",
    "access_token",
    "secret",
    "password",
    "authorization",
    "cv",
    "cv_content",
    "cv_text",
    "resume",
    "resume_text",
    "prompt_cv",
    "private_source",
    "source_code",
    "code_snippet",
    "matched_content",
}

REDACTION_MARKER = "[REDACTED]"


def redact_string(val: str) -> str:
    """Sanitize string values from recognized sensitive tokens and patterns."""
    sanitized = val
    for pat in _PATTERNS:
        sanitized = pat.sub(REDACTION_MARKER, sanitized)
    return sanitized


def redact_payload_recursively(data: Any) -> Any:
    """Recursively mask secrets and drop/mask private source and CV details."""
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            k_lower = str(k).lower()
            if any(sensitive in k_lower for sensitive in SENSITIVE_FIELD_NAMES):
                cleaned[k] = REDACTION_MARKER
            else:
                cleaned[k] = redact_payload_recursively(v)
        return cleaned
    if isinstance(data, list):
        return [redact_payload_recursively(item) for item in data]
    if isinstance(data, str):
        return redact_string(data)
    return data


class TelemetryService:
    """Telemetry recorder and diagnostic querying service."""

    def __init__(self) -> None:
        self._in_memory_store: list[TelemetryEventItem] = []

    def record_event(self, event_in: TelemetryEventCreate) -> TelemetryEventItem:
        """Sanitize payload and record the telemetry event with correlation ID."""
        safe_payload = redact_payload_recursively(event_in.payload)
        now = datetime.now(UTC)
        item = TelemetryEventItem(
            id=str(uuid.uuid4()),
            timestamp=now,
            correlation_id=event_in.correlation_id,
            job_id=event_in.job_id,
            category=event_in.category,
            severity=event_in.severity,
            reason_code=event_in.reason_code,
            event_name=event_in.event_name,
            status=event_in.status,
            redacted_payload=safe_payload,
            user_id=event_in.user_id,
        )
        self._in_memory_store.append(item)
        return item

    def record_rate_limit(
        self,
        correlation_id: str,
        provider: str,
        details: dict[str, Any] | None = None,
    ) -> TelemetryEventItem:
        """Helper to log provider rate limits."""
        return self.record_event(
            TelemetryEventCreate(
                category="github" if "github" in provider.lower() else "ai_provider",
                severity=TelemetrySeverity.WARNING,
                reason_code=TelemetryReasonCode.RATE_LIMIT_EXCEEDED,
                correlation_id=correlation_id,
                event_name=f"{provider}.rate_limit",
                status="rate_limited",
                payload=details or {},
            )
        )

    def record_job_failure(
        self,
        correlation_id: str,
        job_id: str,
        error_msg: str,
        reason: TelemetryReasonCode = TelemetryReasonCode.JOB_EXECUTION_FAILED,
        user_id: int | None = None,
    ) -> TelemetryEventItem:
        """Helper to log job execution errors without exposing private code."""
        return self.record_event(
            TelemetryEventCreate(
                category="worker",
                severity=TelemetrySeverity.ERROR,
                reason_code=reason,
                correlation_id=correlation_id,
                job_id=job_id,
                user_id=user_id,
                event_name="job.failed",
                status="failed",
                payload={"error": error_msg},
            )
        )

    def query_diagnostics(
        self,
        correlation_id: str | None = None,
        job_id: str | None = None,
        reason_code: TelemetryReasonCode | None = None,
    ) -> list[TelemetryEventItem]:
        """Query diagnostic events with filtering."""
        results = self._in_memory_store
        if correlation_id:
            results = [e for e in results if e.correlation_id == correlation_id]
        if job_id:
            results = [e for e in results if e.job_id == job_id]
        if reason_code:
            results = [e for e in results if e.reason_code == reason_code]
        return results


_default_telemetry_service = TelemetryService()


def get_telemetry_service() -> TelemetryService:
    return _default_telemetry_service
