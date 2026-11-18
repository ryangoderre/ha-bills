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

def _bill(next_due="2026-02-28", anchor="2026-01-31", freq="monthly",
          interval=1, end=None, active=True):
    return {"next_due": next_due, "anchor_date": anchor, "frequency": freq,
            "interval": interval, "end_date": end, "active": active}


def test_reschedule_new_due_date_restarts_series():
    out = schedule.reschedule(_bill(), {"due_date": date(2026, 3, 5)})
    assert out["anchor_date"] == "2026-03-05"
    assert out["next_due"] == "2026-03-05"


def test_reschedule_end_date_only_keeps_anchor():
    out = schedule.reschedule(_bill(), {"end_date": date(2026, 12, 31)})
    assert out["anchor_date"] == "2026-01-31"
    assert out["end_date"] == "2026-12-31"
    # month-end behaviour survives: the next one after Feb 28 is Mar 31
    nxt = schedule.next_after(date(2026, 1, 31), "monthly", 1, date(2026, 2, 28))
    assert nxt == date(2026, 3, 31)


def test_reschedule_unchanged_values_keep_anchor():
    out = schedule.reschedule(
        _bill(), {"due_date": date(2026, 2, 28), "frequency": "monthly", "interval": 1}
    )
    assert out["anchor_date"] == "2026-01-31"


def test_reschedule_frequency_change_restarts():
    out = schedule.reschedule(_bill(), {"frequency": "weekly", "interval": 2})
    assert out["anchor_date"] == "2026-02-28"
    assert (out["frequency"], out["interval"]) == ("weekly", 2)


def test_reschedule_clear_end_date():
    out = schedule.reschedule(_bill(end="2026-06-30"), {"end_date": None})
    assert out["end_date"] is None


def test_reschedule_once_drops_end_date():
    out = schedule.reschedule(_bill(end="2026-06-30"), {"frequency": "once"})
    assert out["end_date"] is None


def test_reschedule_rejects_end_before_due():
    with pytest.raises(ValueError):
        schedule.reschedule(_bill(), {"end_date": date(2026, 2, 1)})


def test_reschedule_rejects_retired():
    with pytest.raises(ValueError):
        schedule.reschedule(_bill(active=False, next_due=None), {"interval": 2})


TODAY = date(2026, 11, 18)


def _retired(next_due, anchor="2026-01-31", freq="monthly", end=None):
    return {"name": "Phone", "active": False, "next_due": next_due,
            "anchor_date": anchor, "frequency": freq, "interval": 1,
            "end_date": end}


def test_restore_keeps_future_due_date():
    b = _retired("2026-11-30")
    assert schedule.suggest_restore_due(b, TODAY) == date(2026, 11, 30)
    out = schedule.restore_plan(b, TODAY)
    assert out["next_due"] == "2026-11-30"
    assert out["anchor_date"] == "2026-01-31"


def test_restore_past_due_moves_to_next_on_schedule():
    out = schedule.restore_plan(_retired("2026-08-31"), TODAY)
    assert out["next_due"] == "2026-11-30"
    assert out["anchor_date"] == "2026-01-31"


def test_restore_paid_one_time_needs_a_date():
    b = _retired(None, anchor="2026-05-01", freq="once")
    assert schedule.suggest_restore_due(b, TODAY) is None
    with pytest.raises(ValueError):
        schedule.restore_plan(b, TODAY)
    out = schedule.restore_plan(b, TODAY, date(2026, 12, 1))
    assert out["next_due"] == out["anchor_date"] == "2026-12-01"


def test_restore_off_schedule_date_restarts_series():
    out = schedule.restore_plan(_retired("2026-08-31"), TODAY, date(2026, 12, 10))
    assert out["anchor_date"] == "2026-12-10"


def test_restore_clears_end_date_already_passed():
    b = _retired("2026-06-30", end="2026-06-30")
    assert schedule.suggest_restore_due(b, TODAY) is None
    out = schedule.restore_plan(b, TODAY, date(2026, 11, 30))
    assert out["end_date"] is None
    assert out["anchor_date"] == "2026-01-31"


def test_restore_rejects_active_bill():
    b = _retired("2026-11-30")
    b["active"] = True
    with pytest.raises(ValueError):
        schedule.restore_plan(b, TODAY)
