from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BillsCoordinator
from .entity import BillsEntity
from .summary import (format_money, summary_text, widget_html,
                      widget_lines, widget_text)


class NextDueSensor(BillsEntity, SensorEntity):
    _attr_name = "Next due"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_due")

    @property
    def native_value(self) -> date | None:
        nxt = self.coordinator.data["next"]
        return date.fromisoformat(nxt["due_date"]) if nxt else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        nxt = self.coordinator.data["next"]
        return {**nxt, "summary": summary_text(nxt)} if nxt else {}


class DueSoonSensor(BillsEntity, SensorEntity):
    _attr_name = "Due soon"
    _attr_icon = "mdi:calendar-alert"

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "due_soon")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data["due_soon"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"bills": self.coordinator.data["due_soon"]}


class OverdueSensor(BillsEntity, SensorEntity):
    _attr_name = "Overdue"
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "overdue")

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data["overdue"])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"bills": self.coordinator.data["overdue"]}


class DueThisMonthSensor(BillsEntity, SensorEntity):
    _attr_name = "Due this month"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "due_this_month")
        self._attr_native_unit_of_measurement = coordinator.hass.config.currency

    @property
    def native_value(self) -> float:
        return self.coordinator.data["due_this_month"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "bills_without_amount": self.coordinator.data["due_this_month_unpriced"]
        }


class SummarySensor(BillsEntity, SensorEntity):
    """A short readable line for phone widgets, e.g.
    "Phone due in 2 days · 2 more this week"."""

    _attr_name = "Summary"
    _attr_icon = "mdi:cash-clock"

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "summary")

    @property
    def native_value(self) -> str:
        return widget_text(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        nxt = data["next"]
        currency = self.coordinator.hass.config.currency
        return {
            "widget": widget_html(data, currency),
            "lines": widget_lines(data, currency),
            "this_week_count": len(data["this_week"]),
            "overdue_count": len(data["overdue"]),
            "next_bill_id": nxt["bill_id"] if nxt else None,
        }


def _day_name(iso: str, i: int) -> str:
    return ("Today", "Tomorrow")[i] if i < 2 else date.fromisoformat(iso).strftime("%a")


class BudgetTodaySensor(BillsEntity, SensorEntity):
    """Today's spending budget, with the next two days in attributes."""

    _attr_name = "Budget today"
    _attr_icon = "mdi:wallet"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "budget_today")
        self._attr_native_unit_of_measurement = coordinator.hass.config.currency

    @property
    def _budget(self) -> dict[str, Any]:
        return self.coordinator.data["budget"]

    @property
    def native_value(self) -> float | None:
        b = self._budget
        return b["today"] if b["configured"] else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        b = self._budget
        if not b["configured"]:
            return {"configured": False}
        cur = self.coordinator.hass.config.currency
        days = [{"label": _day_name(d["date"], i), **d} for i, d in enumerate(b["days"])]
        money = [format_money(d["amount"], cur) for d in days]
        summary = " · ".join(f"{d['label']} {m}" for d, m in zip(days, money))
        later = " · ".join(f"{d['label']} {m}" for d, m in zip(days[1:], money[1:]))
        return {
            "days": days,
            "tomorrow": days[1]["amount"],
            "day_after": days[2]["amount"],
            "daily_allowance": b["allowance"]["allowance"],
            "income_per_day": b["allowance"]["income"],
            "bills_per_day": b["allowance"]["bills"],
            "savings_per_day": b["allowance"]["savings"],
            "spent_today": b["spent_today"],
            "savings_total": b["savings"]["total"],
            "summary": summary,
            # Ready-made text for the Android template widget.
            "widget": f"<b>Today's budget {money[0]}</b><br>{later}",
        }


class SavingsTotalSensor(BillsEntity, SensorEntity):
    """All-time savings: plans so far, one-off moves and the starting amount."""

    _attr_name = "Savings total"
    _attr_icon = "mdi:piggy-bank"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "savings_total")
        self._attr_native_unit_of_measurement = coordinator.hass.config.currency

    @property
    def native_value(self) -> float | None:
        b = self.coordinator.data["budget"]
        return b["savings"]["total"] if b["configured"] else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        b = self.coordinator.data["budget"]
        return {"per_month": b["savings"]["per_month"]} if b["configured"] else {}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: BillsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            NextDueSensor(coordinator, entry),
            DueSoonSensor(coordinator, entry),
            OverdueSensor(coordinator, entry),
            DueThisMonthSensor(coordinator, entry),
            SummarySensor(coordinator, entry),
            BudgetTodaySensor(coordinator, entry),
            SavingsTotalSensor(coordinator, entry),
        ]
    )