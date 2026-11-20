import importlib.util
from datetime import date
from pathlib import Path

import pytest

# Load budget.py by path so the test doesn't need Home Assistant installed.
_path = Path(__file__).resolve().parent.parent / "custom_components" / "bills" / "budget.py"
_spec = importlib.util.spec_from_file_location("bills_budget", _path)
budget = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(budget)

TODAY = date(2026, 11, 18)


def make_budget(start="2026-11-18", starting=0.0, savings=0.0):
    b = budget.new_budget()
    b.update(start_date=start, starting_amount=starting, starting_savings=savings)
    return b


def stream(sid, type_, amount, freq="weekly", interval=1, start="2026-01-01", end=None):
    return {"id": sid, "type": type_, "name": sid, "amount": amount, "frequency": freq,
            "interval": interval, "start_date": start, "end_date": end, "category_id": None}


def tx(day, kind, amount):
    return {"id": f"{day}{kind}{amount}", "date": day, "kind": kind, "amount": amount,
            "category_id": None, "note": "", "created": day}


def bill(name, amount, freq="monthly", interval=1, active=True, end=None):
    return {"id": name, "name": name, "amount": amount, "frequency": freq,
            "interval": interval, "active": active, "end_date": end}


def fifty_a_day():
    b = make_budget()
    b["recurring"]["pay"] = stream("pay", "income", 350)  # $350/week = $50/day
    return b


def test_per_day_rates():
    assert budget.per_day(2000, "weekly", 2) == pytest.approx(142.857, abs=1e-3)
    assert budget.per_day(1500, "monthly") == pytest.approx(49.281, abs=1e-3)
    assert budget.per_day(365.25, "yearly") == 1
    assert budget.per_day(100, "once") == 0


def test_not_configured():
    assert budget.compute(budget.new_budget(), [], [], TODAY) == {"configured": False}


def test_overspend_carries_to_next_day():
    # The example: $50/day, spend $100 today -> today -$50, tomorrow $0.
    b = fifty_a_day()
    b["transactions"].append(tx("2026-11-18", "expense", 100))
    out = budget.compute(b, [], [], TODAY)
    assert [d["amount"] for d in out["days"]] == [-50, 0, 50]
    assert out["spent_today"] == 100 and out["allowance"]["allowance"] == 50


def test_underspend_carries_forward():
    b = fifty_a_day()
    b["start_date"] = "2026-11-16"
    b["transactions"].append(tx("2026-11-16", "expense", 20))
    out = budget.compute(b, [], [], TODAY)
    assert out["today"] == 130  # 3 days x 50 - 20


def test_bills_and_savings_come_out_first():
    b = make_budget()
    b["recurring"]["pay"] = stream("pay", "income", 2000, interval=2)
    b["recurring"]["save"] = stream("save", "savings", 140, interval=2)  # $10/day
    bills = [bill("Phone", 85), bill("Gym", 365.25, "yearly"),
             bill("Old", 500, active=False), bill("Varies", None),
             bill("Fee", 40, "once")]
    out = budget.compute(b, bills, [], TODAY)
    a = out["allowance"]
    assert a["income"] == pytest.approx(142.86, abs=0.01)
    assert a["savings"] == 10
    assert a["bills"] == pytest.approx(85 * 12 / 365.25 + 1, abs=0.01)
    assert out["today"] == a["allowance"]
    assert out["bills_without_amount"] == 1


def test_one_off_income_adds_immediately_and_future_one_shows_ahead():
    b = fifty_a_day()
    b["transactions"] += [tx("2026-11-18", "income", 25), tx("2026-11-20", "income", 180)]
    out = budget.compute(b, [], [], TODAY)
    assert [d["amount"] for d in out["days"]] == [75, 125, 355]
    assert out["income_today"] == 25


def test_income_stream_start_and_end_dates():
    b = make_budget(start="2026-11-10")
    b["recurring"]["pay"] = stream("pay", "income", 350, start="2026-11-12", end="2026-11-18")
    out = budget.compute(b, [], [], TODAY)
    # Nov 12..18 earn 50 each = 350; nothing after the end date.
    assert [d["amount"] for d in out["days"]] == [350, 350, 350]


def test_frozen_ledger_keeps_past_days_when_income_changes():
    b = fifty_a_day()
    b["start_date"] = "2026-11-16"
    b["ledger"] = budget.days_to_freeze(b, [], TODAY)
    assert sorted(b["ledger"]) == ["2026-11-16", "2026-11-17"]
    b["recurring"]["pay"]["amount"] = 700  # now $100/day, from today on
    out = budget.compute(b, [], [], TODAY)
    assert out["today"] == 50 + 50 + 100
    assert budget.days_to_freeze(b, [], TODAY) == {}


def test_savings_totals_and_moves():
    b = fifty_a_day()
    b["start_date"] = "2026-11-17"
    b["starting_savings"] = 1000
    b["recurring"]["save"] = stream("save", "savings", 70)  # $10/day
    b["transactions"] += [tx("2026-11-18", "to_savings", 200),
                          tx("2026-11-18", "from_savings", 50)]
    out = budget.compute(b, [], [], TODAY)
    s = out["savings"]
    assert s["total"] == 1000 + 10 + 10 + 200 - 50
    assert s["per_month"] == pytest.approx(10 * 365.25 / 12, abs=0.01)
    # Spending money: 2 days x (50 - 10) - 200 moved in + 50 taken out
    assert out["today"] == 80 - 200 + 50


def test_one_time_bill_payment_comes_out_when_paid():
    b = fifty_a_day()
    bills = [bill("Fee", 30, "once", active=False)]
    payments = [{"bill_id": "Fee", "paid_date": "2026-11-18", "amount_paid": 30},
                {"bill_id": "Fee", "paid_date": "2026-11-01", "amount_paid": 99}]
    out = budget.compute(b, bills, payments, TODAY)
    assert out["today"] == 20 and out["spent_today"] == 30  # Nov 1 is before start


def test_transactions_before_start_are_ignored():
    b = fifty_a_day()
    b["starting_amount"] = 10
    b["transactions"].append(tx("2026-11-01", "expense", 500))
    assert budget.compute(b, [], [], TODAY)["today"] == 60


def paid(bill_id, day, amount, estimate="missing"):
    p = {"id": f"p-{bill_id}-{day}", "bill_id": bill_id, "bill_name": bill_id,
         "due_date": day, "paid_date": day, "amount_paid": amount}
    if estimate != "missing":
        p["estimate"] = estimate
    return p


def test_paying_more_than_estimate_comes_out_of_that_day():
    b = fifty_a_day()
    bills = [bill("Water", 40)]
    base = budget.compute(b, bills, [], TODAY)["today"]
    out = budget.compute(b, bills, [paid("Water", "2026-11-18", 52, estimate=40)], TODAY)
    assert out["today"] == round(base - 12, 2)
    assert out["spent_today"] == 12
    adj = out["bill_adjustments"][0]
    assert (adj["bill_name"], adj["difference"], adj["estimate"], adj["paid"]) == (
        "Water", 12, 40, 52)


def test_paying_less_than_estimate_gives_the_rest_back():
    b = fifty_a_day()
    bills = [bill("Water", 40)]
    base = budget.compute(b, bills, [], TODAY)["today"]
    out = budget.compute(b, bills, [paid("Water", "2026-11-18", 35, estimate=40)], TODAY)
    assert out["today"] == round(base + 5, 2)
    assert out["spent_today"] == 0


def test_no_adjustment_when_paid_matches_or_estimate_missing():
    b = fifty_a_day()
    bills = [bill("Water", 40), bill("Claude", None), bill("Fee", 30, "once")]
    payments = [
        paid("Water", "2026-11-18", 40, estimate=40),      # exactly the estimate
        paid("Water", "2026-11-18", 60),                   # older payment, no saved estimate
        paid("Claude", "2026-11-18", 20, estimate=None),   # bill had no amount
        paid("Fee", "2026-11-18", 30, estimate=25),        # one-time: comes out in full instead
    ]
    out = budget.compute(b, bills, payments, TODAY)
    assert out["bill_adjustments"] == []


def test_adjustments_before_budget_start_are_ignored():
    b = fifty_a_day()
    out = budget.compute(b, [bill("Water", 40)],
                         [paid("Water", "2026-11-01", 90, estimate=40)], TODAY)
    assert out["bill_adjustments"] == [] and out["today"] == budget.compute(
        b, [bill("Water", 40)], [], TODAY)["today"]


def test_changing_an_estimate_later_never_changes_the_past():
    b = fifty_a_day()
    b["start_date"] = "2026-11-15"
    water = bill("Water", 40)
    payments = [paid("Water", "2026-11-16", 52, estimate=40)]
    # Midnight locks in the past days with the $40 estimate.
    b["ledger"] = budget.days_to_freeze(b, [water], TODAY)
    before = budget.compute(b, [water], payments, TODAY)

    water["amount"] = 100  # estimate raised today
    after = budget.compute(b, [water], payments, TODAY)

    # The payment's adjustment still uses the $40 it was measured against.
    assert after["bill_adjustments"][0]["difference"] == 12
    # Past days keep the $40 rate; only today uses the new estimate.
    old_rate, new_rate = 40 * 12 / 365.25, 100 * 12 / 365.25
    assert after["today"] == pytest.approx(before["today"] - (new_rate - old_rate), abs=0.01)


# ---------- "Count in my budget" ----------

def test_bill_not_in_budget_is_not_spread():
    b = fifty_a_day()
    counted = bill("Rent", 1500)
    left_out = {**bill("Gym", 30), "in_budget": False}
    out = budget.compute(b, [counted, left_out], [], TODAY)
    assert out["allowance"]["bills"] == pytest.approx(49.28, abs=0.01)
    # Bills from before the setting existed (no key) still count.
    assert budget.in_budget(bill("Old", 10)) is True


def test_bill_not_in_budget_without_amount_isnt_flagged():
    b = fifty_a_day()
    bills = [bill("Power", None), {**bill("Gift", None), "in_budget": False}]
    assert budget.compute(b, bills, [], TODAY)["bills_without_amount"] == 1


def test_payment_remembers_whether_it_counted():
    b = fifty_a_day()
    fee = bill("Fee", 30, "once", active=False)
    water = bill("Water", 40)
    payments = [{**paid("Fee", "2026-11-18", 30), "in_budget": False},
                {**paid("Water", "2026-11-18", 52, estimate=40), "in_budget": False}]
    out = budget.compute(b, [fee, water], payments, TODAY)
    assert out["spent_today"] == 0 and out["bill_adjustments"] == []
    # Turning the bill back on later doesn't change what that payment did.
    water["in_budget"] = True
    assert budget.compute(b, [fee, water], payments, TODAY)["bill_adjustments"] == []
    # Payments saved before the setting existed still count.
    old = [paid("Fee", "2026-11-18", 30)]
    assert budget.compute(b, [fee, water], old, TODAY)["spent_today"] == 30


# ---------- the 3-day view ----------

def test_each_day_shows_its_step_and_what_changed():
    # Like the screenshot: a savings plan starting tomorrow makes tomorrow's
    # step smaller than today's daily amount.
    b = fifty_a_day()
    b["recurring"]["fund"] = stream("Fund", "savings", 70, start="2026-11-19")  # $10/day
    b["transactions"].append(tx("2026-11-18", "expense", 100))
    days = budget.compute(b, [], [], TODAY)["days"]
    assert [d["amount"] for d in days] == [-50, -10, 30]
    assert [d["change"] for d in days] == [-50, 40, 40]
    assert [d["allowance"] for d in days] == [50, 40, 40]
    assert "reasons" not in days[0] and "reasons" not in days[2]
    assert days[1]["reasons"] == ["Fund (savings plan) starts"]


def test_bill_ending_is_a_reason():
    b = fifty_a_day()
    days = budget.compute(b, [bill("Loan", 304.38, end="2026-11-18")], [], TODAY)["days"]
    assert days[1]["reasons"] == ["Loan (bill) ended"]


def test_breakdown_adds_up_to_the_daily_amount():
    # $3,271.06 every 2 weeks, ~$135.56/day of bills and $800.04/month saved:
    # rounding each part on its own gives 233.65 - 135.56 - 26.28 = 71.81,
    # one cent off the real 71.80.
    b = make_budget()
    b["recurring"]["pay"] = stream("pay", "income", 3271.06, interval=2)
    b["recurring"]["save"] = stream("save", "savings", 800.04, freq="monthly")
    bills = [bill("All", 4123.15)]
    a = budget.compute(b, bills, [], TODAY)["allowance"]
    assert round(a["income"] - a["bills"] - a["savings"], 2) == a["allowance"]
    r = budget.day_rates(TODAY, b, bills)
    for k in ("income", "bills", "savings"):
        assert abs(a[k] - r[k]) <= 0.0151


def test_three_days_add_up_to_the_cent():
    # The real data that showed -180.62 -> -110.13 (+70.49) under a +70.48 step.
    b = make_budget(start="2026-11-13")
    b["recurring"]["pay"] = stream("pay", "income", 3271.06, interval=2, start="2026-11-13")
    for sid, amt, freq, start in (("ef", 150, "weekly", "2026-11-13"), ("ex", 80, "weekly", "2026-11-13"),
                                  ("opie", 40, "monthly", "2026-11-19"), ("auto", 300, "monthly", "2026-11-11")):
        b["recurring"][sid] = stream(sid, "savings", amt, freq=freq,
                                     interval=2 if freq == "weekly" else 1, start=start)
    b["transactions"].append(tx("2026-11-18", "expense", 752.37))
    days = budget.compute(b, [bill("All", 4123.29)], [], date(2026, 11, 19))["days"]
    for prev, d in zip(days, days[1:]):
        assert round(prev["amount"] + d["change"], 2) == d["amount"]


def test_rows_list_transactions_and_bill_payments_newest_first():
    b = make_budget(start="2026-11-10")
    b["transactions"] += [tx("2026-11-17", "expense", 12.5), tx("2026-11-18", "income", 20),
                          tx("2026-11-17", "to_savings", 100)]
    bills = [bill("Water", 40), bill("Fee", 30, "once", active=False)]
    payments = [paid("Water", "2026-11-17", 52, estimate=40),
                paid("Water", "2026-11-12", 35, estimate=40),
                paid("Fee", "2026-11-16", 30),
                paid("Fee", "2026-11-01", 99)]  # before the budget started
    rows = budget.budget_rows(b, bills, payments)
    assert [(r["date"], r["kind"]) for r in rows][0] == ("2026-11-18", "income")
    assert {r["kind"] for r in rows if r["date"] == "2026-11-17"} == {
        "expense", "to_savings", "bill_adjustment"}
    assert all(r["date"] >= "2026-11-10" or r["kind"] in budget.KINDS for r in rows)
    fee = next(r for r in rows if r["kind"] == "bill_payment")
    assert fee["date"] == "2026-11-16" and fee["amount"] == 30 and fee["readonly"]


def test_recent_notes_newest_first_once_each_without_automatic_ones():
    def t(day, kind, note, cat=None, created=None):
        return {"id": note + day, "date": day, "kind": kind, "amount": 5, "note": note,
                "category_id": cat, "created": created or day}
    txs = [t("2026-11-10", "expense", "Chipotle", "food"),
           t("2026-11-15", "expense", "chipotle", "eat"),       # same note, newer
           t("2026-11-12", "expense", "Dining", "food"),         # auto: category name
           t("2026-11-13", "expense", "Expense"),                # auto: no category
           t("2026-11-14", "income", "Card rewards"),
           t("2026-11-14", "to_savings", "Rainy day"),           # savings moves aren't suggested
           t("2026-11-16", "expense", "  ")]
    notes = budget.recent_notes(txs, {"food": "Dining", "eat": "Eating out"})
    assert notes["expense"] == [{"note": "chipotle", "category_id": "eat"}]
    assert notes["income"] == [{"note": "Card rewards", "category_id": None}]


def test_day_totals_match_what_counts_as_spending():
    b = make_budget(start="2026-11-10")
    b["transactions"] += [tx("2026-11-17", "expense", 12.5), tx("2026-11-17", "income", 5),
                          tx("2026-11-17", "to_savings", 100)]
    bills = [bill("Water", 40), bill("Fee", 30, "once", active=False)]
    payments = [paid("Water", "2026-11-17", 52, estimate=40),   # $12 over: spent
                paid("Water", "2026-11-12", 35, estimate=40),   # $5 under: not spending
                paid("Fee", "2026-11-16", 30)]
    totals = budget.day_totals(budget.budget_rows(b, bills, payments))
    assert totals["2026-11-17"] == {"spent": 24.5, "income": 5, "count": 4}
    assert totals["2026-11-16"] == {"spent": 30, "income": 0, "count": 1}
    assert totals["2026-11-12"]["spent"] == 0 and "2026-11-15" not in totals
    # Same rule as "spent today" in the daily budget.
    day = date(2026, 11, 17)
    assert budget.compute(b, bills, payments, day)["spent_today"] == 24.5
