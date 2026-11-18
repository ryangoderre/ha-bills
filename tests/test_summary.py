from datetime import date

from custom_components.bills.summary import compute_reminders, compute_summary

TODAY = date(2026, 11, 17)


def make(name, due, amount=None, freq="monthly", remind=3, active=True):
    return {
        "id": name.lower(), "name": name, "amount": amount,
        "frequency": freq, "interval": 1, "anchor_date": due, "next_due": due,
        "end_date": None, "active": active, "remind_days_before": remind,
        "autopay": False,
    }


def test_empty():
    s = compute_summary([], TODAY)
    assert s["next"] is None and s["due_soon"] == [] and s["overdue"] == []
    assert s["due_this_month"] == 0


def test_next_is_earliest():
    s = compute_summary([make("Rent", "2026-12-01"), make("Phone", "2026-11-20")], TODAY)
    assert s["next"]["name"] == "Phone"
    assert s["next"]["days_until"] == 3


def test_overdue():
    s = compute_summary([make("Water", "2026-11-10"), make("Rent", "2026-12-01")], TODAY)
    assert [b["name"] for b in s["overdue"]] == ["Water"]
    assert s["overdue"][0]["days_until"] == -7
    assert s["next"]["name"] == "Water"


def test_due_soon_uses_each_bills_own_window():
    s = compute_summary([
        make("Phone", "2026-11-20", remind=3),
        make("Gym", "2026-11-25", remind=3),
        make("Car", "2026-11-25", remind=10),
    ], TODAY)
    assert sorted(b["name"] for b in s["due_soon"]) == ["Car", "Phone"]


def test_due_this_month_includes_overdue_excludes_next_month():
    bills = [
        make("Phone", "2026-11-20", amount=50),
        make("Water", "2026-11-10", amount=30),
        make("Rent", "2026-12-01", amount=1500),
    ]
    assert compute_summary(bills, TODAY)["due_this_month"] == 80


def test_weekly_counts_each_remaining_occurrence():
    s = compute_summary([make("Allowance", "2026-11-18", amount=10, freq="weekly")], TODAY)
    assert s["due_this_month"] == 20  # Nov 18 and Nov 25


def test_bills_without_amount_are_counted_separately():
    s = compute_summary([make("Phone", "2026-11-20")], TODAY)
    assert s["due_this_month"] == 0 and s["due_this_month_unpriced"] == 1


def test_retired_bills_ignored():
    assert compute_summary([make("Old", "2026-11-18", active=False)], TODAY)["next"] is None

def test_reminder_kinds():
    bills = [
        make("Water", "2026-11-10"),
        make("Today", "2026-11-17"),
        make("Phone", "2026-11-19", remind=3),
        make("Gym", "2026-11-25", remind=3),
    ]
    got = [(r["name"], r["kind"]) for r in compute_reminders(bills, TODAY)]
    assert got == [("Water", "overdue"), ("Today", "due_today"), ("Phone", "upcoming")]


def test_reminders_skip_retired_bills():
    assert compute_reminders([make("Old", "2026-11-18", active=False)], TODAY) == []


def test_reminder_payload_has_what_the_blueprint_needs():
    b = make("Phone", "2026-11-19")
    b["biller_url"] = "https://example.com/pay"
    r = compute_reminders([b], TODAY)[0]
    assert r["summary"] == "Phone due in 2 days"
    assert r["biller_url"] == "https://example.com/pay"
    assert r["bill_id"] == "phone"