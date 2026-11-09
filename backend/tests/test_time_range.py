from datetime import date, datetime

import pytest
from fastapi import HTTPException

from app.core.time_range import resolve_range
from app.modules.analysis.evidence import UTC
from app.services.activity import _timestamp


def test_month_utc_boundary():
    start, _end = resolve_range("month", month="2026-10")
    assert start.isoformat() == "2026-10-01T00:00:00+00:00"
    assert _end.isoformat() == "2026-11-01T00:00:00+00:00"
    assert start <= datetime(2026, 10, 31, 23, 59, 59, 999999, tzinfo=UTC) < _end
    outside = _end
    assert not (start <= outside < _end)


def test_timezone_ho_chi_minh():
    start, end = resolve_range(
        "custom",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 1),
        timezone_name="Asia/Ho_Chi_Minh",
    )
    assert start.isoformat() == "2026-10-31T17:00:00+00:00"
    assert end.isoformat() == "2026-11-01T17:00:00+00:00"


def test_invalid_range():
    with pytest.raises(HTTPException) as exc_info:
        resolve_range(
            "custom", start_date=date(2026, 11, 2), end_date=date(2026, 11, 1)
        )
    assert exc_info.value.status_code == 422


def test_invalid_month():
    with pytest.raises(HTTPException) as exc_info:
        resolve_range("month", month="2026-13")
    assert exc_info.value.status_code == 422

    with pytest.raises(HTTPException) as exc_info2:
        resolve_range("month", month="invalid-month")
    assert exc_info2.value.status_code == 422


def test_preset_leap_year():
    start, _end = resolve_range(
        "preset", preset="1y", now=datetime(2024, 2, 29, 12, tzinfo=UTC)
    )
    assert start.date() == date(2023, 2, 28)


def test_year_mode_boundaries():
    start, end = resolve_range("year", year=2026, timezone_name="UTC")
    assert start.isoformat() == "2026-01-01T00:00:00+00:00"
    assert end.isoformat() == "2027-01-01T00:00:00+00:00"


def test_cross_month_intervals():
    start, end = resolve_range(
        "custom",
        start_date=date(2026, 3, 15),
        end_date=date(2026, 5, 20),
        timezone_name="UTC",
    )
    assert start.isoformat() == "2026-03-15T00:00:00+00:00"
    assert end.isoformat() == "2026-05-21T00:00:00+00:00"
    assert (end - start).days == 67


def test_cross_year_intervals():
    start, end = resolve_range(
        "custom",
        start_date=date(2025, 11, 1),
        end_date=date(2026, 2, 15),
        timezone_name="UTC",
    )
    assert start.isoformat() == "2025-11-01T00:00:00+00:00"
    assert end.isoformat() == "2026-02-16T00:00:00+00:00"


def test_february_leap_year_boundaries():
    # Leap year 2024
    start_leap, end_leap = resolve_range("month", month="2024-02", timezone_name="UTC")
    assert (end_leap - start_leap).days == 29

    # Non-leap year 2023
    start_non, end_non = resolve_range("month", month="2023-02", timezone_name="UTC")
    assert (end_non - start_non).days == 28


def test_preset_all_interval():
    start, end = resolve_range("preset", preset="all", timezone_name="UTC")
    assert start.isoformat() == "1970-01-01T00:00:00+00:00"
    assert end > start


def test_timestamp_parser_handles_trailing_z_and_offsets():
    dt1 = _timestamp("2026-11-09T08:00:00Z")
    assert dt1.tzinfo is not None
    assert dt1.astimezone(UTC).hour == 8

    dt2 = _timestamp("2026-11-09T15:00:00+07:00")
    assert dt2.astimezone(UTC).hour == 8

    with pytest.raises(ValueError):
        _timestamp("")
