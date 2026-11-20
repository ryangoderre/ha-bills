"""Pure-Python daily budget logic (no Home Assistant imports).

Each day earns an allowance:

    recurring income per day - bills per day - savings plans per day

Today's budget is everything carried over from earlier days, plus today's
allowance, plus one-off income, minus expenses. Overspending or underspending
carries into the next day. Past days are "frozen" into a ledger at midnight so
later changes to income, bills or savings only affect today onward.

The budget dict (stored as-is):
    start_date        ISO date the budget starts, or None until set up
    starting_amount   spending money carried in on the start date
    starting_savings  savings already set aside before the start date
    recurring         {id: stream}; stream = {id, type: income|savings, name,
                      amount, frequency, interval, start_date, end_date,
                      category_id}
    transactions      [{id, date, kind, amount, category_id, note, created}]
    ledger            {ISO date: {income, bills, savings, allowance}} for
                      frozen past days
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

DAYS_PER_YEAR = 365.25
KINDS = ("expense", "income", "to_savings", "from_savings")
SIGN = {"expense": -1, "income": 1, "to_savings": -1, "from_savings": 1}
STREAM_TYPES = ("income", "savings")
STREAM_FREQUENCIES = ("weekly", "monthly", "yearly")
DAYS_AHEAD = 2  # today plus the next two days, like Today's Budget


def new_budget() -> dict[str, Any]:
    return {"start_date": None, "starting_amount": 0.0, "starting_savings": 0.0,
            "recurring": {}, "transactions": [], "ledger": {}}


def per_day(amount: float, frequency: str, interval: int = 1) -> float:
    """Spread a recurring amount evenly over the days of its cycle."""
    if frequency == "weekly":
        return amount / (7 * interval)
    if frequency == "monthly":
        return amount * 12 / DAYS_PER_YEAR / interval
    if frequency == "yearly":
        return amount / DAYS_PER_YEAR / interval
    return 0.0  # one-time amounts aren't spread


def _active(item: dict[str, Any], day: date) -> bool:
    start = item.get("start_date")
    end = item.get("end_date")
    return ((start is None or date.fromisoformat(start) <= day)
            and (end is None or day <= date.fromisoformat(end)))


def in_budget(item: dict[str, Any]) -> bool:
    """Whether a bill (or a payment, as saved when it was made) counts in the
    budget. Bills and payments from before this setting existed count."""
    return item.get("in_budget", True) is not False


def day_rates(day: date, budget: dict[str, Any],
              bills: list[dict[str, Any]]) -> dict[str, float]:
    """Income, bills and savings set aside for one day, and what's left."""
    income = savings = 0.0
    for s in budget["recurring"].values():
        if _active(s, day):
            rate = per_day(s["amount"], s["frequency"], s["interval"])
            if s["type"] == "income":
                income += rate
            else:
                savings += rate
    bill_rate = sum(
        per_day(b["amount"], b["frequency"], b["interval"])
        for b in bills
        if b["active"] and in_budget(b) and b["amount"] is not None
        and b["frequency"] != "once"
        and (not b.get("end_date") or day <= date.fromisoformat(b["end_date"]))
    )
    return {"income": income, "bills": bill_rate, "savings": savings,
            "allowance": income - bill_rate - savings}


def days_to_freeze(budget: dict[str, Any], bills: list[dict[str, Any]],
                   today: date) -> dict[str, dict[str, float]]:
    """Ledger entries for past days (start .. yesterday) not frozen yet."""
    if not budget["start_date"]:
        return {}
    out = {}
    d = date.fromisoformat(budget["start_date"])
    while d < today:
        key = d.isoformat()
        if key not in budget["ledger"]:
            out[key] = {k: round(v, 4) for k, v in day_rates(d, budget, bills).items()}
        d += timedelta(days=1)
    return out


def one_time_bill_spending(bills: list[dict[str, Any]],
                           payments: list[dict[str, Any]]) -> list[tuple[str, float]]:
    """Payments of one-time bills. Recurring bills are spread per day, but a
    one-time bill isn't, so it comes out of the budget on the day it's paid.
    Whether it counts is what the payment saved when it was made."""
    once = {b["id"] for b in bills if b["frequency"] == "once"}
    return [(p["paid_date"], p["amount_paid"]) for p in payments
            if p["bill_id"] in once and p["amount_paid"] is not None
            and in_budget(p)]


def bill_adjustments(bills: list[dict[str, Any]],
                     payments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The difference between what a recurring bill cost and its estimate.

    The budget sets aside each recurring bill's estimate day by day; when the
    bill is paid, paying more takes the extra out of that day's budget and
    paying less gives the rest back. The estimate used is the one saved on the
    payment when it was made, so changing a bill's estimate later never
    changes an earlier adjustment. Payments without a saved estimate (made
    before this existed, or for bills without an amount) are left alone, and
    so are payments of bills that weren't counted in the budget when paid.
    """
    by_id = {b["id"]: b for b in bills}
    out = []
    for p in payments:
        bill = by_id.get(p["bill_id"])
        estimate = p.get("estimate")
        if (bill is None or bill["frequency"] == "once" or estimate is None
                or p["amount_paid"] is None or not in_budget(p)):
            continue
        diff = round(p["amount_paid"] - estimate, 2)
        if diff:
            out.append({"payment_id": p.get("id"), "bill_id": p["bill_id"],
                        "bill_name": p["bill_name"], "date": p["paid_date"],
                        "estimate": estimate, "paid": p["amount_paid"],
                        "difference": diff, "category_id": bill.get("category_id")})
    return out


def budget_rows(budget: dict[str, Any], bills: list[dict[str, Any]],
                payments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Everything the Budget tab lists as a transaction, newest first.

    Transactions plus, read-only, bill payments that touch the budget: the
    difference from the estimate for recurring bills, and the whole payment
    for one-time bills (both only from the budget's start date, like the
    budget itself).
    """
    start = budget["start_date"] or ""
    rows = list(budget["transactions"])
    for a in bill_adjustments(bills, payments):
        if a["date"] >= start:
            rows.append({
                "id": f"adj-{a['payment_id']}", "date": a["date"], "kind": "bill_adjustment",
                "amount": abs(a["difference"]), "difference": a["difference"],
                "estimate": a["estimate"], "paid": a["paid"], "bill_id": a["bill_id"],
                "category_id": a["category_id"], "note": a["bill_name"],
                "created": a["date"], "readonly": True,
            })
    once = {b["id"]: b for b in bills if b["frequency"] == "once"}
    for p in payments:
        bill = once.get(p["bill_id"])
        if (bill and p["amount_paid"] is not None and in_budget(p)
                and p["paid_date"] >= start):
            rows.append({
                "id": f"bill-{p.get('id')}", "date": p["paid_date"], "kind": "bill_payment",
                "amount": p["amount_paid"], "bill_id": p["bill_id"],
                "category_id": bill.get("category_id"), "note": p["bill_name"],
                "created": p["paid_date"], "readonly": True,
            })
    return sorted(rows, key=lambda t: (t["date"], t.get("created") or ""), reverse=True)


NOTES_MAX = 200  # per kind, for the note suggestions in the + Add form


def recent_notes(transactions: list[dict[str, Any]],
                 category_names: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """Notes typed on earlier expenses and income, newest first, once each
    (ignoring case), with the category last used with them. Notes that were
    filled in automatically (the category name, or "Expense"/"Income") are
    left out."""
    out: dict[str, list[dict[str, Any]]] = {"expense": [], "income": []}
    seen: dict[str, set[str]] = {"expense": set(), "income": set()}
    defaults = {"expense": "expense", "income": "income"}
    for t in sorted(transactions, key=lambda t: (t["date"], t.get("created") or ""),
                    reverse=True):
        kind = t["kind"]
        note = (t.get("note") or "").strip()
        if kind not in out or not note or len(out[kind]) >= NOTES_MAX:
            continue
        key = note.lower()
        if key == defaults[kind] or key == category_names.get(t.get("category_id"), "").lower():
            continue
        if key not in seen[kind]:
            seen[kind].add(key)
            out[kind].append({"note": note, "category_id": t.get("category_id")})
    return out


def row_spent(row: dict[str, Any]) -> float:
    """How much a listed row counts as spending (same as "spent today")."""
    if row["kind"] in ("expense", "bill_payment"):
        return row["amount"]
    if row["kind"] == "bill_adjustment" and row["difference"] > 0:
        return row["difference"]
    return 0.0


def day_totals(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{ISO date: {spent, income, count}} for the days that have rows."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        t = out.setdefault(r["date"], {"spent": 0.0, "income": 0.0, "count": 0})
        t["spent"] += row_spent(r)
        if r["kind"] == "income":
            t["income"] += r["amount"]
        t["count"] += 1
    for t in out.values():
        t["spent"], t["income"] = round(t["spent"], 2), round(t["income"], 2)
    return out


def changes_on(day: date, budget: dict[str, Any],
               bills: list[dict[str, Any]]) -> list[str]:
    """What makes `day`'s allowance differ from the day before: recurring
    income or savings starting or ending, or bills ending."""
    prev = (day - timedelta(days=1)).isoformat()
    iso = day.isoformat()
    out = []
    for s in sorted(budget["recurring"].values(), key=lambda s: s["name"].lower()):
        what = "income" if s["type"] == "income" else "savings plan"
        if s.get("start_date") == iso:
            out.append(f"{s['name']} ({what}) starts")
        if s.get("end_date") == prev:
            out.append(f"{s['name']} ({what}) ended")
    for b in sorted(bills, key=lambda b: b["name"].lower()):
        if (b["active"] and in_budget(b) and b["amount"] is not None
                and b["frequency"] != "once" and b.get("end_date") == prev):
            out.append(f"{b['name']} (bill) ended")
    return out


def rounded_rates(r: dict[str, float]) -> dict[str, float]:
    """Round a day's rates to cents so income - bills - savings still adds up
    to the rounded allowance (otherwise $233.65 - $135.56 - $26.28 can show
    next to a $71.80 allowance). The cent goes to bills (a total of many
    bills), or to savings, so a paycheck still shows its exact rate."""
    out = {k: round(v, 2) for k, v in r.items()}
    off = round(out["allowance"] - (out["income"] - out["bills"] - out["savings"]), 2)
    if off:
        for k in ("bills", "savings", "income"):
            if r[k]:
                out[k] = round(out[k] + (off if k == "income" else -off), 2)
                break
    return out


def compute(budget: dict[str, Any], bills: list[dict[str, Any]],
            payments: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Today's budget, the next days, today's allowance and savings totals.

    `bills` should include retired bills (for one-time bill payments); only
    active ones are spread into the allowance.
    """
    if not budget["start_date"]:
        return {"configured": False}
    start = date.fromisoformat(budget["start_date"])
    ledger = budget["ledger"]

    def rates(d: date) -> dict[str, float]:
        if d < today and d.isoformat() in ledger:
            return ledger[d.isoformat()]
        return day_rates(d, budget, bills)

    # Money in or out on each day from transactions and one-time bills.
    effects: dict[str, float] = {}
    to_savings = from_savings = 0.0
    spent: dict[str, float] = {}
    earned: dict[str, float] = {}
    for t in budget["transactions"]:
        if t["date"] < budget["start_date"]:
            continue
        effects[t["date"]] = effects.get(t["date"], 0.0) + SIGN[t["kind"]] * t["amount"]
        if t["date"] <= today.isoformat():
            if t["kind"] == "to_savings":
                to_savings += t["amount"]
            elif t["kind"] == "from_savings":
                from_savings += t["amount"]
        if t["kind"] == "expense":
            spent[t["date"]] = spent.get(t["date"], 0.0) + t["amount"]
        elif t["kind"] == "income":
            earned[t["date"]] = earned.get(t["date"], 0.0) + t["amount"]
    for paid, amount in one_time_bill_spending(bills, payments):
        if paid >= budget["start_date"]:
            effects[paid] = effects.get(paid, 0.0) - amount
            spent[paid] = spent.get(paid, 0.0) + amount
    adjustments = [a for a in bill_adjustments(bills, payments)
                   if a["date"] >= budget["start_date"]]
    for a in adjustments:
        effects[a["date"]] = effects.get(a["date"], 0.0) - a["difference"]
        if a["difference"] > 0:
            spent[a["date"]] = spent.get(a["date"], 0.0) + a["difference"]

    balance = budget["starting_amount"]
    saved = budget["starting_savings"]
    d = start
    while d < today:
        r = rates(d)
        balance += r["allowance"] + effects.get(d.isoformat(), 0.0)
        saved += r["savings"]
        d += timedelta(days=1)

    today_rates = rates(today) if today >= start else {
        "income": 0.0, "bills": 0.0, "savings": 0.0, "allowance": 0.0}
    days = []
    for i in range(DAYS_AHEAD + 1):
        d = today + timedelta(days=i)
        allowance = rates(d)["allowance"] if d >= start else 0.0
        change = allowance + effects.get(d.isoformat(), 0.0) if d >= start else 0.0
        balance += change
        # Later days are the previous day plus the step shown under them, so
        # the displayed numbers always add up (rounding each running total on
        # its own could put them a cent apart).
        amount = (round(days[-1]["amount"] + round(change, 2), 2) if days
                  else round(balance, 2))
        day = {"date": d.isoformat(), "amount": amount,
               "allowance": round(allowance, 2), "change": round(change, 2)}
        if days and d > start and day["allowance"] != days[-1]["allowance"]:
            day["reasons"] = changes_on(d, budget, bills)
        days.append(day)
    if today >= start:
        saved += today_rates["savings"]
    saved += to_savings - from_savings
    plans_per_day = sum(
        per_day(s["amount"], s["frequency"], s["interval"])
        for s in budget["recurring"].values()
        if s["type"] == "savings" and _active(s, today)
    )
    unpriced = sum(1 for b in bills if b["active"] and in_budget(b)
                   and b["amount"] is None and b["frequency"] != "once")
    t = today.isoformat()
    return {
        "configured": True,
        "start_date": budget["start_date"],
        "today": days[0]["amount"],
        "days": days,
        "allowance": rounded_rates(today_rates),
        "spent_today": round(spent.get(t, 0.0), 2),
        "income_today": round(earned.get(t, 0.0), 2),
        "savings": {
            "total": round(saved, 2),
            "per_month": round(plans_per_day * DAYS_PER_YEAR / 12, 2),
            "moved_in": round(to_savings, 2),
            "taken_out": round(from_savings, 2),
        },
        "bills_without_amount": unpriced,
        "bill_adjustments": sorted(adjustments, key=lambda a: a["date"], reverse=True),
    }
