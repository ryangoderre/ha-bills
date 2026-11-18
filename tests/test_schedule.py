import importlib.util
from datetime import date
from pathlib import Path

import pytest

# Load schedule.py directly by path so the test doesn't import the package's
# __init__.py (which needs Home Assistant installed).
_path = (
    Path(__file__).resolve().parent.parent
    / "custom_components" / "bills" / "schedule.py"
)
_spec = importlib.util.spec_from_file_location("bills_schedule", _path)
schedule = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(schedule)


def test_monthly_31st_clamps_without_drift():
    got = schedule.occurrences_between(
        date(2026, 1, 31), "monthly", 1, date(2026, 1, 1), date(2026, 4, 30)
    )
    assert got == [
        date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)
    ]


def test_yearly_leap_day():
    got = schedule.occurrences_between(
        date(2024, 2, 29), "yearly", 1, date(2024, 1, 1), date(2028, 12, 31)
    )
    assert got == [
        date(2024, 2, 29), date(2025, 2, 28), date(2026, 2, 28),
        date(2027, 2, 28), date(2028, 2, 29),
    ]


def test_biweekly():
    got = schedule.next_on_or_after(
        date(2026, 11, 6), "weekly", 2, date(2026, 11, 17)
    )
    assert got == date(2026, 11, 20)


def test_every_six_months():
    got = schedule.next_on_or_after(
        date(2026, 1, 15), "monthly", 6, date(2026, 2, 1)
    )
    assert got == date(2026, 7, 15)


def test_on_or_after_includes_same_day():
    d = date(2026, 11, 17)
    assert schedule.next_on_or_after(d, "monthly", 1, d) == d


def test_next_after_is_strict():
    d = date(2026, 11, 17)
    assert schedule.next_after(d, "monthly", 1, d) == date(2026, 12, 17)


def test_once():
    anchor = date(2026, 12, 1)
    assert schedule.next_on_or_after(anchor, "once", 1, date(2026, 11, 17)) == anchor
    assert schedule.next_on_or_after(anchor, "once", 1, date(2026, 12, 2)) is None


def test_end_date_retires_bill():
    anchor, end = date(2026, 1, 10), date(2026, 3, 15)
    assert schedule.next_on_or_after(
        anchor, "monthly", 1, date(2026, 3, 1), end
    ) == date(2026, 3, 10)
    assert schedule.next_on_or_after(
        anchor, "monthly", 1, date(2026, 3, 11), end
    ) is None


def test_invalid_inputs():
    with pytest.raises(ValueError):
        schedule.next_on_or_after(date(2026, 1, 1), "daily", 1, date(2026, 1, 1))
    with pytest.raises(ValueError):
        schedule.next_on_or_after(date(2026, 1, 1), "monthly", 0, date(2026, 1, 1))