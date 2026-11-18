"""Pure-Python summary of bills for sensors (no Home Assistant imports)."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from . import schedule


def _view(bill: dict[str, Any], today: date) -> dict[str, Any]:
    due = date.fromisoformat(bill["next_due"])
    return {
        "bill_id": bill["id"],
        "name": bill["name"],
        "amount": bill["amount"],
        "due_date": bill["next_due"],
        "days_until": (due - today).days,
        "autopay": bill["autopay"],
    }


def compute_summary(bills: list[dict[str, Any]], today: date) -> dict[str, Any]:
    rows = sorted(
        ((_view(b, today), b) for b in bills if b["active"] and b["next_due"]),
        key=lambda r: (r[0]["due_date"], r[0]["name"].lower()),
    )
    overdue = [v for v, _ in rows if v["days_until"] < 0]
    due_soon = [
        v for v, b in rows if 0 <= v["days_until"] <= b["remind_days_before"]
    ]

    # Unpaid amounts due on or before the end of this month (incl. overdue).
    month_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
    total = 0.0
    unpriced = 0
    for _, b in rows:
        end = date.fromisoformat(b["end_date"]) if b["end_date"] else None
        for _d in schedule.occurrences_between(
            date.fromisoformat(b["anchor_date"]),
            b["frequency"],
            b["interval"],
            date.fromisoformat(b["next_due"]),
            month_end,
            end,
        ):
            if b["amount"] is None:
                unpriced += 1
            else:
                total += b["amount"]

    return {
        "next": rows[0][0] if rows else None,
        "due_soon": due_soon,
        "overdue": overdue,
        "due_this_month": round(total, 2),
        "due_this_month_unpriced": unpriced,
        "active_count": len(rows),
    }
def summary_text(v: dict[str, Any]) -> str:
    d = v["days_until"]
    if d < 0:
        when = f"overdue by {-d} day{'s' if d != -1 else ''}"
    elif d == 0:
        when = "due today"
    elif d == 1:
        when = "due tomorrow"
    else:
        when = f"due in {d} days"
    return f"{v['name']} {when}"


def compute_reminders(bills: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Bills that are overdue, due today, or inside their reminder window."""
    out = []
    for b in bills:
        if not (b["active"] and b["next_due"]):
            continue
        v = _view(b, today)
        d = v["days_until"]
        if d < 0:
            kind = "overdue"
        elif d == 0:
            kind = "due_today"
        elif d <= b["remind_days_before"]:
            kind = "upcoming"
        else:
            continue
        out.append({
            **v,
            "kind": kind,
            "biller_url": b.get("biller_url"),
            "summary": summary_text(v),
        })
    out.sort(key=lambda r: (r["due_date"], r["name"].lower()))
    return out