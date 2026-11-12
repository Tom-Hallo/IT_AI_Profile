from datetime import UTC, date, datetime

import pytest
from fastapi import HTTPException

from app.modules.analysis.report_window import ReportWindow


def test_dashboard_date_window_includes_the_entire_last_utc_day():
    window = ReportWindow(date(2026, 10, 5), date(2026, 10, 5))
    assert window.start == datetime(2026, 10, 5, tzinfo=UTC)
    assert window.end == datetime(2026, 10, 6, tzinfo=UTC)


def test_dashboard_rejects_reversed_dates():
    with pytest.raises(HTTPException) as error:
        ReportWindow(date(2026, 10, 6), date(2026, 10, 5))
    assert error.value.status_code == 422


def test_no_dates_leave_the_query_unfiltered():
    assert ReportWindow().conditions(None) == []
