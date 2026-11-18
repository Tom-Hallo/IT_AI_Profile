"""Unit tests for Operator Telemetry & Redacted Logging (PBI-039)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import create_app
from app.modules.telemetry.schemas import (
    TelemetryEventCategory,
    TelemetryEventCreate,
    TelemetryReasonCode,
    TelemetrySeverity,
)
from app.modules.telemetry.service import (
    TelemetryService,
    redact_payload_recursively,
    redact_string,
)
from app.modules.users.models import User

SENSITIVE_GITHUB_TOKEN = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz012345"
SENSITIVE_OPENAI_KEY = "sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"
SENSITIVE_CV_TEXT = "Candidate full resume content: worked at secret defense lab."
SENSITIVE_CODE_SNIPPET = "def internal_secret_logic(): return 42"


def test_redact_string_masks_github_and_openai_tokens():
    raw = f"Error calling GitHub with token={SENSITIVE_GITHUB_TOKEN} failed"
    redacted = redact_string(raw)
    assert SENSITIVE_GITHUB_TOKEN not in redacted
    assert "[REDACTED]" in redacted

    ai_raw = f"Error provider: {SENSITIVE_OPENAI_KEY}"
    assert SENSITIVE_OPENAI_KEY not in redact_string(ai_raw)


def test_redact_payload_masks_cv_code_and_tokens_recursively():
    payload = {
        "user": "developer_1",
        "nested": {
            "token": SENSITIVE_GITHUB_TOKEN,
            "cv_content": SENSITIVE_CV_TEXT,
            "source_code": SENSITIVE_CODE_SNIPPET,
            "normal_metric": 42,
        },
        "log_message": f"Authorization: Bearer {SENSITIVE_GITHUB_TOKEN}",
    }

    cleaned = redact_payload_recursively(payload)

    assert cleaned["nested"]["token"] == "[REDACTED]"
    assert cleaned["nested"]["cv_content"] == "[REDACTED]"
    assert cleaned["nested"]["source_code"] == "[REDACTED]"
    assert cleaned["nested"]["normal_metric"] == 42
    assert SENSITIVE_GITHUB_TOKEN not in str(cleaned)


def test_telemetry_service_records_and_correlates_events():
    svc = TelemetryService()
    corr_id = "req-corr-001"
    job_id = "job-uuid-123"

    event_in = TelemetryEventCreate(
        category=TelemetryEventCategory.API,
        severity=TelemetrySeverity.ERROR,
        reason_code=TelemetryReasonCode.AI_PROVIDER_ERROR,
        correlation_id=corr_id,
        job_id=job_id,
        event_name="ai_mentor.call_failed",
        status="error",
        payload={
            "api_key": SENSITIVE_OPENAI_KEY,
            "error_detail": "Quota exhausted",
            "prompt_cv": SENSITIVE_CV_TEXT,
        },
    )

    recorded = svc.record_event(event_in)
    assert recorded.correlation_id == corr_id
    assert recorded.job_id == job_id
    assert recorded.reason_code == TelemetryReasonCode.AI_PROVIDER_ERROR
    assert SENSITIVE_OPENAI_KEY not in str(recorded.redacted_payload)
    assert SENSITIVE_CV_TEXT not in str(recorded.redacted_payload)

    # Diagnostic query filter
    matched = svc.query_diagnostics(correlation_id=corr_id)
    assert len(matched) == 1
    assert matched[0].id == recorded.id

    unmatched = svc.query_diagnostics(correlation_id="other-corr-id")
    assert len(unmatched) == 0


def test_telemetry_helpers_for_rate_limit_and_job_failure():
    svc = TelemetryService()
    rl_event = svc.record_rate_limit(
        correlation_id="corr-rl-999",
        provider="github",
        details={"reset_in": 120, "token": SENSITIVE_GITHUB_TOKEN},
    )
    assert rl_event.reason_code == TelemetryReasonCode.RATE_LIMIT_EXCEEDED
    assert rl_event.status == "rate_limited"
    assert SENSITIVE_GITHUB_TOKEN not in str(rl_event.redacted_payload)

    fail_event = svc.record_job_failure(
        correlation_id="corr-job-555",
        job_id="job-555",
        error_msg=f"Failed with key {SENSITIVE_OPENAI_KEY}",
    )
    assert fail_event.reason_code == TelemetryReasonCode.JOB_EXECUTION_FAILED
    assert SENSITIVE_OPENAI_KEY not in str(fail_event.redacted_payload)


@pytest.fixture
def telemetry_api_client():
    app = create_app()
    fake_user = User(id=1, email="operator@test.com", full_name="Operator")
    app.dependency_overrides[get_current_user] = lambda: fake_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_api_record_and_query_diagnostics(telemetry_api_client: TestClient):
    corr_id = "corr-api-777"
    post_resp = telemetry_api_client.post(
        "/api/v1/telemetry/events",
        json={
            "category": "api",
            "correlation_id": corr_id,
            "event_name": "api.request_failed",
            "severity": "ERROR",
            "reason_code": "RATE_LIMIT_EXCEEDED",
            "payload": {
                "token": SENSITIVE_GITHUB_TOKEN,
                "resume_text": SENSITIVE_CV_TEXT,
                "status_code": 429,
            },
        },
    )
    assert post_resp.status_code == 201
    created_data = post_resp.json()
    assert created_data["correlation_id"] == corr_id
    assert SENSITIVE_GITHUB_TOKEN not in str(created_data)
    assert SENSITIVE_CV_TEXT not in str(created_data)

    get_resp = telemetry_api_client.get(
        "/api/v1/telemetry/diagnostics",
        params={"correlation_id": corr_id},
    )
    assert get_resp.status_code == 200
    diag_data = get_resp.json()
    assert diag_data["total"] >= 1
    assert any(e["correlation_id"] == corr_id for e in diag_data["events"])
