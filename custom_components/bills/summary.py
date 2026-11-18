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