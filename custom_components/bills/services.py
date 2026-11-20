"""Service registration for the Bills integration."""
from __future__ import annotations

from datetime import timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .backup import stamped_name as backup_name
from .budget import STREAM_FREQUENCIES, STREAM_TYPES
from .const import DOMAIN, EVENT_PAID
from .schedule import FREQUENCIES, suggest_restore_due
from .summary import bill_history, cost_breakdown, history_years, year_breakdown
from .reminders import fire_reminders
from .store import BillStore

SERVICES = ("add_bill", "update_bill", "retire_bill", "restore_bill", "mark_paid",
            "list_bills", "list_payments", "send_reminders",
            "backup", "list_backups", "restore_backup",
            "add_category", "update_category", "delete_category",
            "list_categories", "cost_summary", "bill_history",
            "budget_setup", "add_expense", "add_income", "move_to_savings",
            "take_from_savings", "delete_transaction", "add_recurring",
            "update_recurring", "delete_recurring", "budget_summary",
            "list_transactions")

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
    vol.Optional("in_budget", default=True): cv.boolean,
    vol.Optional("remind_days_before", default=3): _NONNEG_INT,
    vol.Optional("biller_url"): cv.string,
    vol.Optional("notes"): cv.string,
    vol.Optional("tags", default=list): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("category"): cv.string,
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
    vol.Optional("in_budget"): cv.boolean,
    vol.Optional("remind_days_before"): _NONNEG_INT,
    vol.Optional("biller_url"): _clearable(cv.string),
    vol.Optional("notes"): _clearable(cv.string),
    vol.Optional("tags"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("category"): _clearable(cv.string),
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

RESTORE_BACKUP_SCHEMA = vol.Schema({vol.Required("file"): cv.string})

DEFAULT_CATEGORY_ICON = "mdi:tag"

ADD_CATEGORY_SCHEMA = vol.Schema({
    vol.Required("name"): _NAME,
    vol.Optional("icon", default=DEFAULT_CATEGORY_ICON): cv.icon,
})

UPDATE_CATEGORY_SCHEMA = vol.Schema({
    vol.Required("category"): cv.string,
    vol.Optional("name"): _NAME,
    vol.Optional("icon"): cv.icon,
})

CATEGORY_SCHEMA = vol.Schema({vol.Required("category"): cv.string})

_POSITIVE = vol.All(vol.Coerce(float), vol.Range(min=0.01))

BUDGET_SETUP_SCHEMA = vol.Schema({
    vol.Optional("start_date"): cv.date,
    vol.Optional("starting_amount", default=0.0): vol.Coerce(float),
    vol.Optional("starting_savings", default=0.0): _AMOUNT,
})

TRANSACTION_SCHEMA = vol.Schema({
    vol.Required("amount"): _POSITIVE,
    vol.Optional("category"): cv.string,
    vol.Optional("note"): cv.string,
    vol.Optional("date"): cv.date,
})

SAVINGS_MOVE_SCHEMA = vol.Schema({
    vol.Required("amount"): _POSITIVE,
    vol.Optional("note"): cv.string,
    vol.Optional("date"): cv.date,
})

DELETE_TRANSACTION_SCHEMA = vol.Schema({vol.Required("transaction"): cv.string})

LIST_TRANSACTIONS_SCHEMA = vol.Schema({vol.Required("date"): cv.date})

ADD_RECURRING_SCHEMA = vol.Schema({
    vol.Required("type"): vol.In(STREAM_TYPES),
    vol.Required("amount"): _POSITIVE,
    vol.Required("frequency"): vol.In(STREAM_FREQUENCIES),
    vol.Optional("interval", default=1): _INTERVAL,
    vol.Optional("name"): cv.string,
    vol.Optional("category"): cv.string,
    vol.Optional("start_date"): cv.date,
    vol.Optional("end_date"): cv.date,
})

UPDATE_RECURRING_SCHEMA = vol.Schema({
    vol.Required("recurring"): cv.string,
    vol.Optional("name"): _NAME,
    vol.Optional("amount"): _POSITIVE,
    vol.Optional("frequency"): vol.In(STREAM_FREQUENCIES),
    vol.Optional("interval"): _INTERVAL,
    vol.Optional("category"): _clearable(cv.string),
    vol.Optional("start_date"): cv.date,
    vol.Optional("end_date"): _clearable(cv.date),
})

RECURRING_SCHEMA = vol.Schema({vol.Required("recurring"): cv.string})


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

    async def backup_now(call: ServiceCall):
        name = backup_name(dt_util.now(), "manual")
        path = await store.async_write_backup(name)
        return {"file": name, "path": str(path)}

    async def list_backups(call: ServiceCall):
        return {"folder": str(store.backup_dir),
                "backups": await store.async_list_backups()}

    async def restore_backup(call: ServiceCall):
        return await store.async_restore_backup(call.data["file"])

    async def add_category(call: ServiceCall):
        cat = await store.async_add_category(call.data["name"], call.data["icon"])
        return {"category": cat}

    async def update_category(call: ServiceCall):
        changes = dict(call.data)
        cat = await store.async_update_category(changes.pop("category"), changes)
        return {"category": cat}

    async def delete_category(call: ServiceCall):
        cat, moved = await store.async_delete_category(call.data["category"])
        return {"deleted": cat["name"], "bills_uncategorized": moved}

    async def list_categories(call: ServiceCall):
        return {"categories": store.list_categories()}

    async def cost_summary(call: ServiceCall):
        """This month, this year (with its months) and previous years, by category."""
        today = dt_util.now().date()
        month_start = today.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        bills = store.list_bills(include_retired=True)
        args = (bills, store.payments, store.categories)
        return {
            "today": today.isoformat(),
            "month": cost_breakdown(*args, month_start, next_month - timedelta(days=1)),
            "year": year_breakdown(*args, today.year),
            "previous_years": [
                year_breakdown(*args, y)
                for y in history_years(bills, store.payments, today)
            ],
        }

    async def bill_history_(call: ServiceCall):
        bill = store.find_bill(call.data["bill"])
        payments = store.list_payments(bill["id"])
        payments.sort(key=lambda p: (p["due_date"], p["paid_date"]), reverse=True)
        return {"bill": bill, "payments": payments,
                "stats": bill_history(payments, dt_util.now().date())}

    async def budget_setup(call: ServiceCall):
        d = call.data
        b = await store.async_budget_setup(
            d.get("start_date"), d["starting_amount"], d["starting_savings"])
        return {"start_date": b["start_date"]}

    def _tx(kind: str):
        async def handler(call: ServiceCall):
            d = call.data
            tx = await store.async_add_transaction(
                kind, d["amount"], d.get("category"), d.get("note"), d.get("date"))
            return {"transaction": tx, "today": store.budget_summary()["today"]}
        return handler

    async def delete_transaction(call: ServiceCall):
        return {"deleted": await store.async_delete_transaction(call.data["transaction"])}

    async def add_recurring(call: ServiceCall):
        return {"recurring": await store.async_add_stream(dict(call.data))}

    async def update_recurring(call: ServiceCall):
        changes = dict(call.data)
        return {"recurring": await store.async_update_stream(changes.pop("recurring"), changes)}

    async def delete_recurring(call: ServiceCall):
        return {"deleted": await store.async_delete_stream(call.data["recurring"])}

    async def budget_summary(call: ServiceCall):
        return store.budget_summary()

    async def list_transactions(call: ServiceCall):
        return store.transactions_on(call.data["date"].isoformat())

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
        ("backup", backup_now, vol.Schema({}), optional),
        ("list_backups", list_backups, vol.Schema({}), only),
        ("restore_backup", restore_backup, RESTORE_BACKUP_SCHEMA, optional),
        ("add_category", add_category, ADD_CATEGORY_SCHEMA, optional),
        ("update_category", update_category, UPDATE_CATEGORY_SCHEMA, optional),
        ("delete_category", delete_category, CATEGORY_SCHEMA, optional),
        ("list_categories", list_categories, vol.Schema({}), only),
        ("cost_summary", cost_summary, vol.Schema({}), only),
        ("bill_history", bill_history_, BILL_SCHEMA, only),
        ("budget_setup", budget_setup, BUDGET_SETUP_SCHEMA, optional),
        ("add_expense", _tx("expense"), TRANSACTION_SCHEMA, optional),
        ("add_income", _tx("income"), TRANSACTION_SCHEMA, optional),
        ("move_to_savings", _tx("to_savings"), SAVINGS_MOVE_SCHEMA, optional),
        ("take_from_savings", _tx("from_savings"), SAVINGS_MOVE_SCHEMA, optional),
        ("delete_transaction", delete_transaction, DELETE_TRANSACTION_SCHEMA, optional),
        ("add_recurring", add_recurring, ADD_RECURRING_SCHEMA, optional),
        ("update_recurring", update_recurring, UPDATE_RECURRING_SCHEMA, optional),
        ("delete_recurring", delete_recurring, RECURRING_SCHEMA, optional),
        ("budget_summary", budget_summary, vol.Schema({}), only),
        ("list_transactions", list_transactions, LIST_TRANSACTIONS_SCHEMA, only),
    ):
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=resp
        )


def async_unload_services(hass: HomeAssistant) -> None:
    for name in SERVICES:
        hass.services.async_remove(DOMAIN, name)