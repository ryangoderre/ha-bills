"""Pure helpers for bills backup files (no Home Assistant imports).

Backups are plain JSON in <config>/bills_backups/:
  bills-YYYY-MM-DD.json             daily, the newest KEEP_DAILY are kept
  bills-manual-YYYYMMDD-HHMMSS.json from the bills.backup service, kept
  bills-before-restore-...json      taken automatically before a restore, kept
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

FOLDER = "bills_backups"
KEEP_DAILY = 14
_DAILY = re.compile(r"^bills-\d{4}-\d{2}-\d{2}\.json$")
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.json$")

BILL_KEYS = ("id", "name", "amount", "frequency", "interval", "anchor_date",
             "next_due", "end_date", "active", "remind_days_before", "autopay")
PAYMENT_KEYS = ("id", "bill_id", "bill_name", "due_date", "paid_date",
                "amount_paid")


def daily_name(day: date) -> str:
    return f"bills-{day.isoformat()}.json"


def stamped_name(now: datetime, label: str) -> str:
    return f"bills-{label}-{now:%Y%m%d-%H%M%S}.json"


def daily_to_prune(names: list[str], keep: int = KEEP_DAILY) -> list[str]:
    """Daily files beyond the newest `keep`. Other backups are never pruned."""
    daily = sorted(n for n in names if _DAILY.match(n))
    return daily[:-keep] if len(daily) > keep else []


def check_name(name: str) -> str:
    """Only a bare file name inside the backups folder; no paths."""
    if not _SAFE.match(name) or ".." in name:
        raise ValueError(f"'{name}' isn't a backup file name like bills-2026-11-18.json")
    return name


def build(bills: dict, payments: list, categories: dict, meta: dict,
          created: datetime, version: int,
          budget: dict | None = None) -> dict[str, Any]:
    return {
        "format": "ha-bills-backup",
        "version": version,
        "created": created.isoformat(),
        "bills": bills,
        "payments": payments,
        "categories": categories,
        "budget": budget or {},
        "meta": meta,
    }


def validate(data: Any) -> dict[str, Any]:
    """Check a backup's shape before it replaces the live data."""
    if not isinstance(data, dict):
        raise ValueError("Backup isn't a JSON object")
    bills, payments = data.get("bills"), data.get("payments")
    if not isinstance(bills, dict) or not isinstance(payments, list):
        raise ValueError("Backup is missing its bills or payments")
    for key, bill in bills.items():
        missing = [k for k in BILL_KEYS if not isinstance(bill, dict) or k not in bill]
        if missing:
            raise ValueError(f"Bill '{key}' is missing {', '.join(missing)}")
        if bill["id"] != key:
            raise ValueError(f"Bill '{key}' has a mismatched id")
    for i, p in enumerate(payments):
        missing = [k for k in PAYMENT_KEYS if not isinstance(p, dict) or k not in p]
        if missing:
            raise ValueError(f"Payment {i + 1} is missing {', '.join(missing)}")
    # Backups made before categories existed have none.
    categories = data.get("categories", {})
    if not isinstance(categories, dict):
        raise ValueError("Backup's categories aren't valid")
    for key, c in categories.items():
        if not isinstance(c, dict) or c.get("id") != key or not c.get("name"):
            raise ValueError(f"Category '{key}' isn't valid")
    # Backups made before the budget existed have none.
    budget = data.get("budget", {})
    if not isinstance(budget, dict):
        raise ValueError("Backup's budget isn't valid")
    if not isinstance(budget.get("transactions", []), list) or \
            not isinstance(budget.get("recurring", {}), dict):
        raise ValueError("Backup's budget isn't valid")
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    return {"bills": bills, "payments": payments, "categories": categories,
            "budget": budget, "meta": meta}
