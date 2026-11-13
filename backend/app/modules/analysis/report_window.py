"""Optional inclusive calendar dates for dashboard reads, interpreted in UTC."""

from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException


class ReportWindow:
    def __init__(
        self, date_from: date | None = None, date_to: date | None = None
    ) -> None:
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")
        self.start = datetime.combine(date_from, time.min, UTC) if date_from else None
        self.end = (
            datetime.combine(date_to + timedelta(days=1), time.min, UTC)
            if date_to and date_to < date.max
            else None
        )

    def conditions(self, column):
        filters = []
        if self.start is not None:
            filters.append(column >= self.start)
        if self.end is not None:
            filters.append(column < self.end)
        return filters
