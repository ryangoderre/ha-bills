"""Persistence and business logic for bills and payments."""
from __future__ import annotations

from collections.abc import Callable

from datetime import date
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import schedule
from .const import STORAGE_KEY, STORAGE_VERSION

UPDATABLE = ("name", "amount", "notes", "biller_url", "autopay",
             "remind_days_before", "tags")
SCHEDULE_FIELDS = ("due_date", "frequency", "interval", "end_date")


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


class BillStore:
    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.bills: dict[str, dict[str, Any]] = {}
        self.payments: list[dict[str, Any]] = []
        self._listeners: list[Callable[[], None]] = []

    async def async_load(self) -> None:
        data = await self._store.async_load()
        if data:
            self.bills = data.get("bills", {})
            self.payments = data.get("payments", [])

    def async_add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    async def _async_save(self) -> None:
        await self._store.async_save(
            {"bills": self.bills, "payments": self.payments}
        )
        for cb in list(self._listeners):
            cb()

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
        for key in UPDATABLE:
            if key in changes:
                bill[key] = changes[key]
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