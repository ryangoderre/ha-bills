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
from .summary import summary_text


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
        ]
    )