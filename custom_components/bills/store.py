"""Persistence and business logic for bills and payments."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import backup, schedule
from .const import STORAGE_KEY, STORAGE_VERSION

UPDATABLE = ("name", "amount", "notes", "biller_url", "autopay",
             "remind_days_before", "tags")
SCHEDULE_FIELDS = ("due_date", "frequency", "interval", "end_date")


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write via a temp file and rename, so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


class BillStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.bills: dict[str, dict[str, Any]] = {}
        self.payments: list[dict[str, Any]] = []
        self.categories: dict[str, dict[str, Any]] = {}
        # Bookkeeping that isn't bill data, e.g. last_reminder_date.
        self.meta: dict[str, Any] = {}
        self._listeners: list[Callable[[], None]] = []
        self.backup_dir = Path(hass.config.path(backup.FOLDER))

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self.bills = data.get("bills", {})
            self.payments = data.get("payments", [])
            self.categories = data.get("categories", {})
            self.meta = data.get("meta", {})

    def async_add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    async def _async_save(self, notify: bool = True) -> None:
        await self._store.async_save(
            {"bills": self.bills, "payments": self.payments,
             "categories": self.categories, "meta": self.meta}
        )
        if notify:
            for cb in list(self._listeners):
                cb()

    async def async_set_meta(self, key: str, value: Any) -> None:
        self.meta[key] = value
        await self._async_save(notify=False)

    # ---------- backups ----------

    async def async_write_backup(self, name: str) -> Path:
        path = self.backup_dir / backup.check_name(name)
        data = backup.build(self.bills, self.payments, self.categories,
                            self.meta, dt_util.now(), STORAGE_VERSION)
        # Serialise now, on the event loop, so the copy can't change mid-write.
        data = json.loads(json.dumps(data))
        await self.hass.async_add_executor_job(_write_json, path, data)
        return path

    async def async_daily_backup(self) -> str | None:
        """Today's backup if it doesn't exist yet, then prune old daily ones."""
        name = backup.daily_name(dt_util.now().date())

        def _prune_and_check() -> bool:
            names = [p.name for p in self.backup_dir.glob("*.json")] \
                if self.backup_dir.is_dir() else []
            for old in backup.daily_to_prune(names):
                (self.backup_dir / old).unlink(missing_ok=True)
            return name in names

        if await self.hass.async_add_executor_job(_prune_and_check):
            return None
        await self.async_write_backup(name)
        return name

    async def async_list_backups(self) -> list[dict[str, Any]]:
        def _list() -> list[dict[str, Any]]:
            if not self.backup_dir.is_dir():
                return []
            rows = []
            for p in self.backup_dir.glob("*.json"):
                st = p.stat()
                rows.append({"file": p.name, "size": st.st_size,
                             "modified": dt_util.utc_from_timestamp(st.st_mtime).isoformat()})
            return sorted(rows, key=lambda r: r["modified"], reverse=True)

        return await self.hass.async_add_executor_job(_list)

    async def async_restore_backup(self, name: str) -> dict[str, Any]:
        try:
            path = self.backup_dir / backup.check_name(name)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

        def _read() -> Any:
            return json.loads(path.read_text(encoding="utf-8"))

        try:
            raw = await self.hass.async_add_executor_job(_read)
        except FileNotFoundError as err:
            raise ServiceValidationError(f"No backup named '{name}'") from err
        except (OSError, ValueError) as err:
            raise ServiceValidationError(f"Couldn't read '{name}': {err}") from err
        try:
            data = backup.validate(raw)
        except ValueError as err:
            raise ServiceValidationError(f"'{name}' isn't a valid backup: {err}") from err

        safety = backup.stamped_name(dt_util.now(), "before-restore")
        await self.async_write_backup(safety)
        self.bills, self.payments = data["bills"], data["payments"]
        self.categories = data["categories"]
        # Keep today's reminder bookkeeping so a restore doesn't resend them.
        self.meta = {**data["meta"], **self.meta}
        await self._async_save()
        return {"restored_from": name, "safety_backup": safety,
                "bills": len(self.bills), "payments": len(self.payments),
                "categories": len(self.categories)}

    # ---------- categories ----------

    def find_category(self, ref: str) -> dict[str, Any]:
        """Find a category by id or by name (case-insensitive)."""
        if ref in self.categories:
            return self.categories[ref]
        for c in self.categories.values():
            if c["name"].lower() == ref.lower():
                return c
        raise ServiceValidationError(f"No category found matching '{ref}'")

    def _category_id(self, ref: str | None) -> str | None:
        return self.find_category(ref)["id"] if ref else None

    def _check_category_name(self, name: str, skip_id: str | None = None) -> None:
        for c in self.categories.values():
            if c["id"] != skip_id and c["name"].lower() == name.lower():
                raise ServiceValidationError(f"There's already a category named '{c['name']}'")

    async def async_add_category(self, name: str, icon: str) -> dict[str, Any]:
        self._check_category_name(name)
        cat = {"id": uuid4().hex, "name": name, "icon": icon}
        self.categories[cat["id"]] = cat
        await self._async_save()
        return cat

    async def async_update_category(self, ref: str, changes: dict[str, Any]):
        cat = self.find_category(ref)
        if "name" in changes:
            self._check_category_name(changes["name"], cat["id"])
        for key in ("name", "icon"):
            if key in changes:
                cat[key] = changes[key]
        await self._async_save()
        return cat

    async def async_delete_category(self, ref: str) -> tuple[dict[str, Any], int]:
        """Delete a category; its bills become uncategorized."""
        cat = self.categories.pop(self.find_category(ref)["id"])
        moved = 0
        for b in self.bills.values():
            if b.get("category_id") == cat["id"]:
                b["category_id"] = None
                moved += 1
        await self._async_save()
        return cat, moved

    def list_categories(self) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for b in self.bills.values():
            if b["active"] and b.get("category_id"):
                counts[b["category_id"]] = counts.get(b["category_id"], 0) + 1
        return sorted(
            ({**c, "bill_count": counts.get(c["id"], 0)} for c in self.categories.values()),
            key=lambda c: c["name"].lower(),
        )

    # ---------- bills ----------

    def find_bill(self, ref: str) -> dict[str, Any]:
        """Find a bill by id or by name (prefers the active bill)."""
        if ref in self.bills:
            return self.bills[ref]
        matches = [b for b in self.bills.values()
                   if b["name"].lower() == ref.lower()]
        active = [b for b in matches if b["active"]]
        if len(active) == 1:
            return active[0]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ServiceValidationError(f"No bill found matching '{ref}'")
        raise ServiceValidationError(
            f"More than one bill is named '{ref}'; use its id instead"
        )

    async def async_add_bill(self, data: dict[str, Any]) -> dict[str, Any]:
        bill_id = uuid4().hex
        due: date = data["due_date"]
        end: date | None = data.get("end_date")
        if data["frequency"] == "once":
            end = None
        try:
            schedule.check_end_date(due, data["frequency"], end)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        bill = {
            "id": bill_id,
            "name": data["name"],
            "amount": data.get("amount"),
            "frequency": data["frequency"],
            "interval": data["interval"],
            "anchor_date": due.isoformat(),
            "next_due": due.isoformat(),
            "end_date": _iso(end),
            "active": True,
            "retired_on": None,
            "tags": data["tags"],
            "biller_url": data.get("biller_url"),
            "autopay": data["autopay"],
            "remind_days_before": data["remind_days_before"],
            "notes": data.get("notes"),
            "category_id": self._category_id(data.get("category")),
        }
        self.bills[bill_id] = bill
        await self._async_save()
        return bill

    async def async_update_bill(self, ref: str, changes: dict[str, Any]):
        bill = self.find_bill(ref)
        new_schedule = None
        if any(k in changes for k in SCHEDULE_FIELDS):
            try:
                new_schedule = schedule.reschedule(bill, changes)
            except ValueError as err:
                raise ServiceValidationError(str(err)) from err
        category_id = (self._category_id(changes["category"])
                       if "category" in changes else None)
        for key in UPDATABLE:
            if key in changes:
                bill[key] = changes[key]
        if "category" in changes:
            bill["category_id"] = category_id
        if new_schedule:
            bill.update(new_schedule)
        await self._async_save()
        return bill

    async def async_retire_bill(self, ref: str) -> dict[str, Any]:
        bill = self.find_bill(ref)
        if not bill["active"]:
            raise ServiceValidationError(f"'{bill['name']}' is already retired")
        bill["active"] = False
        bill["retired_on"] = dt_util.now().date().isoformat()
        await self._async_save()
        return bill

    async def async_restore_bill(
        self, ref: str, due_date: date | None = None
    ) -> dict[str, Any]:
        bill = self.find_bill(ref)
        try:
            plan = schedule.restore_plan(bill, dt_util.now().date(), due_date)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        bill.update(plan)
        bill["active"] = True
        bill["retired_on"] = None
        await self._async_save()
        return bill

    async def async_mark_paid(
        self,
        ref: str,
        amount: float | None = None,
        paid_date: date | None = None,
        confirmation: str | None = None,
        note: str | None = None,
        update_amount: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        bill = self.find_bill(ref)
        if not bill["active"] or not bill["next_due"]:
            raise ServiceValidationError(
                f"'{bill['name']}' is retired or has no upcoming due date"
            )
        due = date.fromisoformat(bill["next_due"])
        paid_on = paid_date or dt_util.now().date()
        payment = {
            "id": uuid4().hex,
            "bill_id": bill["id"],
            "bill_name": bill["name"],
            "due_date": bill["next_due"],
            "paid_date": paid_on.isoformat(),
            "amount_paid": amount if amount is not None else bill["amount"],
            "confirmation": confirmation,
            "note": note,
        }
        self.payments.append(payment)
        if update_amount and amount is not None:
            bill["amount"] = amount  # use what was paid as the new estimate

        end = date.fromisoformat(bill["end_date"]) if bill["end_date"] else None
        nxt = schedule.next_after(
            date.fromisoformat(bill["anchor_date"]),
            bill["frequency"], bill["interval"], due, end,
        )
        if nxt is None:  # one-time bill, or schedule has ended
            bill["next_due"] = None
            bill["active"] = False
            bill["retired_on"] = paid_on.isoformat()
        else:
            bill["next_due"] = nxt.isoformat()
        await self._async_save()
        return payment, bill

    def list_bills(self, include_retired: bool = False) -> list[dict[str, Any]]:
        bills = [b for b in self.bills.values() if include_retired or b["active"]]
        return sorted(bills, key=lambda b: (b["next_due"] is None, b["next_due"] or ""))

    def list_payments(self, bill_id: str | None = None) -> list[dict[str, Any]]:
        rows = [p for p in self.payments if bill_id in (None, p["bill_id"])]
        return sorted(rows, key=lambda p: p["paid_date"], reverse=True)