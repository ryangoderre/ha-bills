"""Fires bills_reminder events."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import EVENT_REMINDER
from .store import BillStore
from .summary import compute_reminders


def fire_reminders(hass: HomeAssistant, store: BillStore) -> list[dict[str, Any]]:
    reminders = compute_reminders(store.list_bills(), dt_util.now().date())
    for r in reminders:
        hass.bus.async_fire(EVENT_REMINDER, r)
    return reminders