"""Pure-Python summary of bills for sensors (no Home Assistant imports)."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from html import escape
from typing import Any

from . import schedule

WEEK_DAYS = 7
STATE_MAX = 255  # Home Assistant's limit on a sensor state's length


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
    # Overdue plus everything due in the next WEEK_DAYS days (the widget's "this week").
    this_week = [v for v, _ in rows if v["days_until"] <= WEEK_DAYS]
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
        "this_week": this_week,
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


def widget_text(summary: dict[str, Any]) -> str:
    """One short line for a phone widget.

    e.g. "Phone due in 2 days · 2 more this week",
         "Water overdue by 3 days · 1 more overdue · 2 more this week",
         "No bills due".
    """
    nxt = summary["next"]
    if nxt is None:
        return "No bills due"
    parts = [summary_text(nxt)]
    others = [v for v in summary["this_week"] if v["bill_id"] != nxt["bill_id"]]
    overdue = sum(1 for v in others if v["days_until"] < 0)
    upcoming = len(others) - overdue
    if overdue:
        parts.append(f"{overdue} more overdue")
    if upcoming:
        parts.append(f"{upcoming} more this week")
    text = " · ".join(parts)
    return text if len(text) <= STATE_MAX else text[: STATE_MAX - 1] + "…"


def widget_lines(summary: dict[str, Any], currency: str | None = None) -> list[str]:
    """One line per bill that's overdue or due this week, for larger widgets."""
    out = []
    for v in summary["this_week"]:
        line = summary_text(v)
        if v["amount"] is not None:
            line += f" · {format_money(v['amount'], currency)}"
        out.append(line)
    return out


def widget_html(summary: dict[str, Any], currency: str | None = None) -> str:
    """Ready-made multi-line text for the Android template widget, so the
    widget's template can just be {{ state_attr('sensor.bills_summary', 'widget') }}.
    Overdue lines are bold, which also reads well on e-ink screens.
    """
    rows = summary["this_week"]
    if not rows:
        return escape(widget_text(summary))
    lines = []
    for v, text in zip(rows, widget_lines(summary, currency)):
        text = escape(text)
        lines.append(f"<b>{text}</b>" if v["days_until"] < 0 else text)
    return "<b>Bills this week</b><br>" + "<br>".join(lines)


_SYMBOLS = {"USD": "$", "CAD": "$", "AUD": "$", "NZD": "$", "EUR": "€",
            "GBP": "£", "JPY": "¥", "INR": "₹"}


def format_money(amount: float, currency: str | None = None) -> str:
    sym = _SYMBOLS.get(currency or "USD")
    num = f"{abs(amount):,.2f}"
    sign = "-" if round(amount, 2) < 0 else ""
    return f"{sign}{sym}{num}" if sym else f"{sign}{num} {currency}"


UNCATEGORIZED = {"id": None, "name": "Uncategorized", "icon": "mdi:shape-outline"}


def cost_breakdown(
    bills: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    categories: dict[str, dict[str, Any]],
    start: date,
    end: date,
) -> dict[str, Any]:
    """Costs of bills due between start and end (inclusive), by category.

    Everything is counted by due date, so a bill due in December counts in
    December even if it was paid in November.
      paid:     payments whose due date is in the period (the amount paid)
      upcoming: unpaid due dates in the period, including overdue ones (the
                bill's estimate); dates without an estimate are counted in
                `unpriced` instead
    Each category also lists its `bills` (one row per bill, summed over the
    period, with `count` due dates).
    `bills` must include retired bills so their past payments are categorised.
    """
    by_id = {b["id"]: b for b in bills}
    buckets: dict[str | None, dict[str, Any]] = {}

    def bucket(cat_id: str | None) -> dict[str, Any]:
        if cat_id not in categories:
            cat_id = None  # no category, or one that was deleted
        if cat_id not in buckets:
            c = categories[cat_id] if cat_id else UNCATEGORIZED
            buckets[cat_id] = {"id": cat_id, "name": c["name"], "icon": c.get("icon"),
                               "paid": 0.0, "upcoming": 0.0, "unpriced": 0,
                               "bills": {}}
        return buckets[cat_id]

    def line(k: dict[str, Any], bill_id: str, name: str) -> dict[str, Any]:
        if bill_id not in k["bills"]:
            k["bills"][bill_id] = {"id": bill_id, "name": name, "paid": 0.0,
                                   "upcoming": 0.0, "unpriced": 0, "count": 0}
        row = k["bills"][bill_id]
        row["count"] += 1
        return row

    for p in payments:
        if p["amount_paid"] is None:
            continue
        if start <= date.fromisoformat(p["due_date"]) <= end:
            bill = by_id.get(p["bill_id"])
            k = bucket(bill.get("category_id") if bill else None)
            k["paid"] += p["amount_paid"]
            name = bill["name"] if bill else p["bill_name"]
            line(k, p["bill_id"], name)["paid"] += p["amount_paid"]

    for b in bills:
        if not (b["active"] and b["next_due"]):
            continue
        b_end = date.fromisoformat(b["end_date"]) if b["end_date"] else None
        for _d in schedule.occurrences_between(
            date.fromisoformat(b["anchor_date"]), b["frequency"], b["interval"],
            max(start, date.fromisoformat(b["next_due"])), end, b_end,
        ):
            k = bucket(b.get("category_id"))
            row = line(k, b["id"], b["name"])
            if b["amount"] is None:
                k["unpriced"] += 1
                row["unpriced"] += 1
            else:
                k["upcoming"] += b["amount"]
                row["upcoming"] += b["amount"]

    rows = []
    for k in buckets.values():
        k["paid"] = round(k["paid"], 2)
        k["upcoming"] = round(k["upcoming"], 2)
        k["total"] = round(k["paid"] + k["upcoming"], 2)
        lines = list(k["bills"].values())
        for r in lines:
            r["paid"] = round(r["paid"], 2)
            r["upcoming"] = round(r["upcoming"], 2)
            r["total"] = round(r["paid"] + r["upcoming"], 2)
        lines.sort(key=lambda r: (-r["total"], r["name"].lower()))
        k["bills"] = lines
        rows.append(k)
    # Biggest first; Uncategorized always last.
    rows.sort(key=lambda r: (r["id"] is None, -r["total"], r["name"].lower()))
    paid = round(sum(r["paid"] for r in rows), 2)
    upcoming = round(sum(r["upcoming"] for r in rows), 2)
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "paid": paid,
        "upcoming": upcoming,
        "total": round(paid + upcoming, 2),
        "unpriced": sum(r["unpriced"] for r in rows),
        "categories": rows,
    }


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def year_breakdown(
    bills: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    categories: dict[str, dict[str, Any]],
    year: int,
) -> dict[str, Any]:
    """The whole year plus each of its 12 months (in `months`, Jan first)."""
    out = cost_breakdown(bills, payments, categories,
                         date(year, 1, 1), date(year, 12, 31))
    out["year"] = year
    out["months"] = [
        cost_breakdown(bills, payments, categories,
                       date(year, m, 1), _month_end(year, m))
        for m in range(1, 13)
    ]
    return out


def history_years(
    bills: list[dict[str, Any]], payments: list[dict[str, Any]], today: date
) -> list[int]:
    """Years before this one that have payments or unpaid due dates, newest first."""
    years = {int(p["due_date"][:4]) for p in payments}
    years |= {int(b["next_due"][:4]) for b in bills if b["active"] and b["next_due"]}
    return sorted((y for y in years if y < today.year), reverse=True)


FLAT_PCT = 2.0  # changes smaller than this (%) count as "steady"


def _pct(new: float, old: float) -> float | None:
    return round((new - old) / old * 100, 1) if old else None


def _direction(pct: float | None) -> str | None:
    if pct is None:
        return None
    return "steady" if abs(pct) < FLAT_PCT else ("up" if pct > 0 else "down")


def bill_history(payments: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """Stats for one bill's payments, to see whether it's going up or down.

      last / previous / change:  the latest payment against the one before
      trend:  average of the latest (up to) 3 payments against the 3 before
              them; needs at least 4 payments
      year_over_year:  average of payments due in the last 12 months against
              the 12 months before that; needs payments in both
    Payments are ordered by due date. Ones without an amount are ignored.
    """
    rows = sorted((p for p in payments if p["amount_paid"] is not None),
                  key=lambda p: (p["due_date"], p["paid_date"]))
    amounts = [p["amount_paid"] for p in rows]
    out: dict[str, Any] = {
        "count": len(amounts), "total_paid": round(sum(amounts), 2),
        "average": None, "min": None, "max": None, "first_due": None,
        "last": None, "previous": None, "change": None, "change_pct": None,
        "trend": None, "year_over_year": None,
    }
    if not amounts:
        return out
    out.update({
        "average": round(sum(amounts) / len(amounts), 2),
        "min": min(amounts), "max": max(amounts),
        "first_due": rows[0]["due_date"], "last": amounts[-1],
    })
    if len(amounts) >= 2:
        prev = amounts[-2]
        out["previous"] = prev
        out["change"] = round(amounts[-1] - prev, 2)
        out["change_pct"] = _pct(amounts[-1], prev)
    if len(amounts) >= 4:
        n = min(3, len(amounts) // 2)
        recent = sum(amounts[-n:]) / n
        prior = sum(amounts[-2 * n:-n]) / n
        pct = _pct(recent, prior)
        out["trend"] = {"direction": _direction(pct), "pct": pct, "window": n,
                        "recent_avg": round(recent, 2), "prior_avg": round(prior, 2)}
    year_ago = date(today.year - 1, today.month, min(today.day, 28))
    two_years_ago = date(today.year - 2, today.month, min(today.day, 28))
    last12 = [p["amount_paid"] for p in rows
              if year_ago < date.fromisoformat(p["due_date"]) <= today]
    prior12 = [p["amount_paid"] for p in rows
               if two_years_ago < date.fromisoformat(p["due_date"]) <= year_ago]
    if last12 and prior12:
        recent, prior = sum(last12) / len(last12), sum(prior12) / len(prior12)
        pct = _pct(recent, prior)
        out["year_over_year"] = {"direction": _direction(pct), "pct": pct,
                                 "recent_avg": round(recent, 2),
                                 "prior_avg": round(prior, 2)}
    return out
