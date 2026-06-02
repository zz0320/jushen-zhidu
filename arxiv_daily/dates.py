from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

ARXIV_BATCH_TIMEZONE = "America/New_York"
ARXIV_BATCH_CUTOFF_HOUR = 14


def parse_day(value: Optional[str], timezone_name: str = "Asia/Shanghai") -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(ZoneInfo(timezone_name)).date()


def local_day_to_utc_range(day: date, timezone_name: str = "Asia/Shanghai") -> Tuple[datetime, datetime]:
    local_tz = ZoneInfo(timezone_name)
    start_local = datetime.combine(day, time.min, tzinfo=local_tz)
    end_local = start_local + timedelta(days=1) - timedelta(minutes=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def arxiv_date_range(day: date, timezone_name: str = "Asia/Shanghai") -> str:
    start_utc, end_utc = local_day_to_utc_range(day, timezone_name)
    return f"[{start_utc:%Y%m%d%H%M} TO {end_utc:%Y%m%d%H%M}]"


def arxiv_date_ranges(day: date, timezone_name: str = "Asia/Shanghai") -> List[str]:
    start_utc, end_utc = local_day_to_utc_range(day, timezone_name)
    return _split_utc_ranges(start_utc, end_utc)


def _split_utc_ranges(start_utc: datetime, end_utc: datetime) -> List[str]:
    ranges: List[str] = []
    current_start = start_utc
    while current_start.date() < end_utc.date():
        current_end = datetime.combine(current_start.date(), time(23, 59), tzinfo=timezone.utc)
        ranges.append(f"[{current_start:%Y%m%d%H%M} TO {current_end:%Y%m%d%H%M}]")
        current_start = datetime.combine(current_start.date() + timedelta(days=1), time.min, tzinfo=timezone.utc)
    ranges.append(f"[{current_start:%Y%m%d%H%M} TO {end_utc:%Y%m%d%H%M}]")
    return ranges


def arxiv_batch_utc_range(day: date) -> Optional[Tuple[datetime, datetime]]:
    """Return the arXiv announcement batch window for an Eastern-time date."""
    weekday = day.weekday()
    if weekday in {4, 5}:
        return None

    batch_tz = ZoneInfo(ARXIV_BATCH_TIMEZONE)
    if weekday == 6:
        start_day = day - timedelta(days=3)
        end_day = day - timedelta(days=2)
    else:
        start_day = day - timedelta(days=3 if weekday == 0 else 1)
        end_day = day
    start_local = datetime.combine(start_day, time(ARXIV_BATCH_CUTOFF_HOUR), tzinfo=batch_tz)
    end_local = datetime.combine(end_day, time(ARXIV_BATCH_CUTOFF_HOUR), tzinfo=batch_tz) - timedelta(minutes=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def arxiv_batch_date_ranges(day: date) -> List[str]:
    batch_range = arxiv_batch_utc_range(day)
    if batch_range is None:
        return []
    start_utc, end_utc = batch_range
    return _split_utc_ranges(start_utc, end_utc)


def arxiv_submitted_date_query(day: date, timezone_name: str = "Asia/Shanghai") -> str:
    terms = [f"submittedDate:{date_range}" for date_range in arxiv_batch_date_ranges(day)]
    if len(terms) == 1:
        return terms[0]
    if not terms:
        return ""
    return "(" + " OR ".join(terms) + ")"
