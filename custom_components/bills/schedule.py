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


def check_end_date(due: date, frequency: str, end_date: date | None) -> None:
    if frequency != "once" and end_date is not None and end_date < due:
        raise ValueError("The end date can't be before the due date")


def reschedule(bill: dict, changes: dict) -> dict:
    """Work out a bill's new schedule fields after an edit.

    `changes` may hold due_date, frequency, interval and end_date (dates as
    date objects, end_date may be None to clear it). The result has the
    schedule fields to store on the bill.

    If the due date, frequency or interval change, the series restarts from
    the new due date. If only the end date changes, the original anchor is
    kept, so a bill on the 31st keeps landing on month ends.
    """
    if not bill["active"] or not bill["next_due"]:
        raise ValueError("A retired bill can't be rescheduled")
    cur_due = date.fromisoformat(bill["next_due"])
    cur_end = date.fromisoformat(bill["end_date"]) if bill["end_date"] else None

    due = changes.get("due_date") or cur_due
    frequency = changes.get("frequency", bill["frequency"])
    interval = changes.get("interval", bill["interval"])
    end = changes["end_date"] if "end_date" in changes else cur_end
    validate(frequency, interval)
    if frequency == "once":
        end = None
    check_end_date(due, frequency, end)

    same_series = (due, frequency, interval) == (
        cur_due, bill["frequency"], bill["interval"]
    )
    return {
        "anchor_date": bill["anchor_date"] if same_series else due.isoformat(),
        "next_due": due.isoformat(),
        "frequency": frequency,
        "interval": interval,
        "end_date": end.isoformat() if end else None,
    }

def suggest_restore_due(bill: dict, today: date) -> date | None:
    """A sensible next due date for bringing a retired bill back.

    Keeps the old due date if it hasn't passed (undoing a mistaken retire),
    otherwise the next date on the bill's schedule from today. None when the
    schedule has nothing left (a paid one-time bill, or past its end date).
    """
    if bill["next_due"] and date.fromisoformat(bill["next_due"]) >= today:
        return date.fromisoformat(bill["next_due"])
    end = date.fromisoformat(bill["end_date"]) if bill["end_date"] else None
    return next_on_or_after(
        date.fromisoformat(bill["anchor_date"]),
        bill["frequency"], bill["interval"], today, end,
    )


def restore_plan(bill: dict, today: date, due: date | None = None) -> dict:
    """Schedule fields for restoring a retired bill.

    Without `due`, uses suggest_restore_due. If the date is on the bill's
    existing schedule the original anchor is kept; otherwise the series
    restarts from it. An end date before the new due date is cleared, since
    the bill would otherwise end immediately.
    """
    if bill["active"]:
        raise ValueError(f"'{bill['name']}' isn't retired")
    if due is None:
        due = suggest_restore_due(bill, today)
        if due is None:
            raise ValueError(
                f"'{bill['name']}' has no dates left on its schedule; "
                "pick a new due date"
            )
    anchor = date.fromisoformat(bill["anchor_date"])
    on_schedule = next_on_or_after(
        anchor, bill["frequency"], bill["interval"], due
    ) == due
    end = date.fromisoformat(bill["end_date"]) if bill["end_date"] else None
    if end is not None and end < due:
        end = None
    return {
        "anchor_date": anchor.isoformat() if on_schedule else due.isoformat(),
        "next_due": due.isoformat(),
        "end_date": end.isoformat() if end else None,
    }
