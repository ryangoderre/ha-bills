"""Pure-Python recurrence logic for bills (no Home Assistant imports)."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Iterator

FREQUENCIES = ("once", "weekly", "monthly", "yearly")


def add_months(d: date, months: int) -> date:
    """Add months, clamping the day to the end of shorter months."""
    total = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def validate(frequency: str, interval: int) -> None:
    if frequency not in FREQUENCIES:
        raise ValueError(f"Unknown frequency: {frequency}")
    if interval < 1:
        raise ValueError("interval must be >= 1")


def occurrence(anchor: date, frequency: str, interval: int, n: int) -> date | None:
    """The nth occurrence (n=0 is the anchor), always computed from the anchor.

    Computing from the anchor instead of the previous date avoids drift:
    a bill on the 31st goes Jan 31 -> Feb 28 -> Mar 31, not Mar 28.
    """
    validate(frequency, interval)
    if frequency == "once":
        return anchor if n == 0 else None
    if frequency == "weekly":
        return anchor + timedelta(weeks=interval * n)
    if frequency == "monthly":
        return add_months(anchor, interval * n)
    return add_months(anchor, 12 * interval * n)  # yearly


def iter_occurrences(
    anchor: date, frequency: str, interval: int, end_date: date | None = None
) -> Iterator[date]:
    n = 0
    while True:
        d = occurrence(anchor, frequency, interval, n)
        if d is None or (end_date is not None and d > end_date):
            return
        yield d
        n += 1


def next_on_or_after(
    anchor: date,
    frequency: str,
    interval: int,
    on_or_after: date,
    end_date: date | None = None,
) -> date | None:
    for d in iter_occurrences(anchor, frequency, interval, end_date):
        if d >= on_or_after:
            return d
    return None


def next_after(
    anchor: date,
    frequency: str,
    interval: int,
    after: date,
    end_date: date | None = None,
) -> date | None:
    """Strictly after `after`. Used by mark_paid to advance to the next due date."""
    return next_on_or_after(
        anchor, frequency, interval, after + timedelta(days=1), end_date
    )


def occurrences_between(
    anchor: date,
    frequency: str,
    interval: int,
    start: date,
    end: date,
    end_date: date | None = None,
) -> list[date]:
    """All occurrences in [start, end]. Used for the calendar later."""
    out = []
    for d in iter_occurrences(anchor, frequency, interval, end_date):
        if d > end:
            break
        if d >= start:
            out.append(d)
    return out


def days_until(due: date, today: date) -> int:
    return (due - today).days