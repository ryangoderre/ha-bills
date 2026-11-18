"""Service registration for the Bills integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .schedule import FREQUENCIES
from .store import BillStore

SERVICES = ("add_bill", "update_bill", "retire_bill", "mark_paid",
            "list_bills", "list_payments")

_NONNEG_INT = vol.All(vol.Coerce(int), vol.Range(min=0))

ADD_SCHEMA = vol.Schema({
    vol.Required("name"): cv.string,
    vol.Required("due_date"): cv.date,
    vol.Required("frequency"): vol.In(FREQUENCIES),
    vol.Optional("interval", default=1): vol.All(vol.Coerce(int), vol.Range(min=1)),
    vol.Optional("amount"): vol.Coerce(float),
    vol.Optional("end_date"): cv.date,
    vol.Optional("autopay", default=False): cv.boolean,
    vol.Optional("remind_days_before", default=3): _NONNEG_INT,
    vol.Optional("biller_url"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("tags", default=list): vol.All(cv.ensure_list, [cv.string]),
})

UPDATE_SCHEMA = vol.Schema({
    vol.Required("bill"): cv.string,
    vol.Optional("name"): cv.string,
    vol.Optional("amount"): vol.Coerce(float),
    vol.Optional("autopay"): cv.boolean,
    vol.Optional("remind_days_before"): _NONNEG_INT,
    vol.Optional("biller_url"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("tags"): vol.All(cv.ensure_list, [cv.string]),
})

BILL_SCHEMA = vol.Schema({vol.Required("bill"): cv.string})

PAID_SCHEMA = vol.Schema({
    vol.Required("bill"): cv.string,
    vol.Optional("amount"): vol.Coerce(float),
    vol.Optional("paid_date"): cv.date,
    vol.Optional("confirmation"): cv.string,
    vol.Optional("note"): cv.string,
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

    async def mark_paid(call: ServiceCall):
        d = call.data
        payment, bill = await store.async_mark_paid(
            d["bill"], d.get("amount"), d.get("paid_date"),
            d.get("confirmation"), d.get("note"),
        )
        return {"payment": payment, "next_due": bill["next_due"]}

    async def list_bills(call: ServiceCall):
        return {"bills": store.list_bills(call.data["include_retired"])}

    async def list_payments(call: ServiceCall):
        ref = call.data.get("bill")
        bill_id = store.find_bill(ref)["id"] if ref else None
        return {"payments": store.list_payments(bill_id)}

    optional = SupportsResponse.OPTIONAL
    only = SupportsResponse.ONLY
    for name, handler, schema, resp in (
        ("add_bill", add_bill, ADD_SCHEMA, optional),
        ("update_bill", update_bill, UPDATE_SCHEMA, optional),
        ("retire_bill", retire_bill, BILL_SCHEMA, optional),
        ("mark_paid", mark_paid, PAID_SCHEMA, optional),
        ("list_bills", list_bills, LIST_BILLS_SCHEMA, only),
        ("list_payments", list_payments, LIST_PAYMENTS_SCHEMA, only),
    ):
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=resp
        )


def async_unload_services(hass: HomeAssistant) -> None:
    for name in SERVICES:
        hass.services.async_remove(DOMAIN, name)