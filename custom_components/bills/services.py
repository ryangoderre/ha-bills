"""Service registration for the Bills integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_PAID
from .schedule import FREQUENCIES, suggest_restore_due
from .reminders import fire_reminders
from .store import BillStore

SERVICES = ("add_bill", "update_bill", "retire_bill", "restore_bill", "mark_paid",
            "list_bills", "list_payments", "send_reminders")

_NONNEG_INT = vol.All(vol.Coerce(int), vol.Range(min=0))
_INTERVAL = vol.All(vol.Coerce(int), vol.Range(min=1))
_AMOUNT = vol.All(vol.Coerce(float), vol.Range(min=0))
_NAME = vol.All(cv.string, vol.Strip, vol.Length(min=1))


def _clearable(validator):
    """Accept None (clear the field) as well as a normal value."""
    return vol.Any(None, validator)


ADD_SCHEMA = vol.Schema({
    vol.Required("name"): _NAME,
    vol.Required("due_date"): cv.date,
    vol.Required("frequency"): vol.In(FREQUENCIES),
    vol.Optional("interval", default=1): _INTERVAL,
    vol.Optional("amount"): _AMOUNT,
    vol.Optional("end_date"): cv.date,
    vol.Optional("autopay", default=False): cv.boolean,
    vol.Optional("remind_days_before", default=3): _NONNEG_INT,
    vol.Optional("biller_url"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("tags", default=list): vol.All(cv.ensure_list, [cv.string]),
})

UPDATE_SCHEMA = vol.Schema({
    vol.Required("bill"): cv.string,
    vol.Optional("name"): _NAME,
    vol.Optional("amount"): _clearable(_AMOUNT),
    vol.Optional("due_date"): cv.date,
    vol.Optional("frequency"): vol.In(FREQUENCIES),
    vol.Optional("interval"): _INTERVAL,
    vol.Optional("end_date"): _clearable(cv.date),
    vol.Optional("autopay"): cv.boolean,
    vol.Optional("remind_days_before"): _NONNEG_INT,
    vol.Optional("biller_url"): _clearable(cv.string),
    vol.Optional("notes"): _clearable(cv.string),
    vol.Optional("tags"): vol.All(cv.ensure_list, [cv.string]),
})

BILL_SCHEMA = vol.Schema({vol.Required("bill"): cv.string})

RESTORE_SCHEMA = vol.Schema({
    vol.Required("bill"): cv.string,
    vol.Optional("due_date"): cv.date,
})

PAID_SCHEMA = vol.Schema({
    vol.Required("bill"): cv.string,
    vol.Optional("amount"): _AMOUNT,
    vol.Optional("paid_date"): cv.date,
    vol.Optional("confirmation"): cv.string,
    vol.Optional("note"): cv.string,
    vol.Optional("update_amount", default=False): cv.boolean,
})

LIST_BILLS_SCHEMA = vol.Schema({
    vol.Optional("include_retired", default=False): cv.boolean,
})

LIST_PAYMENTS_SCHEMA = vol.Schema({vol.Optional("bill"): cv.string})


def async_register_services(hass: HomeAssistant, store: BillStore) -> None:
    async def add_bill(call: ServiceCall):
        bill = await store.async_add_bill(dict(call.data))
        return {"bill_id": bill["id"], "next_due": bill["next_due"]}

    async def update_bill(call: ServiceCall):
        changes = dict(call.data)
        ref = changes.pop("bill")
        bill = await store.async_update_bill(ref, changes)
        return {"bill": bill}

    async def retire_bill(call: ServiceCall):
        bill = await store.async_retire_bill(call.data["bill"])
        return {"bill_id": bill["id"], "retired_on": bill["retired_on"]}

    async def restore_bill(call: ServiceCall):
        bill = await store.async_restore_bill(
            call.data["bill"], call.data.get("due_date")
        )
        return {"bill_id": bill["id"], "next_due": bill["next_due"]}

    async def mark_paid(call: ServiceCall):
        d = call.data
        payment, bill = await store.async_mark_paid(
            d["bill"], d.get("amount"), d.get("paid_date"),
            d.get("confirmation"), d.get("note"), d["update_amount"],
        )
        hass.bus.async_fire(EVENT_PAID, {
            "bill_id": bill["id"],
            "bill_name": bill["name"],
            "next_due": bill["next_due"],
        })
        return {"payment": payment, "next_due": bill["next_due"]}

    async def list_bills(call: ServiceCall):
        today = dt_util.now().date()
        bills = []
        for b in store.list_bills(call.data["include_retired"]):
            if not b["active"]:
                # The date restore_bill would use if no due_date is given.
                due = suggest_restore_due(b, today)
                b = {**b, "restore_due": due.isoformat() if due else None}
            bills.append(b)
        return {"bills": bills}

    async def list_payments(call: ServiceCall):
        ref = call.data.get("bill")
        bill_id = store.find_bill(ref)["id"] if ref else None
        return {"payments": store.list_payments(bill_id)}

    async def send_reminders(call: ServiceCall):
        sent = fire_reminders(hass, store)
        return {"sent": len(sent), "reminders": sent}

    optional = SupportsResponse.OPTIONAL
    only = SupportsResponse.ONLY
    for name, handler, schema, resp in (
        ("add_bill", add_bill, ADD_SCHEMA, optional),
        ("update_bill", update_bill, UPDATE_SCHEMA, optional),
        ("retire_bill", retire_bill, BILL_SCHEMA, optional),
        ("restore_bill", restore_bill, RESTORE_SCHEMA, optional),
        ("mark_paid", mark_paid, PAID_SCHEMA, optional),
        ("list_bills", list_bills, LIST_BILLS_SCHEMA, only),
        ("list_payments", list_payments, LIST_PAYMENTS_SCHEMA, only),
        ("send_reminders", send_reminders, vol.Schema({}), optional),
    ):
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=resp
        )


def async_unload_services(hass: HomeAssistant) -> None:
    for name in SERVICES:
        hass.services.async_remove(DOMAIN, name)