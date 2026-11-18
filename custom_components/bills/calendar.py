from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import schedule
from .const import DOMAIN
from .coordinator import BillsCoordinator
from .entity import BillsEntity


def _event(bill: dict[str, Any], d: date) -> CalendarEvent:
    parts = []
    if bill["amount"] is not None:
        parts.append(f"Amount: {bill['amount']}")
    if bill["autopay"]:
        parts.append("Autopay")
    if bill["notes"]:
        parts.append(bill["notes"])
    return CalendarEvent(
        start=d,
        end=d + timedelta(days=1),  # all-day events end the next day
        summary=bill["name"],
        description="\n".join(parts) or None,
    )


class BillsCalendar(BillsEntity, CalendarEntity):
    _attr_name = None  # entity id becomes calendar.bills

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "calendar")

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        for b in self.coordinator.store.list_bills():
            due = date.fromisoformat(b["next_due"])
            if due >= today:
                return _event(b, due)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        start = dt_util.as_local(start_date).date()
        # The end of the range is exclusive.
        last = (dt_util.as_local(end_date) - timedelta(microseconds=1)).date()
        events: list[CalendarEvent] = []
        for b in self.coordinator.store.list_bills():
            retire_on = date.fromisoformat(b["end_date"]) if b["end_date"] else None
            first = max(start, date.fromisoformat(b["next_due"]))
            for d in schedule.occurrences_between(
                date.fromisoformat(b["anchor_date"]),
                b["frequency"], b["interval"], first, last, retire_on,
            ):
                events.append(_event(b, d))
        events.sort(key=lambda e: e.start)
        return events


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: BillsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BillsCalendar(coordinator, entry)])