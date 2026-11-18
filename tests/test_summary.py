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

from custom_components.bills.summary import widget_lines, widget_text


def _widget(bills):
    return widget_text(compute_summary(bills, TODAY))


def test_widget_no_bills():
    assert _widget([]) == "No bills due"


def test_widget_next_only():
    assert _widget([make("Rent", "2026-12-01")]) == "Rent due in 14 days"


def test_widget_counts_others_this_week():
    bills = [make("Phone", "2026-11-19"), make("Gym", "2026-11-22"),
             make("Car", "2026-11-24"), make("Rent", "2026-12-01")]
    assert _widget(bills) == "Phone due in 2 days · 2 more this week"


def test_widget_one_more_today():
    assert _widget([make("Phone", "2026-11-17"), make("Gym", "2026-11-17")]) \
        == "Gym due today · 1 more this week"


def test_widget_overdue_first():
    bills = [make("Water", "2026-11-14"), make("Power", "2026-11-16"),
             make("Phone", "2026-11-19"), make("Rent", "2026-12-01")]
    assert _widget(bills) == (
        "Water overdue by 3 days · 1 more overdue · 1 more this week"
    )


def test_widget_ignores_retired():
    assert _widget([make("Old", "2026-11-18", active=False)]) == "No bills due"


def test_widget_lines_with_amounts():
    s = compute_summary([make("Phone", "2026-11-19", amount=1080.5),
                         make("Gym", "2026-11-20"),
                         make("Rent", "2026-12-01", amount=1500)], TODAY)
    assert widget_lines(s, "USD") == [
        "Phone due in 2 days · $1,080.50",
        "Gym due in 3 days",
    ]
    assert widget_lines(s, "SEK")[0] == "Phone due in 2 days · 1,080.50 SEK"


from custom_components.bills.summary import widget_html


def test_widget_html_lists_week_with_overdue_bold():
    s = compute_summary([make("Water", "2026-11-14", amount=30),
                         make("A&B <Gym>", "2026-11-19"),
                         make("Rent", "2026-12-01")], TODAY)
    assert widget_html(s, "USD") == (
        "<b>Bills this week</b><br>"
        "<b>Water overdue by 3 days · $30.00</b><br>"
        "A&amp;B &lt;Gym&gt; due in 2 days"
    )


def test_widget_html_falls_back_to_summary_line():
    assert widget_html(compute_summary([make("Rent", "2026-12-01")], TODAY)) \
        == "Rent due in 14 days"
    assert widget_html(compute_summary([], TODAY)) == "No bills due"


from datetime import date as _date

from custom_components.bills.summary import cost_breakdown

CATS = {"u": {"id": "u", "name": "Utilities", "icon": "mdi:flash"},
        "s": {"id": "s", "name": "Subscriptions", "icon": "mdi:cloud"}}
NOV = (_date(2026, 11, 1), _date(2026, 11, 30))


def cat(bill, cid):
    bill["category_id"] = cid
    return bill


def pay(bill_id, due, amount):
    return {"bill_id": bill_id, "due_date": due, "paid_date": due, "amount_paid": amount}


def test_cost_breakdown_month_by_category():
    bills = [
        cat(make("Water", "2026-12-10", amount=40), "u"),   # Nov paid, Dec next
        cat(make("Power", "2026-11-25", amount=100), "u"),  # still due in Nov
        cat(make("iCloud", "2026-11-13", amount=0.99), "s"),  # overdue, still due
        make("Gym", "2026-11-20", amount=30),               # uncategorized
    ]
    out = cost_breakdown(bills, [pay("water", "2026-11-10", 42.5)], CATS, *NOV)
    assert (out["paid"], out["upcoming"], out["total"]) == (42.5, 130.99, 173.49)
    rows = [(r["name"], r["paid"], r["upcoming"], r["total"]) for r in out["categories"]]
    assert rows == [("Utilities", 42.5, 100.0, 142.5),
                    ("Subscriptions", 0.0, 0.99, 0.99),
                    ("Uncategorized", 0.0, 30.0, 30.0)]


def test_cost_breakdown_counts_by_due_date_not_paid_date():
    bills = [make("Rent", "2027-01-01", amount=1500)]
    # December's rent paid early in November counts in December, not November.
    p = {"bill_id": "rent", "due_date": "2026-12-01", "paid_date": "2026-11-28",
         "amount_paid": 1500}
    assert cost_breakdown(bills, [p], {}, *NOV)["total"] == 0
    dec = cost_breakdown(bills, [p], {}, _date(2026, 12, 1), _date(2026, 12, 31))
    assert dec["paid"] == 1500 and dec["upcoming"] == 0


def test_cost_breakdown_year_counts_every_occurrence():
    bills = [make("Phone", "2026-11-19", amount=85)]
    payments = [pay("phone", f"2026-{m:02d}-19", 85) for m in range(1, 11)]
    out = cost_breakdown(bills, payments, {}, _date(2026, 1, 1), _date(2026, 12, 31))
    assert (out["paid"], out["upcoming"], out["total"]) == (850, 170, 1020)


def test_cost_breakdown_unpriced_and_retired_and_deleted_category():
    old = cat(make("Old", "2026-11-05", amount=10, active=False), "gone")
    bills = [old, make("Claude", "2026-11-18")]
    out = cost_breakdown(bills, [pay("old", "2026-11-05", 10)], CATS, *NOV)
    assert out["unpriced"] == 1
    assert [(r["name"], r["paid"]) for r in out["categories"]] == [("Uncategorized", 10)]


def test_cost_breakdown_empty():
    out = cost_breakdown([], [], CATS, *NOV)
    assert out["total"] == 0 and out["categories"] == []


from custom_components.bills.summary import history_years, year_breakdown


def test_breakdown_lists_bills_inside_each_category():
    bills = [cat(make("Water", "2026-12-10", amount=40), "u"),
             cat(make("Power", "2026-11-25", amount=100), "u")]
    out = cost_breakdown(bills, [pay("water", "2026-11-10", 42.5)], CATS, *NOV)
    lines = [(b["name"], b["paid"], b["upcoming"], b["count"])
             for b in out["categories"][0]["bills"]]
    assert lines == [("Power", 0.0, 100.0, 1), ("Water", 42.5, 0.0, 1)]


def test_year_breakdown_has_twelve_months_summing_to_year():
    bills = [make("Phone", "2026-11-19", amount=85)]
    payments = [pay("phone", f"2026-{m:02d}-19", 85) for m in range(1, 11)]
    y = year_breakdown(bills, payments, {}, 2026)
    assert y["year"] == 2026 and len(y["months"]) == 12
    assert [m["total"] for m in y["months"]] == [85] * 12
    assert round(sum(m["total"] for m in y["months"]), 2) == y["total"] == 1020
    assert y["months"][1]["end"] == "2026-02-28"
    phone = y["categories"][0]["bills"][0]
    assert (phone["name"], phone["count"], phone["paid"], phone["upcoming"]) == (
        "Phone", 12, 850, 170)


def test_history_years_from_payments_and_old_unpaid():
    bills = [make("Old unpaid", "2023-06-01"), make("Phone", "2026-11-19")]
    payments = [pay("phone", "2025-03-19", 85), pay("phone", "2026-01-19", 85)]
    assert history_years(bills, payments, TODAY) == [2025, 2023]
    assert history_years([], [], TODAY) == []


def test_retired_bill_name_falls_back_to_payment():
    p = {"bill_id": "gone", "bill_name": "Old gym", "due_date": "2026-11-02",
         "paid_date": "2026-11-02", "amount_paid": 20}
    out = cost_breakdown([], [p], {}, *NOV)
    assert out["categories"][0]["bills"][0]["name"] == "Old gym"


from custom_components.bills.summary import bill_history


def _p(due, amount):
    return {"bill_id": "water", "due_date": due, "paid_date": due, "amount_paid": amount}


def test_history_empty():
    h = bill_history([], TODAY)
    assert h["count"] == 0 and h["average"] is None and h["trend"] is None


def test_history_single_payment():
    h = bill_history([_p("2026-11-10", 40)], TODAY)
    assert (h["count"], h["last"], h["previous"], h["trend"]) == (1, 40, None, None)


def test_history_change_and_trend_up():
    pays = [_p(f"2026-{m:02d}-10", a) for m, a in
            zip(range(5, 11), [40, 40, 40, 44, 46, 48])]
    h = bill_history(list(reversed(pays)), TODAY)  # order doesn't matter
    assert (h["last"], h["previous"], h["change"], h["change_pct"]) == (48, 46, 2, 4.3)
    assert h["trend"]["direction"] == "up" and h["trend"]["window"] == 3
    assert (h["trend"]["recent_avg"], h["trend"]["prior_avg"]) == (46, 40)
    assert (h["min"], h["max"], h["average"]) == (40, 48, 43)


def test_history_steady_within_two_percent():
    pays = [_p(f"2026-{m:02d}-10", a) for m, a in zip(range(7, 11), [85, 85, 85.5, 85])]
    assert bill_history(pays, TODAY)["trend"]["direction"] == "steady"


def test_history_year_over_year():
    pays = [_p(f"2025-{m:02d}-01", 1450) for m in range(1, 13)]
    pays += [_p(f"2026-{m:02d}-01", 1500) for m in range(1, 12)]
    yoy = bill_history(pays, TODAY)["year_over_year"]
    # Rolling windows: the last 12 months are Dec 2025 (1450) + Jan-Nov 2026 (1500).
    assert yoy["direction"] == "up" and yoy["recent_avg"] == 1495.83
    assert yoy["prior_avg"] == 1450 and yoy["pct"] == 3.2


def test_history_ignores_payments_without_amount():
    h = bill_history([_p("2026-10-10", None), _p("2026-11-10", 40)], TODAY)
    assert h["count"] == 1 and h["previous"] is None
