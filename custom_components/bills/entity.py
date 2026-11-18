from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BillsCoordinator


class BillsEntity(CoordinatorEntity[BillsCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: BillsCoordinator, entry: ConfigEntry, key: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)}, name="Bills"
        )